import os
import sys
import unittest
from bs4 import BeautifulSoup

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.scraper import MarxistsScraper


def _make_scraper() -> MarxistsScraper:
    return MarxistsScraper(log_fn=lambda *_: None, progress_fn=lambda *_: None, request_delay=0.0)


class HtmlToLatexTests(unittest.TestCase):
    def test_navigation_heading_is_dropped(self) -> None:
        scraper = _make_scraper()
        soup = BeautifulSoup('<h1>>><a href="#toc">Contents</a></h1>', "html.parser")
        result = scraper._html_to_latex(soup.h1)
        self.assertEqual(result, "")

    def test_heading_converts(self) -> None:
        scraper = _make_scraper()
        soup = BeautifulSoup("<h2>Chapter One</h2>", "html.parser")
        result = scraper._html_to_latex(soup.h2)
        self.assertIn("\\subsection*", result)
        self.assertIn("Chapter One", result)

    def test_inline_footnote_inserts_placeholder(self) -> None:
        scraper = _make_scraper()
        soup = BeautifulSoup('<p>Text<a href="#n1">[1]</a></p>', "html.parser")
        scraper._inline_footnote_refs(soup, {"n1": "Footnote content"})
        latex = scraper._html_to_latex(soup.p)
        self.assertIn("\\endnote{Footnote content}", latex)
        self.assertEqual(scraper._last_footnote_stats.get("inlined"), 1)
        self.assertEqual(scraper._last_footnote_stats.get("unmatched_refs"), 0)

    def test_table_converts_to_tabular(self) -> None:
        scraper = _make_scraper()
        html = """
        <table>
            <tr><td>Left</td><td>Right</td></tr>
            <tr><td>Item</td><td>Value</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        latex = scraper._html_to_latex(soup.table)
        self.assertIn("Left", latex)
        self.assertTrue("\\begin{tabular}" in latex or "\\begin{quoting}" in latex)


class MetadataTests(unittest.TestCase):
    def test_metadata_unknown_author(self) -> None:
        scraper = _make_scraper()
        soup = BeautifulSoup("<html><body><div><h3 class='title'>My Title</h3></div></body></html>", "html.parser")
        title, date, author, meta = scraper._extract_metadata(soup, soup.div, "https://example.com/")
        self.assertEqual(title, "My Title")
        self.assertEqual(author, "Unknown")
        self.assertIsNone(date)
        self.assertIsInstance(meta, list)


if __name__ == "__main__":
    unittest.main()
