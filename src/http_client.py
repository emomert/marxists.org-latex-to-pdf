import time
from typing import Callable, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session() -> requests.Session:
    """Create a requests session with retry/backoff and a polite User-Agent."""
    sess = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods={"GET", "HEAD"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.headers.update(
        {
            "User-Agent": "MarxistsConverter/1.0 (+https://www.marxists.org/)",
        }
    )
    return sess


def fetch_html(
    session: requests.Session,
    url: str,
    request_delay: float,
    log_fn: Callable[[str], None],
) -> Tuple[str, str]:
    log_fn(f"Requesting {url}")
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        try:
            html_content = resp.content.decode("utf-8", errors="replace")
        except (UnicodeDecodeError, AttributeError):
            resp.encoding = resp.apparent_encoding or "utf-8"
            html_content = resp.text
        if request_delay:
            time.sleep(request_delay)
        return html_content, content_type
    except requests.RequestException as exc:
        log_fn(f"Request failed for {url}: {exc}")
        raise
