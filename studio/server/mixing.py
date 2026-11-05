"""Rendering for Easy and Advanced modes.

Easy mode = a genre preset (per-role chains + master preset) modulated by five
macro sliders (presets/macros/easy_sliders.json). Advanced mode = explicit
per-stem chains, gain, pan, mute/solo and a master chain. Both end in the same
renderer, which never clips and never overwrites: it always makes a new child
track so undo is just "go back to the parent".
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from . import presets
from .engines import audio_io, dsp, fx, loudness, mastering
from .engines.errors import FriendlyError
from .store import Job, Track, jsonable, probe_duration, tracks

ROLE_WORDS = [
    ("vocals", ("vocal", "vox", "voice", "acapella", "sing")),
    ("drums", ("drum", "kick", "snare", "perc", "hat", "beat")),
    ("bass", ("bass", "808", "sub", "low (")),
    ("guitar", ("guitar",)),
    ("lead", ("lead", "melody", "synth", "high-mid", "air")),
    (
        "keys",
        ("chord", "key", "piano", "pad", "organ", "low-mid", "instrumental", "other", "no_vocals"),
    ),
]


def role_for(name: str) -> str:
    n = name.lower()
    for role, words in ROLE_WORDS:
        if any(w in n for w in words):
            return role
    return "other"


def _lerp(v, t: float):
    if isinstance(v, list) and len(v) == 2 and all(isinstance(a, (int, float)) for a in v):
        return v[0] + (v[1] - v[0]) * t
    return v


def _active_t(value: float, when: str) -> float | None:
    x = min(max(value, 0), 100) / 100
    if when == "above":
        return None if x <= 0.5 else (x - 0.5) * 2
    if when == "below":
        return None if x >= 0.5 else x * 2
    return x


def plan_easy(
    genre_id: str | None, values: dict[str, float], stem_names: list[str]
) -> dict[str, Any]:
    """Build a render plan: {stems: {name: {chain, gain_db}}, master: chain, master_preset}."""
    g = presets.get(genre_id) if genre_id else None
    has_stems = bool(stem_names)
    plan: dict[str, Any] = {
        "stems": {},
        "master": [],
        "master_preset": None,
        "genre": genre_id,
        "macros": {},
    }
    role_chains = (g or {}).get("stems", {})
    for name in stem_names:
        role = role_for(name)
        ref = role_chains.get(role) or (
            role_chains.get("keys") if role in ("other", "guitar") else None
        )
        plan["stems"][name] = {
            "role": role,
            "chain": presets.chain_of(ref) if ref else [],
            "gain_db": 0.0,
        }
    mref = (g or {}).get("master")
    if isinstance(mref, str):
        plan["master_preset"] = mref
    for slider in presets.macros()["sliders"]:
        key = slider["key"]
        val = float(values.get(key, 50))
        plan["macros"][key] = val
        for m in slider["maps"]:
            only = m.get("only")
            if (only == "stems" and not has_stems) or (only == "mix" and has_stems):
                continue
            t = _active_t(val, m.get("when", "both"))
            if t is None:
                continue
            scope = m["scope"]
            if scope == "master":
                targets = None
            elif scope.startswith("role:"):
                targets = {scope[5:]}
            else:
                targets = set(scope.split(":", 1)[1].split(","))
            if m["op"] == "gain":
                amt = float(_lerp(m["value"], t))
                for st in plan["stems"].values():
                    if targets and st["role"] in targets:
                        st["gain_db"] += amt
            elif m["op"] == "insert":
                item = copy.deepcopy(m["fx"])
                item["params"] = {k: _lerp(v, t) for k, v in item["params"].items()}
                if targets is None:
                    plan["master"].append(item)
                else:
                    for st in plan["stems"].values():
                        if st["role"] in targets:
                            st["chain"] = st["chain"] + [copy.deepcopy(item)]
    return plan


def _pan(x: np.ndarray, pan: float) -> np.ndarray:
    if abs(pan) < 1e-3:
        return x
    ang = (pan + 1) * np.pi / 4
    return x * np.array([np.cos(ang), np.sin(ang)], dtype=np.float32) * np.sqrt(2)


def render(
    sources: list[dict], master_chain: list[dict], job: Job | None = None, sr_out: int | None = None
) -> tuple[np.ndarray, int, list[str]]:
    """sources: [{path, chain, gain_db, pan}]. Returns (audio, sr, engines_used)."""
    if not sources:
        raise FriendlyError("Nothing to render: every stem is muted.")
    used: set[str] = set()
    mix = None
    sr = sr_out
    for i, s in enumerate(sources):
        if job:
            job.message = f"Processing {s.get('name', 'audio')} ({i + 1}/{len(sources)})"
        x, sr_i = audio_io.read(s["path"], sr)
        sr = sr or sr_i
        x = audio_io.to_stereo(x)
        if s.get("chain"):
            x, eng = fx.render_chain(x, sr, s["chain"])
            used.add(eng)
        x = _pan(x * dsp.db2lin(float(s.get("gain_db", 0.0))), float(s.get("pan", 0.0)))
        if mix is None:
            mix = x
        else:
            n = max(len(mix), len(x))
            if len(mix) < n:
                mix = np.pad(mix, ((0, n - len(mix)), (0, 0)))
            if len(x) < n:
                x = np.pad(x, ((0, n - len(x)), (0, 0)))
            mix = mix + x
    assert mix is not None and sr is not None
    if job:
        job.message = "Master bus ..."
    # Gain-stage before the master chain so compressors see a sensible level.
    lufs = loudness.integrated_lufs(mix, sr)
    if np.isfinite(lufs):
        mix = mix * dsp.db2lin(float(np.clip(-18.0 - lufs, -30, 30)))
    if master_chain:
        mix, eng = fx.render_chain(mix, sr, master_chain)
        used.add(eng)
    # Pre-master level: about -16 LUFS with a -1 dBTP safety limiter, never clips.
    lufs = loudness.integrated_lufs(mix, sr)
    if np.isfinite(lufs):
        mix = mix * dsp.db2lin(float(np.clip(-16.0 - lufs, -30, 30)))
    mix = dsp.true_peak_limit(mix, sr, ceiling_db=-1.0)
    return mix.astype(np.float32), sr, sorted(used)


def new_child(
    parent: Track, audio: np.ndarray, sr: int, title: str, source: str, notes: str, meta: dict
) -> Track:
    tid, tdir = tracks.new_dir()
    out = tdir / "mix.wav"
    audio_io.write(out, audio, sr)
    child = Track(
        id=tid,
        title=title,
        source=source,
        path=str(out),
        created=time.time(),
        prompt=parent.prompt,
        bpm=parent.bpm,
        key=parent.key,
        duration_s=probe_duration(out),
        parent_id=parent.id,
        notes=notes,
        meta=jsonable(meta),
    )
    # Keep stems available on the child so the user can keep tweaking.
    child.stems = list(parent.stems)
    child.stem_method = parent.stem_method
    return tracks.save(child)


def _get(tid: str) -> Track:
    t = tracks.get(tid)
    if not t:
        raise FriendlyError("That song is no longer in the library.")
    return t


# --------------------------------------------------------------------------- Easy


class EasyRender(BaseModel):
    track_id: str
    genre_id: str | None = None
    energy: float = Field(50, ge=0, le=100)
    vocals: float = Field(50, ge=0, le=100)
    bass: float = Field(50, ge=0, le=100)
    brightness: float = Field(50, ge=0, le=100)
    space: float = Field(50, ge=0, le=100)


def easy_render(req: EasyRender, job: Job | None = None) -> dict[str, Any]:
    t = _get(req.track_id)
    root = tracks.get(t.meta.get("easy_root", "")) if t.meta.get("easy_root") else None
    base = root or t  # re-render from the original so slider moves don't stack
    stem_paths = {s.name: s.path for s in base.stems} or dict(base.hidden_stems)
    values = req.model_dump(include={"energy", "vocals", "bass", "brightness", "space"})
    plan = plan_easy(req.genre_id, values, list(stem_paths))
    if stem_paths:
        sources = [
            {
                "name": n,
                "path": p,
                "chain": plan["stems"][n]["chain"],
                "gain_db": plan["stems"][n]["gain_db"],
            }
            for n, p in stem_paths.items()
        ]
    else:
        sources = [{"name": "mix", "path": base.path, "chain": []}]
    audio, sr, used = render(sources, plan["master"], job)
    label = (
        ", ".join(f"{k[:1].upper()}{k[1:]} {int(v)}" for k, v in values.items() if abs(v - 50) >= 1)
        or "vibe defaults"
    )
    child = new_child(
        base,
        audio,
        sr,
        f"{base.title} (tuned)",
        "easy-mix",
        f"Easy mix: {label}.",
        {
            "easy_root": base.id,
            "plan": plan,
            "fx_engines": used,
            "analysis": loudness.analyze(audio, sr),
        },
    )
    return {"track": child.to_public(), "plan": plan}


# --------------------------------------------------------------------------- Finish


class FinishRequest(BaseModel):
    track_id: str
    target: str = "spotify"
    preset_id: str | None = None  # a master preset; default = platform preset
    chain: list[dict] | None = None  # advanced: explicit chain
    lufs: float | None = Field(None, ge=-30, le=-5)
    true_peak_db: float | None = Field(None, ge=-6, le=0)


def finish(req: FinishRequest, job: Job | None = None) -> dict[str, Any]:
    t = _get(req.track_id)
    if req.target not in mastering.TARGETS:
        raise FriendlyError(f"Unknown platform '{req.target}'.")
    chain = req.chain
    preset_used = None
    if chain is None:
        pid = req.preset_id or f"master/{_platform_slug(req.target)}"
        try:
            p = presets.get(pid)
            chain = p["master"]["chain"]
            preset_used = pid
        except FriendlyError:
            chain = []
    if job:
        job.message = f"Mastering for {mastering.TARGETS[req.target].label} ..."
    x, sr = audio_io.read(t.path)
    y, report = mastering.finish(
        x, sr, req.target, chain, lufs=req.lufs, true_peak=req.true_peak_db
    )
    report["preset"] = preset_used
    tgt = mastering.TARGETS[req.target]
    child = new_child(
        t,
        y,
        sr,
        f"{t.title} ({tgt.label})",
        "master",
        f"Finished for {tgt.label}: {report['lufs']:.1f} LUFS, {report['true_peak_db']:.1f} dBTP.",
        {"master": report, "easy_root": t.meta.get("easy_root", ""), "finished": True},
    )
    return {"track": child.to_public(), "report": report}


def _platform_slug(target: str) -> str:
    label = mastering.TARGETS[target].label
    import re

    return re.sub(r"[^a-z0-9]+", "-", f"{label} master".lower()).strip("-")


# --------------------------------------------------------------------------- Advanced


class StemChain(BaseModel):
    stem_id: str
    chain: list[dict] = Field(default_factory=list)
    gain_db: float = Field(0.0, ge=-60, le=12)
    pan: float = Field(0.0, ge=-1, le=1)
    mute: bool = False
    solo: bool = False


class AdvancedRender(BaseModel):
    track_id: str
    stems: list[StemChain] = Field(default_factory=list)
    master_chain: list[dict] = Field(default_factory=list)


def advanced_render(req: AdvancedRender, job: Job | None = None) -> dict[str, Any]:
    t = _get(req.track_id)
    try:
        master = fx.normalize_chain(req.master_chain)
        by_id = {s.id: s for s in t.stems}
        any_solo = any(s.solo for s in req.stems)
        sources = []
        for i, s in enumerate(req.stems):
            st = by_id.get(s.stem_id)
            if st is None and len(req.stems) == len(t.stems):
                # stems were replaced (for example re-split) while the request was in flight: match by position
                st = t.stems[i]
            if st is None or s.mute or (any_solo and not s.solo):
                continue
            sources.append(
                {
                    "name": st.name,
                    "path": st.path,
                    "chain": fx.normalize_chain(s.chain),
                    "gain_db": s.gain_db,
                    "pan": s.pan,
                }
            )
    except ValueError as e:
        raise FriendlyError(f"A setting is out of range: {e}") from e
    if not t.stems:
        sources = [{"name": "mix", "path": t.path, "chain": []}]
    audio, sr, used = render(sources, master, job)
    child = new_child(
        t,
        audio,
        sr,
        f"{t.title} (advanced mix)",
        "mixdown",
        f"Advanced render of {len(sources)} source(s).",
        {"advanced": req.model_dump(), "fx_engines": used, "analysis": loudness.analyze(audio, sr)},
    )
    return {"track": child.to_public()}


def preview_chain(
    chain: list[dict], src: str, out: Path, seconds: float = 8.0, start_s: float | None = None
) -> dict:
    x, sr = audio_io.read(src)
    n = int(seconds * sr)
    s0 = int((start_s if start_s is not None else max(0.0, len(x) / sr * 0.3)) * sr)
    s0 = min(s0, max(0, len(x) - n))
    seg = audio_io.to_stereo(x[s0 : s0 + n])
    y, eng = fx.render_chain(seg, sr, chain)
    # Loudness-match the preview to the dry clip so "better" isn't just "louder".
    a, b = loudness.integrated_lufs(seg, sr), loudness.integrated_lufs(y, sr)
    if np.isfinite(a) and np.isfinite(b):
        y = y * dsp.db2lin(float(np.clip(a - b, -24, 24)))
    y = dsp.true_peak_limit(y, sr, ceiling_db=-1.0)
    audio_io.write(out, y, sr)
    return {"engine": eng, "seconds": len(seg) / sr}
