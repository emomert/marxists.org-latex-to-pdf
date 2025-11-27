import os
import re
import subprocess
from typing import List, Optional, Tuple, Dict
from .models import ArticleContent
from .utils import escape_latex
from .config import MAX_LATEX_LINE_LENGTH

def clean_latex_spacing(text: str) -> str:
    """
    Remove stray trailing/leading line-break commands around environments/headings
    that cause 'There's no line here to end' errors.
    """
    patterns = [
        (r"(\\begin\{quote\})\s*(\\\\\s*)+", r"\1\n"),
        (r"(\\end\{quote\})\s*(\\\\\s*)+", r"\1\n\n"),
        (r"(\\begin\{quoting\})\s*(\\\\\s*)+", r"\1\n"),
        (r"(\\end\{quoting\})\s*(\\\\\s*)+", r"\1\n\n"),
        (r"(\\subsection\*{[^}]+})\s*(\\\\\s*)+", r"\1\n\n"),
        (r"(\\subsubsection\*{[^}]+})\s*(\\\\\s*)+", r"\1\n\n"),
        (r"(\\section\*{[^}]+})\s*(\\\\\s*)+", r"\1\n\n"),
        (r"(\\paragraph\*{[^}]+}\\mbox\{\}\s*)\s*(\\\\\s*)+", r"\1\n\n"),
    ]
    cleaned = text
    for pat, repl in patterns:
        cleaned = re.sub(pat, repl, cleaned)
    # Collapse excessive backslash lines left alone (e.g., " \\\\ \\")
    cleaned = re.sub(r"(\\\\\s*){2,}", r"\\\\\n", cleaned)
    return cleaned


def break_long_lines(text: str, max_length: int = MAX_LATEX_LINE_LENGTH) -> str:
    """Break very long lines to avoid xelatex buffer overflow.
    
    XeLaTeX has a buffer limit of ~200,000 chars per line.
    We break lines at spaces when they exceed max_length.
    """
    lines = text.split('\n')
    result = []
    for line in lines:
        if len(line) <= max_length:
            result.append(line)
        else:
            # Break at spaces
            current = ""
            for word in line.split(' '):
                if len(current) + len(word) + 1 > max_length:
                    result.append(current)
                    current = word
                else:
                    current = current + " " + word if current else word
            if current:
                result.append(current)
    return '\n'.join(result)


def _latex_metadata_block(entries: List[Tuple[str, str]]) -> str:
    """
    Render a simple LaTeX metadata block.

    NOTE: Values are assumed to already be valid LaTeX fragments (they may
    contain \\href, escaped punctuation, etc.), so we only escape the label.
    """
    if not entries:
        return ""
    lines = []
    for label, value_latex in entries:
        lines.append(rf"\textbf{{{escape_latex(label)}:}} {value_latex}\\")
    return "\n".join(lines)


def build_latex_document(
    main_title: str,
    main_date: Optional[str],
    main_author: Optional[str],
    main_meta: List[Tuple[str, str]],
    chapters: List[ArticleContent],
    is_book: bool,
    toc_entries: Optional[List[Tuple[str, str]]] = None,
) -> str:
    
    latex_parts = [
        r"\documentclass[11pt,a4paper]{article}",
        r"",
        r"% Font setup",
        r"\usepackage{fontspec}",
        r"\setmainfont{FreeSerif}",
        r"\newfontfamily\greekfont{FreeSerif}",
        r"",
        r"% Page geometry - generous margins for readability",
        r"\usepackage{geometry}",
        r"\geometry{",
        r"  top=1.2in,",
        r"  bottom=1.2in,",
        r"  left=1.3in,",
        r"  right=1.3in,",
        r"  headheight=14pt",
        r"}",
        r"",
        r"% Headers and footers",
        r"\usepackage{fancyhdr}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyhead[L]{\small\textit{" + escape_latex(main_author or "Unknown") + r"}}",
        r"\fancyhead[R]{\small\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        r"\fancypagestyle{plain}{",
        r"  \fancyhf{}",
        r"  \fancyfoot[C]{\small\thepage}",
        r"  \renewcommand{\headrulewidth}{0pt}",
        r"}",
        r"",
        r"% Section formatting - elegant numbering",
        r"\usepackage{titlesec}",
        r"\titleformat{\section}",
        r"  {\Large\bfseries}",
        r"  {\thesection}{1em}{}",
        r"\titlespacing*{\section}{0pt}{2.5ex plus 1ex minus .2ex}{1.5ex plus .2ex}",
        r"\titleformat{\subsection}",
        r"  {\large\bfseries}",
        r"  {\thesubsection}{1em}{}",
        r"\titlespacing*{\subsection}{0pt}{2ex plus 1ex minus .2ex}{1ex plus .2ex}",
        r"\titleformat{\subsubsection}",
        r"  {\normalsize\bfseries\itshape}",
        r"  {\thesubsubsection}{1em}{}",
        r"",
        r"% Paragraph spacing",
        r"\usepackage{parskip}",
        r"\setlength{\parskip}{0.6em}",
        r"\setlength{\parindent}{0pt}",
        r"",
        r"% Other packages",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{longtable}",
        r"\usepackage{multirow}",
        r"\usepackage{enumitem}",
        r"\setlist[enumerate]{itemsep=0.3em, parsep=0.2em}",
        r"\setlist[itemize]{itemsep=0.3em, parsep=0.2em}",
        r"",
        r"% Endnotes",
        r"\usepackage{enotez}",
        r"\setenotez{list-name={Notes}, reset=true, backref=true}",
        r"",
        r"% Hyperlinks - subtle coloring",
        r"\usepackage{array}",
        r"\usepackage{xcolor}",
        r"\usepackage[colorlinks=true, linkcolor=blue!70!black, urlcolor=blue!60!black]{hyperref}",
        r"",
        r"% Table of Contents styling",
        r"\usepackage{titletoc}",
        r"\titlecontents{part}",
        r"  [0pt]",
        r"  {\addvspace{1em}\bfseries\large}",
        r"  {\contentslabel{0pt}}",
        r"  {}",
        r"  {\titlerule*[0.5pc]{.}\contentspage}",
        r"  [\addvspace{0.5em}]",
        r"\titlecontents{section}",
        r"  [1.5em]",
        r"  {\bfseries}",
        r"  {\contentslabel{0pt}}",
        r"  {}",
        r"  {\titlerule*[0.5pc]{.}\contentspage}",
        r"  [\addvspace{0.3em}]",
        r"\titlecontents{subsection}",
        r"  [3.8em]",
        r"  {}",
        r"  {\contentslabel{2em}}",
        r"  {}",
        r"  {\titlerule*[0.5pc]{.}\contentspage}",
        r"  [\addvspace{0.2em}]",
        r"",
        r"% Quotation styling",
        r"\usepackage{quoting}",
        r"\quotingsetup{vskip=0.5em, leftmargin=1.5em, rightmargin=1.5em}",
        r"",
        r"% Drop caps for first letter (optional flair)",
        r"% \usepackage{lettrine}",
        r"",
        r"\begin{document}",
        r"",
        r"% Title page",
        r"\thispagestyle{empty}",
        r"\vspace*{2cm}",
        r"\begin{center}",
        r"{\Huge\bfseries " + escape_latex(main_title) + r"}\\[1.5em]",
        r"{\Large " + escape_latex(main_author or "Unknown") + r"}\\[3em]",
        r"\end{center}",
        r"",
    ]

    # Add formatted metadata block with preserved links
    if main_meta:
        latex_parts.append(r"\vfill")
        latex_parts.append(r"\begin{center}")
        latex_parts.append(r"\begin{minipage}{0.8\textwidth}")
        latex_parts.append(r"\small")
        latex_parts.append(r"\hrule")
        latex_parts.append(r"\vspace{0.8em}")
        for label, value_latex in main_meta:
            latex_parts.append(r"\textbf{" + escape_latex(label) + r":} " + value_latex + r"\\[0.3em]")
        latex_parts.append(r"\vspace{0.5em}")
        latex_parts.append(r"\hrule")
        latex_parts.append(r"\end{minipage}")
        latex_parts.append(r"\end{center}")
    
    latex_parts.append(r"\newpage")
    latex_parts.append(r"")
    
    # Add table of contents page for books
    if is_book and chapters:
        latex_parts.append(r"\thispagestyle{empty}")
        latex_parts.append(r"\vspace*{2cm}")
        latex_parts.append(r"\begin{center}")
        latex_parts.append(r"{\Huge\bfseries Table of Contents}\\[2em]")
        latex_parts.append(r"\end{center}")
        latex_parts.append(r"\vspace{2em}")
        latex_parts.append(r"")
        latex_parts.append(r"\tableofcontents")
        latex_parts.append(r"\newpage")
        latex_parts.append(r"")

    if is_book:
        from .utils import canonical_url  # Import here to avoid circular dependency if possible, or move canonical_url to utils
        
        # Create mapping from chapters to TOC entries for proper titles
        toc_map: Dict[int, str] = {}  # chapter index -> TOC title
        if toc_entries:
            available_toc_entries = list(toc_entries)
            
            for idx, chap in enumerate(chapters):
                # Priority 1: Use toc_title that was set during scraping
                if chap.toc_title:
                    toc_map[idx] = chap.toc_title
                    for toc_text, toc_url in available_toc_entries[:]:
                        if toc_text == chap.toc_title:
                            available_toc_entries.remove((toc_text, toc_url))
                            break
                    continue
                
                # Priority 2: URL matching
                if chap.url:
                    chap_url_canon = canonical_url(chap.url)
                    for toc_text, toc_url in available_toc_entries:
                        toc_url_canon = canonical_url(toc_url)
                        if chap_url_canon == toc_url_canon:
                            toc_map[idx] = toc_text
                            available_toc_entries.remove((toc_text, toc_url))
                            break
                
                # Priority 3: Title matching
                if idx not in toc_map:
                    chap_title_normalized = chap.title.lower().strip()
                    for toc_text, toc_url in available_toc_entries:
                        toc_text_normalized = toc_text.lower().strip()
                        
                        if toc_text_normalized == chap_title_normalized:
                            toc_map[idx] = toc_text
                            available_toc_entries.remove((toc_text, toc_url))
                            break
                        toc_part = toc_text_normalized.replace("part", "").strip()
                        if toc_part == chap_title_normalized:
                            toc_map[idx] = toc_text
                            available_toc_entries.remove((toc_text, toc_url))
                            break
                        elif chap_title_normalized and len(chap_title_normalized) > 3:
                            if chap_title_normalized in toc_text_normalized:
                                if (toc_text_normalized.startswith(chap_title_normalized) or 
                                    f" {chap_title_normalized} " in f" {toc_text_normalized} " or
                                    toc_text_normalized.endswith(f" {chap_title_normalized}")):
                                    toc_map[idx] = toc_text
                                    available_toc_entries.remove((toc_text, toc_url))
                                    break
        
        current_part: Optional[str] = None
        for idx, chap in enumerate(chapters):
            if chap.part_title and chap.part_title != current_part:
                latex_parts.append(r"\vspace{1.5em}")
                part_title_escaped = escape_latex(chap.part_title)
                part_label = f"part:{idx}"
                latex_parts.append(rf"\phantomsection")
                latex_parts.append(rf"\hypertarget{{{part_label}}}{{}}")
                latex_parts.append(rf"\part*{{{part_title_escaped}}}")
                latex_parts.append(rf"\addcontentsline{{toc}}{{part}}{{{part_title_escaped}}}")
                latex_parts.append(r"\vspace{0.5em}")
                latex_parts.append(r"")
                current_part = chap.part_title

            display_title_raw = None
            if chap.toc_title and chap.toc_title.lower() != main_title.lower():
                display_title_raw = chap.toc_title
            elif toc_map.get(idx) and toc_map.get(idx).lower() != main_title.lower():
                display_title_raw = toc_map.get(idx)
            elif chap.title and chap.title.lower() != main_title.lower():
                display_title_raw = chap.title
            else:
                display_title_raw = chap.toc_title or toc_map.get(idx) or chap.title
            
            display_title = " ".join((display_title_raw or "").split()) or chap.title
            
            def strip_chapter_prefix(title: str) -> str:
                title_upper = title.upper()
                if title_upper.startswith("CHAPTER "):
                    title = title[8:].strip()
                title = re.sub(r"^([IVX]+)([A-Z])", r"\1. \2", title)
                return title
            
            display_title = strip_chapter_prefix(display_title)
            section_title = strip_chapter_prefix(" ".join(chap.title.split()))

            label = f"chap:{idx}"
            latex_parts.append(rf"\phantomsection")
            latex_parts.append(rf"\hypertarget{{{label}}}{{}}")

            section_title_escaped = escape_latex(section_title)
            toc_title_escaped = escape_latex(display_title)
            latex_parts.append(r"\section*{" + section_title_escaped + "}")
            latex_parts.append(rf"\addcontentsline{{toc}}{{section}}{{{toc_title_escaped}}}")
            
            if chap.meta_entries:
                latex_parts.append(_latex_metadata_block(chap.meta_entries))
            latex_parts.append(chap.latex_body)
            
            if r"\endnote{" in chap.latex_body:
                latex_parts.append(r"\printendnotes")
            latex_parts.append(r"")
    else:
        if chapters:
            chap = chapters[0]
            section_title = " ".join(chap.title.split())
            if section_title.upper().startswith("CHAPTER "):
                section_title = section_title[8:].strip()
                section_title = re.sub(r"^([IVX]+)([A-Z])", r"\1. \2", section_title)
            latex_parts.append(r"\section*{" + escape_latex(section_title) + "}")
            if chap.meta_entries:
                latex_parts.append(_latex_metadata_block(chap.meta_entries))
            latex_parts.append(chap.latex_body)
            if r"\endnote{" in chap.latex_body:
                latex_parts.append(r"\printendnotes")
    
    latex_parts.append("\\end{document}\n")
    return "\n".join(latex_parts)


def compile_pdf(tex_path: str, workdir: str, log_fn=print) -> Tuple[bool, str]:
    log_fn("Running xelatex (pass 1/3)...")
    cmd = ["xelatex", "-interaction=nonstopmode", os.path.basename(tex_path)]
    
    full_output = ""
    success = False
    
    for i in range(3):
        if i > 0:
            log_fn(f"Running xelatex (pass {i+1}/3)...")
        try:
            # Suppress console window on Windows
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            full_output += f"\n--- PASS {i+1} ---\n" + stdout + "\n" + stderr
            if proc.returncode != 0:
                tail = "\n".join((stdout + "\n" + stderr).splitlines()[-12:])
                log_fn(f"xelatex returned {proc.returncode}; tail of log:\n{tail}")
                success = False
                break
            success = True
        except FileNotFoundError:
            return False, "xelatex not found on system PATH."
    
    if success:
        log_fn("PDF compilation completed.")
    else:
        log_fn("xelatex failed; see log for details.")
    return success, full_output
