import re
from typing import Optional

from bs4 import Tag


def strip_book_headers_and_get_chapter_title(
    content_node: Tag,
    book_title: Optional[str],
    book_author: Optional[str],
    fallback_title: str,
) -> str:
    if not content_node:
        return fallback_title

    def normalize(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text.lower().strip())

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
            heading_text_norm.startswith("chapter")
            or re.match(r"^[ivx]+\.", heading_text_norm)
            or re.match(r"^part\s+[ivx]+", heading_text_norm, re.I)
            or re.match(r"^[ivx]+\.\s+[a-z]", heading_text_norm)
        )

        is_preface_heading = (
            "preface" in heading_text_norm
            or "foreword" in heading_text_norm
            or "introduction" in heading_text_norm
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
