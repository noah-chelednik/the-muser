"""
Provider-agnostic LLM interface for The Muser.

Supports three backends via LiteLLM:
  1. Local Ollama (free, unlimited, CPU inference)
  2. Free cloud APIs (Groq, Cerebras, Google Gemini)
  3. Anthropic Claude API (paid, optional)

The orchestrator code calls this module and never imports
anthropic, ollama, or litellm directly.
"""
from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import litellm

# Suppress LiteLLM's noisy logging
litellm.suppress_debug_info = True
litellm.set_verbose = False

logger = logging.getLogger("muser.llm")


# ---------------------------------------------------------------------------
# Data classes for normalized responses
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""
    name: str
    arguments: dict
    id: str | None = None  # Anthropic uses IDs; Ollama does not


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    tokens_per_second: float = 0.0


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

# Models in priority order. LiteLLM routes to the first available.
# Prefixes tell LiteLLM which provider to use.
PROVIDER_CHAIN = [
    # Fast free cloud (requires API keys set in env)
    "groq/llama-3.3-70b-versatile",
    "cerebras/llama-3.3-70b",
    # Google free tier
    "gemini/gemini-2.0-flash",
    # Local unlimited fallback (always available)
    "ollama_chat/qwen3:30b-a3b",
]

# Local-only chain (no cloud dependency)
LOCAL_ONLY_CHAIN = [
    "ollama_chat/qwen3:30b-a3b",
    "ollama_chat/qwen3:8b",
]

# Anthropic chain (paid, highest quality)
ANTHROPIC_CHAIN = [
    "anthropic/claude-sonnet-4-5-20250929",
]


def get_provider_chain() -> list[str]:
    """Select provider chain based on config."""
    mode = os.getenv("MUSER_LLM_MODE", "local")
    if mode == "local":
        return LOCAL_ONLY_CHAIN
    elif mode == "cloud":
        return PROVIDER_CHAIN
    elif mode == "anthropic":
        return ANTHROPIC_CHAIN
    else:  # "hybrid" — default
        return PROVIDER_CHAIN


# ---------------------------------------------------------------------------
# Core chat function
# ---------------------------------------------------------------------------

def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    num_ctx: int = 8192,
) -> LLMResponse:
    """
    Send a chat request to the best available LLM provider.

    If `model` is specified, uses that model directly.
    Otherwise, tries each model in the provider chain until one succeeds.

    Args:
        messages: OpenAI-format message list
        tools: OpenAI-format tool definitions (optional)
        model: Specific model string (optional, overrides chain)
        temperature: Sampling temperature
        max_tokens: Maximum response tokens
        num_ctx: Context window size (Ollama only)

    Returns:
        Normalized LLMResponse with content and/or tool_calls
    """
    chain = [model] if model else get_provider_chain()

    last_error = None
    for model_str in chain:
        try:
            logger.info(f"Trying provider: {model_str}")
            resp = _call_litellm(
                model_str, messages, tools, temperature, max_tokens, num_ctx
            )
            return resp
        except Exception as e:
            logger.warning(f"Provider {model_str} failed: {e}")
            last_error = e
            continue

    raise RuntimeError(
        f"All LLM providers failed. Last error: {last_error}"
    )


def _call_litellm(
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    temperature: float,
    max_tokens: int,
    num_ctx: int,
) -> LLMResponse:
    """Make the actual LiteLLM call and normalize the response."""
    import time as _time

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Only pass tools if we have them
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    # Ollama-specific options
    if model.startswith("ollama"):
        kwargs["api_base"] = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    t0 = _time.monotonic()
    response = litellm.completion(**kwargs)
    latency_ms = (_time.monotonic() - t0) * 1000.0

    # Normalize response
    msg = response.choices[0].message
    content = msg.content or ""

    # Qwen3 thinking mode: the model's actual answer may be in content
    # after a <think>...</think> block, or content may be empty while
    # reasoning_content holds the thinking.  Extract the non-think part.
    if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
        # Model spent all tokens thinking — use last sentence of reasoning
        # as a fallback so callers get *something*.
        logger.warning(
            "LLM returned empty content with reasoning_content. "
            "Consider increasing max_tokens."
        )
    if "<think>" in content:
        # Strip thinking tags to get only the final answer
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCall(
                name=tc.function.name,
                arguments=args,
                id=tc.id,
            ))

    # Calculate tokens/second from usage data
    tokens_per_second = 0.0
    usage = getattr(response, "usage", None)
    if usage and latency_ms > 0:
        total_tokens = getattr(usage, "completion_tokens", 0) or 0
        if total_tokens > 0:
            tokens_per_second = total_tokens / (latency_ms / 1000.0)

    logger.info(
        "LLM response: provider=%s, latency=%.0fms, tok/s=%.1f",
        model.split("/")[0], latency_ms, tokens_per_second,
    )

    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        raw=response,
        provider=model.split("/")[0],
        model=model,
        latency_ms=round(latency_ms, 1),
        tokens_per_second=round(tokens_per_second, 1),
    )


# ---------------------------------------------------------------------------
# Streaming chat
# ---------------------------------------------------------------------------

def chat_stream(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    num_ctx: int = 8192,
    on_token: "Callable[[str], None] | None" = None,
) -> LLMResponse:
    """Streaming version of chat(). Calls on_token for each text delta.

    Tool calls are accumulated and returned in the final LLMResponse.
    Falls back to non-streaming chat() if streaming fails.
    """
    import time as _time

    chain = [model] if model else get_provider_chain()

    for model_str in chain:
        try:
            return _stream_litellm(
                model_str, messages, tools, temperature, max_tokens, num_ctx, on_token,
            )
        except Exception as e:
            logger.warning("Streaming failed for %s: %s. Trying next.", model_str, e)
            continue

    logger.warning("All streaming providers failed. Falling back to non-streaming.")
    return chat(messages, tools, model, temperature, max_tokens, num_ctx)


def _stream_litellm(
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    temperature: float,
    max_tokens: int,
    num_ctx: int,
    on_token: "Callable[[str], None] | None",
) -> LLMResponse:
    """Execute a streaming LiteLLM call."""
    import time as _time

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if model.startswith("ollama"):
        kwargs["api_base"] = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    t0 = _time.monotonic()

    content_parts: list[str] = []
    tc_fragments: dict[int, dict] = {}

    for chunk in litellm.completion(**kwargs):
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        if delta.content:
            content_parts.append(delta.content)
            if on_token:
                on_token(delta.content)

        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index if hasattr(tc_delta, "index") else 0
                if idx not in tc_fragments:
                    tc_fragments[idx] = {"id": "", "name": "", "arguments": ""}
                frag = tc_fragments[idx]
                if tc_delta.id:
                    frag["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        frag["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        frag["arguments"] += tc_delta.function.arguments

    latency_ms = (_time.monotonic() - t0) * 1000.0
    content = "".join(content_parts)

    if "<think>" in content:
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    tool_calls = []
    for idx in sorted(tc_fragments.keys()):
        frag = tc_fragments[idx]
        if frag["name"]:
            args = frag["arguments"]
            try:
                args = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(name=frag["name"], arguments=args, id=frag["id"] or None))

    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        raw=None,
        provider=model.split("/")[0],
        model=model,
        latency_ms=round(latency_ms, 1),
    )


# ---------------------------------------------------------------------------
# Convenience: validate tool calls against known registry
# ---------------------------------------------------------------------------

def validate_tool_call(tool_call: ToolCall, valid_tools: set[str]) -> bool:
    """
    Reject hallucinated tool names.
    Local models sometimes invent tools that don't exist.
    """
    if tool_call.name not in valid_tools:
        logger.error(
            f"Hallucinated tool call: '{tool_call.name}' "
            f"not in {valid_tools}"
        )
        return False
    return True
