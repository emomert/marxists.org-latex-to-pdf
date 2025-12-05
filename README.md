# Marxists.org to PDF Converter

A simple tool to turn articles and books from [Marxists.org](https://www.marxists.org/) into professional, readable PDF books.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Explanation Video

https://github.com/user-attachments/assets/a3a942c7-5416-4dfc-83e2-4ca332fc2ad0

Sorry for the quality of the video, the limit was 10 MB for the free plan 😥


## 🚀 How to Use (Easiest Way)

1.  **Download** the latest release.
2.  **Run `InstallPrerequisites.exe`** first.
    *   This checks if you have LaTeX installed (needed to create PDFs).
    *   If not, it will help you install it automatically.
3.  **Restart your computer** after the installation completes.
4.  **Run `MarxistsConverter.exe`**.
5.  **Paste a URL** from Marxists.org (e.g., an article or a book index).
6.  Click **Convert**.

That's it! The PDF will appear in a new folder.

---

## ✨ Features

*   **One-Click Conversion**: Just paste a link and go.
*   **Smart Detection**: Works with single articles or entire books (automatically finds chapters).
*   **Professional Quality**: Creates high-quality PDFs with proper fonts, table of contents, and formatting.
*   **Endnotes**: Automatically handles footnotes and endnotes so links work perfectly. (Sometimes it can't detect them if the article has both endnote and footnote)
*   **Safe**: Polite crawling that respects the website's servers.

## 🛠️ Troubleshooting

### "It says I don't have LaTeX/XeLaTeX"
Run the included `InstallPrerequisites.exe` file. It will try to install MiKTeX for you. If that fails, download and install [MiKTeX](https://miktex.org/download) manually.

### "I installed MiKTeX but it still says LaTeX is not found"
**Restart your computer.** After installing MiKTeX, your system needs to refresh its PATH environment variables. A restart ensures the converter can find the LaTeX tools.

### "The PDF isn't generating"
*   Make sure you installed LaTeX (see above).
*   Check your internet connection.
*   If a book is very large, it might take a while.

### "It keeps asking to install packages (e.g., levy-font, B.mf)"
**This is normal!**
*   To keep the download small, we installed the "Basic" version of MiKTeX.
*   When you create a PDF for the first time, it needs to download some fonts and packages.
*   **Solution**: Just click **Install**.
*   **Tip**: You can uncheck "Always show this dialog" so it installs them automatically in the future without asking.

### "My antivirus says the file is a virus!"
**Don't worry, this is a False Positive.**
*   The `InstallPrerequisites.exe` file is a simple script that downloads MiKTeX (the PDF tool) from the internet.
*   Because it downloads and installs software, and because it is not "digitally signed" (which costs hundreds of dollars), some antiviruses flag it as suspicious.
*   **The code is open source.** You can check `install_prerequisites.py` to see exactly what it does.
*   **Alternative**: If you prefer, you can install [MiKTeX](https://miktex.org/download) manually and then run the converter.

### "I want to run from source code"
If you don't trust the `.exe` files or are a developer, you can run the Python code directly:
1.  Install [Python 3.8+](https://www.python.org/downloads/).
2.  Open a terminal in the project folder.
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the app:
    ```bash
    python run.py
    ```

## 📄 License
This project is licensed under the MIT License.

