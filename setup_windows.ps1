<#
.SYNOPSIS
  One-time setup for The Muser + NoDAW Labs Studio on Windows 10/11.

.DESCRIPTION
  Creates .venv, installs Python deps, installs + builds the Studio web UI,
  and checks for Ollama, ffmpeg and an NVIDIA GPU. Prints what is missing.

.PARAMETER Gpu
  Also install the CUDA build of PyTorch + the GPU/voice extras (needs an NVIDIA GPU).

.PARAMETER Voice
  Install Demucs (real stem separation) with CPU PyTorch. Ignored if -Gpu is given
  (the GPU install already includes it).

.PARAMETER Separate
  Also install audio-separator (best quality vocal and stem splitting, MIT models).

.PARAMETER Denoise
  Also install DeepFilterNet (AI noise and room removal for voice).

.PARAMETER Extras
  Install every optional engine (same as -Separate -Denoise plus Demucs).

.PARAMETER SkipCore
  Skip the core audio tools (Pedalboard, pyloudnorm, noisereduce, Basic Pitch,
  Matchering). Not recommended: Easy mode falls back to simpler built in DSP.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup_windows.ps1
  powershell -ExecutionPolicy Bypass -File setup_windows.ps1 -Separate -Denoise
  powershell -ExecutionPolicy Bypass -File setup_windows.ps1 -Extras
  powershell -ExecutionPolicy Bypass -File setup_windows.ps1 -Voice
  powershell -ExecutionPolicy Bypass -File setup_windows.ps1 -Gpu
#>
param(
  [switch]$Gpu,
  [switch]$Voice,
  [switch]$Separate,
  [switch]$Denoise,
  [switch]$Extras,
  [switch]$SkipCore
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$missing = New-Object System.Collections.Generic.List[string]

function Say($msg, $color = 'Gray') { Write-Host $msg -ForegroundColor $color }
function Ok($msg)   { Write-Host "  [ OK ] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Bad($msg)  { Write-Host "  [MISS] $msg" -ForegroundColor Red }
function Has($cmd)  { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

Say ""
Say "  NoDAW Labs // THE MUSER STUDIO - Windows setup" 'Yellow'
Say "  ------------------------------------------------" 'DarkYellow'

# ---------------------------------------------------------------- Python
Say "`n[1/7] Python" 'Cyan'
$py = $null
if (Has 'py') {
  foreach ($v in @('3.11', '3.12', '3.10')) {
    & py "-$v" -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = @('py', "-$v"); break }
  }
}
if (-not $py -and (Has 'python')) {
  $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
  if ($ver -in @('3.10', '3.11', '3.12')) { $py = @('python') }
  else { Warn "python on PATH is $ver; The Muser needs 3.10-3.12 (numpy<2 has no 3.13 wheels)." }
}
if (-not $py) {
  Bad "Python 3.10-3.12 not found."
  Say "        Install:  winget install Python.Python.3.11   (then reopen this window)" 'Yellow'
  exit 1
}
$pyExe = $py[0]; $pyArgs = @($py | Select-Object -Skip 1)
Ok ("Using " + ($py -join ' ') + " -> " + (& $pyExe @pyArgs --version))

if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
  Say "  Creating virtual environment .venv ..."
  & $pyExe @pyArgs -m venv .venv
}
$venvPy = "$Root\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip setuptools wheel --quiet

# ---------------------------------------------------------------- Python deps
Say "`n[2/7] Python packages" 'Cyan'
if ($Gpu) {
  Say "  Installing CUDA PyTorch (cu121) - large download ..."
  & $venvPy -m pip install "torch==2.5.1" "torchaudio==2.5.1" --index-url https://download.pytorch.org/whl/cu121
  & $venvPy -m pip install -e ".[web,studio,gpu,voice]"
} elseif ($Voice) {
  Say "  Installing CPU PyTorch + Demucs for real stem separation ..."
  & $venvPy -m pip install "torch==2.5.1" "torchaudio==2.5.1" --index-url https://download.pytorch.org/whl/cpu
  & $venvPy -m pip install -e ".[web,studio,voice]"
} else {
  & $venvPy -m pip install -e ".[web,studio]"
}
if ($LASTEXITCODE -ne 0) { Bad "pip install failed (see errors above)."; exit 1 }
Ok "Python packages installed"

# ---------------------------------------------------------------- Audio engines
Say "`n[3/7] Audio tools (engines)" 'Cyan'
$cli = @('-m', 'studio.server.engines.cli', 'install')
if (-not $SkipCore) { $cli += '--core' }
$ex = @()
if ($Extras) { $ex += 'optional' }
if ($Separate) { $ex += 'separate' }
if ($Denoise) { $ex += 'denoise' }
if ($ex.Count -gt 0) { $cli += @('--extras', ($ex -join ',')) }
if ($cli.Count -gt 3) {
  & $venvPy @cli
  Ok "Audio tools checked (anything that failed can be retried from Studio > Engines)"
} else {
  Warn "Core audio tools skipped (-SkipCore). The built in DSP fallbacks will be used."
}

if (-not (Test-Path "$Root\.env")) { Copy-Item "$Root\.env.example" "$Root\.env"; Ok "Created .env from .env.example" }

# ---------------------------------------------------------------- Node / web UI
Say "`n[4/7] Studio web UI (Node.js)" 'Cyan'
if (Has 'node') {
  $nodeVer = (& node --version).TrimStart('v')
  $parts = $nodeVer.Split('.') | ForEach-Object { [int]$_ }
  if ($parts[0] -lt 20 -or ($parts[0] -eq 20 -and $parts[1] -lt 19)) {
    Bad "Node $nodeVer is too old (need 20.19+ or 22+).  winget install OpenJS.NodeJS.LTS"
    $missing.Add('Node.js 20.19+ (winget install OpenJS.NodeJS.LTS)')
  } else {
    Ok "Node $nodeVer"
    Push-Location "$Root\studio\web"
    if (Test-Path 'package-lock.json') { & npm ci --no-audit --no-fund } else { & npm install --no-audit --no-fund }
    if ($LASTEXITCODE -ne 0) { Pop-Location; Bad "npm install failed"; exit 1 }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Bad "Web UI build failed"; exit 1 }
    Pop-Location
    Ok "Web UI built -> studio\web\dist"
  }
} else {
  Bad "Node.js not found - needed once to build the Studio UI."
  $missing.Add('Node.js 20.19+ (winget install OpenJS.NodeJS.LTS)')
}

# ---------------------------------------------------------------- System tools
Say "`n[5/7] System tools" 'Cyan'
if (Has 'ffmpeg') { Ok "ffmpeg found" } else {
  Bad "ffmpeg not found - needed for effects, mixdown and export."
  $missing.Add('ffmpeg (winget install Gyan.FFmpeg)')
}
if (Has 'ollama') {
  Ok "Ollama installed"
  try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 2
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names.Count -gt 0) { Ok ("Ollama running with models: " + ($names -join ', ')) }
    else { Warn "Ollama running but no models.  Run: ollama pull qwen3:8b   (or qwen3:30b-a3b with 24GB+ RAM/VRAM)" ; $missing.Add('an Ollama model (ollama pull qwen3:8b)') }
  } catch { Warn "Ollama installed but not running. start_studio will try 'ollama serve'." }
} else {
  Bad "Ollama not found - the AI agent (chat) needs it. Studio runs in DEMO mode without it."
  $missing.Add('Ollama (winget install Ollama.Ollama, then: ollama pull qwen3:8b)')
}

# The agent's system prompt + 46 tool schemas is ~12k tokens; Ollama's default
# context is smaller and recent Ollama versions reject over-long requests.
if (-not [Environment]::GetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', 'User')) {
  [Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', '16384', 'User')
  Ok "Set user env OLLAMA_CONTEXT_LENGTH=16384 (quit + restart Ollama from the tray to apply)"
}

# ---------------------------------------------------------------- GPU
Say "`n[6/7] GPU" 'Cyan'
if (Has 'nvidia-smi') {
  $gpu = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
  if ($gpu) {
    Ok "NVIDIA GPU: $gpu"
    $mib = [int](($gpu -split ',')[1] -replace '[^0-9]', '')
    if ($mib -lt 7000) { Warn "Under 8 GB VRAM: the Studio uses CPU-friendly tools; only small GPU models are offered." }
    elseif ($mib -lt 12000) {
      Ok "8 to 12 GB card: the Studio picks low-memory settings automatically (ACE-Step 1.5 turbo + 0.6B LM, offload, INT8)."
      Warn "Not recommended for this card: YuE (24 GB), SongGeneration (10 GB+), the original 24 GB full pipeline. The Engines panel marks them."
    }
    elseif ($mib -lt 20000) { Ok "12 to 20 GB card: most models fit; ACE-Step 1.5 runs with the 1.7B LM." }
    else { Ok "20 GB+ card: every model fits at full quality." }
    if (-not $Gpu) { Warn "Re-run with -Gpu to install CUDA PyTorch + model extras." }
  }
} else {
  Warn "No NVIDIA GPU detected (nvidia-smi missing). CPU = LLM orchestration + demo audio only."
}

# ---------------------------------------------------------------- Recommendation
Say "`n[7/7] Hardware check and model recommendations" 'Cyan'
& $venvPy -m studio.server.engines.cli hardware

# ---------------------------------------------------------------- Summary
Say "`n------------------------------------------------" 'DarkYellow'
if ($missing.Count -eq 0) { Say "  Setup complete. Launch with:  start_studio.bat" 'Green' }
else {
  Say "  Setup finished, but these are missing:" 'Yellow'
  $missing | ForEach-Object { Say "    - $_" 'Yellow' }
  Say "  The Studio still runs in DEMO mode. Launch with:  start_studio.bat" 'Green'
}
Say "  Heavy AI models install with one click from Studio > Engines. Guide: STUDIO_README.md" 'Gray'
Say ""
