import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from .config import PART_HEADING_RE
from .utils import canonical_url, normalize_href


def is_chapter_link(href: str) -> bool:
    href_lower = href.lower()
    if href_lower.startswith("#"):
        return False
    if "index.htm" in href_lower:
        return False
    return href_lower.endswith((".htm", ".html"))


def collect_toc_links(soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str]]:
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
            if full_url and canon and canon not in seen and is_chapter_link(full_url):
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
                if full_url and canon and is_chapter_link(full_url):
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


def collect_chapter_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    links: List[str] = []
    seen: set[str] = set()
    base_dir = "/".join(base_url.split("/")[:-1]) + "/"
    for a in soup.find_all("a", href=True):
        full = normalize_href(a["href"], base_url)
        if not full or not is_chapter_link(full):
            continue
        if not full.startswith(base_dir):
            continue
        canon = canonical_url(full)
        if canon in seen:
            continue
        seen.add(canon)
        links.append(full)
    return links


def detect_parts_for_index(
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

            if current_part and element.name == "a" and element.has_attr("href"):
                full = normalize_href(element["href"], base_url)
                canon = canonical_url(full) if full else ""
                if canon in chapter_set and canon not in part_map:
                    part_map[canon] = current_part

    return part_map
