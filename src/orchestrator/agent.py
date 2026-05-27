"""Agentic loop for The Muser orchestration.

Implements the core conversation loop where the LLM acts as the
composition director, using tools to generate, validate, render,
and produce music from natural language instructions.

Uses the provider-agnostic LLM interface (LiteLLM) so the orchestrator
works with Ollama (local), Groq, Gemini, Cerebras, or Anthropic.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from src.orchestrator.llm_provider import chat, chat_stream, validate_tool_call, LLMResponse
from src.orchestrator.tool_validators import validate_arguments
from src.orchestrator.composition_state import CompositionState
from src.orchestrator.config import MAX_TOOL_ITERATIONS
from src.orchestrator.system_prompt import build_system_prompt
from src.orchestrator.tool_definitions import get_all_tools_openai, get_tool_names
from src.orchestrator.tool_executor import execute_tool, set_state

_MUSICXML_RE = re.compile(
    r"(<score-partwise[\s\S]*?</score-partwise>)",
    re.DOTALL,
)

logger = logging.getLogger(__name__)


def run_agent_turn(
    user_message: str,
    conversation_history: list[dict[str, Any]],
    composition_state: CompositionState,
    model: str | None = None,
    session_logger: Any | None = None,
    on_token: "Callable[[str], None] | None" = None,
) -> str:
    """Run one agent turn: send user message, execute tool calls, return final response.

    Implements the agentic loop:
    1. Build system prompt with current composition state
    2. Send conversation + user message to LLM
    3. If the LLM requests tool calls, execute tools and feed results back
    4. Repeat until the LLM returns a text response (or max iterations)

    Args:
        user_message: The user's natural language instruction.
        conversation_history: Prior conversation messages.
        composition_state: Current composition state for context.
        model: LLM model to use (optional, overrides provider chain).
        session_logger: Optional SessionLogger for training data capture.

    Returns:
        The LLM's final text response to the user.
    """
    system_prompt = build_system_prompt(composition_state)
    tools = get_all_tools_openai()
    valid_tool_names = set(get_tool_names())

    # Set the composition state for tool executor access
    set_state(composition_state)

    # Build messages with system prompt
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    iterations = 0
    final_text = ""
    _pending_inline_section: str | None = None

    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1
        logger.info("Agent iteration %d/%d", iterations, MAX_TOOL_ITERATIONS)

        try:
            if on_token is not None:
                response = chat_stream(
                    messages=messages,
                    tools=tools,
                    model=model,
                    on_token=on_token,
                )
            else:
                response = chat(
                    messages=messages,
                    tools=tools,
                    model=model,
                )
        except RuntimeError as e:
            logger.error("LLM provider error: %s", e)
            return f"LLM error: {e}"

        # Log the turn for future fine-tuning
        if session_logger:
            session_logger.log_turn(
                messages=messages,
                tools=tools,
                response_content=response.content,
                tool_calls=[
                    {"name": tc.name, "arguments": tc.arguments, "id": tc.id}
                    for tc in response.tool_calls
                ],
            )

        # If the LLM responded with text and no tool calls, we're done
        if response.content and not response.tool_calls:
            # Check if the previous iteration requested inline MusicXML composition
            if _pending_inline_section and response.content:
                match = _MUSICXML_RE.search(response.content)
                if match:
                    musicxml = match.group(1)
                    composition_state.save_section(_pending_inline_section, musicxml)
                    logger.info(
                        "Captured inline MusicXML for section '%s' (%d chars)",
                        _pending_inline_section, len(musicxml),
                    )
                _pending_inline_section = None
            final_text = response.content
            break

        # If the LLM wants to call tools, execute them
        if response.tool_calls:
            # Add the assistant's message (with tool calls) to history
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
            }
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id or f"call_{iterations}_{j}",
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    }
                }
                for j, tc in enumerate(response.tool_calls)
            ]
            messages.append(assistant_msg)

            for j, tc in enumerate(response.tool_calls):
                # Validate — reject hallucinated tool names
                if not validate_tool_call(tc, valid_tool_names):
                    result = {"status": "error", "error": f"Unknown tool: {tc.name}"}
                else:
                    # Validate arguments with Pydantic
                    validated = validate_arguments(tc.name, tc.arguments)
                    if isinstance(validated, str):
                        result = {"status": "error", "error": validated}
                    else:
                        result = execute_tool(tc.name, validated)

                if result.get("action") == "compose_inline":
                    _pending_inline_section = result.get("section_name", "unnamed")

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id or f"call_{iterations}_{j}",
                    "content": json.dumps(result),
                })

        # If response has no tool calls and no content, something went wrong
        if not response.tool_calls and not response.content:
            final_text = "I encountered an issue. Please try rephrasing your request."
            break

    if not final_text and iterations >= MAX_TOOL_ITERATIONS:
        final_text = (
            "I've reached the maximum number of tool iterations. "
            "Here's a summary of what was accomplished. "
            "Please provide further instructions to continue."
        )

    # Update conversation history
    conversation_history.clear()
    # Keep only user/assistant turns (not system prompt)
    conversation_history.extend(
        m for m in messages if m["role"] != "system"
    )
    if final_text:
        conversation_history.append({
            "role": "assistant",
            "content": final_text,
        })

    return final_text
