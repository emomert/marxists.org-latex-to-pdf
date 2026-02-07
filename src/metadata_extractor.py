import re
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from .utils import escape_latex


def _author_from_url(url: str) -> Optional[str]:
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


def extract_metadata(
    soup: BeautifulSoup,
    content_node: Tag,
    url: str,
    log_fn: Callable[[str], None],
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
        author = _author_from_url(url)
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
                        if current.name == "br":
                            break
                        if current.name == "a":
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
        log_fn(f"Author detected from {author_source}: {author}")
    elif not author:
        log_fn("Author not detected; leaving as Unknown.")

    return title or "Untitled", date, author or "Unknown", meta_entries
