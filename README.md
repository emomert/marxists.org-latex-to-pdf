# Marxists.org to PDF Converter

A simple tool to turn articles and books from [Marxists.org](https://www.marxists.org/) into professional, readable PDF books.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## 🚀 How to Use (Easiest Way)

1.  **Download** the latest release.
2.  **Run `InstallPrerequisites.exe`** first.
    *   This checks if you have LaTeX installed (needed to create PDFs).
    *   If not, it will help you install it automatically.
3.  **Run `MarxistsConverter.exe`**.
4.  **Paste a URL** from Marxists.org (e.g., an article or a book index).
5.  Click **Convert**.

That's it! The PDF will appear in a new folder.

---

## ✨ Features

*   **One-Click Conversion**: Just paste a link and go.
*   **Smart Detection**: Works with single articles or entire books (automatically finds chapters).
*   **Professional Quality**: Creates high-quality PDFs with proper fonts, table of contents, and formatting.
*   **Endnotes**: Automatically handles footnotes and endnotes so links work perfectly.
*   **Safe**: Polite crawling that respects the website's servers.

## 🛠️ Troubleshooting

### "It says I don't have LaTeX/XeLaTeX"
Run the included `InstallPrerequisites.exe` file. It will try to install MiKTeX for you. If that fails, download and install [MiKTeX](https://miktex.org/download) manually.

### "The PDF isn't generating"
*   Make sure you installed LaTeX (see above).
*   Check your internet connection.
*   If a book is very large, it might take a while.

### "I want to run from source code"
If you are a developer, you can run the Python code directly:
1.  Install Python 3.8+.
2.  Install dependencies: `pip install -r requirements.txt`
3.  Run: `python run.py`

## 📄 License
This project is licensed under the MIT License.

