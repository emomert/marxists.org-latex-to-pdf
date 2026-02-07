# Marxists.org to PDF Converter

A tool to convert articles and books from [Marxists.org](https://www.marxists.org/) into clean PDF books.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Explanation Video

https://github.com/user-attachments/assets/a3a942c7-5416-4dfc-83e2-4ca332fc2ad0

## How to Use (Easiest Way)

1. Open the `release` folder.
2. Run `InstallPrerequisites.exe` first.
   - This checks whether LaTeX is installed.
   - If not, it helps install MiKTeX.
3. Restart your computer after LaTeX installation.
4. Run `MarxistsConverter.exe`.
5. Paste a Marxists.org URL (article or book index).
6. Click **Convert**.

The PDF will be created in a new output folder.

## Features

- One-click conversion from URL to PDF.
- Smart detection for article vs. multi-chapter book pages.
- Professional PDF formatting (TOC, fonts, spacing, endnotes).
- Footnote/endnote handling for most Marxists.org formats.
- Polite crawling with request delays.

## Troubleshooting

### "It says I don't have LaTeX/XeLaTeX"
Run `InstallPrerequisites.exe`. If that fails, install [MiKTeX](https://miktex.org/download) manually.

### "I installed MiKTeX but LaTeX is still not found"
Restart your computer so PATH changes are applied.

### "The PDF isn't generating"
- Confirm LaTeX is installed.
- Check internet connection.
- Large books can take longer.

### "It keeps asking to install packages (fonts/packages)"
This is normal with basic MiKTeX installs. Allow the package install prompts (or enable automatic installs in MiKTeX).

### "My antivirus flags the installer"
`InstallPrerequisites.exe` may trigger false positives because it downloads/install tools and is not code-signed.

### "I want to run from source code"
1. Install [Python 3.8+](https://www.python.org/downloads/).
2. In the project folder:
   ```bash
   pip install -r requirements.txt
   ```
3. Run:
   ```bash
   python run.py
   ```

## License

This project is licensed under the MIT License.
