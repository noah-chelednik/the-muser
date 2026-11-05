"""Track library + background job registry for the Studio API."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.orchestrator.config import COMPOSITIONS_DIR, PROJECT_ROOT

DATA_DIR = Path(os.environ.get("MUSER_STUDIO_DATA", PROJECT_ROOT / "studio_data")).resolve()
TRACKS_DIR = DATA_DIR / "tracks"
UPLOADS_DIR = DATA_DIR / "uploads"
EXPORTS_DIR = DATA_DIR / "exports"
for _d in (TRACKS_DIR, UPLOADS_DIR, EXPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Directories the /files endpoint may serve from.
ALLOWED_ROOTS = [DATA_DIR, COMPOSITIONS_DIR.resolve()]
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aif", ".aiff"}


def file_url(path: str | Path) -> str:
    p = Path(path).resolve()
    for root in ALLOWED_ROOTS:
        try:
            rel = p.relative_to(root)
            return f"/files/{root.name}/{rel.as_posix()}"
        except ValueError:
            continue
    raise ValueError(f"Path outside allowed roots: {p}")


def resolve_file(root_name: str, rel: str) -> Path | None:
    for root in ALLOWED_ROOTS:
        if root.name == root_name:
            p = (root / rel).resolve()
            if root in p.parents or p == root:
                return p if p.is_file() else None
    return None


@dataclass
class Stem:
    id: str
    name: str
    path: str
    color: str = ""


@dataclass
class Track:
    id: str
    title: str
    source: str  # demo-synth | acestep | upload | agent | mixdown
    path: str
    created: float
    prompt: str = ""
    bpm: int | None = None
    key: str = ""
    duration_s: float = 0.0
    stems: list[Stem] = field(default_factory=list)
    stem_method: str = ""  # demucs-4stem | demucs-2stem | demo-synth | band-split
    notes: str = ""
    hidden_stems: dict[str, str] = field(default_factory=dict)  # demo synth pre-renders
    parent_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)  # loudness reports, preset ids, engine used

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("hidden_stems", None)
        d["url"] = file_url(self.path)
        d["stems"] = [dict(asdict(s), url=file_url(s.path)) for s in self.stems]
        return d


STEM_COLORS = {
    "drums": "#ff4d6d",
    "bass": "#ffb703",
    "vocals": "#c77dff",
    "other": "#4cc9f0",
    "no_vocals": "#4cc9f0",
    "chords": "#4cc9f0",
    "lead": "#80ffdb",
}
_FALLBACK_COLORS = ["#ffb703", "#4cc9f0", "#c77dff", "#80ffdb", "#ff4d6d", "#e9c46a"]


class TrackStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tracks: dict[str, Track] = {}
        self._load()

    def _meta(self, tid: str) -> Path:
        return TRACKS_DIR / tid / "meta.json"

    def _load(self) -> None:
        for meta in TRACKS_DIR.glob("*/meta.json"):
            try:
                raw = json.loads(meta.read_text())
                raw["stems"] = [Stem(**s) for s in raw.get("stems", [])]
                t = Track(**raw)
                if Path(t.path).exists():
                    self._tracks[t.id] = t
            except Exception:
                continue

    def new_dir(self) -> tuple[str, Path]:
        tid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        d = TRACKS_DIR / tid
        d.mkdir(parents=True, exist_ok=True)
        return tid, d

    def save(self, t: Track) -> Track:
        with self._lock:
            self._tracks[t.id] = t
            self._meta(t.id).parent.mkdir(parents=True, exist_ok=True)
            raw = asdict(t)
            self._meta(t.id).write_text(json.dumps(raw, indent=2))
        return t

    def get(self, tid: str) -> Track | None:
        with self._lock:
            return self._tracks.get(tid)

    def delete(self, tid: str) -> bool:
        import shutil

        with self._lock:
            t = self._tracks.pop(tid, None)
        if t and (TRACKS_DIR / tid).exists():
            shutil.rmtree(TRACKS_DIR / tid, ignore_errors=True)
        return t is not None

    def list(self) -> list[Track]:
        self.scan_compositions()
        with self._lock:
            return sorted(self._tracks.values(), key=lambda t: t.created, reverse=True)

    def scan_compositions(self) -> list[Track]:
        """Register audio the agent/CLI wrote into compositions/*/(renders|output)."""
        added = []
        if not COMPOSITIONS_DIR.exists():
            return added
        known = {t.path for t in self._tracks.values()}
        for sub in ("renders", "output"):
            for f in COMPOSITIONS_DIR.glob(f"*/{sub}/*"):
                if f.suffix.lower() not in AUDIO_EXT or str(f.resolve()) in known:
                    continue
                tid = "comp-" + hashlib.sha1(str(f.resolve()).encode()).hexdigest()[:10]
                t = Track(
                    id=tid,
                    title=f"{f.parent.parent.name} / {f.stem}",
                    source="agent",
                    path=str(f.resolve()),
                    created=f.stat().st_mtime,
                    duration_s=probe_duration(f),
                )
                added.append(self.save(t))
        return added


def probe_duration(path: str | Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return round(info.frames / info.samplerate, 2)
    except Exception:
        return 0.0


def color_for(name: str, i: int) -> str:
    return STEM_COLORS.get(name.split(" ")[0], _FALLBACK_COLORS[i % len(_FALLBACK_COLORS)])


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | error
    message: str = ""
    result: Any = None
    error: str = ""
    detail: str = ""  # raw technical error, shown under "details" in the UI
    created: float = field(default_factory=time.time)
    finished: float = 0.0


def jsonable(v: Any) -> Any:
    """Make numpy scalars and tuples safe for the track's JSON metadata."""
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if hasattr(v, "item") and type(v).__module__ == "numpy":
        return v.item()
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    return v


class JobRunner:
    def __init__(self, workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="studio-job")
        self._jobs: dict[str, Job] = {}

    def submit(self, kind: str, fn: Callable[[Job], Any]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        self._jobs[job.id] = job

        def run() -> None:
            job.status = "running"
            try:
                job.result = jsonable(fn(job))
                job.status = "done"
            except Exception as e:
                from .engines.errors import friendly_message

                job.status = "error"
                job.error = friendly_message(e)
                job.detail = f"{type(e).__name__}: {e}"
                traceback.print_exc()
            finally:
                job.finished = time.time()

        self._pool.submit(run)
        return job

    def get(self, jid: str) -> Job | None:
        return self._jobs.get(jid)


tracks = TrackStore()
jobs = JobRunner()
