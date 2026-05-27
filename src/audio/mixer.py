"""N-track audio mixer for The Muser.

Combines multiple audio files into a single mixdown using ffmpeg,
with per-track volume, panning, and delay control.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from src.orchestrator.config import FFMPEG_TIMEOUT

logger = logging.getLogger(__name__)


def mix_n_tracks(
    tracks: list[dict],
    output_path: str,
    normalize: bool = True,
) -> str:
    """Mix N audio tracks into a single output file.

    Args:
        tracks: List of dicts, each with:
            - path (str): audio file path (required)
            - volume_db (float): gain in dB (default 0)
            - pan (float): stereo pan -1.0 to 1.0 (default 0)
            - delay_ms (float): delay in ms (default 0)
        output_path: Path for the mixed output WAV.
        normalize: Apply loudness normalization to the mix.

    Returns:
        Path to the output file.
    """
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError("ffmpeg not found on PATH")

    if len(tracks) < 2:
        raise ValueError("mix_n_tracks requires at least 2 tracks")

    for t in tracks:
        if not Path(t["path"]).exists():
            raise FileNotFoundError(f"Track not found: {t['path']}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    inputs = []
    filter_parts = []

    for i, track in enumerate(tracks):
        inputs.extend(["-i", track["path"]])

        chain = [f"[{i}:a]aresample=48000", "aformat=channel_layouts=stereo"]

        vol = track.get("volume_db", 0.0)
        if vol != 0.0:
            chain.append(f"volume={vol}dB")

        pan = track.get("pan", 0.0)
        if pan != 0.0:
            left = round(min(1.0, 0.5 - pan * 0.5), 3)
            right = round(min(1.0, 0.5 + pan * 0.5), 3)
            chain.append(
                f"pan=stereo|c0={left}*c0+{left}*c1|c1={right}*c0+{right}*c1"
            )

        delay_ms = track.get("delay_ms", 0.0)
        if delay_ms > 0:
            d = int(delay_ms)
            chain.append(f"adelay={d}|{d}")

        label = f"t{i}"
        filter_parts.append(f"{','.join(chain)}[{label}]")

    mix_inputs = "".join(f"[t{i}]" for i in range(len(tracks)))
    amix = f"{mix_inputs}amix=inputs={len(tracks)}:duration=longest:dropout_transition=2"

    if normalize:
        amix += "[mix];[mix]loudnorm=I=-14:TP=-1:LRA=11[out]"
        map_label = "[out]"
    else:
        amix += "[out]"
        map_label = "[out]"

    filter_complex = ";".join(filter_parts) + ";" + amix

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", map_label,
        output_path,
    ]

    logger.info("Mixing %d tracks -> %s", len(tracks), output_path)

    result = subprocess.run(
        cmd, check=True, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
    )

    if not Path(output_path).exists():
        raise RuntimeError(f"ffmpeg did not produce output: {output_path}")

    return output_path
