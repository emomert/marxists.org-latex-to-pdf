import re

# Maximum footnote length to prevent xelatex buffer overflow
MAX_FOOTNOTE_LENGTH = 50000

# Maximum line length for LaTeX (xelatex buffer limit is ~200k, we use 10k for safety)
MAX_LATEX_LINE_LENGTH = 10000

# Minimum text length to consider as a footnote (filters out empty/short noise)
MIN_FOOTNOTE_TEXT_LENGTH = 10

LATEX_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Matches headings like "Part I: Commodities and Money"
PART_HEADING_RE = re.compile(r"^\s*Part\s+[IVXLC]+\s*:\s*(.+)$", re.I)

ARTIFACT_TOKEN_REGEX = re.compile(
    r"\b(?:t2h-[a-z0-9_-]+|vol=\d+|pg=\d+|src=\S+|type=endnote|type=ENDNOTE|type=)\b",
    re.I,
)
