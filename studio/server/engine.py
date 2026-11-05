"""Audio operations for the Studio, built on The Muser's existing tools.

* Generation  -> ``execute_tool("generate_audio_acestep_v15")`` when ACE-Step is
  available, otherwise the clearly-labelled demo synthesizer.
* Splitting   -> ``src.voice.demucs_wrapper.separate_stems`` (the repo's
  ``separate_stems_demucs`` tool), else pre-rendered demo stems or a band split.
* Per-stem FX -> ``src.audio.effects`` (apply_eq / apply_compression /
  apply_reverb / adjust_volume - the same functions behind the LLM tools).
* Mixdown     -> ``src.audio.mixer.mix_n_tracks`` (the ``mix_tracks`` tool).
* Export      -> ``src.audio.export.export_composition`` (``export_final``).
"""

from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import capabilities, demo_synth
from .store import EXPORTS_DIR, Job, Stem, Track, color_for, file_url, probe_duration, tracks


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    lyrics: str = ""
    duration_s: float = Field(20.0, ge=4, le=240)
    bpm: int | None = Field(None, ge=40, le=220)
    key: str = ""
    title: str = ""
    force_demo: bool = False
    # Optional ACE-Step overrides, filled from a genre preset's ``generate.acestep`` block.
    tags: str = Field("", max_length=1500)
    infer_step: int | None = Field(None, ge=1, le=200)
    guidance_scale: float | None = Field(None, ge=0, le=30)
    time_signature: str = Field("", max_length=4)


class StemParams(BaseModel):
    stem_id: str
    gain_db: float = Field(0.0, ge=-60, le=12)
    pan: float = Field(0.0, ge=-1, le=1)
    mute: bool = False
    solo: bool = False
    eq_low_db: float = Field(0.0, ge=-18, le=18)
    eq_mid_db: float = Field(0.0, ge=-18, le=18)
    eq_high_db: float = Field(0.0, ge=-18, le=18)
    comp: float = Field(0.0, ge=0, le=1)
    reverb: float = Field(0.0, ge=0, le=1)
    room: float = Field(0.5, ge=0, le=1)


class MixRequest(BaseModel):
    track_id: str
    stems: list[StemParams]
    master_gain_db: float = Field(0.0, ge=-24, le=12)
    normalize: bool = True


class ExportRequest(BaseModel):
    track_id: str
    formats: list[str] = Field(default_factory=lambda: ["wav", "mp3"])
    include_stems: bool = False
    title: str = ""
    artist: str = "NoDAW Labs x The Muser"
    normalize: bool = True


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate(req: GenerateRequest, job: Job | None = None) -> dict[str, Any]:
    caps = capabilities.detect()
    use_model = caps.mode == "full" and not req.force_demo and caps.ok("acestep")
    tid, tdir = tracks.new_dir()

    if use_model:
        if job:
            job.message = "Generating with ACE-Step (this can take minutes)..."
        from src.orchestrator.tool_executor import execute_tool

        result = execute_tool(
            "generate_audio_acestep_v15",
            {
                "tags": req.tags or req.prompt,
                "lyrics": req.lyrics or "[instrumental]",
                "duration_s": req.duration_s,
                "bpm": req.bpm,
                "key_scale": req.key,
                "num_candidates": 1,
                **({"infer_step": req.infer_step} if req.infer_step else {}),
                **({"guidance_scale": req.guidance_scale} if req.guidance_scale is not None else {}),
                **({"time_signature": req.time_signature} if req.time_signature else {}),
            },
        )
        if result.get("status") != "success" or not result.get("wav_paths"):
            raise RuntimeError(f"ACE-Step failed: {result.get('error', result)}")
        src_path = Path(result["wav_paths"][0])
        dst = tdir / "mix.wav"
        shutil.copy2(src_path, dst)
        t = Track(
            id=tid,
            title=req.title or req.prompt[:48],
            source="acestep",
            path=str(dst),
            created=time.time(),
            prompt=req.prompt,
            bpm=req.bpm,
            key=req.key,
            duration_s=probe_duration(dst),
            notes=result.get("note", ""),
        )
        return {"track": tracks.save(t).to_public(), "engine": "acestep"}

    if job:
        job.message = "Demo mode: synthesizing a multitrack sketch..."
    spec = demo_synth.parse_prompt(
        req.prompt, bpm=req.bpm, key=req.key or None, duration_s=req.duration_s
    )
    out = demo_synth.render(spec, tdir)
    reason = (
        "forced demo"
        if req.force_demo or caps.demo_forced
        else "ACE-Step not available on this machine"
    )
    t = Track(
        id=tid,
        title=req.title or f"Sketch - {spec.genre} {spec.key_name} {spec.bpm}bpm",
        source="demo-synth",
        path=out["mix"],
        created=time.time(),
        prompt=req.prompt,
        bpm=spec.bpm,
        key=spec.key_name,
        duration_s=round(out["duration_s"], 2),
        hidden_stems=out["stems"],
        notes=f"Demo synthesizer ({reason}). Not AI-generated audio.",
    )
    return {"track": tracks.save(t).to_public(), "engine": "demo-synth", "reason": reason}


# ---------------------------------------------------------------------------
# Stem separation
# ---------------------------------------------------------------------------


def split(
    track_id: str,
    mode: str = "4stem",
    job: Job | None = None,
    engine: str = "auto",
    model: str | None = None,
) -> dict[str, Any]:
    """Split a track into stems.

    Order: the demo synth's exact sources, then the engine registry's best
    separator (Audio Separator / Demucs), then the band-split fallback. Demo
    mode keeps the band-split fallback unless an engine is picked explicitly.
    """
    t = tracks.get(track_id)
    if not t:
        raise KeyError(f"Unknown track {track_id}")
    caps = capabilities.detect()
    out_dir = Path(t.path).parent / f"stems_{mode}{'_' + engine if engine != 'auto' else ''}"

    def progress(msg: str) -> None:
        if job:
            job.message = msg

    if t.hidden_stems and mode == "4stem" and engine == "auto":
        stems = t.hidden_stems
        method = "demo-synth"
        note = "Stems are the demo synthesizer's own source tracks (exact, not separated)."
    elif engine != "auto" or not caps.demo_forced:
        from .engines import selector, separation
        from .engines.errors import FriendlyError

        chosen = engine
        if engine == "auto":
            try:
                chosen = selector.select("separate").engine
            except FriendlyError:
                chosen = "band-split"
        if job:
            job.message = (
                f"Splitting with {chosen} (on CPU this can take about the length of the song)..."
            )
        res = separation.separate(
            t.path, out_dir, mode=mode, engine=chosen, model=model, progress=progress
        )
        stems = res["stems"]
        method = res["engine"] if res["engine"] == "band-split" else f"{res['engine']}-{mode}"
        note = res["note"]
    else:
        if job:
            job.message = "Demo mode: using 4-band crossover fallback..."
        stems = demo_synth.band_split(t.path, out_dir)
        method = "band-split"
        note = "Demo mode: frequency-band split (crossover), not true source separation."

    t.stems = [
        Stem(id=f"{t.id}:{i}", name=name, path=str(Path(p).resolve()), color=color_for(name, i))
        for i, (name, p) in enumerate(stems.items())
    ]
    t.stem_method = method
    t.notes = note
    tracks.save(t)
    return {"track": t.to_public(), "method": method, "note": note}


# ---------------------------------------------------------------------------
# Per-stem processing + mixdown (server render)
# ---------------------------------------------------------------------------


def _process_stem(src: str, p: StemParams, work: Path, idx: int) -> str:
    from src.audio.effects import apply_compression, apply_eq, apply_reverb

    cur = src
    step = 0

    def nxt() -> str:
        nonlocal step
        step += 1
        return str(work / f"s{idx}_{step}.wav")

    for freq, gain, q in (
        (100, p.eq_low_db, 0.7),
        (1000, p.eq_mid_db, 1.0),
        (8000, p.eq_high_db, 0.7),
    ):
        if abs(gain) >= 0.1:
            cur = apply_eq(cur, nxt(), frequency_hz=freq, gain_db=round(gain, 2), q=q)
    if p.comp > 0.01:
        cur = apply_compression(
            cur,
            nxt(),
            threshold_db=round(-6 - 30 * p.comp, 1),
            ratio=round(1.5 + 6.5 * p.comp, 2),
        )
    if p.reverb > 0.01:
        cur = apply_reverb(
            cur, nxt(), room_size=p.room, decay=round(0.2 + 0.5 * p.reverb, 2), mix=p.reverb
        )
    return cur


def mix(req: MixRequest, job: Job | None = None) -> dict[str, Any]:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for server-side mixdown (install ffmpeg)")
    from src.audio.effects import adjust_volume
    from src.audio.mixer import mix_n_tracks

    t = tracks.get(req.track_id)
    if not t or not t.stems:
        raise KeyError("Track has no stems - split it first")
    by_id = {s.id: s for s in t.stems}
    any_solo = any(s.solo for s in req.stems)
    active = [
        s for s in req.stems if s.stem_id in by_id and not s.mute and (s.solo or not any_solo)
    ]
    if not active:
        raise ValueError("All stems are muted")

    stamp = time.strftime("%H%M%S")
    work = Path(t.path).parent / f"mixwork_{stamp}"
    work.mkdir(exist_ok=True)
    processed = []
    for i, p in enumerate(active):
        if job:
            job.message = f"Processing {by_id[p.stem_id].name} ({i + 1}/{len(active)})"
        path = _process_stem(by_id[p.stem_id].path, p, work, i)
        processed.append({"path": path, "volume_db": round(p.gain_db, 2), "pan": round(p.pan, 3)})

    out = Path(t.path).parent / f"mixdown_{stamp}.wav"
    if job:
        job.message = "Summing stems (mix_n_tracks)..."
    if len(processed) >= 2:
        mixed = mix_n_tracks(processed, str(work / "sum.wav"), normalize=req.normalize)
    else:
        only = processed[0]
        mixed = adjust_volume(only["path"], str(work / "sum.wav"), only["volume_db"])
    if abs(req.master_gain_db) >= 0.1:
        mixed = adjust_volume(mixed, str(work / "master.wav"), req.master_gain_db)
    shutil.copy2(mixed, out)
    shutil.rmtree(work, ignore_errors=True)

    tid, tdir = tracks.new_dir()
    final = tdir / "mix.wav"
    shutil.move(str(out), final)
    child = Track(
        id=tid,
        title=f"{t.title} (mix {stamp})",
        source="mixdown",
        path=str(final),
        created=time.time(),
        prompt=t.prompt,
        bpm=t.bpm,
        key=t.key,
        duration_s=probe_duration(final),
        parent_id=t.id,
        notes=f"Rendered from {len(active)} stem(s) with src.audio.effects + mix_n_tracks.",
    )
    return {"track": tracks.save(child).to_public()}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export(req: ExportRequest, job: Job | None = None) -> dict[str, Any]:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for export (install ffmpeg)")
    from src.audio.export import export_composition

    t = tracks.get(req.track_id)
    if not t:
        raise KeyError("Unknown track")
    formats = [f for f in req.formats if f in ("wav", "mp3", "flac")] or ["wav"]
    out_dir = EXPORTS_DIR / t.id
    if job:
        job.message = f"Exporting {', '.join(formats)} (loudness normalize: {req.normalize})"
    outputs = export_composition(
        wav_path=t.path,
        output_dir=str(out_dir),
        formats=formats,
        title=req.title or t.title,
        artist=req.artist,
        genre="",
        normalize=req.normalize,
    )
    files = {fmt: file_url(p) for fmt, p in outputs.items()}
    if req.include_stems and t.stems:
        zpath = out_dir / f"{t.id}_stems.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for s in t.stems:
                z.write(s.path, arcname=f"{s.name.replace(' ', '_')}.wav")
        files["stems_zip"] = file_url(zpath)
    return {"files": files}


def import_upload(path: Path, title: str) -> Track:
    tid, tdir = tracks.new_dir()
    dst = tdir / ("source" + path.suffix.lower())
    shutil.move(str(path), dst)
    final = dst
    if dst.suffix != ".wav" and shutil.which("ffmpeg"):
        import subprocess

        final = tdir / "mix.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(dst), str(final)], check=True, capture_output=True
        )
    t = Track(
        id=tid,
        title=title or dst.stem,
        source="upload",
        path=str(final),
        created=time.time(),
        duration_s=probe_duration(final),
    )
    return tracks.save(t)
