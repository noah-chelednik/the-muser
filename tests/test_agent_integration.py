"""Integration tests for the agent loop."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.orchestrator.llm_provider import LLMResponse, ToolCall


class TestAgentLoop:

    def _mock_response(self, content="", tool_calls=None):
        return LLMResponse(
            content=content,
            tool_calls=tool_calls or [],
            provider="test",
            model="test/model",
        )

    @patch("src.orchestrator.agent.chat")
    def test_text_only_response(self, mock_chat, composition_state):
        from src.orchestrator.agent import run_agent_turn

        mock_chat.return_value = self._mock_response(content="Hello!")
        result = run_agent_turn("Hi", [], composition_state)
        assert result == "Hello!"

    @patch("src.orchestrator.agent.chat")
    def test_tool_call_then_text(self, mock_chat, composition_state):
        from src.orchestrator.agent import run_agent_turn

        mock_chat.side_effect = [
            self._mock_response(tool_calls=[
                ToolCall(name="list_sections", arguments={}, id="call_1"),
            ]),
            self._mock_response(content="No sections yet."),
        ]

        result = run_agent_turn("What sections exist?", [], composition_state)
        assert "sections" in result.lower() or "No" in result

    @patch("src.orchestrator.agent.chat")
    def test_hallucinated_tool_rejected(self, mock_chat, composition_state):
        from src.orchestrator.agent import run_agent_turn

        mock_chat.side_effect = [
            self._mock_response(tool_calls=[
                ToolCall(name="fake_nonexistent_tool", arguments={}, id="call_1"),
            ]),
            self._mock_response(content="I encountered an issue."),
        ]

        result = run_agent_turn("Do something", [], composition_state)
        assert mock_chat.call_count == 2

    @patch("src.orchestrator.agent.chat")
    def test_compose_inline_captures_musicxml(self, mock_chat, composition_state):
        from src.orchestrator.agent import run_agent_turn

        musicxml = '<score-partwise version="4.0"><part id="P1"></part></score-partwise>'

        mock_chat.side_effect = [
            self._mock_response(tool_calls=[
                ToolCall(
                    name="generate_notation_claude",
                    arguments={"section_name": "intro", "instructions": "4 bars", "instruments": ["Piano"]},
                    id="call_1",
                ),
            ]),
            self._mock_response(content=f"Here is the notation:\n```xml\n{musicxml}\n```"),
        ]

        result = run_agent_turn("Write 4 bars of piano", [], composition_state)
        sections = composition_state.list_sections()
        saved = [s for s in sections if s["name"] == "intro"]
        assert len(saved) == 1

    @patch("src.orchestrator.agent.chat_stream")
    def test_streaming_callback(self, mock_stream, composition_state):
        from src.orchestrator.agent import run_agent_turn

        mock_stream.return_value = self._mock_response(content="Streaming response")

        tokens = []
        result = run_agent_turn(
            "Hello", [], composition_state,
            on_token=lambda t: tokens.append(t),
        )
        assert result == "Streaming response"
        mock_stream.assert_called_once()

    @patch("src.orchestrator.agent.chat")
    def test_max_iterations_safety(self, mock_chat, composition_state):
        from src.orchestrator.agent import run_agent_turn

        mock_chat.return_value = self._mock_response(tool_calls=[
            ToolCall(name="list_sections", arguments={}, id="call_loop"),
        ])

        result = run_agent_turn("loop forever", [], composition_state)
        assert "maximum" in result.lower() or "iterations" in result.lower()
