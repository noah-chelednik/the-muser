#!/usr/bin/env bash
# ACE-Step LoRA voice training script
# Full pipeline: prepare data → create LoRA config → train → export
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== ACE-Step LoRA Voice Training ==="
echo ""

VOICE_NAME="${1:-}"
MAX_STEPS="${2:-5000}"
RANK="${3:-32}"
LEARNING_RATE="${4:-0.0001}"

if [ -z "$VOICE_NAME" ]; then
    echo "Usage: $0 <voice_name> [max_steps] [rank] [learning_rate]"
    echo ""
    echo "Arguments:"
    echo "  voice_name       Name for the LoRA adapter (required)"
    echo "  max_steps        Training steps (default: 5000)"
    echo "  rank             LoRA rank (default: 32, lower=less overfitting)"
    echo "  learning_rate    Learning rate (default: 0.0001)"
    echo ""
    echo "Prerequisites:"
    echo "  1. Full song recordings in: training_data/processed/acestep/"
    echo "     Each song needs: <name>.wav, <name>_prompt.txt, <name>_lyrics.txt"
    echo "  2. ACE-Step installed at: models/ace-step/"
    echo "  3. GPU with at least 18GB VRAM"
    echo ""
    echo "Example:"
    echo "  $0 noah-lora 5000 32"
    echo "  $0 noah-classical 10000 16 0.00005"
    exit 1
fi

ACESTEP_DIR="$PROJECT_ROOT/models/ace-step"
TRAINING_DATA="$PROJECT_ROOT/training_data/processed/acestep"
VOICES_DIR="$PROJECT_ROOT/voices"
DATASET_DIR="$ACESTEP_DIR/${VOICE_NAME}_dataset"
LORA_CONFIG="$ACESTEP_DIR/config/${VOICE_NAME}_lora_config.json"

# Validate prerequisites
if [ ! -d "$ACESTEP_DIR" ]; then
    echo "Error: ACE-Step not found at $ACESTEP_DIR"
    echo "Run scripts/setup_models.sh first"
    exit 1
fi

if [ ! -d "$TRAINING_DATA" ]; then
    echo "Error: Training data directory not found: $TRAINING_DATA"
    echo "Run scripts/preprocess_voice.py first to prepare training data."
    exit 1
fi

# Check for audio files with sidecar metadata
WAV_COUNT=$(find "$TRAINING_DATA" -name "*.wav" -not -name "*_*" | wc -l)
if [ "$WAV_COUNT" -eq 0 ]; then
    echo "Error: No WAV files found in $TRAINING_DATA"
    echo "Expected format: <name>.wav + <name>_prompt.txt + <name>_lyrics.txt"
    exit 1
fi

echo "Voice:         $VOICE_NAME"
echo "Max steps:     $MAX_STEPS"
echo "LoRA rank:     $RANK"
echo "Learning rate: $LEARNING_RATE"
echo "Training data: $WAV_COUNT audio files"
echo ""

# Step 1: Create LoRA config (transformer-only to prevent melody overfitting)
echo "--- Step 1/4: Creating LoRA config ---"
ALPHA=$((RANK * 2))
cat > "$LORA_CONFIG" << EOF
{
    "r": $RANK,
    "lora_alpha": $ALPHA,
    "lora_dropout": 0.1,
    "target_modules": [
        "speaker_embedder",
        "linear_q",
        "linear_k",
        "linear_v",
        "to_q",
        "to_k",
        "to_v",
        "to_out.0"
    ],
    "use_rslora": true
}
EOF
echo "LoRA config written: $LORA_CONFIG"
echo "  rank=$RANK, alpha=$ALPHA, dropout=0.1"
echo "  target: transformer attention layers only (lyrics decoder frozen)"
echo ""

# Step 2: Prepare HuggingFace dataset
echo "--- Step 2/4: Preparing dataset ---"

# Compute repeat count to get enough training steps
# Each song is ~1 step, so repeat_count ≈ max_steps / wav_count
REPEAT_COUNT=$(( (MAX_STEPS + WAV_COUNT - 1) / WAV_COUNT ))
# Minimum repeat of 100 for small datasets
if [ "$REPEAT_COUNT" -lt 100 ]; then
    REPEAT_COUNT=100
fi

cd "$ACESTEP_DIR"
python convert2hf_dataset.py \
    --data_dir "$TRAINING_DATA" \
    --repeat_count "$REPEAT_COUNT" \
    --output_name "$DATASET_DIR"

echo "Dataset created: $DATASET_DIR (${WAV_COUNT} songs × ${REPEAT_COUNT} repeats)"
echo ""

# Step 3: Train LoRA adapter
echo "--- Step 3/4: Training LoRA adapter ---"
echo "This will take a while... Monitor with: tensorboard --logdir $ACESTEP_DIR/exps/logs/"
echo ""

CHECKPOINT_DIR="$ACESTEP_DIR"
# Use local weights if available
if [ -d "$ACESTEP_DIR/ace_step_transformer" ]; then
    CHECKPOINT_DIR="$ACESTEP_DIR"
fi

python trainer.py \
    --checkpoint_dir "$CHECKPOINT_DIR" \
    --dataset_path "$DATASET_DIR" \
    --exp_name "$VOICE_NAME" \
    --lora_config_path "$LORA_CONFIG" \
    --max_steps "$MAX_STEPS" \
    --learning_rate "$LEARNING_RATE" \
    --epochs -1 \
    --precision "bf16-mixed" \
    --devices 1 \
    --num_workers 4 \
    --every_n_train_steps 500 \
    --every_plot_step 1000 \
    --gradient_clip_val 0.5 \
    --logger_dir "$ACESTEP_DIR/exps/logs/"

echo "Training complete."
echo ""

# Step 4: Export adapter to voices directory
echo "--- Step 4/4: Exporting LoRA adapter ---"
mkdir -p "$VOICES_DIR"

# Find the latest checkpoint with the adapter
LATEST_CKPT=$(find "$ACESTEP_DIR/exps/logs/" -path "*${VOICE_NAME}*" -name "*.ckpt" | sort -V | tail -1)

if [ -z "$LATEST_CKPT" ]; then
    echo "Warning: No checkpoint found for $VOICE_NAME"
    echo "Check training logs at: $ACESTEP_DIR/exps/logs/"
    exit 1
fi

# Extract the LoRA adapter weights from the checkpoint
python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
import torch

ckpt = torch.load('$LATEST_CKPT', map_location='cpu', weights_only=False)
state_dict = ckpt.get('state_dict', ckpt)

# Filter for LoRA parameters only
lora_state = {k: v for k, v in state_dict.items() if 'lora' in k.lower()}
if not lora_state:
    print('Warning: No LoRA weights found in checkpoint, saving full state')
    lora_state = state_dict

output_path = '$VOICES_DIR/${VOICE_NAME}.safetensors'
try:
    from safetensors.torch import save_file
    save_file(lora_state, output_path)
    print(f'LoRA adapter exported (safetensors): {output_path}')
except ImportError:
    output_path = '$VOICES_DIR/${VOICE_NAME}.pth'
    torch.save(lora_state, output_path)
    print(f'LoRA adapter exported (pth): {output_path}')
"

# Register in voice registry
python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from src.voice.voice_registry import register_voice
import os

# Determine which format was saved
safetensors_path = '$VOICES_DIR/${VOICE_NAME}.safetensors'
pth_path = '$VOICES_DIR/${VOICE_NAME}.pth'
model_path = safetensors_path if os.path.exists(safetensors_path) else pth_path

register_voice(
    voice_id='$VOICE_NAME',
    name='$VOICE_NAME',
    model_type='acestep_lora',
    model_path=model_path,
    index_path='',
    metadata={
        'max_steps': $MAX_STEPS,
        'rank': $RANK,
        'learning_rate': $LEARNING_RATE,
        'training_songs': $WAV_COUNT,
    },
)
print('Voice registered: $VOICE_NAME')
"

echo ""
echo "=== LoRA Training Complete ==="
echo "Adapter: $VOICES_DIR/${VOICE_NAME}.safetensors"
echo "Use with: generate_audio_acestep_lora(tags=..., lora_path='$VOICES_DIR/${VOICE_NAME}.safetensors')"
