#!/usr/bin/env bash
# The Muser model setup script
# Clones model repos and downloads weights from HuggingFace
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$PROJECT_ROOT/models"
SOUNDFONTS_DIR="$PROJECT_ROOT/soundfonts"

echo "=== The Muser Model Setup ==="

# ---------------------------------------------------------------------------
# 1. NotaGen — Symbolic music generation
# ---------------------------------------------------------------------------
echo ""
echo "--- Cloning NotaGen ---"
if [ ! -d "$MODELS_DIR/notagen/.git" ]; then
    git clone https://github.com/ElectricAlexis/NotaGen.git "$MODELS_DIR/notagen"
else
    echo "NotaGen already cloned, pulling latest..."
    git -C "$MODELS_DIR/notagen" pull
fi

echo "Downloading NotaGen weights (RL3-tuned, ~6.2 GB)..."
python3 -c "
from huggingface_hub import hf_hub_download
import os
out = os.path.join('$MODELS_DIR', 'notagen', 'weights')
os.makedirs(out, exist_ok=True)
# Download the best checkpoint (pretrain + finetune + RL3)
src = 'weights_notagen_pretrain-finetune-RL3_beta_0.1_lambda_10_p_size_16_p_length_1024_p_layers_20_c_layers_6_h_size_1280_lr_1e-06_batch_1.pth'
hf_hub_download('ElectricAlexis/NotaGen', src, local_dir=out)
# Create convenience symlink so model_manager finds it easily
dst = os.path.join(out, 'notagen.pth')
if not os.path.exists(dst):
    os.symlink(src, dst)
print('NotaGen weights downloaded.')
" 2>/dev/null || echo "Warning: Could not download NotaGen weights (install huggingface_hub)"

# Verify weights
if ls "$MODELS_DIR/notagen/weights/"*.pth 1>/dev/null 2>&1; then
    echo "NotaGen weights verified."
else
    echo "Warning: No .pth files found in $MODELS_DIR/notagen/weights/"
fi

# ---------------------------------------------------------------------------
# 2. ACE-Step v1.5 — Text-to-audio generation
# ---------------------------------------------------------------------------
echo ""
echo "--- Cloning ACE-Step ---"
if [ ! -d "$MODELS_DIR/ace-step/.git" ]; then
    git clone https://github.com/ACE-Step/ACE-Step.git "$MODELS_DIR/ace-step"
else
    echo "ACE-Step already cloned, pulling latest..."
    git -C "$MODELS_DIR/ace-step" pull
fi

# ---------------------------------------------------------------------------
# 3. DiffSinger — Singing voice synthesis
# ---------------------------------------------------------------------------
echo ""
echo "--- Cloning DiffSinger ---"
if [ ! -d "$MODELS_DIR/diffsinger/.git" ]; then
    git clone https://github.com/openvpi/DiffSinger.git "$MODELS_DIR/diffsinger"
else
    echo "DiffSinger already cloned, pulling latest..."
    git -C "$MODELS_DIR/diffsinger" pull
fi

# ---------------------------------------------------------------------------
# 4. Applio — RVC voice conversion
# ---------------------------------------------------------------------------
echo ""
echo "--- Cloning Applio ---"
if [ ! -d "$MODELS_DIR/applio/.git" ]; then
    git clone https://github.com/IAHispano/Applio.git "$MODELS_DIR/applio"
else
    echo "Applio already cloned, pulling latest..."
    git -C "$MODELS_DIR/applio" pull
fi

# ---------------------------------------------------------------------------
# 5. Demucs — Source separation
# ---------------------------------------------------------------------------
echo ""
echo "--- Setting up Demucs ---"
# Demucs is installed via pip; models download on first use
python3 -c "
try:
    import demucs
    print(f'Demucs installed: {demucs.__version__}')
except ImportError:
    print('Demucs not installed. Install with: pip install demucs')
"

# ---------------------------------------------------------------------------
# 6. Soundfonts
# ---------------------------------------------------------------------------
echo ""
echo "--- Downloading soundfonts ---"
mkdir -p "$SOUNDFONTS_DIR"

# FluidR3_GM
if [ ! -f "$SOUNDFONTS_DIR/FluidR3_GM.sf2" ]; then
    echo "Downloading FluidR3_GM.sf2..."
    wget -q -O "$SOUNDFONTS_DIR/FluidR3_GM.sf2" \
        "https://keymusician01.s3.amazonaws.com/FluidR3_GM.sf2" \
        2>/dev/null || echo "Warning: Could not download FluidR3_GM.sf2"
else
    echo "FluidR3_GM.sf2 already present"
fi

# GeneralUser GS
if [ ! -f "$SOUNDFONTS_DIR/GeneralUser_GS.sf2" ]; then
    echo "Downloading GeneralUser_GS.sf2..."
    wget -q -O "$SOUNDFONTS_DIR/GeneralUser_GS.sf2" \
        "https://storage.googleapis.com/google-code-archive-downloads/v2/code.google.com/generaluser-gs/GeneralUser_GS_v1.47.sf2" \
        2>/dev/null || echo "Warning: Could not download GeneralUser_GS.sf2"
else
    echo "GeneralUser_GS.sf2 already present"
fi

# Sonatina Symphonic Orchestra (SFZ)
if [ ! -d "$SOUNDFONTS_DIR/sonatina-sso" ]; then
    echo "Note: Sonatina Symphonic Orchestra must be downloaded manually."
    echo "Place SFZ files in: $SOUNDFONTS_DIR/sonatina-sso/"
    mkdir -p "$SOUNDFONTS_DIR/sonatina-sso"
fi

echo ""
echo "=== The Muser model setup complete ==="
echo "Models directory: $MODELS_DIR"
echo "Soundfonts directory: $SOUNDFONTS_DIR"
