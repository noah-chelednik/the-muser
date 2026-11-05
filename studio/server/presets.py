"""Preset library: factory presets (studio/presets) plus user presets and favorites."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from .engines import fx, mastering
from .engines.errors import FriendlyError
from .store import DATA_DIR

FACTORY_DIR = Path(__file__).resolve().parents[1] / "presets"
USER_DIR = DATA_DIR / "presets" / "user"
FAV_FILE = DATA_DIR / "presets" / "favorites.json"
CATEGORIES = {
    "genre": "Genre starters",
    "mix": "Mix chains",
    "master": "Mastering",
    "vocal": "Vocal chains",
    "fx": "FX and creative",
}
CHAIN_CATEGORIES = {"mix", "vocal", "fx"}
_lock = threading.RLock()
_factory: dict[str, dict] | None = None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "preset"


def _load_factory() -> dict[str, dict]:
    global _factory
    if _factory is None:
        out = {}
        for f in sorted(FACTORY_DIR.glob("*/*.json")):
            if f.parent.name == "macros":
                continue
            p = json.loads(f.read_text(encoding="utf-8"))
            out[p["id"]] = p
        _factory = out
    return _factory


def _load_user() -> dict[str, dict]:
    out = {}
    if USER_DIR.exists():
        for f in sorted(USER_DIR.glob("*.json")):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
                out[p["id"]] = p
            except Exception:
                continue
    return out


def favorites() -> set[str]:
    try:
        return set(json.loads(FAV_FILE.read_text()))
    except Exception:
        return set()


def all_presets() -> dict[str, dict]:
    return {**_load_factory(), **_load_user()}


def macros() -> dict:
    return json.loads((FACTORY_DIR / "macros" / "easy_sliders.json").read_text(encoding="utf-8"))


def get(pid: str) -> dict:
    p = all_presets().get(pid)
    if not p:
        raise FriendlyError(f"Preset '{pid}' was not found.")
    return p


def validate(p: dict, known: dict[str, dict] | None = None) -> dict:
    """Check a preset and return a cleaned copy. Raises FriendlyError."""
    known = known if known is not None else all_presets()
    if not isinstance(p, dict):
        raise FriendlyError("A preset must be a JSON object.")
    cat = p.get("category")
    if cat not in CATEGORIES:
        raise FriendlyError(f"Unknown preset category '{cat}'.")
    name = str(p.get("name") or "").strip()
    if not name:
        raise FriendlyError("Give the preset a name.")
    out = {
        k: p[k]
        for k in (
            "id",
            "name",
            "category",
            "subcategory",
            "tags",
            "description",
            "version",
            "factory",
            "role",
            "easy",
            "icon",
        )
        if k in p
    }
    out["name"] = name[:80]
    out["tags"] = [str(t)[:30] for t in (p.get("tags") or [])][:12]
    out["description"] = str(p.get("description") or "")[:300]
    try:
        if cat in CHAIN_CATEGORIES:
            out["chain"] = fx.normalize_chain(p.get("chain"))
        elif cat == "master":
            m = p.get("master") or {}
            if m.get("target") not in mastering.TARGETS:
                raise FriendlyError(f"Unknown loudness target '{m.get('target')}'.")
            out["master"] = {
                "target": m["target"],
                "chain": fx.normalize_chain(m.get("chain")),
                "release_ms": float(m.get("release_ms", 80)),
            }
        else:  # genre
            g = p.get("generate") or {}
            if not str(g.get("prompt") or "").strip():
                raise FriendlyError("A genre starter needs a prompt.")
            out["generate"] = {
                "prompt": str(g["prompt"])[:500],
                "bpm": int(g.get("bpm") or 100),
                "duration_s": float(g.get("duration_s") or 30),
                "lyrics": str(g.get("lyrics") or ""),
            }
            ace = g.get("acestep")
            if isinstance(ace, dict) and str(ace.get("tags") or "").strip():
                out["generate"]["acestep"] = {
                    "profile": str(ace.get("profile") or "8gb")[:20],
                    "tags": str(ace["tags"])[:1500],
                    "lyrics": str(ace.get("lyrics") or "[instrumental]")[:2000],
                    "bpm": max(40, min(220, int(ace.get("bpm") or g.get("bpm") or 100))),
                    "key_scale": str(ace.get("key_scale") or "")[:20],
                    "time_signature": str(ace.get("time_signature") or "4")[:4],
                    "infer_step": max(1, min(200, int(ace.get("infer_step") or 8))),
                    "guidance_scale": max(0.0, min(30.0, float(ace.get("guidance_scale") or 7.0))),
                    "duration_s": max(5.0, min(240.0, float(ace.get("duration_s") or 30))),
                    "num_candidates": max(1, min(2, int(ace.get("num_candidates") or 1))),
                }
            stems = p.get("stems") or {}
            for role, ref in stems.items():
                if isinstance(ref, str) and ref not in known:
                    raise FriendlyError(f"Genre starter refers to a missing preset '{ref}'.")
                if isinstance(ref, list):
                    stems[role] = fx.normalize_chain(ref)
            out["stems"] = stems
            mref = p.get("master")
            if isinstance(mref, str) and mref not in known:
                raise FriendlyError(f"Genre starter refers to a missing master preset '{mref}'.")
            out["master"] = mref
            mac = p.get("macros") or {}
            out["macros"] = {
                k: int(min(max(float(mac.get(k, 50)), 0), 100))
                for k in ("energy", "vocals", "bass", "brightness", "space")
            }
    except ValueError as e:
        raise FriendlyError(f"That preset has a problem: {e}") from e
    return out


def listing(
    category: str | None = None, q: str | None = None, favorites_only: bool = False
) -> list[dict]:
    favs = favorites()
    terms = [t for t in (q or "").lower().split() if t]
    items = []
    for p in all_presets().values():
        if category and p["category"] != category:
            continue
        if favorites_only and p["id"] not in favs:
            continue
        hay = " ".join(
            [
                p["name"],
                p.get("description", ""),
                p.get("subcategory", ""),
                p["category"],
                " ".join(p.get("tags", [])),
            ]
        ).lower()
        if terms and not all(t in hay for t in terms):
            continue
        items.append({**p, "favorite": p["id"] in favs, "user": not p.get("factory", False)})
    items.sort(
        key=lambda p: (not p["favorite"], p["category"], p.get("subcategory", ""), p["name"])
    )
    return items


def counts() -> dict[str, int]:
    c: dict[str, int] = {k: 0 for k in CATEGORIES}
    for p in all_presets().values():
        c[p["category"]] = c.get(p["category"], 0) + 1
    return c


def toggle_favorite(pid: str) -> bool:
    get(pid)
    with _lock:
        favs = favorites()
        on = pid not in favs
        (favs.add if on else favs.discard)(pid)
        FAV_FILE.parent.mkdir(parents=True, exist_ok=True)
        FAV_FILE.write_text(json.dumps(sorted(favs)))
    return on


def save_user(p: dict) -> dict:
    clean = validate(p)
    clean["factory"] = False
    clean["version"] = 1
    clean["created"] = time.time()
    base = f"user-{clean['category']}/{_slug(clean['name'])}"
    pid, n = base, 2
    existing = all_presets()
    while pid in existing and pid != p.get("id"):
        pid, n = f"{base}-{n}", n + 1
    clean["id"] = pid
    with _lock:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        (USER_DIR / (pid.replace("/", "__") + ".json")).write_text(
            json.dumps(clean, indent=2), encoding="utf-8"
        )
    return clean


def delete_user(pid: str) -> bool:
    p = get(pid)
    if p.get("factory", False):
        raise FriendlyError(
            "Factory presets can't be deleted. You can hide them by not favoriting them."
        )
    f = USER_DIR / (pid.replace("/", "__") + ".json")
    if f.exists():
        f.unlink()
        return True
    return False


def export_bundle(ids: list[str] | None = None) -> dict:
    src = all_presets()
    chosen = [
        src[i] for i in (ids or [k for k, v in src.items() if not v.get("factory")]) if i in src
    ]
    return {"format": "muser-presets", "version": 1, "exported": time.time(), "presets": chosen}


def import_bundle(data: Any) -> list[str]:
    items = data.get("presets") if isinstance(data, dict) and "presets" in data else data
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not items:
        raise FriendlyError("That file has no presets in it.")
    saved = []
    for p in items[:500]:
        q = dict(p)
        q.pop("id", None)
        saved.append(save_user(q)["id"])
    return saved


def chain_of(ref: str | list | None) -> list[dict]:
    """Resolve a chain reference (preset id or inline chain) to a chain."""
    if ref is None:
        return []
    if isinstance(ref, list):
        return fx.normalize_chain(ref)
    p = get(ref)
    if p["category"] == "master":
        return fx.normalize_chain(p["master"]["chain"])
    return fx.normalize_chain(p.get("chain"))
