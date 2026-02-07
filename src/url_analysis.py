from typing import Callable, List, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .chapter_discovery import is_chapter_link
from .utils import normalize_href


def analyze_url_kind(url: str, fetch_fn: Callable[[str], Tuple[str, str]]) -> str:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http"):
        raise ValueError("URL must start with http or https")
    if parsed.path.lower().endswith(("index.htm", "index.html")):
        return "book"

    html, _ = fetch_fn(url)
    soup = BeautifulSoup(html, "html.parser")
    base_dir = "/".join(url.split("/")[:-1]) + "/"
    chapterish_links = []
    for a in soup.find_all("a", href=True):
        full = normalize_href(a["href"], url)
        if not full:
            continue
        if not full.startswith(base_dir):
            continue
        if is_chapter_link(full):
            chapterish_links.append(full)
    return "book" if len(chapterish_links) >= 4 else "article"


def guess_chapter_sequence(
    index_url: str,
    get_fn: Callable[[str], object],
    limit: int = 80,
) -> List[str]:
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
                resp = get_fn(candidate)
                if getattr(resp, "status_code", None) == 200 and len(getattr(resp, "text", "")) > 200:
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
