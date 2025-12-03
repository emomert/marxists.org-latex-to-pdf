import sys
import os
import subprocess
import shutil
import urllib.request
import time

def check_latex():
    print("Checking for LaTeX (xelatex)...")
    if shutil.which("xelatex"):
        print("LaTeX is already installed!")
        return True
    return False

def install_with_winget():
    print("Attempting to install MiKTeX using Winget...")
    try:
        subprocess.run(["winget", "install", "MiKTeX.MiKTeX"], check=True)
        print("MiKTeX installed successfully via Winget.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Winget installation failed or winget is not available.")
        return False

def download_and_install_miktex():
    print("Downloading MiKTeX Basic Installer...")
    # URL for MiKTeX Basic Installer (Windows x64)
    # Using a reliable mirror or the main site redirect
    url = "https://miktex.org/download/ctan/systems/win32/miktex/setup/windows-x64/basic-miktex-24.4-x64.exe"
    installer_name = "basic-miktex-installer.exe"
    
    try:
        # Note: This URL might change. A more robust way would be to scrape the download page, 
        # but for a simple script, we'll try a direct link or ask user to download if it fails.
        # Let's try a generic redirect if possible, or just the latest known version.
        # Actually, let's use a safer approach: Open the download page if direct download fails.
        
        urllib.request.urlretrieve(url, installer_name)
        print(f"Downloaded {installer_name}.")
        
        print("Running installer...")
        subprocess.run([installer_name], check=True)
        print("Installation finished.")
        
        # Cleanup
        os.remove(installer_name)
        return True
    except Exception as e:
        print(f"Failed to download or install MiKTeX: {e}")
        print("Opening download page in browser...")
        os.startfile("https://miktex.org/download")
        return False

def main():
    print("--- Marxists Converter Prerequisites Installer ---")
    
    if check_latex():
        input("\nPress Enter to exit...")
        return

    print("\nLaTeX is required to convert documents to PDF.")
    print("We will attempt to install MiKTeX (a LaTeX distribution).")
    
    if not install_with_winget():
        print("\nWinget failed. Trying direct download...")
        if not download_and_install_miktex():
            print("\nCould not install automatically. Please install MiKTeX manually from https://miktex.org/download")
    
    print("\nAfter installation, you may need to restart your computer or the application.")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
