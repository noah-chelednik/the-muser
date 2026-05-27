"""Convert session logs to Unsloth-compatible training format."""
import json
from pathlib import Path

SESSION_DIR = Path(__file__).resolve().parents[1] / "training_data" / "sessions"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "training_data" / "tool_calling_dataset.jsonl"


def convert_sessions():
    examples = []
    for log_file in sorted(SESSION_DIR.glob("session_*.jsonl")):
        with open(log_file) as f:
            for line in f:
                turn = json.loads(line)
                # Only include turns where the model made tool calls
                # (these are the most valuable training signal)
                if turn["response"]["tool_calls"]:
                    examples.append({
                        "messages": turn["messages"] + [{
                            "role": "assistant",
                            "tool_calls": turn["response"]["tool_calls"],
                        }],
                        "tools": turn["tools"],
                    })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    print(f"Created {len(examples)} training examples at {OUTPUT_PATH}")


if __name__ == "__main__":
    convert_sessions()
