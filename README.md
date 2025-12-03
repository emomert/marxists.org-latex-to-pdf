# Marxists.org to PDF Converter

A Python application to scrape articles and book indexes from [Marxists.org](https://www.marxists.org/) and convert them into clean, professional LaTeX/PDF documents using XeLaTeX. Available as a desktop GUI application or command-line tool.

## Features

- **Smart Detection**: Automatically detects single articles vs. multi-chapter books and builds appropriate table of contents
- **Content Cleaning**: Removes navigation elements, cleans up HTML artifacts, and formats content for professional LaTeX output
- **Footnote Handling**: Converts footnotes to endnotes with proper linking, including manual footnote references (e.g., `[1]`)
- **Poetry Support**: Preserves line breaks and formatting for poetry and verse blocks in tables
- **Professional PDFs**: Generates high-quality PDFs with FreeSerif fonts, proper typography, and elegant formatting (titlesec/fancyhdr)
- **Polite Crawling**: Default 0.35s delay between requests to avoid overwhelming the server
- **Flexible Options**: Skip PDF compilation to get only LaTeX files, or enable chapter-guessing for incomplete indexes
- **Standalone Executable**: Available as a portable Windows executable (no Python installation required)
- **Multiple Interfaces**: Desktop GUI (CustomTkinter) or command-line interface

## Installation

### Prerequisites

1. **Python 3.8 or higher** (if running from source)
   - Download from [python.org](https://www.python.org/downloads/)
   - Ensure Python is added to your system PATH

2. **TeX Distribution with XeLaTeX**
   - **Windows**: [MiKTeX](https://miktex.org/download) (recommended)
     - During installation, enable "Auto-install missing packages"
     - Ensure `xelatex` is available in your PATH
   - **Linux**: TeX Live
     ```bash
     sudo apt-get install texlive-xetex texlive-fonts-recommended
     ```
   - **macOS**: MacTeX or BasicTeX
     ```bash
     brew install --cask basictex
     sudo tlmgr update --self
     sudo tlmgr install xetex
     ```

3. **GNU FreeFont** (FreeSerif) - Usually included with TeX distributions

### Option 1: Using the Standalone Executable (Windows)

1. Download `MarxistsConverter.exe` from the [Releases](https://github.com/yourusername/marxist-org-to-latex/releases) page
2. Download the entire `dist` folder containing `MarxistsConverter.exe` and `_internal` folder
3. Ensure both are in the same directory
4. Double-click `MarxistsConverter.exe` to run

**Note**: The `_internal` folder is required - do not delete it. It contains necessary DLL files.

### Option 2: Running from Source

#### Quick Start (Windows PowerShell)

The easiest way to get started on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

This script will:
- Create a virtual environment (`.venv`)
- Install required dependencies
- Check for XeLaTeX
- Launch the application

**Flags**:
- `-UseGlobalPython`: Skip virtual environment creation
- `-SkipInstall`: Skip dependency installation

#### Manual Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/yourusername/marxist-org-to-latex.git
   cd marxist-org-to-latex
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv .venv
   
   # Windows
   .venv\Scripts\activate
   
   # Linux/macOS
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Verify XeLaTeX is available:
   ```bash
   xelatex --version
   ```

## Usage

### GUI Mode

Launch the application:

```bash
python run.py
```

The GUI will open. Then:

1. Paste a Marxists.org URL into the input field
2. Click **Analyze URL** to verify the URL and detect the content type
3. (Optional) Check "Skip PDF compilation" if you only want LaTeX files
4. Click **Convert & Compile** to start the conversion
5. Wait for the process to complete
6. Click **Open Output Folder** to view the generated PDF

Output files are saved in a timestamped directory: `output_YYYYMMDD_HHMMSS/`

### Command-Line Interface

```bash
python run.py --url <URL> [OPTIONS]
```

**Required argument**:
- `--url`: Marxists.org article or book index URL

**Optional arguments**:
- `--output-dir <DIR>`: Custom output directory (default: creates `output_YYYYMMDD_HHMMSS` in current directory)
- `--no-pdf`: Generate LaTeX file only, skip PDF compilation
- `--delay <SECONDS>`: Delay between HTTP requests in seconds (default: 0.35)
- `--allow-guessing`: Enable chapter-guessing when links are missing (may issue many extra HTTP requests)

**Examples**:

```bash
# Convert a single article to PDF
python run.py --url https://www.marxists.org/archive/malatesta/1889/a-revolt-is-no-revolution.html

# Convert a book index, skip PDF compilation
python run.py --url https://www.marxists.org/archive/lafargue/index.htm --no-pdf

# Custom output directory with longer delay
python run.py --url https://www.marxists.org/archive/marx/works/1867-c1/index.htm --output-dir ./my-output --delay 0.5

# Enable chapter guessing for incomplete indexes
python run.py --url https://www.marxists.org/archive/some-book/index.htm --allow-guessing
```

## Building the Executable

To create a standalone executable for Windows:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

2. Build using the spec file:
   ```bash
   python -m PyInstaller --noconfirm --clean MarxistsConverter.spec
   ```

3. The executable will be in `dist\MarxistsConverter.exe` along with the required DLLs in `dist\_internal\`

**Note**: The directory-based approach (using `_internal` folder) is more reliable than a single-file executable, especially with Python 3.12, and avoids DLL loading issues.

## Known Issues and Limitations

### Content Accuracy

- **Table of Contents Names**: In some cases, chapter names in the table of contents may be slightly different from the actual chapter titles. This is due to variations in how Marxists.org structures their indexes. The table of contents is generated from the index page, and sometimes the link text doesn't exactly match the chapter heading.
- **Footnote Placement**: Some footnotes may appear in slightly different positions than on the original webpage. This can happen when:
  - Footnotes are referenced multiple times in the text
  - Manual footnote references (like `[1]`) don't perfectly match the extracted footnotes
  - Footnotes are in complex table structures or nested elements

These are known limitations of automated conversion and may require manual editing of the generated LaTeX file if perfect accuracy is needed.

### Technical Limitations

- **Large Books**: Very large books (100+ chapters) may take a long time to process. Consider using `--delay` to increase the request delay.
- **Complex HTML**: Some pages with unusual HTML structures may not convert perfectly.
- **Images**: Images are not downloaded or included in the PDF output.

### Workarounds

- If a footnote reference doesn't work, check the `xelatex.log` file in the output directory for warnings
- For books with many chapters, use `--no-pdf` first to generate LaTeX, then compile separately to debug issues
- If table of contents names are wrong, you can manually edit the `.tex` file before compiling

## Troubleshooting

### "xelatex not found" error

**Solution**: 
- Ensure MiKTeX/TeX Live is installed
- Verify `xelatex` is in your system PATH
- Restart your terminal/command prompt after installation

**Verify installation**:
```bash
xelatex --version
```

### "Failed to load Python DLL" error (Windows executable)

**Solution**:
- Ensure you have both `MarxistsConverter.exe` and the `_internal` folder in the same directory
- Do not delete or move the `_internal` folder - it contains essential DLL files
- If the error persists, try installing [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- Make sure you're running the executable from `dist\MarxistsConverter.exe`, not from a nested folder

### Fonts missing or PDF compilation fails

**Solution**:
- Install GNU FreeFont (FreeSerif) - usually included with TeX distributions
- For MiKTeX: Missing packages should auto-install. If not, install manually:
  - Open MiKTeX Console
  - Go to Packages → Search "FreeSerif"
  - Install the package
- Check `xelatex.log` for specific missing font errors

### Footnotes missing or not linking correctly

**Solution**:
- Check the `xelatex.log` file in the output directory for warnings about unmatched footnotes
- Some footnotes may not match if they're in unusual formats on the webpage
- Manual footnote references like `[1]` should work, but may occasionally fail if the numbering doesn't match exactly
- If footnotes are missing, they may not have been extracted from the HTML properly - check the original webpage structure

### Application crashes or freezes

**Solution**:
- For large books, increase the delay: `--delay 1.0`
- Check your internet connection - the app needs to fetch pages from Marxists.org
- Ensure sufficient disk space in the output directory
- Check the console/log for error messages
- Try running with `--no-pdf` first to isolate whether the issue is with scraping or PDF compilation

### Module not found errors (when running from source)

**Solution**:
- Ensure virtual environment is activated (check your prompt shows `(.venv)`)
- Reinstall dependencies: `pip install -r requirements.txt`
- Check that you're running from the project root directory
- Verify all files in `src/` directory are present

### Characters appear garbled in PDF

**Solution**:
- Ensure UTF-8 encoding is properly handled (the app should handle this automatically)
- Check that XeLaTeX (not pdfLaTeX) is being used for compilation
- Verify your TeX distribution supports the characters being used

## Development

### Requirements

- Python 3.8+
- XeLaTeX on PATH
- All dependencies in `requirements.txt`

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/marxist-org-to-latex.git
cd marxist-org-to-latex

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m unittest discover -s tests
```

### Project Structure

```
marxist-org-to-latex/
├── src/
│   ├── scraper.py      # Web scraping and content extraction
│   ├── latex.py        # LaTeX document generation
│   ├── gui.py          # Desktop GUI (CustomTkinter)
│   ├── main.py         # CLI interface
│   ├── models.py       # Data models
│   ├── utils.py        # Utility functions
│   └── config.py       # Configuration
├── tests/
│   └── test_scraper.py # Unit tests
├── dist/               # Built executable (after building)
├── run.py              # Entry point
├── start.ps1           # Windows quick start script
├── requirements.txt    # Python dependencies
├── MarxistsConverter.spec  # PyInstaller configuration
└── README.md           # This file
```

### Running Tests

```bash
python -m unittest discover -s tests
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Marxists.org](https://www.marxists.org/) for providing the content
- BeautifulSoup4 for HTML parsing
- CustomTkinter for the modern GUI
- The LaTeX community for excellent typesetting tools
