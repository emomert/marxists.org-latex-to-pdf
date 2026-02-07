import requests
from typing import Callable, Dict, List, Optional, Tuple

from .models import ArticleContent
from .metadata_extractor import extract_metadata
from .html_to_latex_renderer import HtmlToLatexRenderer
from .url_analysis import analyze_url_kind, guess_chapter_sequence
from .book_pipeline import run_book_pipeline
from .http_client import build_session, fetch_html
from .article_pipeline import prepare_article_content

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
        self.session = session or build_session()
        self.request_delay = max(0.0, request_delay)
        self.allow_guessing = allow_guessing
        self._last_footnote_stats: Dict[str, int] = {}
        self._renderer = HtmlToLatexRenderer()

    # ---- network helpers ----
    def fetch(self, url: str) -> Tuple[str, str]:
        return fetch_html(self.session, url, self.request_delay, self.log_fn)

    # ---- analysis ----
    def analyze_url(self, url: str) -> str:
        return analyze_url_kind(url, self.fetch)

    # ---- scraping ----
    def scrape_article(
        self, url: str, images_dir: str, book_title: Optional[str] = None, book_author: Optional[str] = None
    ) -> ArticleContent:
        html, _ = self.fetch(url)
        chapter_title, meta_date, author, meta_entries, latex_body, stats = prepare_article_content(
            html=html,
            url=url,
            images_dir=images_dir,
            render_fn=lambda node, base_url: self._renderer.render(node, base_url=base_url),
            log_fn=self.log_fn,
            book_title=book_title,
            book_author=book_author,
        )
        self._last_footnote_stats = stats
        if stats:
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
        return run_book_pipeline(
            index_url,
            work_dir,
            self.allow_guessing,
            self.fetch,
            lambda s, c, u: extract_metadata(s, c, u, self.log_fn),
            lambda u, limit: guess_chapter_sequence(u, lambda candidate: self.session.get(candidate, timeout=10), limit=limit),
            self.scrape_article,
            self.progress_fn,
            self.log_fn,
        )

