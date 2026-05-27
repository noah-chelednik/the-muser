"""Final format exports (WAV, MP3, FLAC) using ffmpeg.

All conversions and loudness processing are performed via ffmpeg
subprocesses, keeping this module free of heavy native dependencies.
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from src.orchestrator.config import FFMPEG_TIMEOUT, MP3_BITRATE, TARGET_LUFS

logger = logging.getLogger(__name__)


def _validate_wav(path: str) -> Path:
    """Validate that a WAV input file exists."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"WAV file not found: {path}")
    return p


def _ensure_output_dir(path: str) -> Path:
    """Ensure the parent directory exists and return the path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _require_ffmpeg() -> None:
    """Raise FileNotFoundError if ffmpeg is not on PATH."""
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError(
            "ffmpeg not found. Install ffmpeg and ensure it is on PATH."
        )


def convert_to_mp3(
    wav_path: str,
    output_path: str,
    bitrate: str = MP3_BITRATE,
) -> str:
    """Convert a WAV file to MP3 using ffmpeg and libmp3lame.

    Args:
        wav_path: Path to the input WAV file.
        output_path: Desired path for the output MP3 file.
        bitrate: MP3 bitrate string (e.g. ``"320k"``).

    Returns:
        The absolute path to the generated MP3 file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If encoding exceeds FFMPEG_TIMEOUT.
    """
    wav = _validate_wav(wav_path)
    out = _ensure_output_dir(output_path)
    _require_ffmpeg()

    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        str(out),
    ]

    logger.info("Converting WAV to MP3: %s -> %s (bitrate=%s)", wav, out, bitrate)

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg MP3 conversion failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg MP3 conversion timed out after %d seconds", FFMPEG_TIMEOUT)
        raise

    if not out.is_file():
        raise RuntimeError(f"ffmpeg did not produce expected MP3: {out}")

    logger.info("MP3 created: %s (%d bytes)", out, out.stat().st_size)
    return str(out.resolve())


def convert_to_flac(wav_path: str, output_path: str) -> str:
    """Convert a WAV file to lossless FLAC using ffmpeg.

    Args:
        wav_path: Path to the input WAV file.
        output_path: Desired path for the output FLAC file.

    Returns:
        The absolute path to the generated FLAC file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If encoding exceeds FFMPEG_TIMEOUT.
    """
    wav = _validate_wav(wav_path)
    out = _ensure_output_dir(output_path)
    _require_ffmpeg()

    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav),
        "-codec:a", "flac",
        str(out),
    ]

    logger.info("Converting WAV to FLAC: %s -> %s", wav, out)

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg FLAC conversion failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg FLAC conversion timed out after %d seconds", FFMPEG_TIMEOUT)
        raise

    if not out.is_file():
        raise RuntimeError(f"ffmpeg did not produce expected FLAC: {out}")

    logger.info("FLAC created: %s (%d bytes)", out, out.stat().st_size)
    return str(out.resolve())


def normalize_loudness(
    wav_path: str,
    output_path: str,
    target_lufs: float = TARGET_LUFS,
) -> str:
    """Normalize the loudness of a WAV file using the EBU R128 loudnorm filter.

    This is a two-pass process:

    1. **Analysis pass** -- measures integrated loudness (I), loudness range
       (LRA), true peak (TP), and threshold values.
    2. **Normalization pass** -- applies the loudnorm filter with the
       measured values to achieve the target LUFS.

    Args:
        wav_path: Path to the input WAV file.
        output_path: Desired path for the normalized output WAV file.
        target_lufs: Target integrated loudness in LUFS (default -14.0).

    Returns:
        The absolute path to the normalized WAV file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If processing exceeds FFMPEG_TIMEOUT.
        RuntimeError: If loudness analysis output cannot be parsed.
    """
    wav = _validate_wav(wav_path)
    out = _ensure_output_dir(output_path)
    _require_ffmpeg()

    # ------------------------------------------------------------------
    # Pass 1: Analyze loudness
    # ------------------------------------------------------------------
    analysis_filter = (
        f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5:print_format=json"
    )
    cmd_pass1 = [
        "ffmpeg", "-y",
        "-i", str(wav),
        "-af", analysis_filter,
        "-f", "null",
        "-",
    ]

    logger.info("Loudness analysis (pass 1): %s (target=%s LUFS)", wav, target_lufs)

    try:
        result = subprocess.run(
            cmd_pass1,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("Loudness analysis failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("Loudness analysis timed out after %d seconds", FFMPEG_TIMEOUT)
        raise

    # The loudnorm JSON block is printed to stderr by ffmpeg.
    measured = _parse_loudnorm_stats(result.stderr)

    # ------------------------------------------------------------------
    # Pass 2: Apply normalization with measured values
    # ------------------------------------------------------------------
    norm_filter = (
        f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5"
        f":measured_I={measured['input_i']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_thresh={measured['input_thresh']}"
        f":linear=true:print_format=summary"
    )
    cmd_pass2 = [
        "ffmpeg", "-y",
        "-i", str(wav),
        "-af", norm_filter,
        str(out),
    ]

    logger.info(
        "Applying normalization (pass 2): measured_I=%s, target=%s LUFS",
        measured["input_i"], target_lufs,
    )

    try:
        subprocess.run(
            cmd_pass2,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("Normalization failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("Normalization timed out after %d seconds", FFMPEG_TIMEOUT)
        raise

    if not out.is_file():
        raise RuntimeError(f"ffmpeg did not produce expected output: {out}")

    logger.info("Normalized audio: %s (%d bytes)", out, out.stat().st_size)
    return str(out.resolve())


def _parse_loudnorm_stats(stderr: str) -> dict[str, str]:
    """Extract loudnorm measurement values from ffmpeg stderr output.

    The ``loudnorm`` filter with ``print_format=json`` emits a JSON object
    at the end of stderr.  This function finds and parses that block.

    Args:
        stderr: Full stderr text from the ffmpeg analysis pass.

    Returns:
        A dict with keys ``input_i``, ``input_lra``, ``input_tp``,
        ``input_thresh`` (all as strings suitable for reinsertion into
        an ffmpeg filter).

    Raises:
        RuntimeError: If the JSON block cannot be found or parsed.
    """
    # Find the JSON block -- it starts with '{' and ends with '}'.
    # The loudnorm output is the last JSON object in stderr.
    brace_start = stderr.rfind("{")
    brace_end = stderr.rfind("}")

    if brace_start == -1 or brace_end == -1 or brace_end <= brace_start:
        raise RuntimeError(
            "Could not locate loudnorm JSON in ffmpeg output. "
            "Ensure ffmpeg was built with the loudnorm filter."
        )

    json_text = stderr[brace_start : brace_end + 1]

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse loudnorm JSON: {exc}\nRaw: {json_text}") from exc

    required_keys = ("input_i", "input_lra", "input_tp", "input_thresh")
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise RuntimeError(
            f"Loudnorm JSON missing required keys {missing}. Got: {list(data.keys())}"
        )

    return {k: str(data[k]) for k in required_keys}


def add_metadata(
    audio_path: str,
    output_path: str | None = None,
    title: str = "",
    artist: str = "",
    album: str = "",
    genre: str = "",
    year: str = "",
    comment: str = "",
) -> str:
    """Add ID3/Vorbis metadata to an audio file using ffmpeg.

    Uses a temp-file swap pattern to avoid corruption.  If
    ``output_path`` is ``None``, the input file is overwritten.

    Args:
        audio_path: Path to the input audio file (WAV, MP3, or FLAC).
        output_path: Desired path for the tagged output.  Defaults to
            overwriting the input file in place.
        title: Track title.
        artist: Artist name.
        album: Album name.
        genre: Genre string.
        year: Year string (e.g. ``"2026"``).
        comment: Free-form comment (e.g. AI disclosure).

    Returns:
        The absolute path to the tagged audio file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    inp = Path(audio_path)
    if not inp.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    _require_ffmpeg()

    in_place = output_path is None or str(Path(output_path).resolve()) == str(inp.resolve())

    if in_place:
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=inp.suffix, dir=str(inp.parent))
        os.close(tmp_fd)
        dest = tmp_path
    else:
        dest = str(_ensure_output_dir(output_path))

    cmd = ["ffmpeg", "-y", "-i", str(inp)]

    metadata_flags: list[str] = []
    if title:
        metadata_flags += ["-metadata", f"title={title}"]
    if artist:
        metadata_flags += ["-metadata", f"artist={artist}"]
    if album:
        metadata_flags += ["-metadata", f"album={album}"]
    if genre:
        metadata_flags += ["-metadata", f"genre={genre}"]
    if year:
        metadata_flags += ["-metadata", f"date={year}"]
    if comment:
        metadata_flags += ["-metadata", f"comment={comment}"]

    cmd += metadata_flags + ["-codec", "copy", dest]

    logger.info("Adding metadata to %s", inp)

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg metadata tagging failed (rc=%d): %s", exc.returncode, exc.stderr)
        if in_place and Path(dest).exists():
            Path(dest).unlink()
        raise

    if in_place:
        # Swap temp file over the original
        import shutil as _shutil
        _shutil.move(dest, str(inp))
        logger.info("Metadata written in-place: %s", inp)
        return str(inp.resolve())

    logger.info("Metadata written: %s", dest)
    return str(Path(dest).resolve())


def export_composition(
    wav_path: str,
    output_dir: str,
    formats: list[str] | None = None,
    title: str = "",
    artist: str = "The Muser",
    genre: str = "",
    normalize: bool = True,
    target_lufs: float = TARGET_LUFS,
) -> dict[str, str]:
    """Export a composition to distributable formats with metadata.

    Combines loudness normalization, format conversion, and metadata
    tagging into a single high-level call.

    Args:
        wav_path: Path to the mastered WAV file.
        output_dir: Directory for exported files.
        formats: List of output formats (default: ``["wav", "mp3"]``).
        title: Track title (defaults to filename stem).
        artist: Artist name.
        genre: Genre tag.
        normalize: Whether to apply loudness normalization.
        target_lufs: Target LUFS for normalization.

    Returns:
        Dict mapping format names to output file paths.
    """
    if formats is None:
        formats = ["wav", "mp3"]

    wav = Path(wav_path)
    if not wav.is_file():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not title:
        title = wav.stem.replace("_", " ").replace("-", " ").title()

    # Normalize loudness first if requested
    if normalize:
        norm_path = str(out_dir / f"{wav.stem}_normalized.wav")
        source_wav = normalize_loudness(wav_path, norm_path, target_lufs=target_lufs)
    else:
        source_wav = wav_path

    outputs: dict[str, str] = {}
    year = str(__import__("datetime").date.today().year)
    comment = "Generated by The Muser (AI music composition)"

    if "wav" in formats:
        final_wav = str(out_dir / f"{wav.stem}.wav")
        if source_wav != final_wav:
            import shutil as _shutil
            _shutil.copy2(source_wav, final_wav)
        outputs["wav"] = add_metadata(
            final_wav, title=title, artist=artist, genre=genre,
            year=year, comment=comment,
        )

    if "mp3" in formats:
        mp3_path = str(out_dir / f"{wav.stem}.mp3")
        convert_to_mp3(source_wav, mp3_path)
        outputs["mp3"] = add_metadata(
            mp3_path, title=title, artist=artist, genre=genre,
            year=year, comment=comment,
        )

    if "flac" in formats:
        flac_path = str(out_dir / f"{wav.stem}.flac")
        convert_to_flac(source_wav, flac_path)
        outputs["flac"] = add_metadata(
            flac_path, title=title, artist=artist, genre=genre,
            year=year, comment=comment,
        )

    # Clean up intermediate normalized file
    if normalize:
        norm_file = Path(norm_path)
        if norm_file.exists() and str(norm_file) not in outputs.values():
            norm_file.unlink()

    logger.info("Export complete: %s", outputs)
    return outputs
