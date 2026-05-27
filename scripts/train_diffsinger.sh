#!/usr/bin/env bash
# =============================================================================
# DiffSinger Training Pipeline for The Muser
#
# Full pipeline: acoustic model -> variance model -> ONNX export -> registration
#
# Usage:
#   bash scripts/train_diffsinger.sh <voice_name> <dataset_dir>
#
# Environment variables:
#   DIFFSINGER_DIR  — path to DiffSinger repo (default: models/diffsinger)
#   VOICE_NAME      — voice model name (overrides positional arg)
#   DATASET_DIR     — prepared dataset path (overrides positional arg)
#   EPOCHS          — training epochs (default: 1000)
#   BATCH_SIZE      — batch size (default: 16)
#   LEARNING_RATE   — learning rate (default: 0.0004)
#   VOCODER         — vocoder choice: fish-hifigan (commercial) or nsf-hifigan (community, default)
#   RESUME_CKPT     — path to checkpoint to resume from (optional)
#   GPU_ID          — CUDA device ID (default: 0)
#   NUM_WORKERS     — data loader workers (default: 4)
#   SAVE_EVERY      — save checkpoint every N epochs (default: 100)
#   VAL_EVERY       — run validation every N epochs (default: 50)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VOICE_NAME="${VOICE_NAME:-${1:-}}"
DATASET_DIR="${DATASET_DIR:-${2:-}}"
DIFFSINGER_DIR="${DIFFSINGER_DIR:-$PROJECT_ROOT/models/diffsinger}"
EPOCHS="${EPOCHS:-1000}"
BATCH_SIZE="${BATCH_SIZE:-16}"
LEARNING_RATE="${LEARNING_RATE:-0.0004}"
VOCODER="${VOCODER:-nsf-hifigan}"
RESUME_CKPT="${RESUME_CKPT:-}"
GPU_ID="${GPU_ID:-0}"
NUM_WORKERS="${NUM_WORKERS:-4}"
SAVE_EVERY="${SAVE_EVERY:-100}"
VAL_EVERY="${VAL_EVERY:-50}"

# Derived paths
VOICES_DIR="$PROJECT_ROOT/voices"
CHECKPOINTS_DIR="$DIFFSINGER_DIR/checkpoints"
CONFIGS_DIR="$DIFFSINGER_DIR/configs"
EXP_DIR="$CHECKPOINTS_DIR/$VOICE_NAME"
ACOUSTIC_EXP="${EXP_DIR}/acoustic"
VARIANCE_EXP="${EXP_DIR}/variance"
ONNX_DIR="${EXP_DIR}/onnx"
FINAL_VOICE_DIR="${VOICES_DIR}/${VOICE_NAME}-diffsinger"

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
header()  { echo -e "\n${BOLD}=== $* ===${NC}\n"; }

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    echo "Usage: $0 <voice_name> <dataset_dir>"
    echo ""
    echo "Arguments:"
    echo "  voice_name    Name for the voice model (e.g., 'noah-singing')"
    echo "  dataset_dir   Path to prepared dataset (from prepare_diffsinger_dataset.py)"
    echo ""
    echo "Environment variables:"
    echo "  DIFFSINGER_DIR  Path to DiffSinger repo (default: models/diffsinger)"
    echo "  EPOCHS          Training epochs (default: 1000)"
    echo "  BATCH_SIZE      Batch size (default: 16)"
    echo "  LEARNING_RATE   Learning rate (default: 0.0004)"
    echo "  VOCODER         Vocoder: fish-hifigan or nsf-hifigan (default)"
    echo "  RESUME_CKPT     Checkpoint to resume from (optional)"
    echo "  GPU_ID          CUDA device ID (default: 0)"
    echo ""
    echo "Example:"
    echo "  bash $0 my-voice training_data/my-voice/"
    echo "  EPOCHS=500 BATCH_SIZE=8 bash $0 my-voice training_data/my-voice/"
}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
header "DiffSinger Voice Training Pipeline"

if [ -z "$VOICE_NAME" ]; then
    error "voice_name is required"
    usage
    exit 1
fi

if [ -z "$DATASET_DIR" ]; then
    error "dataset_dir is required"
    usage
    exit 1
fi

# Resolve to absolute path
DATASET_DIR="$(cd "$DATASET_DIR" 2>/dev/null && pwd)" || {
    error "Dataset directory does not exist: $DATASET_DIR"
    exit 1
}

info "Voice name:     $VOICE_NAME"
info "Dataset dir:    $DATASET_DIR"
info "DiffSinger dir: $DIFFSINGER_DIR"
info "Epochs:         $EPOCHS"
info "Batch size:     $BATCH_SIZE"
info "Learning rate:  $LEARNING_RATE"
info "Vocoder:        $VOCODER"
info "GPU ID:         $GPU_ID"

# Check DiffSinger installation
if [ ! -d "$DIFFSINGER_DIR" ]; then
    error "DiffSinger not found at $DIFFSINGER_DIR"
    echo "  Clone with: git clone https://github.com/openvpi/DiffSinger.git $DIFFSINGER_DIR"
    echo "  Then: pip install -e $DIFFSINGER_DIR"
    exit 1
fi

if [ ! -f "$DIFFSINGER_DIR/setup.py" ] && [ ! -f "$DIFFSINGER_DIR/pyproject.toml" ]; then
    warn "DiffSinger does not appear to be a proper Python package."
    warn "Ensure 'pip install -e $DIFFSINGER_DIR' has been run."
fi

# Check dataset
if [ ! -d "$DATASET_DIR/wavs" ] && [ ! -d "$DATASET_DIR/raw" ]; then
    error "Dataset directory does not contain 'wavs/' or 'raw/' subdirectory."
    error "Run prepare_diffsinger_dataset.py first."
    exit 1
fi

# Check CUDA availability
if ! python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    error "CUDA is not available. DiffSinger training requires a GPU."
    exit 1
fi

# Report GPU info
info "GPU info:"
python3 -c "
import torch
for i in range(torch.cuda.device_count()):
    name = torch.cuda.get_device_name(i)
    mem = torch.cuda.get_device_properties(i).total_mem / (1024**3)
    print(f'  GPU {i}: {name} ({mem:.1f} GB)')
" 2>/dev/null || warn "Could not query GPU info"

# Check vocoder availability
VOCODER_DIR="$DIFFSINGER_DIR/checkpoints/$VOCODER"
if [ ! -d "$VOCODER_DIR" ]; then
    warn "Vocoder checkpoint not found at $VOCODER_DIR"
    info "Attempting to download $VOCODER vocoder..."
    mkdir -p "$VOCODER_DIR"

    if [ "$VOCODER" = "nsf-hifigan" ]; then
        # NSF-HiFiGAN is the default community vocoder
        if command -v wget &>/dev/null; then
            wget -q -P "$VOCODER_DIR" \
                "https://github.com/openvpi/vocoders/releases/download/nsf-hifigan-v1/nsf_hifigan_44.1k_hop512_128bin_2024.02.zip" \
                2>/dev/null && {
                cd "$VOCODER_DIR" && unzip -qo *.zip && rm -f *.zip
                success "Downloaded NSF-HiFiGAN vocoder."
            } || warn "Failed to download vocoder. Training may fail."
        else
            warn "wget not available. Please download the vocoder manually."
        fi
    elif [ "$VOCODER" = "fish-hifigan" ]; then
        info "fish-hifigan must be downloaded manually for commercial use."
        info "See: https://github.com/fishaudio/fish-diffusion"
    fi
fi

# ---------------------------------------------------------------------------
# Step 1: Generate training configuration
# ---------------------------------------------------------------------------
header "Step 1: Generating Training Configuration"

mkdir -p "$EXP_DIR" "$ACOUSTIC_EXP" "$VARIANCE_EXP"

# Acoustic model config
ACOUSTIC_CONFIG="$ACOUSTIC_EXP/config.yaml"
info "Writing acoustic config: $ACOUSTIC_CONFIG"

cat > "$ACOUSTIC_CONFIG" << YAML
# DiffSinger Acoustic Model Configuration
# Voice: $VOICE_NAME
# Generated by The Muser training pipeline

base_config: configs/acoustic.yaml

task_cls: training.acoustic_task.AcousticTask
vocoder: $VOCODER
vocoder_ckpt: checkpoints/$VOCODER

audio_sample_rate: 44100
audio_num_mel_bins: 128
hop_size: 512
fft_size: 2048
win_size: 2048

# Dataset
raw_data_dir: $DATASET_DIR
binary_data_dir: $ACOUSTIC_EXP/binary
valid_set_size: 5
test_set_size: 5

# Training
max_epochs: $EPOCHS
max_batch_size: $BATCH_SIZE
max_batch_frames: 80000
lr: $LEARNING_RATE
optimizer_adam_beta1: 0.9
optimizer_adam_beta2: 0.98
lr_scheduler_args:
  step_size: 50000
  gamma: 0.5
weight_decay: 0.0
clip_grad_norm: 1.0
accumulate_grad_batches: 1

# Architecture
hidden_size: 256
residual_channels: 512
residual_layers: 20
diff_decoder_type: wavenet
diff_loss_type: l2
use_pitch_embed: true
pitch_type: frame

# Diffusion
K_step: 1000
timesteps: 1000
max_beta: 0.06
schedule_type: linear
diff_accelerator: ddim
pndm_speedup: 10

# Data augmentation
augmentation_args:
  random_pitch_shifting:
    enabled: true
    range: [-5, 5]
    scale: 0.75
  fixed_pitch_shifting:
    enabled: false
  random_time_stretching:
    enabled: true
    range: [0.9, 1.1]

# Saving
num_ckpt_keep: 5
save_every_n_epochs: $SAVE_EVERY
val_check_interval: $VAL_EVERY

# Logging
log_interval: 100
num_valid_plots: 5

# System
ds_workers: $NUM_WORKERS
seed: 42
YAML

# Variance model config
VARIANCE_CONFIG="$VARIANCE_EXP/config.yaml"
info "Writing variance config: $VARIANCE_CONFIG"

cat > "$VARIANCE_CONFIG" << YAML
# DiffSinger Variance Model Configuration
# Voice: $VOICE_NAME
# Generated by The Muser training pipeline

base_config: configs/variance.yaml

task_cls: training.variance_task.VarianceTask
vocoder: $VOCODER
vocoder_ckpt: checkpoints/$VOCODER

audio_sample_rate: 44100
audio_num_mel_bins: 128
hop_size: 512
fft_size: 2048
win_size: 2048

# Dataset (same as acoustic)
raw_data_dir: $DATASET_DIR
binary_data_dir: $VARIANCE_EXP/binary
valid_set_size: 5
test_set_size: 5

# Training
max_epochs: $EPOCHS
max_batch_size: $BATCH_SIZE
lr: $LEARNING_RATE
optimizer_adam_beta1: 0.9
optimizer_adam_beta2: 0.98
weight_decay: 0.0
clip_grad_norm: 1.0

# Variance parameters to predict
predict_pitch: true
predict_energy: true
predict_breathiness: true
predict_voicing: true
predict_tension: true

# Pitch predictor
pitch_prediction_args:
  pitd_norm_mean: 0.0
  pitd_norm_stdev: 1.0
  pitd_clip_min: -12.0
  pitd_clip_max: 12.0
  repeat_bins: 64
  residual_layers: 10
  residual_channels: 256

# Energy predictor
energy_prediction_args:
  energy_smooth_width: 0.12

# Breathiness predictor
breathiness_prediction_args:
  breathiness_smooth_width: 0.12
  breathiness_db_min: -96.0
  breathiness_db_max: -20.0

# Voicing predictor
voicing_prediction_args:
  voicing_smooth_width: 0.12
  voicing_db_min: -96.0
  voicing_db_max: 0.0

# Tension predictor
tension_prediction_args:
  tension_smooth_width: 0.12
  tension_logit_min: -10.0
  tension_logit_max: 10.0

# Saving
num_ckpt_keep: 5
save_every_n_epochs: $SAVE_EVERY
val_check_interval: $VAL_EVERY

# Logging
log_interval: 100

# System
ds_workers: $NUM_WORKERS
seed: 42
YAML

success "Training configurations generated."

# ---------------------------------------------------------------------------
# Step 2: Preprocess dataset (binarize)
# ---------------------------------------------------------------------------
header "Step 2: Preprocessing Dataset"

export CUDA_VISIBLE_DEVICES="$GPU_ID"
cd "$DIFFSINGER_DIR"

info "Binarizing acoustic dataset..."
if python3 scripts/binarize.py --config "$ACOUSTIC_CONFIG" 2>&1 | tee "$ACOUSTIC_EXP/binarize.log"; then
    success "Acoustic dataset binarized."
else
    error "Acoustic binarization failed. Check $ACOUSTIC_EXP/binarize.log"
    exit 1
fi

info "Binarizing variance dataset..."
if python3 scripts/binarize.py --config "$VARIANCE_CONFIG" 2>&1 | tee "$VARIANCE_EXP/binarize.log"; then
    success "Variance dataset binarized."
else
    error "Variance binarization failed. Check $VARIANCE_EXP/binarize.log"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: Train acoustic model
# ---------------------------------------------------------------------------
header "Step 3: Training Acoustic Model"

ACOUSTIC_TRAIN_CMD=(
    python3 scripts/train.py
    --config "$ACOUSTIC_CONFIG"
    --exp_name "$VOICE_NAME/acoustic"
    --work_dir "$CHECKPOINTS_DIR"
)

if [ -n "$RESUME_CKPT" ]; then
    ACOUSTIC_TRAIN_CMD+=(--resume_from "$RESUME_CKPT")
    info "Resuming from checkpoint: $RESUME_CKPT"
fi

info "Starting acoustic model training ($EPOCHS epochs)..."
info "Command: ${ACOUSTIC_TRAIN_CMD[*]}"

TRAIN_START=$(date +%s)

if "${ACOUSTIC_TRAIN_CMD[@]}" 2>&1 | tee "$ACOUSTIC_EXP/train.log"; then
    TRAIN_END=$(date +%s)
    TRAIN_DURATION=$(( TRAIN_END - TRAIN_START ))
    success "Acoustic model training complete (${TRAIN_DURATION}s / $(( TRAIN_DURATION / 60 ))min)."
else
    error "Acoustic model training failed. Check $ACOUSTIC_EXP/train.log"
    warn "You can resume training by setting RESUME_CKPT to the last checkpoint."
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 4: Train variance model
# ---------------------------------------------------------------------------
header "Step 4: Training Variance Model"

VARIANCE_TRAIN_CMD=(
    python3 scripts/train.py
    --config "$VARIANCE_CONFIG"
    --exp_name "$VOICE_NAME/variance"
    --work_dir "$CHECKPOINTS_DIR"
)

info "Starting variance model training ($EPOCHS epochs)..."
info "Command: ${VARIANCE_TRAIN_CMD[*]}"

TRAIN_START=$(date +%s)

if "${VARIANCE_TRAIN_CMD[@]}" 2>&1 | tee "$VARIANCE_EXP/train.log"; then
    TRAIN_END=$(date +%s)
    TRAIN_DURATION=$(( TRAIN_END - TRAIN_START ))
    success "Variance model training complete (${TRAIN_DURATION}s / $(( TRAIN_DURATION / 60 ))min)."
else
    error "Variance model training failed. Check $VARIANCE_EXP/train.log"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 5: Export to ONNX
# ---------------------------------------------------------------------------
header "Step 5: Exporting to ONNX"

mkdir -p "$ONNX_DIR"

# Find the best/latest checkpoint for acoustic model
ACOUSTIC_CKPT=$(find "$ACOUSTIC_EXP" -name "model_ckpt_steps_*.ckpt" -o -name "model_ckpt_epoch_*.ckpt" | sort -V | tail -1)
if [ -z "$ACOUSTIC_CKPT" ]; then
    ACOUSTIC_CKPT=$(find "$ACOUSTIC_EXP" -name "*.ckpt" | sort -V | tail -1)
fi

if [ -z "$ACOUSTIC_CKPT" ]; then
    error "No acoustic checkpoint found in $ACOUSTIC_EXP"
    exit 1
fi

info "Acoustic checkpoint: $ACOUSTIC_CKPT"

# Find the best/latest checkpoint for variance model
VARIANCE_CKPT=$(find "$VARIANCE_EXP" -name "model_ckpt_steps_*.ckpt" -o -name "model_ckpt_epoch_*.ckpt" | sort -V | tail -1)
if [ -z "$VARIANCE_CKPT" ]; then
    VARIANCE_CKPT=$(find "$VARIANCE_EXP" -name "*.ckpt" | sort -V | tail -1)
fi

if [ -z "$VARIANCE_CKPT" ]; then
    error "No variance checkpoint found in $VARIANCE_EXP"
    exit 1
fi

info "Variance checkpoint: $VARIANCE_CKPT"

# Export acoustic model
info "Exporting acoustic model to ONNX..."
if python3 scripts/export.py \
    --exp_name "$VOICE_NAME/acoustic" \
    --work_dir "$CHECKPOINTS_DIR" \
    --out "$ONNX_DIR/acoustic.onnx" \
    2>&1 | tee "$ONNX_DIR/export_acoustic.log"; then
    success "Acoustic ONNX export complete."
else
    warn "ONNX export for acoustic model failed. PyTorch fallback will be used."
    warn "Check $ONNX_DIR/export_acoustic.log"
    # Copy PyTorch checkpoint as fallback
    cp "$ACOUSTIC_CKPT" "$ONNX_DIR/acoustic.ckpt"
    info "Copied PyTorch acoustic checkpoint to $ONNX_DIR/acoustic.ckpt"
fi

# Export variance model
info "Exporting variance model to ONNX..."
if python3 scripts/export.py \
    --exp_name "$VOICE_NAME/variance" \
    --work_dir "$CHECKPOINTS_DIR" \
    --out "$ONNX_DIR/variance.onnx" \
    2>&1 | tee "$ONNX_DIR/export_variance.log"; then
    success "Variance ONNX export complete."
else
    warn "ONNX export for variance model failed. PyTorch fallback will be used."
    warn "Check $ONNX_DIR/export_variance.log"
    # Copy PyTorch checkpoint as fallback
    cp "$VARIANCE_CKPT" "$ONNX_DIR/variance.ckpt"
    info "Copied PyTorch variance checkpoint to $ONNX_DIR/variance.ckpt"
fi

# ---------------------------------------------------------------------------
# Step 6: Package and install voice
# ---------------------------------------------------------------------------
header "Step 6: Installing Voice Model"

mkdir -p "$FINAL_VOICE_DIR"

# Copy ONNX models (or PyTorch fallbacks)
if [ -f "$ONNX_DIR/acoustic.onnx" ]; then
    cp "$ONNX_DIR/acoustic.onnx" "$FINAL_VOICE_DIR/"
    info "Copied acoustic ONNX model."
elif [ -f "$ONNX_DIR/acoustic.ckpt" ]; then
    cp "$ONNX_DIR/acoustic.ckpt" "$FINAL_VOICE_DIR/"
    info "Copied acoustic PyTorch checkpoint."
fi

if [ -f "$ONNX_DIR/variance.onnx" ]; then
    cp "$ONNX_DIR/variance.onnx" "$FINAL_VOICE_DIR/"
    info "Copied variance ONNX model."
elif [ -f "$ONNX_DIR/variance.ckpt" ]; then
    cp "$ONNX_DIR/variance.ckpt" "$FINAL_VOICE_DIR/"
    info "Copied variance PyTorch checkpoint."
fi

# Copy configs
cp "$ACOUSTIC_CONFIG" "$FINAL_VOICE_DIR/acoustic_config.yaml"
cp "$VARIANCE_CONFIG" "$FINAL_VOICE_DIR/variance_config.yaml"

# Copy vocoder info
echo "$VOCODER" > "$FINAL_VOICE_DIR/vocoder.txt"

# Write voice model metadata
cat > "$FINAL_VOICE_DIR/metadata.json" << JSON
{
    "voice_name": "$VOICE_NAME",
    "type": "diffsinger",
    "vocoder": "$VOCODER",
    "sample_rate": 44100,
    "hop_size": 512,
    "epochs_trained": $EPOCHS,
    "batch_size": $BATCH_SIZE,
    "learning_rate": $LEARNING_RATE,
    "dataset_dir": "$DATASET_DIR",
    "has_onnx_acoustic": $([ -f "$FINAL_VOICE_DIR/acoustic.onnx" ] && echo "true" || echo "false"),
    "has_onnx_variance": $([ -f "$FINAL_VOICE_DIR/variance.onnx" ] && echo "true" || echo "false"),
    "variance_parameters": ["pitch", "energy", "breathiness", "voicing", "tension"],
    "created_at": "$(date -Iseconds)",
    "pipeline": "the-muser"
}
JSON

success "Voice model files installed to: $FINAL_VOICE_DIR"

# ---------------------------------------------------------------------------
# Step 7: Register in voice registry
# ---------------------------------------------------------------------------
header "Step 7: Registering Voice"

# Determine if ONNX models are available for description
HAS_ONNX="false"
if [ -f "$FINAL_VOICE_DIR/acoustic.onnx" ] && [ -f "$FINAL_VOICE_DIR/variance.onnx" ]; then
    HAS_ONNX="true"
fi

python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from src.voice.voice_registry import register_voice

register_voice(
    voice_id='${VOICE_NAME}-diffsinger',
    name='${VOICE_NAME} (DiffSinger)',
    voice_type='diffsinger',
    model_path='$FINAL_VOICE_DIR',
    description='DiffSinger singing voice model trained from custom recordings',
    has_onnx=$HAS_ONNX,
    vocoder='$VOCODER',
    variance_parameters=['pitch', 'energy', 'breathiness', 'voicing', 'tension'],
    use_cases=['singing', 'vocal synthesis', 'score-driven vocals'],
    sample_rate=44100,
)
print('Voice registered successfully: ${VOICE_NAME}-diffsinger')
" 2>&1 || {
    warn "Failed to register voice in registry. You can register manually later."
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
header "Training Pipeline Complete"

echo -e "${GREEN}Voice model: ${BOLD}$VOICE_NAME${NC}"
echo -e "${GREEN}Model files: ${BOLD}$FINAL_VOICE_DIR${NC}"
echo ""

# List final files
info "Installed files:"
ls -lh "$FINAL_VOICE_DIR/" | tail -n +2 | while read -r line; do
    echo "  $line"
done

echo ""
info "To use this voice in The Muser:"
echo "  muser> Sing the vocal part using the ${VOICE_NAME}-diffsinger voice"
echo ""
info "To test inference directly:"
echo "  python -c \"from src.generation.diffsinger_wrapper import synthesize_singing; \\"
echo "    synthesize_singing('score.musicxml', '$FINAL_VOICE_DIR', output_path='test_vocals.wav')\""
echo ""

success "Done!"
