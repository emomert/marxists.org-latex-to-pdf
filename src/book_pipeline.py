import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag

from .chapter_discovery import collect_chapter_links, collect_toc_links, detect_parts_for_index
from .chapter_discovery import is_chapter_link
from .content_cleanup import select_content_node, strip_unwanted
from .models import ArticleContent
from .utils import canonical_url


OrderedLink = Tuple[str, str, bool]  # (url, toc_title, is_external)

@dataclass
class BookContext:
    title: Optional[str]
    date: Optional[str]
    author: Optional[str]
    meta_entries: List[Tuple[str, str]]
    toc_entries: List[Tuple[str, str]]
    chapter_links: List[str]
    part_map: Dict[str, str]
    all_links: List[OrderedLink]


def reconcile_chapter_links(
    toc_entries: List[Tuple[str, str]],
    chapter_links: List[str],
) -> Tuple[List[str], List[str]]:
    toc_urls = [url for _, url in toc_entries if is_chapter_link(url)]
    if not chapter_links and toc_urls:
        chapter_links = toc_urls
    return chapter_links, toc_urls


def build_ordered_links(
    toc_entries: List[Tuple[str, str]],
    chapter_links: List[str],
) -> List[OrderedLink]:
    url_to_chapter_link = {canonical_url(link): link for link in chapter_links}

    all_links: List[OrderedLink] = []
    seen_urls: set[str] = set()

    for toc_text, toc_url in toc_entries:
        toc_url_canon = canonical_url(toc_url)
        if toc_url_canon in seen_urls:
            continue

        if toc_url_canon in url_to_chapter_link:
            all_links.append((url_to_chapter_link[toc_url_canon], toc_text, False))
            seen_urls.add(toc_url_canon)
        elif is_chapter_link(toc_url):
            all_links.append((toc_url, toc_text, True))
            seen_urls.add(toc_url_canon)

    for link in chapter_links:
        link_canon = canonical_url(link)
        if link_canon not in seen_urls:
            all_links.append((link, "", False))
            seen_urls.add(link_canon)

    return all_links


def scrape_ordered_links(
    all_links: List[OrderedLink],
    images_dir: str,
    book_title: Optional[str],
    book_author: Optional[str],
    part_map: Dict[str, str],
    scrape_article_fn: Callable[[str, str, Optional[str], Optional[str]], ArticleContent],
    progress_fn: Callable[[float, str], None],
    log_fn: Callable[[str], None],
) -> Tuple[List[ArticleContent], int]:
    chapters: List[ArticleContent] = []
    total = len(all_links)
    failed_chapters = 0

    for idx, (link, toc_title, is_external) in enumerate(all_links, start=1):
        label_hint = toc_title or os.path.basename(urlparse(link).path) or f"Chapter {idx}"
        progress_fn(idx / total, f"Scraping {idx}/{total}: {label_hint[:60]}")
        try:
            chapter = scrape_article_fn(link, images_dir, book_title, book_author)
        except Exception as exc:  # noqa: BLE001
            log_fn(f"Failed chapter {link}: {exc}")
            failed_chapters += 1
            continue

        if not chapter.title:
            chapter.title = f"Chapter {idx}"
        if toc_title:
            if is_external:
                chapter.title = toc_title
            chapter.toc_title = toc_title
        chapter.part_title = part_map.get(canonical_url(link))
        chapters.append(chapter)

    return chapters, failed_chapters


def prepare_book_context(
    soup: BeautifulSoup,
    content_node: Tag,
    index_url: str,
    allow_guessing: bool,
    extract_metadata_fn: Callable[[BeautifulSoup, Tag, str], Tuple[str, Optional[str], Optional[str], List[Tuple[str, str]]]],
    guess_chapter_sequence_fn: Callable[[str, int], List[str]],
    log_fn: Callable[[str], None],
) -> BookContext:
    title, date, author, meta_entries = extract_metadata_fn(soup, content_node, index_url)
    toc_entries = collect_toc_links(soup, index_url)
    chapter_links = collect_chapter_links(soup, index_url)
    chapter_links, toc_urls = reconcile_chapter_links(toc_entries, chapter_links)
    part_map = detect_parts_for_index(content_node, index_url, chapter_links)

    if len(chapter_links) < 3 and not toc_urls:
        if allow_guessing:
            guessed = guess_chapter_sequence_fn(index_url, 40)
            log_fn(f"No or few chapters found; using guessed sequence ({len(guessed)} links).")
            if guessed:
                log_fn("Chapters guessed: " + ", ".join(guessed[:6]) + (" ..." if len(guessed) > 6 else ""))
            chapter_links = guessed
        else:
            log_fn("No or few chapters found; chapter guessing disabled.")

    if not chapter_links:
        raise RuntimeError("No chapter links detected or guessed.")

    all_links = build_ordered_links(toc_entries, chapter_links)

    return BookContext(
        title=title,
        date=date,
        author=author,
        meta_entries=meta_entries,
        toc_entries=toc_entries,
        chapter_links=chapter_links,
        part_map=part_map,
        all_links=all_links,
    )


def run_book_pipeline(
    index_url: str,
    work_dir: str,
    allow_guessing: bool,
    fetch_fn: Callable[[str], Tuple[str, str]],
    extract_metadata_fn: Callable[[BeautifulSoup, Tag, str], Tuple[str, Optional[str], Optional[str], List[Tuple[str, str]]]],
    guess_chapter_sequence_fn: Callable[[str, int], List[str]],
    scrape_article_fn: Callable[[str, str, Optional[str], Optional[str]], ArticleContent],
    progress_fn: Callable[[float, str], None],
    log_fn: Callable[[str], None],
) -> Tuple[str, Optional[str], Optional[str], List[Tuple[str, str]], List[ArticleContent], List[Tuple[str, str]]]:
    html, _ = fetch_fn(index_url)
    soup = BeautifulSoup(html, "html.parser")
    strip_unwanted(soup)
    content_node = select_content_node(soup)
    context = prepare_book_context(
        soup,
        content_node,
        index_url,
        allow_guessing,
        extract_metadata_fn,
        guess_chapter_sequence_fn,
        log_fn,
    )

    images_dir = os.path.join(work_dir, "images")
    chapters, failed_chapters = scrape_ordered_links(
        context.all_links,
        images_dir,
        context.title,
        context.author,
        context.part_map,
        scrape_article_fn,
        progress_fn,
        log_fn,
    )

    if not chapters:
        raise RuntimeError("No chapters were successfully scraped. All chapters failed or were empty.")
    if failed_chapters:
        log_fn(f"Warning: {failed_chapters} of {len(context.all_links)} chapters failed to scrape.")
    else:
        log_fn(f"Chapters scraped successfully: {len(chapters)}/{len(context.all_links)}.")

    return (
        context.title or "Collected Works",
        context.date,
        context.author,
        context.meta_entries,
        chapters,
        context.toc_entries,
    )
