"""Individual audio effect tools for The Muser.

Each function wraps a single ffmpeg audio filter, giving the LLM
fine-grained control over the mix beyond all-or-nothing genre presets.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from src.orchestrator.config import FFMPEG_TIMEOUT

logger = logging.getLogger(__name__)


def _run_ffmpeg_af(wav_path: str, output_path: str, af_filter: str) -> str:
    """Apply a single ffmpeg audio filter."""
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError("ffmpeg not found on PATH")
    if not Path(wav_path).exists():
        raise FileNotFoundError(f"Input not found: {wav_path}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-i", wav_path, "-af", af_filter, output_path]

    subprocess.run(
        cmd, check=True, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
    )

    if not Path(output_path).exists():
        raise RuntimeError(f"ffmpeg did not produce output: {output_path}")

    return output_path


def apply_eq(
    wav_path: str,
    output_path: str,
    frequency_hz: int,
    gain_db: float,
    q: float = 1.0,
) -> str:
    """Apply parametric EQ band."""
    af = f"equalizer=f={frequency_hz}:t=q:w={q}:g={gain_db}"
    logger.info("EQ: %dHz %+.1fdB Q=%.1f on %s", frequency_hz, gain_db, q, wav_path)
    return _run_ffmpeg_af(wav_path, output_path, af)


def apply_reverb(
    wav_path: str,
    output_path: str,
    room_size: float = 0.5,
    decay: float = 0.4,
    mix: float = 0.3,
) -> str:
    """Apply reverb via echo taps simulating room reflections."""
    base_delay = int(20 + room_size * 80)
    d1, d2, d3 = base_delay, base_delay + 20, base_delay + 45
    dc1 = round(decay, 2)
    dc2 = round(decay * 0.6, 2)
    dc3 = round(decay * 0.3, 2)

    in_gain = round(1.0 - mix * 0.3, 2)
    out_gain = round(0.5 + mix * 0.3, 2)

    af = f"aecho={in_gain}:{out_gain}:{d1}|{d2}|{d3}:{dc1}|{dc2}|{dc3}"
    logger.info("Reverb: room=%.1f decay=%.1f mix=%.1f on %s", room_size, decay, mix, wav_path)
    return _run_ffmpeg_af(wav_path, output_path, af)


def apply_compression(
    wav_path: str,
    output_path: str,
    threshold_db: float = -20.0,
    ratio: float = 4.0,
    attack_ms: float = 10.0,
    release_ms: float = 200.0,
) -> str:
    """Apply dynamic range compression."""
    af = (
        f"acompressor=threshold={threshold_db}dB:ratio={ratio}"
        f":attack={attack_ms}:release={release_ms}:knee=4"
    )
    logger.info(
        "Compression: thresh=%.0fdB ratio=%.1f:1 on %s",
        threshold_db, ratio, wav_path,
    )
    return _run_ffmpeg_af(wav_path, output_path, af)


def adjust_volume(
    wav_path: str,
    output_path: str,
    gain_db: float,
) -> str:
    """Adjust volume by a dB amount."""
    af = f"volume={gain_db}dB"
    logger.info("Volume: %+.1fdB on %s", gain_db, wav_path)
    return _run_ffmpeg_af(wav_path, output_path, af)
