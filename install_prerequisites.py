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
    
    # Attempt to install packages even if we didn't just install MiKTeX (in case they are missing)
    install_latex_packages()
    
    input("\nPress Enter to exit...")

def install_latex_packages():
    print("\n--- Checking/Installing Required LaTeX Packages ---")
    print("This prevents 'missing font' errors.")
    
    # Packages used in latex.py
    packages = [
        "gnu-free-fonts", # Fixes miktex-maketfm error
        "titlesec", "fancyhdr", "geometry", "fontspec", "xcolor", "hyperref",
        "enumitem", "multirow", "longtable", "float", "graphicx", "enotez",
        "quoting", "parskip", "titletoc", "uucharclasses"
    ]
    
    # Find mpm (MiKTeX Package Manager)
    mpm_cmd = "mpm"
    if not shutil.which(mpm_cmd):
        # Check default user install location if not in PATH
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Programs", "MiKTeX", "miktex", "bin", "x64", "mpm.exe")
        if os.path.exists(candidate):
            mpm_cmd = candidate
            # Also add to PATH for this process so other commands work
            os.environ["PATH"] += os.pathsep + os.path.dirname(candidate)
        else:
            print("Could not find MiKTeX Package Manager (mpm). Skipping package installation.")
            print("You may need to restart this installer after MiKTeX finishes installing.")
            return

    for pkg in packages:
        print(f"Installing package: {pkg}...")
        try:
            # --install installs the package
            subprocess.run([mpm_cmd, "--install", pkg], check=False, capture_output=False)
        except Exception as e:
            print(f"Warning: Could not install {pkg}. It might already be installed or network failed.")

    print("Updating font maps...")
    try:
        initexmf_cmd = "initexmf"
        if not shutil.which(initexmf_cmd) and shutil.which(mpm_cmd):
             initexmf_cmd = os.path.join(os.path.dirname(mpm_cmd), "initexmf.exe")
        
        subprocess.run([initexmf_cmd, "--update-fndb"], check=False)
        subprocess.run([initexmf_cmd, "--mkmaps"], check=False)
        print("Packages and fonts updated successfully!")
    except Exception as e:
        print(f"Warning: Could not update font maps: {e}")

if __name__ == "__main__":
    main()
