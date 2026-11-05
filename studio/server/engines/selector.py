"""Auto-selector: pick the best installed engine for a job on this machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import hardware, registry
from .errors import FriendlyError

COMMERCIAL_RANK = {"yes": 2, "conditional": 1, "no": 0}


@dataclass
class Choice:
    task: str
    engine: str
    name: str
    reasons: list[str]
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    upgrades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def verdict(spec: registry.EngineSpec, hw: hardware.Hardware) -> dict[str, Any]:
    """How well this engine fits this machine.

    status: cpu | fits | fits-reduced | tight | too-big | no-gpu
    ``recommended`` is True only for cpu / fits / fits-reduced. Tight engines can be
    installed and picked by hand but are never the automatic default.
    """
    profiles = spec.vram_profiles
    caveat = spec.vram_caveat
    if spec.min_vram_gb <= 0 and not profiles:
        return _v("cpu", "Runs on CPU", "runs on CPU", None, True)
    if spec.min_vram_gb <= 0 and spec.cpu_ok and not hw.has_gpu:
        return _v("cpu", "Runs on CPU", "runs on CPU (faster with a GPU)", None, True)
    if not hw.has_gpu:
        if spec.cpu_ok:
            # Usable, but a GPU model on CPU is too slow to recommend.
            return _v("cpu", "CPU (slow)", "runs on CPU (slow without a GPU)", None, False)
        return _v("no-gpu", "Needs NVIDIA GPU", "needs an NVIDIA GPU", None, False)
    usable = hw.usable_vram_gb
    wired = [p for p in profiles if p.wired] or profiles
    if not wired:
        if spec.min_vram_gb <= usable:
            return _v("fits", "Fits", f"fits your {hw.vram_gb:g} GB GPU", None, True)
        return _v("too-big", "Won't fit", f"needs {spec.min_vram_gb:g} GB", None, False)
    best = next((p for p in sorted(wired, key=lambda p: -p.vram_gb) if p.vram_gb <= usable), None)
    if spec.needs_flash_attn and not hw.flash_attn and hw.compute_cap:
        caveat = (caveat + " " if caveat else "") + "This GPU has no FlashAttention 2."
    if best is None:
        smallest = min(wired, key=lambda p: p.vram_gb)
        if smallest.vram_gb <= hw.vram_gb + 0.05:
            reason = f"needs about {smallest.vram_gb:g} GB ({smallest.how}) on your {hw.vram_gb:g} GB card"
            return _v("tight", "Tight fit", reason, smallest, False, caveat)
        unwired = [p for p in profiles if not p.wired and p.vram_gb <= hw.vram_gb + 0.05]
        reason = f"needs {smallest.vram_gb:g} GB of GPU memory (you have {hw.vram_gb:g} GB)"
        if unwired:
            reason += f"; a community {unwired[0].vram_gb:g} GB route exists but the Studio does not set it up"
        if spec.cpu_ok:
            return _v("cpu", "CPU (slow)", reason + ", runs on CPU instead", None, False, caveat)
        return _v("too-big", "Not recommended for your card", reason, smallest, False, caveat)
    if spec.key in TIGHT_DESPITE_SPEC and hw.vram_gb < TIGHT_DESPITE_SPEC[spec.key]:
        reason = caveat
        return _v("tight", "Tight fit", reason, best, False, caveat)
    if best.quality == "full":
        return _v(
            "fits", "Fits", f"fits your {hw.vram_gb:g} GB GPU at full quality", best, True, caveat
        )
    return _v(
        "fits-reduced",
        f"Fits ({best.label})",
        f"fits your {hw.vram_gb:g} GB GPU with {best.how}",
        best,
        True,
        caveat,
    )


# Engines whose small profile is documented but users report out-of-memory below this.
TIGHT_DESPITE_SPEC = {"audiosr": 10.0}


def _v(status, label, reason, profile, recommended, caveat=""):
    return {
        "status": status,
        "label": label,
        "reason": reason,
        "profile": None
        if profile is None
        else {
            "id": profile.id,
            "label": profile.label,
            "vram_gb": profile.vram_gb,
            "how": profile.how,
        },
        "recommended": recommended,
        "caveat": caveat,
    }


def fits(spec: registry.EngineSpec, hw: hardware.Hardware) -> tuple[bool, str]:
    """Usable at all on this machine (tight counts, with a penalty in ``score``)."""
    v = verdict(spec, hw)
    return v["status"] in ("cpu", "fits", "fits-reduced", "tight"), v["reason"]


def allowed(
    spec: registry.EngineSpec, commercial_only: bool, allow_conditional: bool = True
) -> bool:
    if not commercial_only:
        return True
    if spec.commercial == "no":
        return False
    if spec.commercial == "conditional" and not allow_conditional:
        return False
    return True


def score(spec: registry.EngineSpec, task: str, hw: hardware.Hardware) -> float:
    s = float(spec.quality.get(task, 0)) * 10
    s += COMMERCIAL_RANK[spec.commercial]  # tie-break toward the safest licence
    if spec.verified == "working":
        s += 3  # prefer engines proven on this codebase when quality is close
    if spec.min_vram_gb > 0 and not hw.has_gpu:
        s -= 25  # CPU fallback of a GPU model is painfully slow
    v = verdict(spec, hw)
    if v["status"] == "tight":
        s -= 30  # never the automatic default: only when picked by hand
    return s


def candidates(
    task: str,
    hw: hardware.Hardware | None = None,
    commercial_only: bool = True,
    allow_conditional: bool = True,
    health_fn=None,
) -> list[dict[str, Any]]:
    hw = hw or hardware.detect()
    health_fn = health_fn or registry.health
    out = []
    for spec in registry.ENGINES:
        if task not in spec.tasks:
            continue
        v = verdict(spec, hw)
        ok = v["status"] in ("cpu", "fits", "fits-reduced", "tight")
        h = health_fn(spec)
        out.append(
            {
                "key": spec.key,
                "name": spec.name,
                "score": score(spec, task, hw),
                "fits": ok,
                "fit_reason": v["reason"],
                "fit_status": v["status"],
                "recommended": v["recommended"],
                "installed": h["installed"],
                "healthy": h["healthy"],
                "detail": h["detail"],
                "allowed": allowed(spec, commercial_only, allow_conditional),
                "commercial": spec.commercial,
                "verified": spec.verified,
            }
        )
    out.sort(key=lambda c: -c["score"])
    return out


def select(
    task: str,
    hw: hardware.Hardware | None = None,
    commercial_only: bool = True,
    allow_conditional: bool = True,
    prefer: str | None = None,
    health_fn=None,
) -> Choice:
    """Return the best usable engine. ``prefer`` forces a key if it is usable."""
    if task not in registry.TASKS:
        raise FriendlyError(f"Unknown job type '{task}'.")
    hw = hw or hardware.detect()
    cands = candidates(task, hw, commercial_only, allow_conditional, health_fn)
    usable = [
        c
        for c in cands
        if c["fits"] and c["healthy"] and c["allowed"] and c["fit_status"] != "tight"
    ]
    if prefer and prefer != "auto":
        forced = next((c for c in cands if c["key"] == prefer), None)
        if forced is None:
            raise FriendlyError(f"'{prefer}' can't do that job.")
        if not forced["healthy"]:
            raise FriendlyError(
                f"{forced['name']} is not installed yet.", "Open System and press Install."
            )
        if not forced["fits"]:
            raise FriendlyError(
                f"{forced['name']} is not recommended for your card: {forced['fit_reason']}."
            )
        usable = [forced] + [c for c in usable if c is not forced]
    if not usable:
        raise FriendlyError(
            "No engine for this job is installed yet.",
            "Open System and press Install on one of the suggested tools.",
        )
    best = usable[0]
    spec = registry.get(best["key"])
    reasons = [
        f"Best quality installed for '{registry.TASKS[task]}'"
        if not prefer or prefer == "auto"
        else "You picked this engine",
        best["fit_reason"][:1].upper() + best["fit_reason"][1:],
        {
            "yes": "Commercial-safe output",
            "conditional": "Commercial use has conditions: " + spec.commercial_note,
            "no": "Non-commercial licence: personal use only",
        }[spec.commercial],
    ]
    if best["fit_status"] == "tight":
        reasons.append("Tight fit on your card: close other GPU apps first")
    if spec.verified != "working":
        reasons.append("Adapter untested here: report issues if it fails")
    upgrades = [
        {"key": c["key"], "name": c["name"], "detail": c["fit_reason"]}
        for c in cands
        if c["score"] > best["score"] and c["recommended"] and c["allowed"] and not c["installed"]
    ]
    return Choice(
        task,
        best["key"],
        best["name"],
        reasons,
        alternatives=[{"key": c["key"], "name": c["name"]} for c in usable[1:]],
        upgrades=upgrades,
    )


def recommendations(hw: hardware.Hardware | None = None) -> list[dict[str, Any]]:
    """Which heavy models this PC can run (used by setup and the System panel)."""
    hw = hw or hardware.detect()
    rec = []
    order = {"fits": 0, "fits-reduced": 0, "cpu": 1, "tight": 2, "too-big": 3, "no-gpu": 3}
    for spec in registry.ENGINES:
        if spec.tier != "heavy":
            continue
        v = verdict(spec, hw)
        rec.append(
            {
                "key": spec.key,
                "name": spec.name,
                "tasks": spec.tasks,
                "can_run": v["recommended"],
                "status": v["status"],
                "label": v["label"],
                "reason": v["reason"],
                "profile": v["profile"],
                "caveat": v["caveat"],
                "commercial": spec.commercial,
                "min_vram_gb": spec.min_vram_gb,
                "vram_full_gb": spec.vram_full_gb,
                "windows": spec.windows,
                "_order": order.get(v["status"], 3),
            }
        )
    rec.append(_full_pipeline_row(hw, order))
    rec.sort(key=lambda r: (r["_order"], -COMMERCIAL_RANK[r["commercial"]], r["min_vram_gb"]))
    for r in rec:
        r.pop("_order")
    return rec


def _full_pipeline_row(hw: hardware.Hardware, order: dict[str, int]) -> dict[str, Any]:
    """The original Muser full-quality pipeline (ACE-Step sft + 1.7B LM, NotaGen, voices)."""
    if hw.usable_vram_gb >= 20:
        status, label, reason = "fits", "Fits", "your card runs the original full-quality pipeline"
    else:
        status, label = "too-big", "Not recommended for your card"
        reason = (
            "the original full-quality pipeline wants about 24 GB; the Studio runs ACE-Step 1.5 "
            "with its low-memory profile instead"
            if hw.has_gpu
            else "needs a 24 GB NVIDIA GPU"
        )
    return {
        "key": "full-pipeline-24gb",
        "name": "Full pipeline (24 GB)",
        "tasks": ["generate"],
        "can_run": status == "fits",
        "status": status,
        "label": label,
        "reason": reason,
        "profile": None,
        "caveat": "",
        "commercial": "yes",
        "min_vram_gb": 20.0,
        "vram_full_gb": 24.0,
        "windows": "native",
        "_order": order[status],
    }
