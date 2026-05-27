"""Test the provider-agnostic LLM interface."""

import os
from src.orchestrator.llm_provider import chat, validate_tool_call, ToolCall

TEST_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_melody",
            "description": "Generate a MIDI melody in the specified key",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Musical key (e.g., 'C major')"},
                    "bars": {"type": "integer", "description": "Number of bars"},
                },
                "required": ["key", "bars"],
            },
        },
    }
]


def test_ollama_basic_chat():
    """Test basic text response from local Ollama."""
    os.environ["MUSER_LLM_MODE"] = "local"
    response = chat(
        messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
    )
    assert response.content is not None
    assert len(response.content) > 0


def test_ollama_tool_calling():
    """Test that local Ollama produces valid tool calls."""
    os.environ["MUSER_LLM_MODE"] = "local"
    response = chat(
        messages=[
            {
                "role": "system",
                "content": "You are a music composition assistant. Use tools when asked to generate music.",
            },
            {"role": "user", "content": "Generate a 4-bar melody in D major."},
        ],
        tools=TEST_TOOLS,
    )
    assert len(response.tool_calls) > 0
    tc = response.tool_calls[0]
    assert tc.name == "generate_melody"
    assert "key" in tc.arguments


def test_validate_tool_call():
    """Test hallucinated tool rejection."""
    valid = {"generate_melody", "render_audio"}
    real_tc = ToolCall(name="generate_melody", arguments={})
    fake_tc = ToolCall(name="hack_the_planet", arguments={})
    assert validate_tool_call(real_tc, valid) is True
    assert validate_tool_call(fake_tc, valid) is False


if __name__ == "__main__":
    test_ollama_basic_chat()
    print("Basic chat works")
    test_ollama_tool_calling()
    print("Tool calling works")
    test_validate_tool_call()
    print("Tool validation works")
