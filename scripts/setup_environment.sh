#!/usr/bin/env bash
# The Muser environment setup script
# Installs tools locally (no sudo required), creates Python venv, installs deps
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCAL_DIR="$PROJECT_ROOT/.local"

echo "=== The Muser Environment Setup ==="
echo "Project root: $PROJECT_ROOT"

mkdir -p "$LOCAL_DIR/bin"

# ---------------------------------------------------------------------------
# 1. Ollama (CPU-only LLM server)
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing Ollama ---"
if [ -x "$LOCAL_DIR/bin/ollama" ]; then
    echo "Ollama already installed: $("$LOCAL_DIR/bin/ollama" --version 2>&1 || true)"
else
    echo "Downloading Ollama..."
    OLLAMA_URL="https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst"
    TMP_FILE=$(mktemp)
    curl -L "$OLLAMA_URL" -o "$TMP_FILE"
    if command -v zstd >/dev/null 2>&1; then
        TMP_TAR=$(mktemp)
        zstd -d "$TMP_FILE" -o "$TMP_TAR"
        tar xf "$TMP_TAR" -C "$LOCAL_DIR/"
        rm "$TMP_TAR"
    else
        echo "ERROR: zstd is required to extract Ollama. Install it with:"
        echo "  conda install -c conda-forge zstd"
        rm "$TMP_FILE"
        exit 1
    fi
    rm "$TMP_FILE"
    echo "Ollama installed: $("$LOCAL_DIR/bin/ollama" --version 2>&1 || true)"
fi

# ---------------------------------------------------------------------------
# 2. FluidSynth (via conda-forge)
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing FluidSynth ---"
if [ -x "$LOCAL_DIR/bin/fluidsynth" ]; then
    echo "FluidSynth already installed: $("$LOCAL_DIR/bin/fluidsynth" --version 2>&1 | head -1)"
else
    CONDA_BIN=$(command -v conda 2>/dev/null || find /mnt/ai_workspace -name "conda" -type f 2>/dev/null | head -1)
    if [ -n "$CONDA_BIN" ]; then
        echo "Installing FluidSynth via conda..."
        "$CONDA_BIN" install -y -c conda-forge fluidsynth --prefix "$LOCAL_DIR" 2>&1 | tail -5
    else
        echo "WARNING: conda not found. Install FluidSynth manually:"
        echo "  sudo apt-get install fluidsynth"
    fi
fi

# ---------------------------------------------------------------------------
# 3. LilyPond (pre-built binary from GitLab)
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing LilyPond ---"
LILYPOND_BIN=$(find "$LOCAL_DIR" -maxdepth 2 -name "lilypond" -type f 2>/dev/null | head -1)
if [ -n "$LILYPOND_BIN" ]; then
    echo "LilyPond already installed: $("$LILYPOND_BIN" --version 2>&1 | head -1)"
else
    echo "Downloading LilyPond 2.24.4..."
    LILYPOND_URL="https://gitlab.com/lilypond/lilypond/-/releases/v2.24.4/downloads/lilypond-2.24.4-linux-x86_64.tar.gz"
    TMP_FILE=$(mktemp)
    curl -L "$LILYPOND_URL" -o "$TMP_FILE"
    tar xzf "$TMP_FILE" -C "$LOCAL_DIR/"
    rm "$TMP_FILE"
    LILYPOND_BIN=$(find "$LOCAL_DIR" -maxdepth 2 -name "lilypond" -type f 2>/dev/null | head -1)
    echo "LilyPond installed: $("$LILYPOND_BIN" --version 2>&1 | head -1)"
fi

# ---------------------------------------------------------------------------
# 4. Soundfonts
# ---------------------------------------------------------------------------
echo ""
echo "--- Downloading soundfonts ---"
SF_DIR="$PROJECT_ROOT/soundfonts"
mkdir -p "$SF_DIR"

if [ -f "$SF_DIR/FluidR3_GM.sf2" ]; then
    echo "FluidR3_GM.sf2 already present ($(du -h "$SF_DIR/FluidR3_GM.sf2" | cut -f1))"
else
    echo "Downloading FluidR3_GM.sf2 (~142 MB)..."
    curl -L "https://sourceforge.net/projects/androidframe/files/soundfonts/FluidR3_GM.sf2/download" \
        -o "$SF_DIR/FluidR3_GM.sf2"
    echo "Downloaded: $(du -h "$SF_DIR/FluidR3_GM.sf2" | cut -f1)"
fi

# ---------------------------------------------------------------------------
# 5. Python virtual environment
# ---------------------------------------------------------------------------
echo ""
echo "--- Setting up Python virtual environment ---"
VENV_DIR="$PROJECT_ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Created venv at $VENV_DIR"
else
    echo "Venv already exists at $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "--- Installing Python dependencies ---"
pip install --upgrade pip setuptools wheel
pip install -e "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# 6. Pull Ollama model
# ---------------------------------------------------------------------------
echo ""
echo "--- Pulling Ollama model ---"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"

# Start Ollama server temporarily if not running
STARTED_OLLAMA=false
if ! curl -s "$OLLAMA_HOST/api/version" >/dev/null 2>&1; then
    echo "Starting temporary Ollama server..."
    CUDA_VISIBLE_DEVICES=-1 "$LOCAL_DIR/bin/ollama" serve > /dev/null 2>&1 &
    OLLAMA_PID=$!
    STARTED_OLLAMA=true
    sleep 3
fi

echo "Pulling qwen3:30b-a3b (this may take a while on first run)..."
"$LOCAL_DIR/bin/ollama" pull qwen3:30b-a3b

if [ "$STARTED_OLLAMA" = true ]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 7. Verify
# ---------------------------------------------------------------------------
echo ""
echo "--- Verifying installation ---"
python3 -c "import litellm; print('litellm OK')"
python3 -c "import pydantic; print(f'pydantic {pydantic.__version__}')"
python3 -c "import music21; print(f'music21 OK')"
"$LOCAL_DIR/bin/fluidsynth" --version 2>&1 | head -1 || echo "fluidsynth: not found"
"$LILYPOND_BIN" --version 2>&1 | head -1 || echo "lilypond: not found"
ffmpeg -version 2>&1 | head -1 || echo "ffmpeg: not found"

echo ""
echo "=== The Muser environment setup complete ==="
echo ""
echo "To start The Muser:"
echo "  bash scripts/start_muser.sh"
echo ""
echo "Or manually:"
echo "  source .venv/bin/activate"
echo "  export PATH=\"$LOCAL_DIR/bin:\$PATH\""
echo "  python -m src.cli"
