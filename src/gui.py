import os
import sys
import shutil
import threading
import subprocess
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from .scraper import MarxistsScraper
from .latex import build_latex_document, compile_pdf
from .utils import ensure_dir, output_basename_from_title

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title("Marxists.org to LaTeX Converter")
        self.geometry("960x700")
        self.resizable(True, True)
        self.converter: Optional[MarxistsScraper] = None
        self.worker: Optional[threading.Thread] = None
        self.output_dir: Optional[str] = None
        self.skip_pdf_var = ctk.BooleanVar(value=False)
        self._build_ui()

    # ---- UI helpers ----
    def _build_ui(self) -> None:
        # Configure main window grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Main container frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(4, weight=1)  # Log area expands

        # ---- Header Section ----
        header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        
        hero_font = ctk.CTkFont(size=24, weight="bold")
        sub_font = ctk.CTkFont(size=14)
        
        self.hero_label = ctk.CTkLabel(header_frame, text="Marxists.org to PDF Converter", font=hero_font)
        self.hero_label.pack(anchor="w")
        
        self.sub_label = ctk.CTkLabel(
            header_frame,
            text="Convert articles or books to clean LaTeX and PDF documents.",
            font=sub_font,
            text_color="gray70"
        )
        self.sub_label.pack(anchor="w", pady=(5, 0))

        # ---- Input Section ----
        input_frame = ctk.CTkFrame(self.main_frame)
        input_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(input_frame, placeholder_text="Paste Marxists.org URL here...", height=40)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(15, 10), pady=15)

        self.analyze_btn = ctk.CTkButton(input_frame, text="Analyze URL", command=self.on_analyze, height=40, width=120)
        self.analyze_btn.grid(row=0, column=1, sticky="e", padx=(0, 15), pady=15)

        # ---- Options & Actions Section ----
        action_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        action_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        action_frame.grid_columnconfigure(1, weight=1) # Spacer

        self.skip_pdf_checkbox = ctk.CTkCheckBox(
            action_frame,
            text="Skip PDF compilation (LaTeX only)",
            variable=self.skip_pdf_var,
        )
        self.skip_pdf_checkbox.grid(row=0, column=0, sticky="w")

        self.open_btn = ctk.CTkButton(action_frame, text="Open Output Folder", command=self.on_open_folder, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"))
        self.open_btn.grid(row=0, column=2, sticky="e", padx=(0, 10))

        self.convert_btn = ctk.CTkButton(action_frame, text="Convert & Compile", command=self.on_convert, font=ctk.CTkFont(weight="bold"), height=35)
        self.convert_btn.grid(row=0, column=3, sticky="e")

        # ---- Status & Progress Section ----
        status_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        status_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 5))
        status_frame.grid_columnconfigure(1, weight=1)

        self.status_label = ctk.CTkLabel(status_frame, text="Ready", font=ctk.CTkFont(size=12, weight="bold"))
        self.status_label.grid(row=0, column=0, sticky="w")

        self.progress = ctk.CTkProgressBar(status_frame)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        # ---- Log Section ----
        self.log_text = ctk.CTkTextbox(self.main_frame, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self.log_text.grid(row=4, column=0, sticky="nsew", padx=20, pady=(5, 20))
        self.log_text.configure(state="disabled")

    def log(self, message: str) -> None:
        def _append() -> None:
            self.log_text.configure(state="normal")
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{timestamp}] {message}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        self.after(0, _append)

    def set_progress(self, value: float, text: str) -> None:
        value = max(0.0, min(1.0, value))
        def _update() -> None:
            self.progress.set(value)
            self.status_label.configure(text=text)
        self.after(0, _update)

    def _disable_buttons(self) -> None:
        for btn in (self.analyze_btn, self.convert_btn):
            btn.configure(state="disabled")

    def _enable_buttons(self) -> None:
        for btn in (self.analyze_btn, self.convert_btn):
            btn.configure(state="normal")

    # ---- button callbacks ----
    def on_analyze(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self.log("Please enter a URL.")
            return
        if self.worker and self.worker.is_alive():
            self.log("Another task is running.")
            return
        self._disable_buttons()
        self.worker = threading.Thread(target=self._analyze_worker, args=(url,), daemon=True)
        self.worker.start()

    def _analyze_worker(self, url: str) -> None:
        try:
            converter = MarxistsScraper(self.log, self.set_progress)
            kind = converter.analyze_url(url)
            self.set_progress(0, f"Detected: {'Book index' if kind == 'book' else 'Single article'}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Analyze failed: {exc}")
            self.set_progress(0, "Idle")
        finally:
            self.after(0, self._enable_buttons)

    def on_convert(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self.log("Please enter a URL.")
            return
        if self.worker and self.worker.is_alive():
            self.log("Another task is running.")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = os.path.join(os.getcwd(), f"output_{timestamp}")
        ensure_dir(self.output_dir)
        self._disable_buttons()
        self.worker = threading.Thread(target=self._convert_worker, args=(url,), daemon=True)
        self.worker.start()

    def _convert_worker(self, url: str) -> None:
        converter = MarxistsScraper(self.log, self.set_progress)
        images_dir = os.path.join(self.output_dir, "images")
        ensure_dir(images_dir)
        try:
            self.set_progress(0.02, "Analyzing URL...")
            kind = converter.analyze_url(url)
            self.log(f"Detected {'book index' if kind == 'book' else 'single article'}")
            if kind == "book":
                title, date, author, meta_entries, chapters, toc_entries = converter.scrape_book(url, self.output_dir)
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
            tex_path = os.path.join(self.output_dir, f"{base_name}.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex)
            self.log(f"LaTeX written to {tex_path}")
            if self.skip_pdf_var.get():
                self.set_progress(1.0, "Done (PDF skipped)")
                self.log("Skipped PDF compilation (checkbox enabled).")
            else:
                self.set_progress(0.9, "Compiling with xelatex...")
                success, latex_log = compile_pdf(tex_path, self.output_dir, log_fn=self.log)
                log_path = os.path.join(self.output_dir, "xelatex.log")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(latex_log)
                if success:
                    self.set_progress(1.0, "Done")
                    pdf_path = os.path.join(self.output_dir, f"{base_name}.pdf")
                    self.log(f"PDF created: {pdf_path}")
                else:
                    self.set_progress(0.0, "xelatex failed")
                    self.log("xelatex failed; see xelatex.log in output folder.")
        except Exception as exc:  # noqa: BLE001
            self.set_progress(0, "Failed")
            self.log(f"Conversion failed: {exc}")
            shutil.rmtree(self.output_dir, ignore_errors=True)
            self.output_dir = None
        finally:
            self.after(0, self._enable_buttons)

    def on_open_folder(self) -> None:
        if not self.output_dir or not os.path.isdir(self.output_dir):
            self.log("No output folder yet.")
            return
        if sys.platform.startswith("win"):
            os.startfile(self.output_dir)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.output_dir])
        else:
            subprocess.Popen(["xdg-open", self.output_dir])
