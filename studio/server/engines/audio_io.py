"""Safe audio I/O with guardrails: never write a silent, broken or clipping file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .errors import FriendlyError

SILENCE_PEAK = 10 ** (-80 / 20)  # anything quieter than -80 dBFS peak counts as silent


def read(path: str | Path, sr: int | None = None) -> tuple[np.ndarray, int]:
    """Read audio as float32 (frames, channels). Optionally resample to ``sr``."""
    p = Path(path)
    if not p.exists():
        raise FriendlyError(
            "An audio file the Studio needed is missing.", "Re-import the song and try again."
        )
    try:
        x, rate = sf.read(str(p), dtype="float32", always_2d=True)
    except Exception:
        x, rate = _read_ffmpeg(p)
    if x.shape[0] == 0:
        raise FriendlyError(
            "That audio file is empty.", "Pick a file that actually contains sound."
        )
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    if sr and rate != sr:
        x = resample(x, rate, sr)
        rate = sr
    return x, rate


def _read_ffmpeg(p: Path) -> tuple[np.ndarray, int]:
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        raise FriendlyError("That audio file could not be read.", "Try a WAV, MP3 or FLAC file.")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "conv.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(p), str(out)], check=True)
        x, rate = sf.read(str(out), dtype="float32", always_2d=True)
    return x, rate


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(src, dst)
    return resample_poly(x, dst // g, src // g, axis=0).astype(np.float32)


def to_stereo(x: np.ndarray) -> np.ndarray:
    if x.ndim == 1:
        x = x[:, None]
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    return x[:, :2]


def peak_db(x: np.ndarray) -> float:
    p = float(np.max(np.abs(x))) if x.size else 0.0
    return 20 * np.log10(max(p, 1e-12))


def is_silent(x: np.ndarray) -> bool:
    return x.size == 0 or float(np.max(np.abs(x))) < SILENCE_PEAK


def write(
    path: str | Path,
    x: np.ndarray,
    sr: int,
    *,
    allow_silent: bool = False,
    subtype: str = "PCM_24",
    limit: bool = True,
) -> str:
    """Write audio with guardrails.

    * NaN / inf are removed.
    * Silent output raises a :class:`FriendlyError` instead of producing a dead file.
    * Anything above 0 dBFS is caught by a transparent safety limiter (no clipping). Pass
      ``limit=False`` to keep sample values exactly as given (hard-clipped at full scale), which
      is what stem sets need so that they still add up to the song.
    * The file is written atomically and re-opened to prove it is valid.
    """
    x = np.nan_to_num(np.asarray(x, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if x.ndim == 1:
        x = x[:, None]
    if not allow_silent and is_silent(x):
        raise FriendlyError(
            "The result came out silent, so it was not saved.",
            "Check that the stems are not all muted and try again.",
        )
    if not limit:
        x = np.clip(x, -1.0, 1.0 - 2.0**-23)
    elif float(np.max(np.abs(x))) > 0.999:
        from .dsp import true_peak_limit

        x = true_peak_limit(x, sr, ceiling_db=-0.3)
        x = np.clip(x, -0.999, 0.999)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=p.suffix or ".wav", dir=str(p.parent))
    os.close(fd)
    try:
        sf.write(tmp, x, sr, subtype=subtype)
        info = sf.info(tmp)
        if info.frames != x.shape[0]:
            raise FriendlyError("Saving the audio failed.", "Your disk may be full.")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return str(p)
