#!/usr/bin/env bash
# Launch The Muser Studio on Linux/macOS.  Usage: ./start_studio.sh [--demo] [--port 8765]
# First run installs the core audio tools. Add extras with e.g. MUSER_EXTRAS=separate,denoise
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -e ".[web,studio]"
  .venv/bin/python -m studio.server.engines.cli install --core ${MUSER_EXTRAS:+--extras "$MUSER_EXTRAS"}
  .venv/bin/python -m studio.server.engines.cli hardware
fi
if [ ! -f studio/web/dist/index.html ]; then
  (cd studio/web && npm install --no-audit --no-fund && npm run build)
fi
command -v ffmpeg >/dev/null || echo "[WARN] ffmpeg missing: mixdown/export disabled"
command -v nvidia-smi >/dev/null || echo "[INFO] no NVIDIA GPU: generation uses the demo synthesizer"
curl -s http://localhost:11434/api/version >/dev/null 2>&1 || echo "[INFO] Ollama not reachable: chat runs in demo mode (start with: OLLAMA_CONTEXT_LENGTH=16384 ollama serve)"
exec .venv/bin/python -m studio.server "$@"
