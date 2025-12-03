import os
import re
import time
import requests
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, NavigableString, Tag, Comment

from .models import ArticleContent
from .config import (
    MAX_FOOTNOTE_LENGTH,
    MIN_FOOTNOTE_TEXT_LENGTH,
    PART_HEADING_RE,
)
from .utils import (
    ensure_dir,
    safe_filename,
    escape_latex,
    clean_text_fragments,
    clean_text_node,
    normalize_href,
    canonical_url,
)
from .latex import clean_latex_spacing, break_long_lines

DEFAULT_REQUEST_DELAY = 0.35  # seconds between requests to be polite to marxists.org

class MarxistsScraper:
    def __init__(
        self,
        log_fn: Callable[[str], None],
        progress_fn: Callable[[float, str], None],
        session: Optional[requests.Session] = None,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        allow_guessing: bool = False,
    ):
        self.log_fn = log_fn
        self.progress_fn = progress_fn
        self.session = session or self._build_session()
        self.request_delay = max(0.0, request_delay)
        self.allow_guessing = allow_guessing
        self._last_footnote_stats: Dict[str, int] = {}

    def _build_session(self) -> requests.Session:
        """Create a requests session with retry/backoff and a polite User-Agent."""
        sess = requests.Session()
        retry = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET", "HEAD"},
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        sess.headers.update(
            {
                "User-Agent": "MarxistsConverter/1.0 (+https://www.marxists.org/)",
            }
        )
        return sess

    # ---- network helpers ----
    def fetch(self, url: str) -> Tuple[str, str]:
        self.log_fn(f"Requesting {url}")
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            # Ensure proper UTF-8 encoding handling
            # Try to decode as UTF-8 first, with fallback to detected encoding
            try:
                html_content = resp.content.decode('utf-8', errors='replace')
            except (UnicodeDecodeError, AttributeError):
                # Fallback: use requests' automatic encoding detection
                resp.encoding = resp.apparent_encoding or 'utf-8'
                html_content = resp.text
            if self.request_delay:
                time.sleep(self.request_delay)
            return html_content, content_type
        except requests.RequestException as exc:
            self.log_fn(f"Request failed for {url}: {exc}")
            raise

    # ---- analysis ----
    def analyze_url(self, url: str) -> str:
        parsed = urlparse(url)
        if not parsed.scheme.startswith("http"):
            raise ValueError("URL must start with http or https")
        if parsed.path.lower().endswith(("index.htm", "index.html")):
            return "book"
        # heuristic: many links in content section
        html, _ = self.fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        base_dir = "/".join(url.split("/")[:-1]) + "/"
        chapterish_links = []
        for a in soup.find_all("a", href=True):
            full = normalize_href(a["href"], url)
            if not full:
                continue
            if not full.startswith(base_dir):
                continue
            if self._is_chapter_link(full):
                chapterish_links.append(full)
        return "book" if len(chapterish_links) >= 4 else "article"

    # ---- scraping ----
    def scrape_article(
        self, url: str, images_dir: str, book_title: Optional[str] = None, book_author: Optional[str] = None
    ) -> ArticleContent:
        html, _ = self.fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        self._strip_unwanted(soup)
        footnotes = self._extract_footnotes(soup)
        self._inline_footnote_refs(soup, footnotes)
        self._inline_manual_footnote_refs(soup, footnotes)  # Handle manual [1], [2] references
        self._remove_artifact_nodes(soup)
        content_node = self._select_content_node(soup)
        meta_title, meta_date, author, meta_entries = self._extract_metadata(soup, content_node, url)
        self._handle_images(soup, content_node, url, images_dir)
        
        # If this is a chapter of a book, strip repeated book/author headers
        # and extract the real chapter title from the first remaining heading
        chapter_title = meta_title
        if book_title or book_author:
            chapter_title = self._strip_book_headers_and_get_chapter_title(
                content_node, book_title, book_author, meta_title
            )
        
        latex_body = self._html_to_latex(content_node, base_url=url)
        # Remove any endnote commands that contain navigation breadcrumbs (shouldn't have been created)
        latex_body = re.sub(r"\\endnote\{[^}]*MIA[^}]*Archive[^}]*\}", "", latex_body, flags=re.I)
        # Break very long lines to avoid xelatex buffer overflow
        latex_body = clean_latex_spacing(latex_body)
        latex_body = break_long_lines(latex_body)
        if self._last_footnote_stats:
            extracted = self._last_footnote_stats.get("extracted", 0)
            inlined = self._last_footnote_stats.get("inlined", 0)
            unmatched = self._last_footnote_stats.get("unmatched_refs", 0)
            self.log_fn(f"Footnotes: extracted {extracted}, inlined {inlined}, unmatched refs {unmatched}.")
        return ArticleContent(
            title=chapter_title,
            date=meta_date,
            author=author,
            meta_entries=meta_entries,
            latex_body=latex_body,
            url=url,
        )

    def scrape_book(self, index_url: str, work_dir: str) -> Tuple[str, Optional[str], Optional[str], List[Tuple[str, str]], List[ArticleContent], List[Tuple[str, str]]]:
        html, _ = self.fetch(index_url)
        soup = BeautifulSoup(html, "html.parser")
        self._strip_unwanted(soup)
        content_node = self._select_content_node(soup)
        title, date, author, meta_entries = self._extract_metadata(soup, content_node, index_url)
        # Collect TOC links (including external ones like "Marx to Bracke")
        toc_entries = self._collect_toc_links(soup, index_url)
        chapter_links = self._collect_chapter_links(soup, index_url)
        toc_urls = [url for _, url in toc_entries if self._is_chapter_link(url)]
        if not chapter_links and toc_urls:
            # Use TOC URLs directly when no inline chapter links exist (e.g., external letters)
            chapter_links = toc_urls
        # Try to detect higher-level "Part ..." groupings on the index page
        part_map = self._detect_parts_for_index(content_node, index_url, chapter_links)
        if len(chapter_links) < 3 and not toc_urls:
            if self.allow_guessing:
                guessed = self._guess_chapter_sequence(index_url, limit=40)
                self.log_fn(f"No or few chapters found; using guessed sequence ({len(guessed)} links).")
                if guessed:
                    self.log_fn("Chapters guessed: " + ", ".join(guessed[:6]) + (" ..." if len(guessed) > 6 else ""))
                chapter_links = guessed
            else:
                self.log_fn("No or few chapters found; chapter guessing disabled.")
        if not chapter_links:
            raise RuntimeError("No chapter links detected or guessed.")
        
        # Collect external TOC items that aren't in chapter_links
        external_toc_items: List[Tuple[str, str]] = []
        for toc_text, toc_url in toc_entries:
            # Normalize URLs for comparison
            toc_url_normalized = toc_url.rstrip("/").lower()
            is_in_chapters = any(
                link.rstrip("/").lower() == toc_url_normalized 
                for link in chapter_links
            )
            if not is_in_chapters and self._is_chapter_link(toc_url):
                external_toc_items.append((toc_text, toc_url))
        
        # Build ordered list following TOC order
        # Create a mapping from URL to chapter link for quick lookup
        url_to_chapter_link: Dict[str, str] = {}
        for link in chapter_links:
            url_to_chapter_link[canonical_url(link)] = link
        
        # Build ordered list following TOC entries order
        all_links: List[Tuple[str, str, bool]] = []  # (url, title, is_external)
        seen_urls: set[str] = set()
        
        # First, add items in TOC order
        for toc_text, toc_url in toc_entries:
            toc_url_canon = canonical_url(toc_url)
            if toc_url_canon in seen_urls:
                continue

            # Check if it's a regular chapter
            if toc_url_canon in url_to_chapter_link:
                all_links.append((url_to_chapter_link[toc_url_canon], toc_text, False))
                seen_urls.add(toc_url_canon)
            # Check if it's an external TOC item
            elif self._is_chapter_link(toc_url):
                all_links.append((toc_url, toc_text, True))
                seen_urls.add(toc_url_canon)
        
        # Add any remaining chapter_links that weren't in TOC (fallback)
        for link in chapter_links:
            link_canon = canonical_url(link)
            if link_canon not in seen_urls:
                all_links.append((link, "", False))
                seen_urls.add(link_canon)
        
        chapters: List[ArticleContent] = []
        total = len(all_links)
        images_dir = os.path.join(work_dir, "images")
        failed_chapters = 0
        for idx, (link, toc_title, is_external) in enumerate(all_links, start=1):
            label_hint = toc_title or os.path.basename(urlparse(link).path) or f"Chapter {idx}"
            self.progress_fn(idx / total, f"Scraping {idx}/{total}: {label_hint[:60]}")
            try:
                # Pass book title/author so chapter can strip repeated headers
                chapter = self.scrape_article(link, images_dir, book_title=title, book_author=author)
            except Exception as exc:  # noqa: BLE001
                self.log_fn(f"Failed chapter {link}: {exc}")
                failed_chapters += 1
                continue
            if not chapter.title:
                chapter.title = f"Chapter {idx}"
            # Always store TOC title if available (for TOC display)
            if toc_title:
                # Prefer TOC title for external items
                if is_external:
                    chapter.title = toc_title
                # Always store TOC title even if it matches chapter title
                # (needed for proper TOC display when multiple chapters have same title)
                chapter.toc_title = toc_title
            # Attach part title if this link was associated with a "Part ..." heading
            chapter.part_title = part_map.get(canonical_url(link))
            chapters.append(chapter)

        # Validate that we have at least one chapter
        if not chapters:
            raise RuntimeError("No chapters were successfully scraped. All chapters failed or were empty.")
        if failed_chapters:
            self.log_fn(f"Warning: {failed_chapters} of {total} chapters failed to scrape.")
        else:
            self.log_fn(f"Chapters scraped successfully: {len(chapters)}/{total}.")

        return title or "Collected Works", date, author, meta_entries, chapters, toc_entries

    # ---- internal helpers ----
    def _strip_unwanted(self, soup: BeautifulSoup) -> None:
        for tag in soup(["script", "style", "header", "footer", "nav", "form"]):
            tag.decompose()
        for a in soup.find_all("a"):
            text = (a.get_text() or "").lower()
            if "back to" in text or "return to" in text:
                parent = a.parent
                if parent:
                    parent.decompose()

    def _remove_artifact_nodes(self, soup: BeautifulSoup) -> None:
        class_pattern = re.compile(r"(t2h-|footnote|endnote)", re.I)
        for tag in list(soup.find_all(True, class_=class_pattern)):
            tag.decompose()
        for tag in list(soup.find_all(True, id=class_pattern)):
            tag.decompose()
        for span in list(soup.find_all("span", string=re.compile(r"t2h-", re.I))):
            span.decompose()
        # Remove common marxists.org navigation/footer classes
        for tag in soup.find_all(class_=re.compile(r"(footer|terms|nav|header|crumbs)", re.I)):
            tag.decompose()
        
        # Remove navigation breadcrumbs
        for elem in soup.find_all(["p", "div", "span"]):
            text = elem.get_text(strip=True)
            if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", text, re.I):
                if ">" in text and ("Archive" in text or "MIA" in text):
                    elem.decompose()
                    continue

    def _strip_book_headers_and_get_chapter_title(
        self, content_node: Tag, book_title: Optional[str], book_author: Optional[str], fallback_title: str
    ) -> str:
        if not content_node:
            return fallback_title
        
        def normalize(s: str) -> str:
            if not s:
                return ""
            return re.sub(r"\s+", " ", s.lower().strip())
        
        book_title_norm = normalize(book_title) if book_title else ""
        book_author_norm = normalize(book_author) if book_author else ""
        
        subtitle_patterns = [
            r"a brief biographical sketch",
            r"with an exposition of marxism",
        ]
        
        chapter_title = None
        preferred_chapter_title = None
        
        for heading in list(content_node.find_all(["h1", "h2", "h3", "h4"], limit=15)):
            heading_text = heading.get_text(strip=True)
            heading_text_norm = normalize(heading_text)
            
            if not heading_text_norm:
                heading.decompose()
                continue
            
            should_remove = False
            if book_title_norm and heading_text_norm == book_title_norm:
                should_remove = True
            elif book_author_norm and heading_text_norm == book_author_norm:
                should_remove = True
            elif any(pat in heading_text_norm for pat in subtitle_patterns):
                should_remove = True
            
            is_chapter_heading = (
                heading_text_norm.startswith("chapter") or
                re.match(r"^[ivx]+\.", heading_text_norm) or
                re.match(r"^part\s+[ivx]+", heading_text_norm, re.I) or
                re.match(r"^[ivx]+\.\s+[a-z]", heading_text_norm)
            )
            
            is_preface_heading = (
                "preface" in heading_text_norm or
                "foreword" in heading_text_norm or
                "introduction" in heading_text_norm
            )
            
            if should_remove:
                heading.decompose()
            elif is_chapter_heading:
                if preferred_chapter_title is None:
                    preferred_chapter_title = heading_text
                    heading.decompose()
            elif is_preface_heading and chapter_title is None:
                chapter_title = heading_text
                heading.decompose()
            elif chapter_title is None:
                chapter_title = heading_text
                heading.decompose()
        
        return preferred_chapter_title or chapter_title or fallback_title

    def _author_from_url(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if "archive" in parts:
            idx = parts.index("archive")
            if idx + 1 < len(parts):
                candidate = parts[idx + 1]
                candidate = candidate.replace("-", " ").replace("_", " ")
                if candidate:
                    return candidate.title()
        return None

    def _collect_toc_links(self, soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str]]:
        toc_entries: List[Tuple[str, str]] = []
        seen: set[str] = set()

        toc_heading = soup.find(string=re.compile(r"(Table of Contents|Contents)\b", re.I))
        toc_container: Optional[Tag] = None
        if toc_heading:
            toc_container = toc_heading.find_parent(["p", "div", "section", "h2", "h3", "h4"])

        def add_links_from(container: Tag) -> None:
            for link in container.find_all("a", href=True):
                link_text = link.get_text(" ", strip=True)
                if not link_text:
                    continue
                href = link.get("href")
                if not href:
                    continue
                full_url = normalize_href(href, base_url)
                canon = canonical_url(full_url) if full_url else ""
                if full_url and canon and canon not in seen and self._is_chapter_link(full_url):
                    seen.add(canon)
                    toc_entries.append((link_text, full_url))

        if toc_container:
            add_links_from(toc_container)
            for sib in toc_container.find_all_next(["p", "ul", "ol"], limit=6):
                add_links_from(sib)
                if len(toc_entries) >= 6:
                    break

        if not toc_entries:
            for lst in soup.find_all(["ul", "ol"]):
                candidate_links = []
                for link in lst.find_all("a", href=True):
                    full_url = normalize_href(link.get("href", ""), base_url)
                    canon = canonical_url(full_url) if full_url else ""
                    if full_url and canon and self._is_chapter_link(full_url):
                        text = link.get_text(" ", strip=True)
                        if text:
                            candidate_links.append((text, full_url, canon))
                if len(candidate_links) >= 3:
                    for text, url, canon in candidate_links:
                        if canon not in seen:
                            seen.add(canon)
                            toc_entries.append((text, url))
                    break

        return toc_entries

    def _collect_chapter_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        links: List[str] = []
        seen: set[str] = set()
        base_dir = "/".join(base_url.split("/")[:-1]) + "/"
        for a in soup.find_all("a", href=True):
            full = normalize_href(a["href"], base_url)
            if not full or not self._is_chapter_link(full):
                continue
            if not full.startswith(base_dir):
                continue
            canon = canonical_url(full)
            if canon in seen:
                continue
            seen.add(canon)
            links.append(full)
        return links

    def _detect_parts_for_index(
        self,
        content_node: Tag,
        base_url: str,
        chapter_links: List[str],
    ) -> Dict[str, str]:
        if not content_node or not chapter_links:
            return {}

        chapter_set = {canonical_url(link) for link in chapter_links}
        part_map: Dict[str, str] = {}
        current_part: Optional[str] = None

        for element in content_node.descendants:
            if isinstance(element, Tag):
                text = element.get_text(" ", strip=True)
                if text:
                    m = PART_HEADING_RE.match(text)
                    if m:
                        current_part = text.strip()
                        continue

                if current_part:
                    if element.name == "a" and element.has_attr("href"):
                        full = normalize_href(element["href"], base_url)
                        canon = canonical_url(full) if full else ""
                        if canon in chapter_set and canon not in part_map:
                            part_map[canon] = current_part

        return part_map

    def _is_chapter_link(self, href: str) -> bool:
        href_lower = href.lower()
        if href_lower.startswith("#"):
            return False
        if "index.htm" in href_lower:
            return False
        return href_lower.endswith((".htm", ".html"))

    def _guess_chapter_sequence(self, index_url: str, limit: int = 80) -> List[str]:
        base = urljoin(index_url, "./")
        patterns = [
            "ch{num:02d}.htm",
            "ch{num}.htm",
            "ch{num:02d}.html",
            "ch{num}.html",
        ]
        results: List[str] = []
        consecutive_misses = 0
        hits_found = False
        for num in range(0, limit):
            hit_any = False
            for pat in patterns:
                candidate = urljoin(base, pat.format(num=num))
                try:
                    resp = self.session.get(candidate, timeout=10)
                    if resp.status_code == 200 and len(resp.text) > 200:
                        results.append(candidate)
                        hit_any = True
                        hits_found = True
                        break
                except Exception:  # noqa: BLE001
                    continue
            if not hit_any:
                consecutive_misses += 1
            else:
                consecutive_misses = 0
            if hits_found and consecutive_misses >= 10:
                break
        return results

    def _select_content_node(self, soup: BeautifulSoup) -> Tag:
        candidates = soup.find_all(
            ["div", "article", "section", "main"],
            id=re.compile("(content|main|text)", re.I),
        )
        if not candidates:
            candidates = soup.find_all(
                ["div", "article", "section", "main", "table"],
                class_=re.compile("(content|main|text|body)", re.I),
            )
        if candidates:
            return max(candidates, key=lambda c: len(c.get_text()))
        return soup.body or soup

    def _extract_metadata(
        self, soup: BeautifulSoup, content_node: Tag, url: str
    ) -> Tuple[str, Optional[str], Optional[str], List[Tuple[str, str]]]:
        title = ""
        date = None
        author = None
        author_source = None
        meta_entries: List[Tuple[str, str]] = []

        if content_node:
            title_tag = content_node.find("h3", class_="title")
            if title_tag:
                title = title_tag.get_text(strip=True)
            
            h2_tag = content_node.find("h2")
            if h2_tag:
                candidate = h2_tag.get_text(" ", strip=True)
                if candidate and len(candidate.split()) <= 5:
                    author = candidate
                    author_source = "heading"
            if not author:
                non_author_keywords = ["background", "table of contents", "contents", "foreword", "preface", "introduction"]
                for h4_tag in content_node.find_all("h4"):
                    h4_text = h4_tag.get_text(" ", strip=True)
                    if h4_text.lower() in non_author_keywords:
                        continue
                    author_match = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(?:\s+\d{4})?$", h4_text)
                    if author_match:
                        author = author_match.group(1)
                        author_source = "subheading"
                        break

        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        if not author:
            author = self._author_from_url(url)
            if author:
                author_source = "url"

        meta_keys = [
            "Written", "Published", "First Published", "Source", "Publisher", 
            "Translated", "Transcription", "Transcribed", "Markup", "HTML Markup",
            "Online Version", "Public Domain"
        ]
    
        info_para = soup.find("p", class_="information")
        if info_para:
            for span in info_para.find_all("span", class_="info"):
                label_text = span.get_text(strip=True)
                label = label_text.rstrip(":–-").strip().title()
                
                if label in [k.title() for k in meta_keys]:
                    content_parts = []
                    current = span.next_sibling
                    
                    while current:
                        if isinstance(current, Tag):
                            if current.name == "span" and "info" in current.get("class", []):
                                break
                            elif current.name == "br":
                                break
                            elif current.name == "a":
                                href = current.get("href", "")
                                link_text = current.get_text(strip=True)
                                if href.startswith("http"):
                                    content_parts.append(f"\\href{{{escape_latex(href)}}}{{{escape_latex(link_text)}}}")
                                else:
                                    content_parts.append(escape_latex(link_text))
                            else:
                                content_parts.append(escape_latex(current.get_text(strip=True)))
                            current = current.next_sibling
                        elif isinstance(current, NavigableString):
                            text = str(current).strip()
                            if text:
                                content_parts.append(escape_latex(text))
                            current = current.next_sibling
                        else:
                            break
                    
                    if content_parts:
                        value_latex = " ".join(content_parts)
                        meta_entries.append((label, value_latex))
            
            info_para.decompose()
        else:
            for para in soup.find_all("p"):
                para_text = para.get_text(" ", strip=True)
                for key in meta_keys:
                    pattern = rf"^{re.escape(key)}\s*[:–-]\s*(.+?)(?:\s*;\s*|$)"
                    match = re.match(pattern, para_text, re.I)
                    if match:
                        value = match.group(1).strip().rstrip(";")
                        if not any(k.lower() == key.lower() for k, _ in meta_entries):
                            value_parts = []
                            for part in para.children:
                                if isinstance(part, Tag) and part.name == "a":
                                    href = part.get("href", "")
                                    link_text = part.get_text(strip=True)
                                    if href.startswith("http"):
                                        value_parts.append(f"\\href{{{escape_latex(href)}}}{{{escape_latex(link_text)}}}")
                                    else:
                                        value_parts.append(escape_latex(link_text))
                                elif isinstance(part, NavigableString):
                                    text = str(part).strip()
                                    if text:
                                        value_parts.append(escape_latex(text))
                            if value_parts:
                                value_latex = " ".join(value_parts)
                            else:
                                value_latex = escape_latex(value)
                            meta_entries.append((key, value_latex))
                        break
        
        date_candidate = soup.find(
            string=re.compile(
                r"\b(\d{4}|January|February|March|April|May|June|July|August|September|October|November|December)",
                re.I,
            )
        )
        if date_candidate:
            date = date_candidate.strip()
        if author_source:
            self.log_fn(f"Author detected from {author_source}: {author}")
        elif not author:
            self.log_fn("Author not detected; leaving as Unknown.")

        return title or "Untitled", date, author or "Unknown", meta_entries

    def _extract_footnotes(self, soup: BeautifulSoup) -> Dict[str, str]:
        footnotes: Dict[str, str] = {}

        footnotes_heading = soup.find(string=re.compile(r"^(Footnotes?|Notes?)$", re.I))
        if footnotes_heading:
            heading_elem = footnotes_heading.find_parent()
            if heading_elem:
                for elem in heading_elem.find_all_next(["p", "li"]):
                    parent_heading = elem.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                    if parent_heading and parent_heading is not heading_elem:
                        heading_text = parent_heading.get_text(strip=True).lower()
                        if heading_text and "footnote" not in heading_text and "note" not in heading_text:
                            break

                    text = elem.get_text(strip=True)
                    if not text or len(text) < MIN_FOOTNOTE_TEXT_LENGTH:
                        continue
                    
                    if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", text, re.I):
                        continue

                    # Try pattern like "1. text", "[1] text", or just "[1] text"
                    footnote_match = re.match(r"^(\*+)?\s*\[?(\d+)\]?\.?\s*(.+)$", text, re.S)
                    if not footnote_match:
                        # Also try pattern starting with just "[1]" followed by text
                        footnote_match = re.match(r"^\[(\d+)\]\s*(.+)$", text, re.S)
                    
                    if footnote_match:
                        footnote_num = footnote_match.group(2)
                        footnote_text = footnote_match.group(3)

                        footnote_text = re.sub(r"^\*+\s*", "", footnote_text)
                        footnote_text = clean_text_fragments(footnote_text)

                        if footnote_text and len(footnote_text) < MAX_FOOTNOTE_LENGTH:
                            anchors = elem.find_all("a", attrs={"name": True}) + elem.find_all("a", attrs={"id": True})

                            effective_anchor_count = 0
                            temp_contents = list(elem.children)
                            temp_contents_set = set(temp_contents)
                            for a in anchors:
                                if a in temp_contents_set:
                                    effective_anchor_count += 1

                            if effective_anchor_count <= 1:
                                raw = elem.get_text("\n", strip=True)
                                parts = list(re.finditer(r"(?m)^(\d+)\.\s*", raw))
                                if len(parts) > 1:
                                    for idx, match in enumerate(parts):
                                        num_val = match.group(1)
                                        start = match.end()
                                        end = parts[idx + 1].start() if idx + 1 < len(parts) else len(raw)
                                        segment = raw[start:end].strip()
                                        segment = clean_text_fragments(segment)
                                        if segment:
                                            num_key = f"n{num_val}".lower()
                                            direct_key = num_val
                                            if num_key not in footnotes:
                                                footnotes[num_key] = segment
                                            if direct_key not in footnotes:
                                                footnotes[direct_key] = segment
                                    elem.decompose()
                                    continue

                            anchor_specific_text: Dict[str, str] = {}
                            if effective_anchor_count > 1:
                                contents = list(elem.children)
                                anchor_positions: List[int] = []
                                anchors_in_contents: List[Tag] = []
                                for anchor in anchors:
                                    try:
                                        idx = contents.index(anchor)
                                    except ValueError:
                                        continue
                                    anchor_positions.append(idx)
                                    anchors_in_contents.append(anchor)

                                for i, anchor in enumerate(anchors_in_contents):
                                    start = anchor_positions[i]
                                    end = anchor_positions[i + 1] if i + 1 < len(anchor_positions) else len(contents)
                                    if start >= len(contents) or end > len(contents) or start >= end:
                                        continue
                                    segment_parts: List[str] = []
                                    for part in contents[start + 1 : end]:
                                        if isinstance(part, Tag):
                                            if part.name == "br":
                                                segment_parts.append("\n")
                                                continue
                                            segment_parts.append(part.get_text(" ", strip=True))
                                        elif isinstance(part, NavigableString):
                                            segment_parts.append(str(part))
                                    segment_text = clean_text_fragments(" ".join(segment_parts))
                                    segment_text = re.sub(r"^\[?\d+\]?\.?\s*", "", segment_text).strip()
                                    if segment_text and len(segment_text) < MAX_FOOTNOTE_LENGTH:
                                        anchor_specific_text[id(anchor)] = segment_text

                            for anchor in anchors:
                                anchor_id = anchor.get("name") or anchor.get("id")
                                if not anchor_id:
                                    continue
                                anchor_key = anchor_id.lower()

                                specific = anchor_specific_text.get(id(anchor), footnote_text)
                                if specific:
                                    footnotes[anchor_key] = specific

                                    anchor_num = re.search(r"(\d+)", anchor_key)
                                    num_val = anchor_num.group(1) if anchor_num else footnote_num
                                    if num_val:
                                        num_key = f"n{num_val}".lower()
                                        direct_key = num_val
                                        if num_key not in footnotes:
                                            footnotes[num_key] = specific
                                        if direct_key not in footnotes:
                                            footnotes[direct_key] = specific

                            elem.decompose()
        
        for node in soup.find_all(["p", "div"], class_=re.compile(r"(endnote|footnote)", re.I)):
            anchor = node.find("a", attrs={"name": True}) or node.find("a", attrs={"id": True})
            if not anchor:
                continue
            
            text_content = node.get_text(strip=True)
            if re.match(r"^\[?\d+\]?$", text_content):
                continue
            
            anchor_text = anchor.get_text(strip=True)
            if re.match(r"^\[?\d+\]?$", anchor_text):
                 if len(text_content) < 50:
                     continue

            anchor_id = anchor.get("name") or anchor.get("id")
            if anchor_id:
                key = anchor_id.lower()
                if key in footnotes:
                    node.decompose()
                    continue
                
                if not anchor.get_text(strip=True):
                    anchor.decompose()
                
                content = clean_text_fragments(node.get_text(" ", strip=True))
                content = re.sub(r"^\[?\d+\]?\s*", "", content)
                
                if content and len(content) < 50000:
                    footnotes[key] = content
                    node.decompose()

        seen = set()
        anchors = []
        for a in soup.find_all("a", attrs={"name": True}) + soup.find_all("a", attrs={"id": True}):
            if a not in seen:
                seen.add(a)
                anchors.append(a)

        for anchor in anchors:
            if not anchor or not hasattr(anchor, "get"):
                continue
            if getattr(anchor, "attrs", None) is None:
                continue

            anchor_id = anchor.get("name") or anchor.get("id")
            if not anchor_id:
                continue
            
            if anchor_id.lower() in footnotes:
                continue

            key = anchor_id.lower()
            
            parent = anchor.find_parent(["p", "li", "div"])
            target = parent if parent else anchor
            
            if parent:
                parent_text = parent.get_text(strip=True)
            else:
                parent_text = anchor.get_text(strip=True)
            
            anchor_text = anchor.get_text(strip=True)
            
            if not anchor_text:
                continue
            
            if not parent_text.startswith(anchor_text):
                if not parent_text.startswith("[" + anchor_text) and not parent_text.startswith(anchor_text.replace("[", "").replace("]", "")):
                     continue

            if re.match(r"^\[?\d+\]?$", parent_text):
                continue
                
            clean_text = clean_text_fragments(target.get_text(" ", strip=True))
            clean_text = re.sub(r"^\s*\[?\d+\]?[\.\)]?\s*", "", clean_text)
            
            if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", clean_text, re.I):
                continue
            
            if clean_text and len(clean_text) > 5 and len(clean_text) < MAX_FOOTNOTE_LENGTH:
                footnotes[key] = clean_text
                target.decompose()
                
        # Add fallback: extract footnotes from paragraphs that start with [1], [2], etc.
        footnotes_heading = soup.find(string=re.compile(r"^(Footnotes?|Notes?)$", re.I))
        if footnotes_heading:
            heading_elem = footnotes_heading.find_parent()
            if heading_elem:
                # Look for paragraphs starting with [1], [2], etc. that we might have missed
                for elem in heading_elem.find_all_next(["p", "li"], limit=50):
                    parent_heading = elem.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                    if parent_heading and parent_heading is not heading_elem:
                        heading_text = parent_heading.get_text(strip=True).lower()
                        if heading_text and "footnote" not in heading_text and "note" not in heading_text:
                            break
                    
                    text = elem.get_text(strip=True)
                    if not text or len(text) < MIN_FOOTNOTE_TEXT_LENGTH:
                        continue
                    
                    # Try to match "[1] text" pattern
                    bracket_match = re.match(r"^\[(\d+)\]\s*(.+)$", text, re.S)
                    if bracket_match:
                        num = bracket_match.group(1)
                        content = clean_text_fragments(bracket_match.group(2))
                        if content and len(content) < MAX_FOOTNOTE_LENGTH:
                            # Store with multiple key variations
                            for key_variant in [num, f"n{num}", f"note{num}", f"footnote{num}"]:
                                if key_variant.lower() not in footnotes:
                                    footnotes[key_variant.lower()] = content
        
        # Extract footnotes from table structures (common in Marxists.org)
        # Look for tables after footnote heading with anchors in first cell and content in second
        if footnotes_heading:
            heading_elem = footnotes_heading.find_parent()
            if heading_elem:
                for table in heading_elem.find_all_next("table", limit=50):
                    parent_heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                    if parent_heading and parent_heading is not heading_elem:
                        heading_text = parent_heading.get_text(strip=True).lower()
                        if heading_text and "footnote" not in heading_text and "note" not in heading_text:
                            break
                    
                    rows = table.find_all("tr")
                    for row in rows:
                        cells = row.find_all(["td", "th"])
                        if len(cells) >= 2:
                            # First cell contains anchor, second cell contains content
                            anchor_cell = cells[0]
                            content_cell = cells[1]
                            
                            anchor = anchor_cell.find("a", attrs={"id": True}) or anchor_cell.find("a", attrs={"name": True})
                            if anchor:
                                anchor_id = anchor.get("id") or anchor.get("name")
                                if anchor_id:
                                    # Extract content from second cell
                                    content_text = clean_text_fragments(content_cell.get_text("\n", strip=True))
                                    # Remove the anchor number prefix if present
                                    content_text = re.sub(r"^\[?\d+\]?\.?\s*", "", content_text).strip()
                                    
                                    if content_text and len(content_text) < MAX_FOOTNOTE_LENGTH:
                                        key = anchor_id.lower()
                                        if key not in footnotes:
                                            footnotes[key] = content_text
                                        # Also add numeric variants
                                        num_match = re.search(r"(\d+)", key)
                                        if num_match:
                                            num = num_match.group(1)
                                            for variant in [num, f"n{num}", f"note{num}", f"footnote{num}"]:
                                                if variant not in footnotes:
                                                    footnotes[variant] = content_text
        
        normalized: Dict[str, str] = {}
        for key, text in footnotes.items():
            k = key.lower()
            normalized.setdefault(k, text)
            num_match = re.search(r"(\d+)", k)
            if num_match:
                num = num_match.group(1)
                for alt in (num, f"n{num}", f"note{num}", f"footnote{num}", f"fn{num}"):
                    normalized.setdefault(alt, text)
            for prefix in ("fw", "bk"):
                if k.startswith(prefix):
                    stripped = k[len(prefix):]
                    if stripped:
                        normalized.setdefault(stripped, text)

        self._last_footnote_stats = {
            "extracted": len(normalized),
        }
        return normalized

    def _match_footnote_content(self, ref: Tag, footnotes: Dict[str, str]) -> Optional[str]:
        href = ref.get("href", "")
        link_text = ref.get_text(" ", strip=True)
        href_lower = href.lower()

        if href_lower in ("#top", "#toc"):
            return None

        if href_lower.startswith("#s") or href_lower.startswith("#fig"):
            return None
        
        if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", link_text, re.I):
            return None

        candidates: List[str] = []

        if href.startswith("#"):
            raw = href.lstrip("#").lower()
            candidates.append(raw)
            for prefix in ("fw", "bk"):
                if raw.startswith(prefix):
                    candidates.append(raw[len(prefix):])
            num_match = re.search(r"(\d+)", raw)
            if num_match:
                num = num_match.group(1)
                candidates.extend([num, f"n{num}", f"note{num}", f"footnote{num}"])

        text_num = re.search(r"(\d+)", link_text)
        if text_num:
            num = text_num.group(1)
            candidates.extend([num, f"n{num}", f"note{num}", f"footnote{num}"])

        seen: set[str] = set()
        ordered_candidates = []
        for cand in candidates:
            if cand and cand not in seen:
                seen.add(cand)
                ordered_candidates.append(cand)

        for cand in ordered_candidates:
            if cand in footnotes:
                return footnotes[cand]
        return None

    def _inline_footnote_refs(self, soup: BeautifulSoup, footnotes: Dict[str, str]) -> None:
        unmatched_examples: List[str] = []
        matched = 0
        unmatched = 0
        for ref in soup.find_all("a", href=True):
            href = ref["href"]
            if not href.startswith("#"):
                continue

            content = self._match_footnote_content(ref, footnotes)

            if content:
                placeholder = soup.new_tag("latexfootnote")
                placeholder["content"] = content
                ref.replace_with(placeholder)
                matched += 1
            else:
                unmatched += 1
                if len(unmatched_examples) < 5 and not href.lower().startswith("#s"):
                    text_preview = ref.get_text(" ", strip=True)[:40]
                    unmatched_examples.append(f"{href} ({text_preview})")
                ref.unwrap()

        if unmatched_examples:
            sample = "; ".join(unmatched_examples)
            self.log_fn(f"Warning: {len(unmatched_examples)} footnote references had no match: {sample}")
        self._last_footnote_stats["inlined"] = matched
        self._last_footnote_stats["unmatched_refs"] = unmatched

    def _inline_manual_footnote_refs(self, soup: BeautifulSoup, footnotes: Dict[str, str]) -> None:
        """
        Find and replace manual footnote references like [1], [2] in text nodes
        that aren't clickable links, matching them with extracted footnotes.
        """
        # Pattern to match footnote references like [1], [2], etc. in text
        footnote_pattern = re.compile(r'\[(\d+)\]')
        
        manual_matched = 0
        manual_unmatched = []
        
        # Get content node
        content_node = self._select_content_node(soup)
        if not content_node:
            return
        
        # Process text nodes - need to collect first, then replace (can't modify during iteration)
        text_nodes_to_process = []
        for text_node in content_node.descendants:
            if not isinstance(text_node, NavigableString):
                continue
            parent = text_node.find_parent()
            if not parent:
                continue
            # Skip if inside script, style, or link
            if parent.name in ['script', 'style']:
                continue
            if parent.find_parent('a'):
                continue
            # Skip footnote sections
            footnote_parent = parent.find_parent(class_=re.compile(r'(footnote|endnote|note)', re.I))
            if footnote_parent:
                continue
            
            text = str(text_node.string)
            if '[' in text and ']' in text:
                matches = list(footnote_pattern.finditer(text))
                if matches:
                    text_nodes_to_process.append((text_node, parent, text, matches))
        
        # Process collected text nodes
        for text_node, parent, text, matches in text_nodes_to_process:
            parts = []
            last_pos = 0
            matched_any = False
            
            for match in matches:
                # Add text before this match
                if match.start() > last_pos:
                    parts.append(NavigableString(text[last_pos:match.start()]))
                
                # Extract footnote number
                footnote_num = match.group(1)
                
                # Try to find matching footnote content - check all possible key variations
                footnote_content = None
                # Try various key formats that might be in the normalized dictionary
                key_variants = [
                    footnote_num,  # "1"
                    f"n{footnote_num}",  # "n1"
                    f"note{footnote_num}",  # "note1"
                    f"footnote{footnote_num}",  # "footnote1"
                    f"#{footnote_num}",  # "#1"
                    f"fn{footnote_num}",  # "fn1"
                ]
                
                # Check each variant (case-insensitive)
                for key in key_variants:
                    key_lower = key.lower()
                    if key_lower in footnotes:
                        footnote_content = footnotes[key_lower]
                        break
                
                # If still not found, try searching for any key containing the number
                if not footnote_content:
                    for key, value in footnotes.items():
                        # Check if key contains just the number (like "1" or ends with "1")
                        if key == footnote_num or key == f"n{footnote_num}":
                            footnote_content = value
                            break
                        # Check if key has the number in it
                        if re.search(rf'\b{footnote_num}\b', key):
                            num_in_key = re.search(r'(\d+)', key)
                            if num_in_key and num_in_key.group(1) == footnote_num:
                                footnote_content = value
                                break
                
                if footnote_content:
                    # Create placeholder tag for endnote
                    placeholder = soup.new_tag("latexfootnote")
                    placeholder["content"] = footnote_content
                    parts.append(placeholder)
                    manual_matched += 1
                    matched_any = True
                else:
                    # Keep original if no match
                    parts.append(NavigableString(match.group(0)))
                    if len(manual_unmatched) < 5:
                        manual_unmatched.append(f"[{footnote_num}]")
                        # Debug: log available footnote keys
                        if len(manual_unmatched) == 1:
                            available_keys = list(footnotes.keys())[:10]
                            self.log_fn(f"Debug: Available footnote keys (first 10): {available_keys}")
                
                last_pos = match.end()
            
            # Add remaining text
            if last_pos < len(text):
                parts.append(NavigableString(text[last_pos:]))
            
            # Replace the text node if we made any replacements
            if matched_any:
                text_node.extract()
                for part in parts:
                    parent.append(part)
        
        if manual_unmatched:
            self.log_fn(f"Warning: {len(manual_unmatched)} manual footnote references had no match: {', '.join(manual_unmatched[:5])}")
        if manual_matched > 0:
            self.log_fn(f"Converted {manual_matched} manual footnote references to endnotes.")
            self._last_footnote_stats["inlined"] = self._last_footnote_stats.get("inlined", 0) + manual_matched

    def _handle_images(self, soup: BeautifulSoup, node: Tag, page_url: str, images_dir: str) -> None:
        if not node:
            return
        for img in node.find_all("img"):
                img.decompose()

    def _html_to_latex(self, element, base_url: str = "") -> str:
        if isinstance(element, Comment):
            return ""
        if isinstance(element, NavigableString):
            text = clean_text_node(str(element))
            if not text:
                return ""
            return escape_latex(text)
        if not isinstance(element, Tag):
            return ""
        name = element.name.lower()

        def convert_children(tag: Tag) -> str:
            return "".join(self._html_to_latex(child, base_url) for child in tag.children)

        if name == "latexfootnote":
            content = clean_text_fragments(element.get("content", ""))
            if not content:
                return ""
            if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", content, re.I):
                return ""
            return f"\\endnote{{{escape_latex(content)}}}"
        if name == "lateximage":
            path = element.get("path", "")
            path = path.replace("\\", "/")
            return (
                "\\begin{figure}[H]\\centering"
                f"\\includegraphics[width=0.9\\linewidth]{{{path}}}"
                "\\end{figure}"
            )
        if name in ["p", "div", "center"]:
            classes = element.get("class", [])
            if classes and any("quote" in c.lower() for c in classes):
                body = self._normalize_block(convert_children(element))
                return "\\begin{quoting}\n" + body + "\n\\end{quoting}\n\n"
            if classes and any("indentb" in c.lower() for c in classes):
                raw = convert_children(element)
                lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
                body = " \\\\n".join(lines)
                body = self._normalize_block(body)
                return "\\begin{quote}\n" + body + "\n\\end{quote}\n\n"
            if classes and any("inline" == c.lower() for c in classes):
                content = convert_children(element)
                return f"\\begin{{flushright}}\n{content}\n\\end{{flushright}}\n\n"
            return convert_children(element) + "\n\n"
        if name == "br":
            return "\n"
        if name in ["em", "i", "cite"]:
            return f"\\textit{{{convert_children(element)}}}"
        if name in ["strong", "b"]:
            return f"\\textbf{{{convert_children(element)}}}"
        if name in ["span", "font"]:
            classes = element.get("class", [])
            if classes and any("inline" == c.lower() for c in classes):
                return f"\\begin{{flushright}}{convert_children(element)}\\end{{flushright}}"
            return convert_children(element)

        if name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(name[1])
            return self._convert_heading(element, level, convert_children)
        if name == "blockquote":
            body = self._normalize_block(convert_children(element))
            if "\\begin{quoting}" in body:
                return body + "\n\n"
            return "\\begin{quoting}\n" + body + "\n\\end{quoting}\n\n"
        if name == "ul":
            items = "".join("\\item " + convert_children(li) + "\n" for li in element.find_all("li", recursive=False))
            return "\\begin{itemize}\n" + items + "\\end{itemize}\n\n"
        if name == "ol":
            items = "".join("\\item " + convert_children(li) + "\n" for li in element.find_all("li", recursive=False))
            return "\\begin{enumerate}\n" + items + "\\end{enumerate}\n\n"
        if name == "li":
            return "\\item " + convert_children(element) + "\n"
        if name == "table":
            return self._convert_table(element, convert_children)
        if name in ["tbody", "thead", "tfoot", "tr", "td", "th"]:
            return convert_children(element)
        if name == "a":
            href = element.get("href")
            text = convert_children(element)
            if href:
                if href.startswith("#"):
                    return text
                if not href.startswith("http"):
                    if base_url:
                        href = urljoin(base_url, href)
                    else:
                        return text
                return f"\\href{{{escape_latex(href)}}}{{{text}}}"
            return text
        return convert_children(element)

    def _convert_heading(self, element: Tag, level: int, convert_children):
        heading_text = element.get_text(strip=True).lower()
        if heading_text in ["notes", "note", "footnotes", "endnotes"]:
            return ""
        if self._is_navigation_heading(element):
            return ""
        content = self._clean_heading_content(convert_children(element))
        if not content:
            return ""
        content = content.replace("\n", " ").replace("\r", " ").strip()
        if level == 1:
            return f"\\section*{{{content}}}\n\n"
        if level == 2:
            return f"\\subsection*{{{content}}}\n\n"
        if level == 3:
            return f"\\subsubsection*{{{content}}}\n\n"
        if level == 4:
            return f"\\subsection*{{{content}}}\n\n"
        return f"\\paragraph*{{{content}}}\\mbox{{}}\\\\\n\n"

    def _convert_table(self, element: Tag, convert_children):
        table_class = element.get("class", [])
        if table_class and any("foot" in c.lower() or "nav" in c.lower() for c in table_class):
            return ""

        # If the table contains lists, it's usually a structured outline; render as text to avoid LaTeX alignment issues.
        if element.find(["ol", "ul", "li"]):
            return self._table_to_text(element, in_blockquote=bool(element.find_parent("blockquote")))

        nested_inner = element.find("table")
        if nested_inner:
            # Nested tables (often value-form diagrams) show up in Marx's value-form sections; try a structured rendering first.
            rendered = self._convert_nested_value_form_table(element, convert_children)
            if rendered:
                return rendered
            return self._table_to_text(element, in_blockquote=bool(element.find_parent("blockquote")))

        rows = element.find_all("tr")
        if not rows:
            return ""

        if len(rows) == 1:
            cells = rows[0].find_all(["td", "th"])
            if len(cells) == 1:
                cell = cells[0]
                parent = element.find_parent("blockquote")
                # Check if this is poetry BEFORE converting to preserve structure
                if self._is_poetry_cell(cell):
                    formatted_content = self._extract_and_format_poetry(cell)
                    if parent:
                        return f"{formatted_content}\n\n"
                    return "\\begin{center}\n\\begin{quoting}\n" + formatted_content + "\n\\end{quoting}\n\\end{center}\n\n"
                else:
                    # Normal table cell formatting
                    cell_content = convert_children(cell)
                    if cell_content.strip():
                        if parent:
                            return self._normalize_block(cell_content) + "\n\n"
                        return "\\begin{quoting}\n" + self._normalize_block(cell_content) + "\n\\end{quoting}\n\n"
                    return ""

        if self._is_section_list_table(rows, convert_children):
            table_rows = []
            for row in rows:
                cells = row.find_all(["td", "th"], recursive=False)
                if len(cells) == 1 and cells[0].get("colspan") == "2":
                    table_rows.append("\\hline")
                    continue
                if row.find("hr"):
                    table_rows.append("\\hline")
                    continue

                if len(cells) == 2:
                    left_content = convert_children(cells[0])
                    left_content_clean = escape_latex(left_content.strip())
                    if re.match(r"^[IVX]+\.\s*[A-Z\s]+$", left_content_clean, re.I):
                        left_content_clean = f"\\textbf{{{left_content_clean}}}"
                    right_content = convert_children(cells[1])
                    right_content = self._normalize_block(right_content)
                    table_rows.append(f"{left_content_clean} & {right_content} \\\\")

            if table_rows:
                table_content = "\n".join(table_rows)
                return (
                    "\\begin{center}\n"
                    "\\begin{tabular}{>{\\raggedleft\\arraybackslash}p{0.22\\textwidth}|p{0.73\\textwidth}}\n"
                    "\\renewcommand{\\arraystretch}{1.1}\n"
                    "\\setlength{\\tabcolsep}{0.8em}\n"
                    f"{table_content}\n"
                    "\\end{tabular}\n"
                    "\\end{center}\n\n"
                )

        if self._is_numbered_list_table(rows):
            result = self._convert_numbered_list_table(rows)
            if result:
                return result

        parent = element.find_parent("blockquote")
        in_blockquote = parent is not None

        return self._table_to_text(element, in_blockquote=in_blockquote)

    def _clean_heading_content(self, raw: str) -> str:
        cleaned = re.sub(r"\\endnote\{[^}]*\}", "", raw)
        cleaned = re.sub(r"\s*>>\s*", "", cleaned)
        cleaned = re.sub(r"\s*<<\s*", "", cleaned)
        cleaned = re.sub(r"\\href\{[^}]+\}\{[^}]+\}", "", cleaned)
        cleaned = re.sub(r"\s*\|\s*", " ", cleaned)
        if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", cleaned, re.I):
            return ""
        if re.match(r"^Top\s+of\s+the\s+page\s*$", cleaned, re.I):
            return ""
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _is_navigation_heading(self, elem: Tag) -> bool:
        raw_text = elem.get_text(strip=True)
        has_nav_arrows = ">>" in raw_text or "<<" in raw_text
        has_nav_text = "top of the page" in raw_text.lower()
        has_nav_links = len(elem.find_all("a", href=True)) > 0 and ("contents" in raw_text.lower() or "page" in raw_text.lower())
        return has_nav_arrows or has_nav_text or has_nav_links

    def _strip_trailing_breaks(self, text: str) -> str:
        text = text.rstrip()
        text = re.sub(r"(\\\\\s*)+$", "", text)
        return text

    def _strip_leading_breaks(self, text: str) -> str:
        text = text.lstrip()
        text = re.sub(r"^(\\\\\s*)+", "", text)
        return text

    def _normalize_block(self, text: str) -> str:
        text = text or ""
        text = self._strip_leading_breaks(self._strip_trailing_breaks(text))
        lines = text.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def _is_poetry_cell(self, cell: Tag) -> bool:
        """Check if a table cell contains poetry (multiple line breaks from br tags)."""
        br_tags = cell.find_all("br")
        if len(br_tags) >= 3:  # Poetry usually has multiple line breaks
            return True
        # Also check if content has multiple paragraphs or lines that look like poetry
        text_content = cell.get_text("\n", strip=True)
        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
        if len(lines) >= 3:
            # Check if lines are short (typical of poetry)
            short_lines = sum(1 for line in lines if len(line) < 80)
            if short_lines >= len(lines) * 0.7:  # 70% are short lines
                return True
        return False

    def _extract_and_format_poetry(self, cell: Tag) -> str:
        """Extract poetry directly from HTML cell, preserving line breaks from br tags."""
        from .utils import escape_latex
        from .utils import clean_text_node
        
        lines = []
        current_line_parts = []
        
        def extract_inline_content(elem):
            """Extract and convert inline content (text, footnotes, emphasis, etc.) without wrapping."""
            nonlocal current_line_parts
            if isinstance(elem, NavigableString):
                text = clean_text_node(str(elem))
                if text:
                    current_line_parts.append(escape_latex(text))
            elif isinstance(elem, Tag):
                if elem.name == "latexfootnote":
                    # Handle footnote placeholder
                    content = clean_text_fragments(elem.get("content", ""))
                    if content:
                        current_line_parts.append(f"\\endnote{{{escape_latex(content)}}}")
                elif elem.name in ["em", "i", "cite"]:
                    text = elem.get_text(" ", strip=True)
                    if text:
                        current_line_parts.append(f"\\textit{{{escape_latex(text)}}}")
                elif elem.name in ["strong", "b"]:
                    text = elem.get_text(" ", strip=True)
                    if text:
                        current_line_parts.append(f"\\textbf{{{escape_latex(text)}}}")
                elif elem.name == "a":
                    # Handle links - if it's a footnote, it should be converted already
                    # Otherwise just get text
                    text = elem.get_text(" ", strip=True)
                    if text:
                        current_line_parts.append(escape_latex(text))
                else:
                    # Recursively process other inline elements
                    for child in elem.children:
                        extract_inline_content(child)
        
        def process_poetry_element(elem):
            """Process elements in poetry, handling br tags as line breaks."""
            nonlocal current_line_parts
            if isinstance(elem, NavigableString):
                extract_inline_content(elem)
            elif isinstance(elem, Tag):
                if elem.name == "br":
                    # br tag = end of line
                    if current_line_parts:
                        line_content = " ".join(current_line_parts).strip()
                        if line_content:
                            lines.append(line_content)
                        current_line_parts = []
                elif elem.name == "p":
                    # Process paragraph contents directly (don't wrap)
                    for child in elem.children:
                        process_poetry_element(child)
                else:
                    extract_inline_content(elem)
        
        # Process all children of the cell
        for child in cell.children:
            process_poetry_element(child)
        
        # Add the last line if it has content
        if current_line_parts:
            line_content = " ".join(current_line_parts).strip()
            if line_content:
                lines.append(line_content)
        
        # Remove empty lines
        lines = [line for line in lines if line.strip()]
        
        if not lines:
            return ""
        
        # Format: each line ends with \\ except the last one
        result_parts = []
        for i, line in enumerate(lines):
            if i > 0:
                result_parts.append(" \\\\")
            result_parts.append(f"\n{line}")
        
        return "".join(result_parts)
    
    def _format_poetry_content(self, content: str) -> str:
        """Format poetry content preserving line breaks with proper LaTeX line breaks."""
        # Remove any nested quoting environments that might have been added to paragraphs
        content = re.sub(r"\\begin\{quoting\}\s*", "", content)
        content = re.sub(r"\\end\{quoting\}\s*", "", content)
        
        # Split by line breaks and preserve them
        lines = content.split("\n")
        # Clean up lines but preserve structure
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)
        
        if not cleaned_lines:
            return content
        
        # Join lines with LaTeX line breaks (\\ for line break in quoting environment)
        # Each line ends with \\ except the last one
        result_parts = []
        for i, line in enumerate(cleaned_lines):
            if i > 0:
                result_parts.append(" \\\\")
            result_parts.append(f"\n{line}")
        
        return "".join(result_parts)

    def _is_section_list_table(self, rows_list, convert_children) -> bool:
        if len(rows_list) < 2:
            return False
        section_count = 0
        list_count = 0
        for row in rows_list:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) == 1 and cells[0].get("colspan") == "2":
                continue
            if row.find("hr"):
                continue
            if len(cells) == 2:
                left_text = cells[0].get_text(strip=True)
                right_elem = cells[1]
                if re.match(r"^[IVX]+\.\s+[A-Z\s]+$", left_text.strip()):
                    section_count += 1
                if right_elem.find("ol"):
                    list_count += 1
        return section_count >= 1 and list_count >= 1
    def _table_to_text(self, table: Tag, in_blockquote: bool = False) -> str:
        rows = table.find_all("tr")
        if not rows:
            return ""

        # Flatten any nested lists to plain text for stable LaTeX.
        for lst in table.find_all(["ol", "ul"]):
            lst.replace_with(lst.get_text(" ", strip=True))

        lines = []
        for row in rows:
            cells = row.find_all(["td", "th"])
            cell_texts = []
            for cell in cells:
                text = cell.get_text(" ", strip=True)
                text = clean_text_fragments(text)
                if text:
                    escaped = escape_latex(text)
                    cell_texts.append(escaped)
            if cell_texts:
                row_text = " --- ".join(cell_texts)
                lines.append(row_text)
        
        if not lines:
            return ""
        
        content = "\n\n".join(lines)
        
        if in_blockquote:
            return f"\n{content}\n\n"
        
        return f"\n\\begin{{quoting}}\n{content}\n\\end{{quoting}}\n\n"

    def _is_numbered_list_table(self, rows: List[Tag]) -> bool:
        if not rows:
            return False
        
        number_pattern = re.compile(r"\(\d+\)")
        
        full_text = ""
        for row in rows:
            full_text += row.get_text()
        
        matches = number_pattern.findall(full_text)
        return len(matches) >= 2
    
    def _convert_numbered_list_table(self, rows: List[Tag]) -> str:
        number_pattern = re.compile(r"^\s*\((\d+)\)\s*$")
        
        all_cells = []
        for row in rows:
            all_cells.extend(row.find_all(["td", "th"]))
        
        if len(all_cells) < 2:
            return ""
        
        first_cell = all_cells[0]
        second_cell = all_cells[1] if len(all_cells) > 1 else None
        
        if not second_cell:
            return ""
        
        item_line_counts = self._parse_numbered_cell(first_cell)
        
        if len(item_line_counts) < 2:
            return ""
        
        content_lines = self._get_content_lines(second_cell)
        
        artifact_pattern = re.compile(r"vol=\d+\s*pg=\d+\s*src=\S*\s*type=\s*", re.I)
        content_lines = [artifact_pattern.sub("", line).strip() for line in content_lines]
        content_lines = [line for line in content_lines if line]
        
        items = []
        line_idx = 0
        for count in item_line_counts:
            item_parts = []
            for _ in range(count):
                if line_idx < len(content_lines):
                    item_parts.append(content_lines[line_idx])
                    line_idx += 1
            if item_parts:
                items.append(" ".join(item_parts))
        
        if line_idx < len(content_lines) and items:
            remaining = " ".join(content_lines[line_idx:])
            items[-1] = items[-1] + " " + remaining
        
        if items:
            item_strs = [f"\\item {escape_latex(item)}" for item in items]
            return "\\begin{enumerate}\n" + "\n".join(item_strs) + "\n\\end{enumerate}\n\n"
        
        return ""
    
    def _parse_numbered_cell(self, cell: Tag) -> List[int]:
        number_pattern = re.compile(r"^\s*\((\d+)\)\s*$")
        
        items_info = []
        current_number = None
        br_count = 0
        
        for child in cell.children:
            if isinstance(child, Tag) and child.name == "br":
                br_count += 1
            elif isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    match = number_pattern.match(text)
                    if match:
                        if current_number is not None:
                            items_info.append(br_count)
                        current_number = int(match.group(1))
                        br_count = 0
        
        if current_number is not None:
            items_info.append(max(br_count, 1))
        
        return items_info
    
    def _get_content_lines(self, cell: Tag) -> List[str]:
        lines = []
        current_parts = []
        
        for child in cell.children:
            if isinstance(child, Tag):
                if child.name == "br":
                    if current_parts:
                        lines.append(" ".join(current_parts))
                        current_parts = []
                elif child.name == "comment":
                    continue
                else:
                    text = child.get_text().strip()
                    if text:
                        current_parts.append(text)
            elif isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    current_parts.append(text)
        
        if current_parts:
            lines.append(" ".join(current_parts))
        
        return lines

    def _convert_nested_value_form_table(self, element: Tag, convert_children) -> str:
        """Render nested Marx value-form tables (vertical bar with a single equivalent column) as a tidy tabular layout."""
        outer_rows = element.find_all("tr", recursive=False)
        if len(outer_rows) != 1:
            return ""

        outer_cells = outer_rows[0].find_all("td", recursive=False)
        if len(outer_cells) < 2:
            return ""

        inner_table = None
        right_cell: Optional[Tag] = None
        for cell in outer_cells:
            nested = cell.find("table")
            if nested and inner_table is None:
                inner_table = nested
            else:
                text = clean_text_fragments(cell.get_text(" ", strip=True))
                if text:
                    right_cell = cell

        if not inner_table or right_cell is None:
            return ""

        inner_rows = inner_table.find_all("tr", recursive=False)
        if len(inner_rows) < 2:
            return ""

        left_items: List[str] = []
        has_equals_column = False
        for row in inner_rows:
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                continue

            raw_texts = [clean_text_fragments(c.get_text(" ", strip=True)) for c in cells]
            if raw_texts and raw_texts[-1] == "=":
                has_equals_column = True
                cells = cells[:-1]

            parts: List[str] = []
            for cell in cells:
                content = convert_children(cell)
                content = self._normalize_block(content)
                content = content.replace("\n", " ").strip()
                content = re.sub(r"\s+", " ", content)
                if content:
                    parts.append(content)

            combined = " ".join(parts).strip()
            if combined:
                left_items.append(combined)

        if len(left_items) < 2:
            return ""

        right_content = convert_children(right_cell)
        right_content = self._normalize_block(right_content)
        right_content = right_content.replace("\n", " ").strip()
        right_content = re.sub(r"\s+", " ", right_content)
        if not right_content:
            return ""

        if not has_equals_column and not right_content.lstrip().startswith("="):
            right_content = f"= {right_content}"

        col_spec = (
            r">{\raggedleft\arraybackslash}p{0.38\textwidth} c|p{0.5\textwidth}"
            if has_equals_column
            else r">{\raggedleft\arraybackslash}p{0.42\textwidth}|p{0.5\textwidth}"
        )

        total_rows = len(left_items)
        table_rows: List[str] = []
        for idx, item in enumerate(left_items):
            if has_equals_column:
                if idx == 0:
                    table_rows.append(f"{item} & = & \\multirow{{{total_rows}}}{{*}}{{{right_content}}} \\\\")
                else:
                    table_rows.append(f"{item} & = & \\\\")
            else:
                if idx == 0:
                    table_rows.append(f"{item} & \\multirow{{{total_rows}}}{{*}}{{{right_content}}} \\\\")
                else:
                    table_rows.append(f"{item} & \\\\")

        return (
            "\\begin{center}\n"
            "\\setlength{\\tabcolsep}{1.1em}\n"
            "\\renewcommand{\\arraystretch}{1.15}\n"
            f"\\begin{{tabular}}{{{col_spec}}}\n"
            + "\n".join(table_rows)
            + "\n\\end{tabular}\n"
            "\\end{center}\n\n"
        )
