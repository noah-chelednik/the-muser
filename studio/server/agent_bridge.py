"""Bridge between the Studio's streaming chat and The Muser's agent loop.

Calls ``src.orchestrator.agent.run_agent_turn`` exactly like the Gradio UI
does, but in a worker thread, forwarding streamed tokens and tool activity
to the browser as Server-Sent Events.

Tool activity is observed by wrapping the ``execute_tool`` reference the agent
module uses (a thin, reversible wrapper - the upstream code is not modified).
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import capabilities, engine
from .store import AUDIO_EXT, tracks

_agent_lock = threading.Lock()  # tool executor state is process-global upstream
_local = threading.local()


@dataclass
class Session:
    id: str
    history: list[dict[str, Any]] = field(default_factory=list)
    state: Any = None


_sessions: dict[str, Session] = {}


def get_session(sid: str | None) -> Session:
    if sid and sid in _sessions:
        return _sessions[sid]
    s = Session(id=sid or uuid.uuid4().hex[:12])
    _sessions[s.id] = s
    return s


def _install_tool_hook() -> None:
    import src.orchestrator.agent as agent_mod

    if getattr(agent_mod.execute_tool, "_studio_hooked", False):
        return
    original = agent_mod.execute_tool

    def hooked(name: str, args: dict) -> dict:
        emit = getattr(_local, "emit", None)
        if emit:
            emit("tool_start", {"name": name, "args": _safe(args)})
        result = original(name, args)
        if emit:
            emit(
                "tool_end", {"name": name, "status": result.get("status"), "result": _safe(result)}
            )
        return result

    hooked._studio_hooked = True  # type: ignore[attr-defined]
    agent_mod.execute_tool = hooked


def _safe(obj: Any, limit: int = 1500) -> Any:
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    if len(s) > limit:
        return s[:limit] + "..."
    return json.loads(s) if s.startswith(("{", "[")) else s


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _find_new_audio(since: float, state: Any) -> list[Path]:
    roots = []
    if state is not None and getattr(state, "project_dir", ""):
        roots.append(Path(state.project_dir))
    from src.orchestrator.config import COMPOSITIONS_DIR

    roots.append(COMPOSITIONS_DIR)
    found = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.suffix.lower() in AUDIO_EXT and p.stat().st_mtime >= since:
                found.append(p)
    return found


def stream_chat(message: str, session_id: str | None, model: str | None) -> Iterator[str]:
    sess = get_session(session_id)
    caps = capabilities.detect(force=True)
    yield _sse("session", {"session_id": sess.id, "mode": caps.mode})

    if caps.mode == "demo":
        yield from _demo_reply(message, caps)
        return

    from src.orchestrator.agent import run_agent_turn
    from src.orchestrator.composition_state import CompositionState

    _install_tool_hook()
    if sess.state is None:
        sess.state = CompositionState()

    q: queue.Queue[tuple[str, Any] | None] = queue.Queue()
    started = time.time()

    def worker() -> None:
        _local.emit = lambda ev, data: q.put((ev, data))
        try:
            with _agent_lock:
                text = run_agent_turn(
                    user_message=message,
                    conversation_history=sess.history,
                    composition_state=sess.state,
                    model=model or None,
                    on_token=lambda tok: q.put(("token", {"text": tok})),
                )
            q.put(("final", {"text": text}))
        except Exception as e:  # pragma: no cover - depends on LLM availability
            q.put(("error", {"message": f"{type(e).__name__}: {e}"}))
        finally:
            _local.emit = None
            q.put(None)

    threading.Thread(target=worker, daemon=True, name="studio-agent").start()
    while True:
        try:
            item = q.get(timeout=15)
        except queue.Empty:
            yield ": keep-alive\n\n"
            continue
        if item is None:
            break
        yield _sse(*item)

    for p in _find_new_audio(started, sess.state):
        for t in tracks.scan_compositions():
            if Path(t.path) == p.resolve():
                yield _sse("track", {"track": t.to_public()})
    status = sess.state.to_context_string() if sess.state else ""
    yield _sse("done", {"status": status})


def _demo_reply(message: str, caps: capabilities.Capabilities) -> Iterator[str]:
    """Offline reply: parse the prompt locally and render a demo-synth sketch."""
    llm = caps.items.get("ollama")
    if caps.demo_forced:
        why = "demo mode was forced with --demo, so the LLM agent is not used"
    else:
        why = "no LLM is connected: " + (llm.detail if llm else "no provider configured")
    intro = (
        f"**Demo mode** - {why}. "
        "I parsed your prompt locally and rendered a synthesized multitrack sketch "
        "so you can try the stems, knobs and mixer. This is *not* AI-generated audio.\n\n"
    )
    for chunk in re.findall(r"\S+\s*", intro):
        yield _sse("token", {"text": chunk})
        time.sleep(0.012)

    yield _sse("tool_start", {"name": "demo_synth", "args": {"prompt": message}})
    try:
        dur = 20.0
        m = re.search(r"(\d+)\s*(?:s|sec|seconds)\b", message.lower())
        if m:
            dur = float(max(4, min(60, int(m.group(1)))))
        res = engine.generate(
            engine.GenerateRequest(prompt=message, duration_s=dur, force_demo=True)
        )
        t = res["track"]
        yield _sse(
            "tool_end", {"name": "demo_synth", "status": "success", "result": {"track_id": t["id"]}}
        )
        yield _sse("track", {"track": t})
        outro = (
            f"Rendered **{t['title']}** - {t['key']}, {t['bpm']} BPM, {t['duration_s']:.0f}s. "
            "Hit **Split** to load its 4 stems (drums, bass, chords, lead) into the mixer. "
            "Connect Ollama (`ollama pull qwen3:8b`) to talk to the real 46-tool agent."
        )
    except Exception as e:
        yield _sse("tool_end", {"name": "demo_synth", "status": "error", "result": str(e)})
        outro = f"Demo render failed: {e}"
    for chunk in re.findall(r"\S+\s*", outro):
        yield _sse("token", {"text": chunk})
        time.sleep(0.012)
    yield _sse("final", {"text": intro + outro})
    yield _sse("done", {"status": ""})
