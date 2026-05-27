#!/usr/bin/env bash
# Start The Muser in CPU-only mode.
#
# This script:
#   1. Adds local tool binaries to PATH (.local/bin, .local/lilypond-*/bin)
#   2. Activates the Python venv
#   3. Starts Ollama in CPU-only mode (if not already running)
#   4. Launches the CLI
#
# Usage:
#   bash scripts/start_muser.sh [-- any CLI args]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# 1. PATH — local tool binaries
# ---------------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PROJECT_ROOT/.local/bin:$PATH"
export LD_LIBRARY_PATH="${HOME}/.local/lib/ollama:${LD_LIBRARY_PATH:-}"

# LilyPond (versioned directory)
LILYPOND_BIN=$(find "$PROJECT_ROOT/.local" -maxdepth 2 -name "lilypond" -type f 2>/dev/null | head -1)
if [ -n "$LILYPOND_BIN" ]; then
    export PATH="$(dirname "$LILYPOND_BIN"):$PATH"
fi

# ---------------------------------------------------------------------------
# 2. Activate Python venv
# ---------------------------------------------------------------------------
VENV_DIR="$PROJECT_ROOT/.venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "ERROR: Python venv not found at $VENV_DIR"
    echo "Run: python3 -m venv $VENV_DIR && pip install -e $PROJECT_ROOT"
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Start Ollama in CPU-only mode (if not already running)
# ---------------------------------------------------------------------------
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"

if ! curl -s "$OLLAMA_HOST/api/version" >/dev/null 2>&1; then
    echo "Starting Ollama server (CPU-only)..."
    CUDA_VISIBLE_DEVICES=-1 ollama serve \
        > "$PROJECT_ROOT/.local/ollama.log" 2>&1 &
    OLLAMA_PID=$!
    echo "Ollama PID: $OLLAMA_PID"

    # Wait for server to be ready
    for i in $(seq 1 15); do
        if curl -s "$OLLAMA_HOST/api/version" >/dev/null 2>&1; then
            echo "Ollama server ready."
            break
        fi
        sleep 1
    done

    if ! curl -s "$OLLAMA_HOST/api/version" >/dev/null 2>&1; then
        echo "WARNING: Ollama server did not start within 15 seconds."
        echo "Check logs at: $PROJECT_ROOT/.local/ollama.log"
    fi
else
    echo "Ollama server already running at $OLLAMA_HOST"
fi

# ---------------------------------------------------------------------------
# 4. Launch The Muser CLI
# ---------------------------------------------------------------------------
echo ""
echo "=== The Muser ==="

# Forward any extra CLI arguments
exec python -m src.cli "$@"
