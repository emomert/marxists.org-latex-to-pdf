import re
from typing import Callable, Dict, Optional, Tuple

from bs4 import BeautifulSoup

from .chapter_title import strip_book_headers_and_get_chapter_title
from .content_cleanup import remove_artifact_nodes, select_content_node, strip_unwanted
from .footnotes import extract_footnotes, inline_footnote_refs, inline_manual_footnote_refs
from .image_handler import handle_images
from .latex import break_long_lines, clean_latex_spacing
from .metadata_extractor import extract_metadata


StatsDict = Dict[str, int]


def prepare_article_content(
    html: str,
    url: str,
    images_dir: str,
    render_fn: Callable[[object, str], str],
    log_fn: Callable[[str], None],
    book_title: Optional[str] = None,
    book_author: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str], list[tuple[str, str]], str, StatsDict]:
    soup = BeautifulSoup(html, "html.parser")
    strip_unwanted(soup)

    footnotes = extract_footnotes(soup)
    stats: StatsDict = {"extracted": len(footnotes)}

    inline_stats = inline_footnote_refs(soup, footnotes, log_fn)
    stats["inlined"] = inline_stats.get("inlined", 0)
    stats["unmatched_refs"] = inline_stats.get("unmatched_refs", 0)

    content_node = select_content_node(soup)
    manual_matched = inline_manual_footnote_refs(soup, content_node, footnotes, log_fn)
    if manual_matched > 0:
        stats["inlined"] = stats.get("inlined", 0) + manual_matched

    remove_artifact_nodes(soup)
    content_node = select_content_node(soup)

    meta_title, meta_date, author, meta_entries = extract_metadata(soup, content_node, url, log_fn)
    handle_images(soup, content_node, url, images_dir)

    chapter_title = meta_title
    if book_title or book_author:
        chapter_title = strip_book_headers_and_get_chapter_title(content_node, book_title, book_author, meta_title)

    latex_body = render_fn(content_node, url)
    latex_body = re.sub(r"\\endnote\{[^}]*MIA[^}]*Archive[^}]*\}", "", latex_body, flags=re.I)
    latex_body = clean_latex_spacing(latex_body)
    latex_body = break_long_lines(latex_body)

    return chapter_title, meta_date, author, meta_entries, latex_body, stats
