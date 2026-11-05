"""All-in-one API: engines, hardware, presets, Easy mode, Finish, one-click tools,
Advanced render and session autosave. Included before the SPA catch-all."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import engine, mixing, presets
from .engines import (
    audio_io,
    cleanup,
    fx,
    generation,
    hardware,
    installer,
    loudness,
    mastering,
    reference,
    registry,
    selector,
    separation,
    transcribe,
)
from .engines.errors import FriendlyError
from .store import DATA_DIR, EXPORTS_DIR, Job, Track, file_url, jobs, probe_duration, tracks

router = APIRouter(prefix="/api")
SESSION_FILE = DATA_DIR / "session.json"


def _job(kind: str, fn) -> dict:
    j = jobs.submit(kind, fn)
    return {"job_id": j.id, "status": j.status}


def _track(tid: str) -> Track:
    t = tracks.get(tid)
    if not t:
        raise HTTPException(404, "That song is no longer in the library.")
    return t


def _friendly(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except FriendlyError as e:
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\"")) from e


# --------------------------------------------------------------------------- engines


@router.get("/hardware")
def get_hardware(refresh: bool = False) -> dict:
    hw = hardware.detect(force=refresh)
    return {
        "hardware": hw.to_dict(),
        "tier": hw.tier(),
        "recommendations": selector.recommendations(hw),
    }


@router.get("/engines")
def list_engines(commercial_only: bool = True) -> dict:
    hw = hardware.detect()
    out = []
    for spec in registry.ENGINES:
        h = registry.health(spec)
        v = selector.verdict(spec, hw)
        ok = v["status"] in ("cpu", "fits", "fits-reduced", "tight")
        out.append(
            {
                **spec.public(),
                "health": h,
                "fits": ok,
                "fit_reason": v["reason"],
                "fit": v,
            }
        )
    picks = {}
    for task in registry.TASKS:
        try:
            c = selector.select(task, hw, commercial_only=commercial_only)
            picks[task] = {
                "engine": c.engine,
                "name": c.name,
                "reasons": c.reasons,
                "alternatives": c.alternatives,
                "upgrades": c.upgrades,
            }
        except FriendlyError as e:
            picks[task] = {
                "engine": None,
                "name": None,
                "reasons": [str(e)],
                "alternatives": [],
                "upgrades": [],
            }
    return {"engines": out, "tasks": registry.TASKS, "selected": picks}


@router.get("/engines/{key}/health")
def engine_health(key: str, deep: bool = False) -> dict:
    spec = _friendly(registry.get, key)
    return registry.health(spec, deep=deep)


@router.post("/engines/{key}/install")
def engine_install(key: str, dry_run: bool = False) -> dict:
    _friendly(registry.get, key)

    def run(job: Job) -> dict:
        lines: list[str] = []

        def log(m: str) -> None:
            lines.append(m)
            job.message = m[-200:]

        res = installer.install(key, log=log, dry_run=dry_run)
        hardware.detect(force=True)
        return {**res, "health": registry.health(registry.get(key))}

    return _job("install", run)


@router.get("/fx/plugins")
def fx_plugins() -> dict:
    return {"plugins": fx.PLUGINS}


@router.get("/mastering/targets")
def master_targets() -> dict:
    return {
        "targets": {
            k: {
                "label": v.label,
                "lufs": v.lufs,
                "true_peak_db": v.true_peak_db,
                "easy": v.easy,
                "note": v.note,
            }
            for k, v in mastering.TARGETS.items()
        }
    }


# --------------------------------------------------------------------------- presets


@router.get("/presets")
def list_presets(
    category: str | None = None, q: str | None = None, favorites: bool = False
) -> dict:
    return {
        "presets": presets.listing(category, q, favorites),
        "counts": presets.counts(),
        "categories": presets.CATEGORIES,
    }


@router.get("/presets/macros")
def get_macros() -> dict:
    return presets.macros()


@router.get("/presets/export")
def export_presets(ids: str = "") -> JSONResponse:
    bundle = presets.export_bundle([i for i in ids.split(",") if i] or None)
    return JSONResponse(
        bundle, headers={"Content-Disposition": 'attachment; filename="muser-presets.json"'}
    )


@router.get("/presets/{pid:path}/item")
def get_preset(pid: str) -> dict:
    return _friendly(presets.get, pid)


class SavePreset(BaseModel):
    preset: dict


@router.post("/presets")
def save_preset(req: SavePreset) -> dict:
    return {"preset": _friendly(presets.save_user, req.preset)}


@router.delete("/presets/{pid:path}/item")
def delete_preset(pid: str) -> dict:
    return {"deleted": _friendly(presets.delete_user, pid)}


@router.post("/presets/{pid:path}/favorite")
def favorite_preset(pid: str) -> dict:
    return {"favorite": _friendly(presets.toggle_favorite, pid)}


@router.post("/presets/import")
async def import_presets(file: UploadFile = File(...)) -> dict:
    try:
        data = json.loads((await file.read()).decode("utf-8"))
    except Exception as e:
        raise HTTPException(400, "That file isn't a valid preset JSON file.") from e
    return {"imported": _friendly(presets.import_bundle, data)}


class PreviewRequest(BaseModel):
    preset_id: str | None = None
    chain: list[dict] | None = None
    track_id: str | None = None
    stem_id: str | None = None
    seconds: float = Field(8.0, ge=2, le=20)


@router.post("/presets/preview")
def preview_preset(req: PreviewRequest) -> dict:
    def run(job: Job) -> dict:
        if req.chain is not None:
            chain = fx.normalize_chain(req.chain)
        elif req.preset_id:
            p = presets.get(req.preset_id)
            if p["category"] == "genre":
                chain = (
                    presets.chain_of(p.get("master")) if isinstance(p.get("master"), str) else []
                )
            else:
                chain = presets.chain_of(req.preset_id)
        else:
            raise FriendlyError("Pick a preset to preview.")
        src = _preview_source(req.track_id, req.stem_id, req.preset_id)
        out = DATA_DIR / "previews" / f"pv_{int(time.time() * 1000)}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        dry = out.with_name(out.stem + "_dry.wav")
        info = mixing.preview_chain(chain, src, out, req.seconds)
        mixing.preview_chain([], src, dry, req.seconds)
        return {"url": file_url(out), "dry_url": file_url(dry), **info}

    return _job("preview", run)


def _preview_source(track_id: str | None, stem_id: str | None, preset_id: str | None) -> str:
    if track_id:
        t = tracks.get(track_id)
        if t:
            if stem_id:
                s = next((s for s in t.stems if s.id == stem_id), None)
                if s:
                    return s.path
            return t.path
    loop = DATA_DIR / "previews" / "demo_loop.wav"
    if not loop.exists():
        from . import demo_synth

        spec = demo_synth.parse_prompt("lofi chill beat", duration_s=10, bpm=90)
        d = DATA_DIR / "previews" / "demo_src"
        d.mkdir(parents=True, exist_ok=True)
        out = demo_synth.render(spec, d)
        shutil.copy2(out["mix"], loop)
    return str(loop)


# --------------------------------------------------------------------------- Easy mode


@router.get("/vibes")
def vibes() -> dict:
    tiles = [p for p in presets.listing("genre") if p.get("easy")]
    targets = master_targets()["targets"]
    return {
        "vibes": tiles,
        "sliders": presets.macros()["sliders"],
        "finish": {k: v for k, v in targets.items() if v["easy"]},
    }


def match_vibe(text: str) -> str:
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    best, best_score = "genre/pop", 0.0
    for p in presets.listing("genre"):
        hay = set(
            re.findall(
                r"[a-z0-9]+",
                " ".join(
                    [
                        p["name"],
                        " ".join(p.get("tags", [])),
                        p.get("description", ""),
                        p["generate"]["prompt"],
                    ]
                ).lower(),
            )
        )
        name = set(
            re.findall(r"[a-z0-9]+", (p["name"] + " " + " ".join(p.get("tags", []))).lower())
        )
        score = len(words & hay) + 2 * len(words & name)
        if score > best_score:
            best, best_score = p["id"], score
    return best


class EasyMake(BaseModel):
    genre_id: str | None = None
    vibe: str = Field("", max_length=500)
    lyrics: str = Field("", max_length=4000)
    duration_s: float | None = Field(None, ge=8, le=240)
    energy: float | None = Field(None, ge=0, le=100)
    vocals: float | None = Field(None, ge=0, le=100)
    bass: float | None = Field(None, ge=0, le=100)
    brightness: float | None = Field(None, ge=0, le=100)
    space: float | None = Field(None, ge=0, le=100)


@router.post("/easy/make")
def easy_make(req: EasyMake) -> dict:
    if not req.genre_id and not req.vibe.strip():
        raise HTTPException(400, "Pick a vibe tile or describe the vibe first.")
    gid = req.genre_id or match_vibe(req.vibe)
    g = _friendly(presets.get, gid)

    def run(job: Job) -> dict:
        gen = g["generate"]
        prompt = f"{req.vibe.strip()}, {gen['prompt']}" if req.vibe.strip() else gen["prompt"]
        ace = gen.get("acestep") or {}
        # With the real model, use the genre's tuned ACE-Step tags; the user's own words come first.
        tags = ""
        if ace.get("tags"):
            tags = (f"{req.vibe.strip()}, {ace['tags']}" if req.vibe.strip() else ace["tags"])[:1500]
        job.message = f"Writing a {g['name']} track..."
        res = engine.generate(
            engine.GenerateRequest(
                prompt=prompt[:2000],
                lyrics=req.lyrics or gen.get("lyrics", ""),
                duration_s=req.duration_s or ace.get("duration_s") or gen.get("duration_s", 30),
                bpm=gen.get("bpm"),
                key=str(ace.get("key_scale") or ""),
                title=f"{g['name']} idea",
                tags=tags,
                infer_step=ace.get("infer_step"),
                guidance_scale=ace.get("guidance_scale"),
                time_signature=str(ace.get("time_signature") or ""),
            ),
            job,
        )
        root_id = res["track"]["id"]
        root = tracks.get(root_id)
        if root:
            root.meta = {**root.meta, "genre_id": gid, "easy": True}
            tracks.save(root)
        job.message = "Splitting into stems so the sliders can shape each part..."
        try:
            engine.split(root_id, "4stem", job)
        except Exception as e:  # sliders still work on the full mix
            job.message = f"Stems unavailable ({e}); shaping the full mix instead."
        macros = {
            k: (getattr(req, k) if getattr(req, k) is not None else g["macros"][k])
            for k in ("energy", "vocals", "bass", "brightness", "space")
        }
        job.message = "Mixing with your vibe..."
        out = mixing.easy_render(mixing.EasyRender(track_id=root_id, genre_id=gid, **macros), job)
        return {
            **out,
            "root_id": root_id,
            "genre_id": gid,
            "macros": macros,
            "engine": res.get("engine"),
        }

    return _job("easy-make", run)


@router.post("/easy/render")
def easy_render(req: mixing.EasyRender) -> dict:
    _track(req.track_id)
    return _job("easy-render", lambda j: mixing.easy_render(req, j))


@router.post("/finish")
def finish(req: mixing.FinishRequest) -> dict:
    _track(req.track_id)
    if req.target not in mastering.TARGETS:
        raise HTTPException(400, f"Unknown platform '{req.target}'.")
    return _job("finish", lambda j: mixing.finish(req, j))


# --------------------------------------------------------------------------- one-click tools


class ToolRequest(BaseModel):
    track_id: str
    engine: str = "auto"
    model: str | None = None
    mode: str = Field("4stem", pattern="^(4stem|2stem)$")
    strength: float = Field(0.8, ge=0, le=1)
    reference_track_id: str | None = None
    amount: float = Field(1.0, ge=0, le=1)


def _child_from_file(
    parent: Track, src: str | Path, title: str, source: str, notes: str, meta: dict
) -> Track:
    x, sr = audio_io.read(str(src))
    return mixing.new_child(parent, x, sr, title, source, notes, meta)


def tool_split(req: ToolRequest, job: Job) -> dict:
    return engine.split(req.track_id, req.mode, job, engine=req.engine, model=req.model)


def tool_remove_vocals(req: ToolRequest, job: Job) -> dict:
    t = _track(req.track_id)
    eng = req.engine
    if eng == "auto":
        try:
            eng = selector.select("separate").engine
        except FriendlyError:
            eng = "band-split"
    if eng == "band-split":
        raise FriendlyError(
            "Removing vocals needs a real separator.",
            "Open System and press Install on Audio Separator (about 1 minute).",
        )
    job.message = f"Removing vocals with {eng}..."
    res = separation.separate(
        t.path,
        Path(t.path).parent / f"karaoke_{int(time.time())}",
        mode="2stem",
        engine=eng,
        model=req.model,
        progress=lambda m: setattr(job, "message", m),
    )
    voc, rest = separation.vocals_and_instrumental(res["stems"])
    if not rest:
        raise FriendlyError("The separator didn't return an instrumental.")
    if len(rest) == 1:
        src = rest[0]
    else:
        out, sr, _ = mixing.render([{"path": p} for p in rest], [])
        src = Path(rest[0]).with_name("instrumental_sum.wav")
        audio_io.write(src, out, sr)
    child = _child_from_file(
        t,
        src,
        f"{t.title} (instrumental)",
        "instrumental",
        res["note"],
        {"tool": "remove_vocals", "engine": res["engine"], "model": res["model"]},
    )
    if voc:
        child.meta["vocals_url"] = file_url(voc)
        tracks.save(child)
    return {"track": child.to_public(), "vocals_url": file_url(voc) if voc else None}


def tool_denoise(req: ToolRequest, job: Job) -> dict:
    t = _track(req.track_id)
    job.message = "Cleaning up noise..."
    x, sr = audio_io.read(t.path)
    y, eng = cleanup.clean(x, sr, engine=req.engine, strength=req.strength)
    child = mixing.new_child(
        t,
        y,
        sr,
        f"{t.title} (clean)",
        "denoise",
        f"Noise reduced with {eng}.",
        {"tool": "denoise", "engine": eng},
    )
    return {"track": child.to_public(), "engine": eng}


def tool_match(req: ToolRequest, job: Job) -> dict:
    t = _track(req.track_id)
    if not req.reference_track_id:
        raise FriendlyError("Upload or pick a reference song first.")
    r = _track(req.reference_track_id)
    job.message = "Matching tone and loudness to your reference..."
    out = Path(t.path).parent / f"matched_{int(time.time())}.wav"
    eng = reference.match(t.path, r.path, str(out), engine=req.engine, amount=req.amount)
    child = _child_from_file(
        t,
        out,
        f"{t.title} (matched to {r.title})",
        "match",
        f"Matched to '{r.title}' with {eng}.",
        {"tool": "match", "engine": eng, "reference": r.id},
    )
    return {"track": child.to_public(), "engine": eng}


def tool_midi(req: ToolRequest, job: Job) -> dict:
    t = _track(req.track_id)
    job.message = "Listening for notes..."
    src = t.path
    if t.stems:  # prefer a melodic stem
        mel = next(
            (s for s in t.stems if mixing.role_for(s.name) in ("lead", "vocals", "keys")), None
        )
        src = mel.path if mel else src
    out = EXPORTS_DIR / t.id / f"{t.id}.mid"
    out.parent.mkdir(parents=True, exist_ok=True)
    res = transcribe.to_midi(src, str(out), engine=req.engine)
    return {"midi_url": file_url(out), **{k: v for k, v in res.items() if k != "path"}}


TOOLS = {
    "split": tool_split,
    "remove_vocals": tool_remove_vocals,
    "denoise": tool_denoise,
    "match": tool_match,
    "midi": tool_midi,
}


@router.post("/tools/{name}")
def run_tool(name: str, req: ToolRequest) -> dict:
    if name not in TOOLS:
        raise HTTPException(404, "Unknown tool")
    _track(req.track_id)
    return _job(name, lambda j: TOOLS[name](req, j))


# --------------------------------------------------------------------------- Advanced


@router.post("/advanced/render")
def advanced_render(req: mixing.AdvancedRender) -> dict:
    _track(req.track_id)
    return _job("advanced-render", lambda j: mixing.advanced_render(req, j))


class AdvancedGenerate(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    lyrics: str = ""
    engine: str = "auto"
    duration_s: float = Field(30, ge=4, le=285)
    steps: int = Field(32, ge=1, le=500)
    guidance: float = Field(7.0, ge=0, le=30)
    seed: int = -1
    temperature: float = Field(1.0, ge=0.1, le=2.0)
    bpm: int | None = Field(None, ge=40, le=220)
    title: str = ""


@router.post("/advanced/generate")
def advanced_generate(req: AdvancedGenerate) -> dict:
    def run(job: Job) -> dict:
        if req.engine in ("auto", "acestep", "demo-synth"):
            return engine.generate(
                engine.GenerateRequest(
                    prompt=req.prompt,
                    lyrics=req.lyrics,
                    duration_s=min(req.duration_s, 240),
                    bpm=req.bpm,
                    title=req.title,
                    force_demo=req.engine == "demo-synth",
                ),
                job,
            )
        spec = registry.get(req.engine)
        if not registry.health(spec)["installed"]:
            raise FriendlyError(
                f"{spec.name} is not installed yet.", "Open System and press Install."
            )
        tid, tdir = tracks.new_dir()
        params = generation.GenParams(
            prompt=req.prompt,
            lyrics=req.lyrics,
            duration_s=req.duration_s,
            steps=req.steps,
            guidance=req.guidance,
            seed=req.seed,
            temperature=req.temperature,
        )
        path = generation.run(
            req.engine, params, tdir / "mix.wav", progress=lambda m: setattr(job, "message", m)
        )
        t = Track(
            id=tid,
            title=req.title or f"{spec.name} - {req.prompt[:40]}",
            source=req.engine,
            path=str(path),
            created=time.time(),
            prompt=req.prompt,
            bpm=req.bpm,
            duration_s=probe_duration(path),
            notes=f"Generated with {spec.name}. Licence: {spec.weights_license}.",
            meta={"gen": req.model_dump()},
        )
        return {"track": tracks.save(t).to_public(), "engine": req.engine}

    return _job("generate", run)


@router.get("/separation/models")
def separation_models() -> dict:
    return {
        "models": separation.MODELS,
        "default": {
            "2stem": separation.default_model("2stem"),
            "4stem": separation.default_model("4stem"),
        },
    }


@router.get("/tracks/{tid}/analysis")
def analysis(tid: str) -> dict:
    t = _track(tid)
    x, sr = audio_io.read(t.path)
    return {"analysis": loudness.analyze(x, sr), "meta": t.meta}


# --------------------------------------------------------------------------- session


@router.get("/session")
def get_session() -> dict:
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


@router.put("/session")
def put_session(body: dict[str, Any]) -> dict:
    data = json.dumps({**body, "saved": time.time()})
    if len(data) > 2_000_000:
        raise HTTPException(413, "Session too large")
    tmp = Path(tempfile.mkstemp(dir=DATA_DIR, suffix=".json")[1])
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(SESSION_FILE)
    return {"saved": True}
