"""Audio playback for The Muser CLI.

Detects available system audio players and plays WAV files inline,
allowing the LLM agent to present generated audio to the user.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_PLAYER_CHAIN = ["ffplay", "paplay", "aplay", "afplay"]


def _find_player() -> tuple[str, str] | None:
    """Find the first available audio player.

    Returns (binary_path, player_name) or None.
    """
    for name in _PLAYER_CHAIN:
        path = shutil.which(name)
        if path:
            return path, name
    return None


def play_audio(
    wav_path: str,
    start_s: float = 0.0,
    duration_s: float = 0.0,
) -> dict:
    """Play an audio file through system speakers.

    Args:
        wav_path: Path to audio file.
        start_s: Start playback at this offset (seconds).
        duration_s: Play for this duration (0 = full file).

    Returns:
        Dict with status, player used, and any error.
    """
    path = Path(wav_path)
    if not path.exists():
        return {"status": "error", "error": f"File not found: {wav_path}"}

    found = _find_player()
    if found is None:
        return {
            "status": "error",
            "error": "No audio player found. Install ffmpeg (provides ffplay) for playback.",
        }

    binary, name = found

    if name == "ffplay":
        cmd = [binary, "-nodisp", "-autoexit"]
        if start_s > 0:
            cmd.extend(["-ss", str(start_s)])
        if duration_s > 0:
            cmd.extend(["-t", str(duration_s)])
        cmd.append(wav_path)
    elif name == "afplay":
        cmd = [binary]
        if start_s > 0:
            cmd.extend(["--time", str(duration_s if duration_s > 0 else 999)])
        cmd.append(wav_path)
    else:
        cmd = [binary, wav_path]

    logger.info("Playing %s via %s", wav_path, name)

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        return {"status": "success", "player": name, "file": wav_path}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Playback timed out"}
    except subprocess.CalledProcessError as exc:
        return {"status": "error", "error": f"Playback failed: {exc}"}
