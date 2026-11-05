# Build NoDAW Studio PRO Windows installer
# Requires: Node.js, Python, Inno Setup Compiler (ISCC.exe in PATH)
# Run from repo root: .\packaging\windows\build-installer.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $Root

Write-Host "Building web UI..." -ForegroundColor Cyan
Push-Location studio/web
npm ci
npm run build
Pop-Location

Write-Host "Preparing dist folder for installer..." -ForegroundColor Cyan
$Dist = "$Root\packaging\windows\dist"
if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
New-Item -ItemType Directory -Path $Dist | Out-Null

# Copy built UI and a launcher stub
Copy-Item -Recurse studio/web/dist/* $Dist
Copy-Item start_studio.bat $Dist
Copy-Item start_studio.ps1 $Dist

# Minimal launcher exe placeholder note (replace with real Electron/PyInstaller binary)
@"
@echo off
cd /d "%~dp0"
start_studio.bat
"@ | Set-Content "$Dist\NoDAWStudio.bat"

Write-Host "Compiling Inno Setup installer..." -ForegroundColor Cyan
$Iss = "$Root\packaging\windows\nodaw-studio.iss"
if (Get-Command iscc -ErrorAction SilentlyContinue) {
  iscc $Iss
  Write-Host "Installer written to packaging/windows/Output/" -ForegroundColor Green
} else {
  Write-Host "Inno Setup Compiler (iscc) not found. Install from https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
  Write-Host "Then re-run this script." -ForegroundColor Yellow
}

Write-Host "Done." -ForegroundColor Green
