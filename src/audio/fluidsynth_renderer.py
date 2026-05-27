"""MIDI to audio rendering via FluidSynth.

FluidSynth is invoked as a subprocess to render MIDI files to WAV using
SoundFont (.sf2) instruments.  This module resolves named soundfont presets
from the project configuration or accepts direct filesystem paths.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from src.orchestrator.config import (
    FLUIDSYNTH_TIMEOUT,
    SAMPLE_RATE,
    SOUNDFONT_PATHS,
)

logger = logging.getLogger(__name__)


def _resolve_soundfont(soundfont: str) -> Path:
    """Resolve a soundfont name or path to an existing file.

    Args:
        soundfont: Either a key in SOUNDFONT_PATHS (e.g. ``"preview"``,
            ``"draft"``) or an absolute/relative filesystem path to an
            ``.sf2`` file.

    Returns:
        Resolved Path to the soundfont file.

    Raises:
        FileNotFoundError: If the resolved soundfont file does not exist.
    """
    if soundfont in SOUNDFONT_PATHS:
        sf_path = SOUNDFONT_PATHS[soundfont]
    else:
        sf_path = Path(soundfont)

    if not sf_path.is_file():
        raise FileNotFoundError(
            f"Soundfont not found: {sf_path}  "
            f"(available presets: {', '.join(SOUNDFONT_PATHS.keys())})"
        )
    return sf_path


def render_fluidsynth(
    midi_path: str,
    output_path: str,
    soundfont: str = "preview",
    sample_rate: int = SAMPLE_RATE,
) -> str:
    """Render a MIDI file to WAV audio using FluidSynth.

    Args:
        midi_path: Path to the input MIDI file.
        output_path: Desired path for the output WAV file.
        soundfont: A key from the SOUNDFONT_PATHS config dict (e.g.
            ``"preview"``, ``"draft"``) or a direct path to an ``.sf2`` file.
        sample_rate: Audio sample rate in Hz.  Defaults to the project
            SAMPLE_RATE (44100).

    Returns:
        The absolute path to the generated WAV file.

    Raises:
        FileNotFoundError: If the MIDI file, soundfont, or fluidsynth
            binary is not found.
        subprocess.CalledProcessError: If fluidsynth exits with an error.
        subprocess.TimeoutExpired: If rendering exceeds FLUIDSYNTH_TIMEOUT.
    """
    midi = Path(midi_path)
    if not midi.is_file():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")

    from src.orchestrator.config import FLUIDSYNTH_PATH
    fluidsynth_bin = shutil.which(FLUIDSYNTH_PATH) or shutil.which("fluidsynth")
    if not fluidsynth_bin:
        raise FileNotFoundError(
            "fluidsynth not found. Install FluidSynth and ensure it is on PATH, "
            "or set MUSER_FLUIDSYNTH_PATH."
        )

    sf_path = _resolve_soundfont(soundfont)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        fluidsynth_bin,
        "-ni",          # non-interactive
        "-g", "1.0",    # gain
        "-r", str(sample_rate),
        str(sf_path),
        str(midi),
        "-F", str(out),
        "-T", "wav",
    ]

    logger.info(
        "Rendering MIDI via FluidSynth: %s -> %s (sf=%s, rate=%d)",
        midi, out, sf_path.name, sample_rate,
    )

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=FLUIDSYNTH_TIMEOUT,
        )
        if result.stderr:
            logger.debug("FluidSynth stderr: %s", result.stderr.strip())
    except subprocess.CalledProcessError as exc:
        logger.error("FluidSynth failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("FluidSynth timed out after %d seconds", FLUIDSYNTH_TIMEOUT)
        raise

    if not out.is_file():
        raise RuntimeError(f"FluidSynth did not produce expected output: {out}")

    logger.info("WAV rendered successfully: %s (%d bytes)", out, out.stat().st_size)
    return str(out.resolve())


def list_soundfonts() -> dict[str, str]:
    """Return available soundfonts with their filesystem paths.

    Only soundfonts whose backing files actually exist on disk are
    included in the result.

    Returns:
        A dict mapping preset names to their absolute path strings.
        Example: ``{"preview": "/path/to/FluidR3_GM.sf2"}``.
    """
    available: dict[str, str] = {}
    for name, path in SOUNDFONT_PATHS.items():
        if path.is_file():
            available[name] = str(path.resolve())
        else:
            logger.debug("Soundfont preset '%s' not on disk: %s", name, path)
    return available
