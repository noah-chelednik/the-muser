"""Stem fidelity: keep split stems faithful to the song they came from.

Splitters run at a fixed model rate (44.1 kHz) and then ``audio-separator`` peak-limits and
bit-depth-matches each stem on its own. For a producer that has three practical costs:

* a 48 kHz session gets 44.1 kHz stems back (a second sample-rate conversion in the DAW);
* stems that peak above 0.9 are each turned down by a *different* amount, so they no longer add
  up to the song;
* a model that drops energy leaves a gap: mute one stem and the rest are not "the song minus that
  stem".

This module brings the stems back to the source's sample rate with a single high quality
resample, measures how far they sum back to the source (a null test), optionally rebuilds one
stem as *source minus the others* (residual subtraction), and writes 24-bit WAVs.

The approach (single resample, residual subtraction, null test) follows the open-source
``stemsep`` project by badwolf-ro (MIT): https://github.com/badwolf-ro/stemsep. The code here is
an independent implementation for this code base. See NOTICE.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from . import audio_io
from .errors import FriendlyError

# Stems that sum to the source within this (dB re source RMS) count as an exact decomposition.
EXACT_DB = -60.0
# Which stem absorbs the difference, in order of preference. "instrumental" for 2-stem models,
# "other" for Demucs-style 4 and 6 stem models (it is the catch-all bucket by design).
RESIDUAL_PREFERENCE = ("instrumental", "other", "no_vocals", "accompaniment")

ResidualMode = str  # "auto", "off", or the name of a stem


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    """One sample-rate conversion, (frames, channels) float32. soxr VHQ if present, else scipy."""
    if src == dst:
        return x
    try:
        import soxr  # type: ignore  # installed with librosa

        return soxr.resample(np.ascontiguousarray(x, dtype=np.float32), src, dst, quality="VHQ")
    except ImportError:  # pragma: no cover - librosa always brings soxr
        return audio_io.resample(x, src, dst)


def _fit(x: np.ndarray, frames: int) -> np.ndarray:
    """Trim or zero-pad ``x`` (frames, channels) to exactly ``frames``."""
    if x.shape[0] >= frames:
        return x[:frames]
    pad = np.zeros((frames - x.shape[0], x.shape[1]), dtype=x.dtype)
    return np.concatenate([x, pad], axis=0)


def _match_channels(x: np.ndarray, channels: int) -> np.ndarray:
    if x.shape[1] == channels:
        return x
    if x.shape[1] == 1:
        return np.repeat(x, channels, axis=1)
    if channels == 1:  # fold to mono rather than keep only the left channel
        return x.mean(axis=1, keepdims=True).astype(x.dtype)
    return x[:, :channels]


def null_test_db(mix: np.ndarray, stems: dict[str, np.ndarray]) -> float:
    """dB (relative to the source's RMS) by which the stems fail to add up to the source.

    More negative is better. ``-inf`` is capped at -200. A plain dry gain error of 1% shows up as
    about -40 dB; a splitter that discards a quiet instrument typically shows -15 to -30 dB.
    """
    if not stems:
        raise ValueError("no stems to test")
    total = np.zeros_like(mix)
    for s in stems.values():
        total += _fit(_match_channels(s, mix.shape[1]), mix.shape[0])
    rms_mix = float(np.sqrt(np.mean(mix.astype(np.float64) ** 2)))
    rms_res = float(np.sqrt(np.mean((mix - total).astype(np.float64) ** 2)))
    if rms_mix < 1e-9:
        return -200.0
    return max(20.0 * np.log10(max(rms_res, 1e-10) / rms_mix), -200.0)


def make_residual(
    mix: np.ndarray, stems: dict[str, np.ndarray], target: str
) -> dict[str, np.ndarray]:
    """Return ``stems`` with ``target`` rebuilt as ``mix`` minus every other stem."""
    if target not in stems:
        raise ValueError(f"no stem named {target!r} (have {sorted(stems)})")
    others = np.zeros_like(mix)
    for name, s in stems.items():
        if name != target:
            others += _fit(_match_channels(s, mix.shape[1]), mix.shape[0])
    out = {k: _fit(_match_channels(v, mix.shape[1]), mix.shape[0]) for k, v in stems.items()}
    out[target] = (mix - others).astype(np.float32)
    return out


def _clipped(stems: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {k: np.clip(v, -1.0, 1.0) for k, v in stems.items()}


def pick_residual_target(names: list[str]) -> str | None:
    """The stem that should absorb the difference, or None when there is no sensible choice."""
    lowered = {n.lower(): n for n in names}
    for pref in RESIDUAL_PREFERENCE:
        if pref in lowered:
            return lowered[pref]
    return None


def reconcile(
    source: str | Path,
    stem_paths: dict[str, str],
    *,
    residual: ResidualMode = "auto",
    subtype: str = "PCM_24",
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Bring ``stem_paths`` back to the source's sample rate, null-test them, write 24-bit WAVs.

    ``residual``: ``"auto"`` rebuilds the catch-all stem (instrumental / other) as source minus the
    rest when the stems do not already sum back to the source; ``"off"`` never does; any stem name
    forces that stem. Files are replaced in place (same names), so callers' paths stay valid.

    Returns ``{"stems", "sample_rate", "null_db_before", "null_db_after", "residual", "subtype"}``.
    Never raises for an audio problem in a single stem: on failure the original files are left
    untouched and the result carries ``"error"``.
    """
    mix, sr = audio_io.read(source)
    try:
        loaded: dict[str, np.ndarray] = {}
        for name, p in stem_paths.items():
            x, rate = audio_io.read(p)
            x = resample(x, rate, sr) if rate != sr else x
            loaded[name] = _fit(_match_channels(x, mix.shape[1]), mix.shape[0])
        before = null_test_db(mix, loaded)
        used: str | None = None
        stems = loaded
        if residual != "off":
            target = residual if residual != "auto" else None
            if residual == "auto" and before > EXACT_DB:
                target = pick_residual_target(list(loaded))
            if target is not None:
                candidate = make_residual(mix, loaded, target)
                # The rebuilt stem is written without a limiter; only keep it if, after the
                # unavoidable full-scale clip, the set really does add up better than before.
                if residual != "auto" or null_test_db(mix, _clipped(candidate)) < before:
                    if progress:
                        progress(f"Rebuilding '{target}' as the song minus the other stems ...")
                    stems = candidate
                    used = target
        paths: dict[str, str] = {}
        for name, x in stems.items():
            paths[name] = audio_io.write(
                stem_paths[name], x, sr, allow_silent=True, subtype=subtype, limit=False
            )
        # Report what is on disk, not what we meant to write.
        written = {name: audio_io.read(p)[0] for name, p in paths.items()}
        after = null_test_db(mix, written)
    except FriendlyError:
        raise
    except Exception as exc:  # noqa: BLE001  keep the raw stems rather than lose the user's split
        return {
            "stems": dict(stem_paths),
            "sample_rate": None,
            "null_db_before": None,
            "null_db_after": None,
            "residual": None,
            "subtype": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "stems": paths,
        "sample_rate": sr,
        "null_db_before": round(before, 2),
        "null_db_after": round(after, 2),
        "residual": used,
        "subtype": subtype,
    }


def describe(result: dict[str, Any]) -> str:
    """One plain sentence for the UI."""
    if result.get("error") or result.get("null_db_after") is None:
        return "Stems saved as the splitter wrote them (fidelity pass skipped)."
    db = result["null_db_after"]
    sr_khz = result["sample_rate"] / 1000
    how = (
        f" '{result['residual']}' is the song minus the other stems."
        if result.get("residual")
        else ""
    )
    quality = (
        f"add back up to the song (error {db:.0f} dB, inaudible)"
        if db <= EXACT_DB
        else f"add back up to the song within {db:.0f} dB"
    )
    return f"24-bit stems at {sr_khz:g} kHz (your file's rate); they {quality}.{how}"
