import argparse
import os
import sys
import shutil
from datetime import datetime
from typing import List, Optional

from .scraper import MarxistsScraper, DEFAULT_REQUEST_DELAY
from .latex import build_latex_document, compile_pdf
from .utils import ensure_dir, output_basename_from_title
from .gui import App

def cli_main(argv: Optional[List[str]] = None) -> int:
    """
    Minimal CLI interface so the converter can be used without the GUI.

    Examples:
      python run.py --url https://www.marxists.org/... --output-dir ./out
    """
    parser = argparse.ArgumentParser(description="Marxists.org to LaTeX to PDF converter (CLI)")
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
        default=DEFAULT_REQUEST_DELAY,
        help=f"Seconds to sleep between HTTP requests (default: {DEFAULT_REQUEST_DELAY})",
    )
    parser.add_argument(
        "--allow-guessing",
        action="store_true",
        help="Enable chapter guessing when links are missing (may issue many HTTP requests).",
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
        converter = MarxistsScraper(
            log_fn,
            progress_fn,
            request_delay=args.delay,
            allow_guessing=args.allow_guessing,
        )
        log_fn(f"Analyzing {url}...")
        kind = converter.analyze_url(url)
        log_fn(f"Detected: {kind}")

        if kind == "book":
            title, date, author, meta_entries, chapters, toc_entries = converter.scrape_book(url, output_dir)
            latex = build_latex_document(title, date, author, meta_entries, chapters, is_book=True, toc_entries=toc_entries)
            base_name = output_basename_from_title(title)
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
            base_name = output_basename_from_title(chapter.title)
        
        tex_path = os.path.join(output_dir, f"{base_name}.tex")
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
                pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
                log_fn(f"PDF created: {pdf_path}")
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
