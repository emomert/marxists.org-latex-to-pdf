from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class ArticleContent:
    title: str
    date: Optional[str]
    author: Optional[str]
    meta_entries: List[Tuple[str, str]]
    latex_body: str
    # Optional higher-level grouping for multi-part works (e.g. "Part I: Commodities and Money")
    part_title: Optional[str] = None
    # Optional TOC title (may differ from chapter title)
    toc_title: Optional[str] = None
    # URL this chapter was scraped from (for TOC matching)
    url: Optional[str] = None
