$ErrorActionPreference = "Stop"

Write-Host "Building MarxistsConverter..." -ForegroundColor Cyan
python -m PyInstaller --noconfirm --onefile --windowed --name "MarxistsConverter" --hidden-import "customtkinter" --collect-all "customtkinter" run.py

Write-Host "Building InstallPrerequisites..." -ForegroundColor Cyan
python -m PyInstaller --noconfirm --onefile --console --name "InstallPrerequisites" install_prerequisites.py

Write-Host "Moving executables to root..." -ForegroundColor Cyan
Move-Item -Path "dist\MarxistsConverter.exe" -Destination ".\MarxistsConverter.exe" -Force
Move-Item -Path "dist\InstallPrerequisites.exe" -Destination ".\InstallPrerequisites.exe" -Force

Write-Host "Cleaning up build artifacts..." -ForegroundColor Cyan
Remove-Item -Path "build" -Recurse -Force
Remove-Item -Path "dist" -Recurse -Force
Remove-Item -Path "*.spec" -Force

Write-Host "Build complete! Executables are in the root directory." -ForegroundColor Green
