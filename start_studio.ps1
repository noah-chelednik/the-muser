<#
.SYNOPSIS
  Launch The Muser Studio (API + web UI) at http://127.0.0.1:8765
.PARAMETER Demo     Force demo mode (no LLM / models used).
.PARAMETER Port     Port (default 8765).
.PARAMETER Gradio   Also launch the original Gradio UI on http://localhost:7860
.PARAMETER NoBrowser Do not open the browser.
#>
param([switch]$Demo, [int]$Port = 8765, [switch]$Gradio, [switch]$NoBrowser)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$venvPy = "$Root\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Write-Host "No .venv found - running setup_windows.ps1 first..." -ForegroundColor Yellow
  & powershell -NoProfile -ExecutionPolicy Bypass -File "$Root\setup_windows.ps1"
}
if (-not (Test-Path "$Root\studio\web\dist\index.html")) {
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host "Building Studio web UI..." -ForegroundColor Cyan
    Push-Location "$Root\studio\web"; & npm install --no-audit --no-fund; & npm run build; Pop-Location
  } else {
    Write-Host "Web UI not built and Node.js is missing (winget install OpenJS.NodeJS.LTS)." -ForegroundColor Red
  }
}

# Missing-tool report
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host "[WARN] ffmpeg missing: mixdown/export disabled (winget install Gyan.FFmpeg)" -ForegroundColor Yellow }
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { Write-Host "[INFO] No NVIDIA GPU: audio generation uses the demo synthesizer." -ForegroundColor DarkYellow }

# Ollama: start it if installed but not running
if (-not $Demo -and (Get-Command ollama -ErrorAction SilentlyContinue)) {
  try { Invoke-RestMethod -Uri 'http://localhost:11434/api/version' -TimeoutSec 2 | Out-Null }
  catch {
    Write-Host "Starting Ollama (context 16384 - the 46-tool prompt needs ~12k tokens)..." -ForegroundColor Cyan
    if (-not $env:OLLAMA_CONTEXT_LENGTH) { $env:OLLAMA_CONTEXT_LENGTH = '16384' }
    Start-Process -WindowStyle Hidden ollama -ArgumentList 'serve'
    Start-Sleep -Seconds 3
  }
} elseif (-not $Demo) {
  Write-Host "[INFO] Ollama not installed: chat runs in DEMO mode (winget install Ollama.Ollama)." -ForegroundColor DarkYellow
}

if ($Gradio) {
  Write-Host "Launching original Gradio UI on http://localhost:7860" -ForegroundColor Cyan
  Start-Process -WindowStyle Minimized $venvPy -ArgumentList '-m', 'src.web.app'
}

$args2 = @('-m', 'studio.server', '--port', "$Port")
if ($Demo) { $args2 += '--demo' }
if (-not $NoBrowser) {
  Start-Job -ScriptBlock { param($p) Start-Sleep -Seconds 3; Start-Process "http://127.0.0.1:$p" } -ArgumentList $Port | Out-Null
}
Write-Host "`n  THE MUSER STUDIO -> http://127.0.0.1:$Port   (Ctrl+C to stop)`n" -ForegroundColor Yellow
& $venvPy @args2
