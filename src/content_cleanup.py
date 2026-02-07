import re

from bs4 import BeautifulSoup, Tag


def strip_unwanted(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style", "header", "footer", "nav", "form"]):
        tag.decompose()
    for a in soup.find_all("a"):
        text = (a.get_text() or "").lower()
        if "back to" in text or "return to" in text:
            parent = a.parent
            if parent:
                parent.decompose()


def remove_artifact_nodes(soup: BeautifulSoup) -> None:
    class_pattern = re.compile(r"(t2h-|footnote|endnote)", re.I)
    for tag in list(soup.find_all(True, class_=class_pattern)):
        tag.decompose()
    for tag in list(soup.find_all(True, id=class_pattern)):
        tag.decompose()
    for span in list(soup.find_all("span", string=re.compile(r"t2h-", re.I))):
        span.decompose()

    for tag in soup.find_all(class_=re.compile(r"(footer|terms|nav|header|crumbs)", re.I)):
        tag.decompose()

    for elem in soup.find_all(["p", "div", "span"]):
        text = elem.get_text(strip=True)
        if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", text, re.I):
            if ">" in text and ("Archive" in text or "MIA" in text):
                elem.decompose()
                continue


def select_content_node(soup: BeautifulSoup) -> Tag:
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
