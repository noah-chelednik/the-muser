"""Session logging for The Muser composition workflow.

Logs tool calls, generation results, and session metadata
with timestamps for debugging and audit trails.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.orchestrator.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Session log directory
LOG_DIR = PROJECT_ROOT / "logs"


class SessionLogger:
    """Logs composition session activity to structured JSON files."""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = LOG_DIR / self.session_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "session.jsonl"
        self._start_time = time.time()
        self._log_event("session_start", {"session_id": self.session_id})

    def log_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        result: dict[str, Any],
        duration_s: float,
    ) -> None:
        """Log a tool call with its input, result, and duration."""
        self._log_event("tool_call", {
            "tool": tool_name,
            "input": tool_input,
            "result_status": result.get("status", "unknown"),
            "duration_s": round(duration_s, 2),
        })

    def log_generation(
        self,
        generator: str,
        params: dict[str, Any],
        output_path: str | None,
        success: bool,
    ) -> None:
        """Log a generation event."""
        self._log_event("generation", {
            "generator": generator,
            "params": params,
            "output_path": output_path,
            "success": success,
        })

    def log_validation(
        self,
        target: str,
        passed: bool,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """Log a validation result."""
        self._log_event("validation", {
            "target": target,
            "passed": passed,
            "error_count": len(errors),
            "warning_count": len(warnings),
        })

    def log_user_message(self, message: str) -> None:
        """Log a user message (content truncated for privacy)."""
        self._log_event("user_message", {
            "length": len(message),
            "preview": message[:100],
        })

    def log_error(self, context: str, error: str) -> None:
        """Log an error event."""
        self._log_event("error", {"context": context, "error": error})

    def _log_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Write a structured log event to the session file."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": round(time.time() - self._start_time, 2),
            "type": event_type,
            **data,
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except OSError as e:
            logger.warning("Failed to write session log: %s", e)


def configure_logging(verbose: bool = False) -> None:
    """Configure the logging system for The Muser.

    Args:
        verbose: If True, set DEBUG level. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
        ],
    )
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
