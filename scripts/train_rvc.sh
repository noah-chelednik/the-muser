#!/usr/bin/env bash
# RVC voice model training script using Applio
# Full pipeline: preprocess → extract → train → index → export
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== RVC Voice Training (Applio) ==="
echo ""

VOICE_NAME="${1:-}"
EPOCHS="${2:-300}"
BATCH_SIZE="${3:-8}"
SAMPLE_RATE="${4:-48000}"
F0_METHOD="${5:-rmvpe}"

if [ -z "$VOICE_NAME" ]; then
    echo "Usage: $0 <voice_name> [epochs] [batch_size] [sample_rate] [f0_method]"
    echo ""
    echo "Arguments:"
    echo "  voice_name    Name for the voice model (required)"
    echo "  epochs        Training epochs (default: 300)"
    echo "  batch_size    Batch size (default: 8, reduce to 4 for 6GB VRAM)"
    echo "  sample_rate   Sample rate: 32000, 40000, 48000 (default: 48000)"
    echo "  f0_method     Pitch extraction: rmvpe, crepe, fcpe (default: rmvpe)"
    echo ""
    echo "Example:"
    echo "  $0 noah 300 8"
    echo "  $0 noah-fem 200 4 48000 crepe"
    exit 1
fi

APPLIO_DIR="$PROJECT_ROOT/models/applio"
TRAINING_DATA="$PROJECT_ROOT/training_data/processed/segments"
VOICES_DIR="$PROJECT_ROOT/voices"
DATASET_DIR="$APPLIO_DIR/datasets/$VOICE_NAME"

# Validate prerequisites
if [ ! -d "$APPLIO_DIR" ]; then
    echo "Error: Applio not found at $APPLIO_DIR"
    echo "Clone it: git clone --depth 1 https://github.com/IAHispano/Applio.git $APPLIO_DIR"
    exit 1
fi

if [ ! -d "$TRAINING_DATA" ] || [ -z "$(ls -A "$TRAINING_DATA"/*.wav 2>/dev/null)" ]; then
    echo "Error: No WAV files found in $TRAINING_DATA"
    echo "Run scripts/preprocess_voice.py first to prepare training segments."
    exit 1
fi

echo "Voice:       $VOICE_NAME"
echo "Epochs:      $EPOCHS"
echo "Batch size:  $BATCH_SIZE"
echo "Sample rate: $SAMPLE_RATE"
echo "F0 method:   $F0_METHOD"
echo ""

# Step 1: Copy training data to Applio dataset directory
echo "--- Step 1/5: Copying training data ---"
mkdir -p "$DATASET_DIR"
cp "$TRAINING_DATA"/*.wav "$DATASET_DIR/"
WAV_COUNT=$(ls -1 "$DATASET_DIR"/*.wav 2>/dev/null | wc -l)
echo "Copied $WAV_COUNT WAV files to $DATASET_DIR"
echo ""

# Step 2: Preprocess dataset
echo "--- Step 2/5: Preprocessing ---"
cd "$APPLIO_DIR"
python core.py preprocess \
    --model_name "$VOICE_NAME" \
    --dataset_path "$DATASET_DIR" \
    --sample_rate "$SAMPLE_RATE" \
    --cut_preprocess "Automatic" \
    --noise_reduction true \
    --noise_reduction_strength 0.5 \
    --chunk_len 3.0 \
    --overlap_len 0.3
echo "Preprocessing complete."
echo ""

# Step 3: Extract features (pitch + embeddings)
echo "--- Step 3/5: Extracting features ---"
python core.py extract \
    --model_name "$VOICE_NAME" \
    --f0_method "$F0_METHOD" \
    --sample_rate "$SAMPLE_RATE" \
    --embedder_model "contentvec" \
    --include_mutes 2 \
    --gpu "0"
echo "Feature extraction complete."
echo ""

# Step 4: Train model
echo "--- Step 4/5: Training ($EPOCHS epochs) ---"
python core.py train \
    --model_name "$VOICE_NAME" \
    --total_epoch "$EPOCHS" \
    --batch_size "$BATCH_SIZE" \
    --sample_rate "$SAMPLE_RATE" \
    --gpu "0" \
    --pretrained true \
    --save_every_epoch 50 \
    --save_only_latest false \
    --save_every_weights true \
    --overtraining_detector true \
    --overtraining_threshold 50 \
    --vocoder "HiFi-GAN" \
    --index_algorithm "Auto"
echo "Training complete."
echo ""

# Step 5: Export model and index to voices directory
echo "--- Step 5/5: Exporting to voices/ ---"
mkdir -p "$VOICES_DIR"

# Find the latest .pth model file
LOGS_DIR="$APPLIO_DIR/logs/$VOICE_NAME"
LATEST_PTH=$(find "$LOGS_DIR" -name "*.pth" -not -name "D_*.pth" -not -name "G_*.pth" | sort -V | tail -1)
LATEST_INDEX=$(find "$LOGS_DIR" -name "*.index" | sort | tail -1)

if [ -z "$LATEST_PTH" ]; then
    echo "Warning: No .pth model found in $LOGS_DIR"
    echo "Check training logs for errors."
    exit 1
fi

cp "$LATEST_PTH" "$VOICES_DIR/${VOICE_NAME}.pth"
echo "Model exported: $VOICES_DIR/${VOICE_NAME}.pth"

if [ -n "$LATEST_INDEX" ]; then
    cp "$LATEST_INDEX" "$VOICES_DIR/${VOICE_NAME}.index"
    echo "Index exported: $VOICES_DIR/${VOICE_NAME}.index"
fi

# Register in voice registry
python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from src.voice.voice_registry import register_voice
register_voice(
    voice_id='$VOICE_NAME',
    name='$VOICE_NAME',
    model_type='rvc',
    model_path='$VOICES_DIR/${VOICE_NAME}.pth',
    index_path='$VOICES_DIR/${VOICE_NAME}.index' if '$LATEST_INDEX' else '',
    metadata={
        'epochs': $EPOCHS,
        'batch_size': $BATCH_SIZE,
        'sample_rate': $SAMPLE_RATE,
        'f0_method': '$F0_METHOD',
    },
)
print('Voice registered: $VOICE_NAME')
"

echo ""
echo "=== Training Complete ==="
echo "Model: $VOICES_DIR/${VOICE_NAME}.pth"
echo "Use with: muser --voice $VOICE_NAME"
