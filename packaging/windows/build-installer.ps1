# Build The Muser Windows desktop app and a full Inno Setup installer.
# Requires: Node.js, Python 3.10+, Inno Setup Compiler (ISCC.exe in PATH)
# Run from the repo root:  .\packaging\windows\build-installer.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $Root

Write-Host "Building web UI..." -ForegroundColor Cyan
Push-Location studio/web
if (Test-Path package-lock.json) { npm ci } else { npm install }
npm run build
Pop-Location

Write-Host "Bundling desktop app with PyInstaller..." -ForegroundColor Cyan
python -m pip install --disable-pip-version-check -q pyinstaller
python -m PyInstaller packaging\muser.spec --noconfirm

Write-Host "Compiling Inno Setup installer..." -ForegroundColor Cyan
$Iss = "$Root\packaging\windows\muser.iss"
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
  $guess = @(
    "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($guess) { $iscc = $guess }
}

if ($iscc) {
  & $iscc "/DAppVersion=1.1.0" $Iss
  Write-Host "Installer written to dist/installer/TheMuser-Setup-1.1.0-win64.exe" -ForegroundColor Green
} else {
  Write-Host "Inno Setup Compiler (iscc) not found. Install from https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
  Write-Host "PyInstaller output is at dist/TheMuser/. Compile packaging/windows/muser.iss after installing Inno Setup." -ForegroundColor Yellow
}
