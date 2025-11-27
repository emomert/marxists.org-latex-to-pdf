import os
import re
from urllib.parse import urljoin, urlparse
from .config import LATEX_ESCAPES, ARTIFACT_TOKEN_REGEX

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[<>:\"/\\\\|?*]+", "_", name)
    return cleaned.strip() or "file"


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters in text."""
    # First escape backslashes to avoid issues with control sequences
    escaped = text.replace("\\", r"\textbackslash{}")
    # Convert smart quotes to LaTeX quotes
    # Left double quote (") -> `` (two backticks)
    escaped = escaped.replace("\u201C", "``")
    # Right double quote (") -> '' (two single quotes)
    escaped = escaped.replace("\u201D", "''")
    # Left single quote (') -> ` (one backtick)
    escaped = escaped.replace("\u2018", "`")
    # Right single quote (') -> ' (one single quote)
    escaped = escaped.replace("\u2019", "'")
    # Also handle straight quotes that might be used incorrectly
    # This is a heuristic: if we see a quote followed by a space or punctuation, it's likely closing
    # But we'll be conservative and only handle the obvious Unicode cases above
    # Then escape other special characters
    for key, val in LATEX_ESCAPES.items():
            escaped = escaped.replace(key, val)
    return escaped


def clean_text_fragments(text: str) -> str:
    cleaned = ARTIFACT_TOKEN_REGEX.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def clean_text_node(text: str) -> str:
    """Normalize whitespace but keep leading/trailing spaces if they existed."""
    if not text:
        return ""
    leading = text[0].isspace()
    trailing = text[-1].isspace()
    cleaned = ARTIFACT_TOKEN_REGEX.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", cleaned)
    cleaned = cleaned.strip()
    # Remove "type=" artifacts that might have been missed if they were not word-bounded correctly or had spaces
    cleaned = re.sub(r"\btype=\s*", "", cleaned, flags=re.I)
    if leading and cleaned and not cleaned.startswith(" "):
        cleaned = " " + cleaned
    if trailing and cleaned and not cleaned.endswith(" "):
        cleaned = cleaned + " "
    return cleaned


def normalize_href(href: str, base_url: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("#"):
        return ""
    return urljoin(base_url, href)


def canonical_url(url: str) -> str:
    """Lowercase URL without fragment/trailing slash for stable comparisons."""
    parsed = urlparse(url)
    parsed = parsed._replace(fragment="")
    return parsed.geturl().rstrip("/").lower()
