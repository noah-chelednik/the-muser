"""Demucs stem separation wrapper.

Separates audio into stems (vocals, drums, bass, other) using
Meta's Demucs model. Used to isolate vocals before voice conversion.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def separate_stems(
    input_audio: str,
    output_dir: str = "",
    two_stems: bool = True,
    model: str = "htdemucs",
) -> dict[str, str]:
    """Separate audio into stems using Demucs.

    Args:
        input_audio: Path to input audio file.
        output_dir: Directory for output stems. Auto-created if empty.
        two_stems: If True, only separate vocals/accompaniment.
            If False, separate into vocals/drums/bass/other.
        model: Demucs model name (htdemucs, htdemucs_ft, mdx_extra).

    Returns:
        Dict mapping stem names to file paths.
        E.g., {"vocals": "/path/vocals.wav", "no_vocals": "/path/no_vocals.wav"}

    Raises:
        FileNotFoundError: If input audio doesn't exist.
        RuntimeError: If separation fails.
    """
    input_path = Path(input_audio)
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio not found: {input_audio}")

    if not output_dir:
        output_dir = str(input_path.parent / "stems")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    logger.info(
        "Demucs separation: %s (model: %s, two_stems: %s)",
        input_audio,
        model,
        two_stems,
    )

    # Try Python API first
    try:
        return _separate_via_python(input_audio, output_dir, two_stems, model)
    except ImportError:
        logger.info("Demucs Python API not available, falling back to CLI")

    # Fall back to CLI
    return _separate_via_cli(input_audio, output_dir, two_stems, model)


def _separate_via_python(
    input_audio: str,
    output_dir: str,
    two_stems: bool,
    model: str,
) -> dict[str, str]:
    """Separate using Demucs Python API."""
    import demucs.separate  # type: ignore

    args = [
        "--out",
        output_dir,
        "-n",
        model,
    ]
    if two_stems:
        args.extend(["--two-stems", "vocals"])
    args.append(input_audio)

    demucs.separate.main(args)

    return _collect_outputs(input_audio, output_dir, model, two_stems)


def _separate_via_cli(
    input_audio: str,
    output_dir: str,
    two_stems: bool,
    model: str,
) -> dict[str, str]:
    """Separate using Demucs CLI."""
    cmd = [
        "python",
        "-m",
        "demucs.separate",
        "--out",
        output_dir,
        "-n",
        model,
    ]
    if two_stems:
        cmd.extend(["--two-stems", "vocals"])
    cmd.append(input_audio)

    logger.info("Running Demucs CLI: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Demucs CLI failed (exit {result.returncode}): {result.stderr}")

    return _collect_outputs(input_audio, output_dir, model, two_stems)


def _collect_outputs(
    input_audio: str,
    output_dir: str,
    model: str,
    two_stems: bool,
) -> dict[str, str]:
    """Collect output stem files from Demucs output directory."""
    input_stem = Path(input_audio).stem
    stems_dir = Path(output_dir) / model / input_stem

    result = {}

    if two_stems:
        vocals = stems_dir / "vocals.wav"
        no_vocals = stems_dir / "no_vocals.wav"
        if vocals.exists():
            result["vocals"] = str(vocals)
        if no_vocals.exists():
            result["no_vocals"] = str(no_vocals)
    else:
        for stem_name in ["vocals", "drums", "bass", "other"]:
            stem_file = stems_dir / f"{stem_name}.wav"
            if stem_file.exists():
                result[stem_name] = str(stem_file)

    if not result:
        logger.warning("No output stems found in %s", stems_dir)

    logger.info("Demucs separation complete: %s", list(result.keys()))
    return result
