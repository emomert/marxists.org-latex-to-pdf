import argparse
import os
import sys
import shutil
from datetime import datetime
from typing import List, Optional

from .scraper import MarxistsScraper
from .latex import build_latex_document, compile_pdf
from .utils import ensure_dir
from .gui import App

def cli_main(argv: Optional[List[str]] = None) -> int:
    """
    Minimal CLI interface so the converter can be used without the GUI.

    Examples:
      python run.py --url https://www.marxists.org/... --output-dir ./out
    """
    parser = argparse.ArgumentParser(description="Marxists.org → LaTeX → PDF converter (CLI)")
    parser.add_argument("--url", required=True, help="Marxists.org article or index URL")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: creates output_YYYYMMDD_HHMMSS in current dir)",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Stop after writing output.tex (do not run xelatex)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to sleep between HTTP requests (default: 0)",
    )
    args = parser.parse_args(argv)

    def log_fn(msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")

    def progress_fn(value: float, text: str) -> None:
        pct = int(value * 100)
        print(f"[{pct:3d}%] {text}")

    url = args.url
    output_dir = args.output_dir
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.getcwd(), f"output_{timestamp}")
    
    ensure_dir(output_dir)
    images_dir = os.path.join(output_dir, "images")
    ensure_dir(images_dir)

    try:
        converter = MarxistsScraper(log_fn, progress_fn, request_delay=args.delay)
        log_fn(f"Analyzing {url}...")
        kind = converter.analyze_url(url)
        log_fn(f"Detected: {kind}")

        if kind == "book":
            title, date, author, meta_entries, chapters, toc_entries = converter.scrape_book(url, output_dir)
            latex = build_latex_document(title, date, author, meta_entries, chapters, is_book=True, toc_entries=toc_entries)
        else:
            chapter = converter.scrape_article(url, images_dir)
            latex = build_latex_document(
                chapter.title,
                chapter.date,
                chapter.author,
                chapter.meta_entries,
                [chapter],
                is_book=False,
            )
        
        tex_path = os.path.join(output_dir, "output.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex)
        log_fn(f"LaTeX written to {tex_path}")

        if args.no_pdf:
            log_fn("Skipping PDF compilation.")
        else:
            log_fn("Compiling PDF...")
            success, latex_log = compile_pdf(tex_path, output_dir, log_fn=log_fn)
            log_path = os.path.join(output_dir, "xelatex.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(latex_log)
            
            if success:
                log_fn(f"PDF created: {os.path.join(output_dir, 'output.pdf')}")
            else:
                log_fn("PDF compilation failed. See xelatex.log.")
                return 1

    except Exception as exc:
        log_fn(f"Error: {exc}")
        # Cleanup if empty or failed? Maybe keep for debugging.
        return 1

    return 0

def main() -> None:
    if len(sys.argv) > 1:
        sys.exit(cli_main())
    else:
        app = App()
        app.mainloop()
