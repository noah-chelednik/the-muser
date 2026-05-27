"""
Fine-tune Qwen3-8B for The Muser tool calling.

Requires: ~10GB VRAM on RTX 4090 (with QLoRA 4-bit)
Time: ~2-3 hours for 500 examples, 3 epochs

Prerequisites:
  pip install unsloth
  python scripts/create_training_dataset.py  (to generate training data)

Usage:
  python scripts/finetune_orchestrator.py
"""

from pathlib import Path

from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

TRAINING_DATA = Path(__file__).resolve().parents[1] / "training_data" / "tool_calling_dataset.jsonl"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "muser-orchestrator-lora"
GGUF_DIR = Path(__file__).resolve().parents[1] / "muser-orchestrator-gguf"

# Load base model in 4-bit
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen3-8B",
    max_seq_length=2048,
    load_in_4bit=True,
)

# Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0,
    use_gradient_checkpointing="unsloth",
)

# Load training data
dataset = load_dataset("json", data_files=str(TRAINING_DATA), split="train")

# Train
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=10,
        save_strategy="epoch",
    ),
)
trainer.train()

# Export to GGUF for Ollama
model.save_pretrained_gguf(str(GGUF_DIR), tokenizer, quantization_method="q4_k_m")
print(f"Done! Deploy with: ollama create muser-orchestrator -f {GGUF_DIR}/Modelfile")
