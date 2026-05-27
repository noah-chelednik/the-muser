"""Tests for session logging."""

import json
from pathlib import Path
from unittest.mock import patch


class TestSessionLogger:

    def test_creates_log_file(self, tmp_path):
        with patch("src.orchestrator.session_logger.LOG_DIR", tmp_path):
            from src.orchestrator.session_logger import SessionLogger
            logger = SessionLogger()
            assert Path(logger.log_path).parent == tmp_path

    def test_log_turn_appends_jsonl(self, tmp_path):
        with patch("src.orchestrator.session_logger.LOG_DIR", tmp_path):
            from src.orchestrator.session_logger import SessionLogger
            logger = SessionLogger()
            logger.log_turn(
                messages=[{"role": "user", "content": "hello"}],
                tools=[],
                response_content="Hi there",
                tool_calls=[],
            )
            lines = Path(logger.log_path).read_text().strip().split("\n")
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["response"]["content"] == "Hi there"

    def test_multiple_turns(self, tmp_path):
        with patch("src.orchestrator.session_logger.LOG_DIR", tmp_path):
            from src.orchestrator.session_logger import SessionLogger
            logger = SessionLogger()
            for i in range(3):
                logger.log_turn(
                    messages=[{"role": "user", "content": f"msg {i}"}],
                    tools=[], response_content=f"resp {i}", tool_calls=[],
                )
            lines = Path(logger.log_path).read_text().strip().split("\n")
            assert len(lines) == 3

    def test_export_training_format(self, tmp_path):
        with patch("src.orchestrator.session_logger.LOG_DIR", tmp_path):
            from src.orchestrator.session_logger import SessionLogger
            logger = SessionLogger()
            logger.log_turn(
                messages=[{"role": "user", "content": "compose"}],
                tools=[{"type": "function", "function": {"name": "test"}}],
                response_content="OK",
                tool_calls=[],
            )
            examples = logger.export_training_format()
            assert len(examples) == 1
            assert "messages" in examples[0]
            assert "tools" in examples[0]
            last_msg = examples[0]["messages"][-1]
            assert last_msg["role"] == "assistant"
            assert last_msg["content"] == "OK"

    def test_export_empty_session(self, tmp_path):
        with patch("src.orchestrator.session_logger.LOG_DIR", tmp_path):
            from src.orchestrator.session_logger import SessionLogger
            logger = SessionLogger()
            assert logger.export_training_format() == []
