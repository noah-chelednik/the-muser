"""
Log orchestrator sessions as JSONL for fine-tuning dataset creation.

Each line in the log file is a complete conversation turn:
  {"messages": [...], "tools": [...], "timestamp": "..."}

These logs become training data for a future fine-tuned Qwen3-8B.
"""

import json
from pathlib import Path
from datetime import datetime

LOG_DIR = Path(__file__).resolve().parents[2] / "training_data" / "sessions"


class SessionLogger:
    def __init__(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = LOG_DIR / f"session_{timestamp}.jsonl"
        self.turns = []

    def log_turn(
        self,
        messages: list[dict],
        tools: list[dict],
        response_content: str | None,
        tool_calls: list[dict],
    ):
        """Log a single orchestrator turn."""
        turn = {
            "timestamp": datetime.now().isoformat(),
            "messages": messages,
            "tools": tools,
            "response": {
                "content": response_content,
                "tool_calls": tool_calls,
            },
        }
        self.turns.append(turn)
        # Append to file immediately (crash-safe)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(turn) + "\n")

    def export_training_format(self) -> list[dict]:
        """
        Convert logged session to fine-tuning format.
        Returns a list of training examples, each with
        "messages" and "tools" keys.
        """
        examples = []
        for turn in self.turns:
            # Build the training example as a complete conversation
            msgs = list(turn["messages"])
            # Add the assistant response
            assistant_msg: dict = {"role": "assistant"}
            if turn["response"]["content"]:
                assistant_msg["content"] = turn["response"]["content"]
            if turn["response"]["tool_calls"]:
                assistant_msg["tool_calls"] = turn["response"]["tool_calls"]
            msgs.append(assistant_msg)

            examples.append(
                {
                    "messages": msgs,
                    "tools": turn["tools"],
                }
            )
        return examples
