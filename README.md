# Marxists.org to PDF Converter

A powerful, user-friendly tool to scrape articles and books from [Marxists.org](https://www.marxists.org/) and convert them into professional, book-quality PDF documents using LaTeX.

![Application Screenshot](https://via.placeholder.com/800x500?text=Application+Screenshot+Placeholder)

## ✨ Features

-   **📖 Book & Article Support**: Automatically detects whether a URL is a single article or a full book index and scrapes accordingly.
-   **📄 Professional PDFs**: Generates high-quality PDFs with proper typography, margins, and headers using XeLaTeX.
-   **📑 Table of Contents**: Automatically generates a clickable Table of Contents for books.
-   **🔗 Smart Linking**: Preserves internal links and footnotes/endnotes from the original text.
-   **🖼️ Modern UI**: Clean, dark-themed user interface built with `customtkinter`.
-   **⚡ Standalone**: Available as a single executable file—no Python installation required for end users.

---

## 📥 How to Use (For Users)

### 1. Prerequisites
To generate PDFs, this application relies on **XeLaTeX**. You must have a TeX distribution installed on your computer.

-   **Windows**: Install [MiKTeX](https://miktex.org/download) (Recommended) or [TeX Live](https://www.tug.org/texlive/).
    -   *Tip*: During MiKTeX installation, select **"Install missing packages on-the-fly"**. This allows the app to automatically download any necessary LaTeX packages (like `enotez`, `titlesec`, etc.) the first time you run a conversion.

### 2. Download & Run
1.  Download the latest `MarxistsConverter.exe` from the [Releases page](#) (or check the `dist` folder if you built it yourself).
2.  Double-click `MarxistsConverter.exe` to launch the application.

### 3. Convert a Document
1.  **Copy a URL** from Marxists.org (e.g., a specific work like *The State and Revolution* or a single article).
2.  **Paste the URL** into the application.
3.  Click **"Analyze URL"** to see what the app detects (Book or Article).
4.  Click **"Convert & Compile"**.
5.  Wait for the process to finish. The app will scrape the content, generate LaTeX, and compile the PDF.
6.  Click **"Open Output Folder"** to find your new PDF!

---

## 💻 Development (For Developers)

If you want to modify the source code or build the executable yourself, follow these steps.

### Requirements
-   Python 3.8+
-   XeLaTeX (in your system PATH)

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/marxist-org-to-latex.git
    cd marxist-org-to-latex
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**:
    ```bash
    python run.py
    ```

### Building the Executable
To create the standalone `.exe` file:

```bash
python -m PyInstaller --noconfirm --onefile --windowed --name "MarxistsConverter" --add-data "src;src" --collect-all customtkinter run.py
```
The output will be in the `dist/` folder.

---

## 🔧 Troubleshooting

**"xelatex not found"**
-   Ensure you have installed MiKTeX or TeX Live.
-   Restart your computer or terminal after installation to update your system PATH.

**Font errors / "Font not found"**
-   The application uses **FreeSerif**. This is standard in most TeX distributions.
-   If missing, install the **GNU FreeFont** family on your system.

**Console window appears during PDF creation**
-   This issue has been fixed in the latest version. If you are running from source, ensure you have the latest `src/latex.py`.

---

## 📄 License

[MIT License](LICENSE) - Feel free to use and modify this code.
