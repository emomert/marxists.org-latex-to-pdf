import sys
import os
import subprocess
import shutil
import urllib.request
import time


def add_common_miktex_paths_to_env():
    """
    After installing MiKTeX, the PATH in the current process is often stale.
    Add the typical install locations so we can immediately find the CLI tools.
    """
    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")

    for base in (local_app_data, program_files, program_files_x86):
        if not base:
            continue
        candidates.extend(
            [
                os.path.join(base, "Programs", "MiKTeX", "miktex", "bin", "x64"),
                os.path.join(base, "MiKTeX", "miktex", "bin", "x64"),
                os.path.join(base, "MiKTeX 2.9", "miktex", "bin", "x64"),
            ]
        )

    for path in candidates:
        if os.path.isdir(path) and path not in os.environ.get("PATH", ""):
            os.environ["PATH"] += os.pathsep + path

def check_latex():
    print("Checking for LaTeX (xelatex)...")
    add_common_miktex_paths_to_env()
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
        # Fonts and engine support
        "fontspec",
        "gnu-freefont",  # Provides FreeSerif used in the templates
        # Formatting/layout
        "titlesec",
        "fancyhdr",
        "geometry",
        "parskip",
        "titletoc",
        # Tables, figures, lists
        "array",
        "float",
        "longtable",
        "multirow",
        "enumitem",
        "graphicx",
        # Links/notes/quoting
        "xcolor",
        "hyperref",
        "enotez",
        "quoting",
    ]
    
    # Find mpm (MiKTeX Package Manager) or miktex CLI
    miktex_cmd = "miktex"
    mpm_cmd = "mpm"
    use_miktex_cli = False

    add_common_miktex_paths_to_env()
    initexmf_cmd = shutil.which("initexmf")

    if shutil.which(miktex_cmd):
        use_miktex_cli = True
        print(f"Found MiKTeX CLI: {miktex_cmd}")
    elif shutil.which(mpm_cmd):
        print(f"Found Legacy MPM: {mpm_cmd}")
    else:
        # Try to find miktex tools in common install locations (user or machine)
        search_paths = []
        for base in (
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
        ):
            if not base:
                continue
            search_paths.extend(
                [
                    os.path.join(base, "Programs", "MiKTeX", "miktex", "bin", "x64"),
                    os.path.join(base, "MiKTeX", "miktex", "bin", "x64"),
                    os.path.join(base, "MiKTeX 2.9", "miktex", "bin", "x64"),
                ]
            )

        for path in search_paths:
            candidate_miktex = os.path.join(path, "miktex.exe")
            candidate_mpm = os.path.join(path, "mpm.exe")
            if os.path.exists(candidate_miktex):
                miktex_cmd = candidate_miktex
                use_miktex_cli = True
                os.environ["PATH"] += os.pathsep + path
                break
            if os.path.exists(candidate_mpm):
                mpm_cmd = candidate_mpm
                os.environ["PATH"] += os.pathsep + path
                break

        mpm_available = use_miktex_cli or shutil.which(mpm_cmd) or os.path.exists(mpm_cmd)
        if not mpm_available:
            print("Could not find MiKTeX tools. Skipping package installation.")
            return

    # Update package database first!
    print("Updating package database (this is critical)...")
    try:
        if use_miktex_cli:
            # 1. Update package database
            subprocess.run([miktex_cmd, "packages", "update-package-database"], check=False)
            
            # 2. Check for updates (required by MiKTeX logic)
            print("Checking for updates...")
            subprocess.run([miktex_cmd, "packages", "check-update"], check=False)
            
            # 3. Apply updates (required to fix 'miktex-maketfm' error)
            print("Applying critical updates...")
            subprocess.run([miktex_cmd, "packages", "update"], check=False)
        else:
            subprocess.run([mpm_cmd, "--update-db"], check=False)
            # Legacy mpm doesn't have easy 'update all' without admin, but update-db is usually enough
    except Exception as e:
        print(f"Warning: Could not update package database: {e}")

    # Allow on-the-fly installs if anything is still missing later
    if initexmf_cmd:
        try:
            subprocess.run([initexmf_cmd, "--set-config-value=[MPM]AutoInstall=1"], check=False)
        except Exception as e:
            print(f"Warning: Could not enable AutoInstall: {e}")

    for pkg in packages:
        print(f"Installing package: {pkg}...")
        try:
            if use_miktex_cli:
                subprocess.run([miktex_cmd, "packages", "install", pkg], check=False)
            else:
                subprocess.run([mpm_cmd, "--install", pkg], check=False)
        except Exception as e:
            print(f"Warning: Could not install {pkg}: {e}")

    print("Updating font maps...")
    try:
        if use_miktex_cli:
            subprocess.run([miktex_cmd, "fndb", "refresh"], check=False)
            subprocess.run([miktex_cmd, "fontmaps", "refresh"], check=False)
        else:
            initexmf_cmd = initexmf_cmd or "initexmf"
            if not shutil.which(initexmf_cmd) and shutil.which(mpm_cmd):
                initexmf_cmd = os.path.join(os.path.dirname(mpm_cmd), "initexmf.exe")

            subprocess.run([initexmf_cmd, "--update-fndb"], check=False)
            subprocess.run([initexmf_cmd, "--mkmaps"], check=False)
        print("Packages and fonts updated successfully!")
    except Exception as e:
        print(f"Warning: Could not update font maps: {e}")

if __name__ == "__main__":
    main()
