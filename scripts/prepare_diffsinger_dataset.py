#!/usr/bin/env python3
"""Prepare vocal recordings for DiffSinger training.

Takes raw WAV recordings and produces a DiffSinger-ready dataset directory
with segmented audio, phoneme alignments, F0 curves, and .ds project files.

Pipeline:
    1. Segmentation   — Split recordings into 5-15 second phrases (silence detection)
    2. Transcription   — Generate text transcription (Whisper)
    3. Phoneme alignment — SOFA (singing-oriented) or MFA fallback
    4. F0 extraction    — SOME (singing-oriented) or librosa.pyin fallback
    5. Format conversion — Convert to DiffSinger .ds format
    6. Quality report    — Flag segments needing manual review

Usage::

    python scripts/prepare_diffsinger_dataset.py \\
        --input-dir recordings/ \\
        --output-dir training_data/my_voice/ \\
        --voice-name "my-voice" \\
        --sample-rate 44100
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import click
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("Error: click and rich are required. Install with: pip install click rich")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("muser.prepare_dataset")
console = Console()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """A single audio segment extracted from a recording."""
    source_file: str
    segment_id: str
    wav_path: str
    start_s: float
    end_s: float
    duration_s: float
    transcript: str = ""
    phonemes: list[str] = field(default_factory=list)
    phone_durations: list[float] = field(default_factory=list)
    f0_values: list[float] = field(default_factory=list)
    f0_timestep_s: float = 0.005  # 5ms default
    quality_score: float = 0.0
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)


@dataclass
class DatasetReport:
    """Summary report of dataset preparation."""
    voice_name: str
    total_recordings: int = 0
    total_segments: int = 0
    total_duration_s: float = 0.0
    segments_needing_review: int = 0
    avg_segment_duration_s: float = 0.0
    avg_quality_score: float = 0.0
    transcription_method: str = ""
    alignment_method: str = ""
    f0_method: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1: Segmentation
# ---------------------------------------------------------------------------

def segment_audio(
    wav_path: str,
    output_dir: str,
    min_duration_s: float = 5.0,
    max_duration_s: float = 15.0,
    silence_threshold_db: float = -40.0,
    min_silence_len_s: float = 0.3,
    sample_rate: int = 44100,
) -> list[Segment]:
    """Split a recording into phrases using silence detection.

    Uses librosa to detect silent intervals, then splits the audio at
    silence boundaries, merging short segments and splitting long ones.

    Args:
        wav_path: Path to the input WAV file.
        output_dir: Directory to write segment WAV files.
        min_duration_s: Minimum segment duration (shorter segments are merged).
        max_duration_s: Maximum segment duration (longer segments are split).
        silence_threshold_db: Silence detection threshold in dB.
        min_silence_len_s: Minimum silence duration to consider as a boundary.
        sample_rate: Target sample rate for output segments.

    Returns:
        List of Segment objects with wav_path, timing, and source info.
    """
    import librosa
    import numpy as np
    import soundfile as sf

    logger.info("Segmenting: %s", wav_path)

    y, sr = librosa.load(wav_path, sr=sample_rate, mono=True)
    total_duration = len(y) / sr

    if total_duration < min_duration_s:
        logger.warning(
            "Recording too short (%.1fs < %.1fs): %s",
            total_duration, min_duration_s, wav_path,
        )
        return []

    # Detect non-silent intervals
    # Convert dB threshold to amplitude
    threshold_amp = librosa.db_to_amplitude(silence_threshold_db)

    # Use librosa's effects to find non-silent intervals
    intervals = librosa.effects.split(
        y,
        top_db=abs(silence_threshold_db),
        frame_length=int(sr * 0.025),  # 25ms frames
        hop_length=int(sr * 0.010),    # 10ms hops
    )

    if len(intervals) == 0:
        logger.warning("No non-silent intervals found in %s", wav_path)
        return []

    # Merge intervals that are close together (gap < min_silence_len_s)
    merged: list[tuple[int, int]] = []
    min_silence_samples = int(min_silence_len_s * sr)

    for start, end in intervals:
        if merged and (start - merged[-1][1]) < min_silence_samples:
            # Merge with previous interval
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    # Further merge short segments
    min_samples = int(min_duration_s * sr)
    final_intervals: list[tuple[int, int]] = []
    for start, end in merged:
        if final_intervals and (end - start) < min_samples:
            # Merge with previous if result won't be too long
            prev_start = final_intervals[-1][0]
            if (end - prev_start) / sr <= max_duration_s * 1.5:
                final_intervals[-1] = (prev_start, end)
                continue
        final_intervals.append((start, end))

    # Split segments that are too long
    max_samples = int(max_duration_s * sr)
    split_intervals: list[tuple[int, int]] = []
    for start, end in final_intervals:
        duration_samples = end - start
        if duration_samples > max_samples:
            # Find good split points (at lower energy moments)
            n_splits = int(np.ceil(duration_samples / max_samples))
            chunk = y[start:end]
            rms = librosa.feature.rms(
                y=chunk,
                frame_length=int(sr * 0.05),
                hop_length=int(sr * 0.01),
            )[0]

            split_size = len(rms) // n_splits
            sub_start = start
            for i in range(n_splits - 1):
                # Find minimum energy point in search window
                search_start = max(0, (i + 1) * split_size - split_size // 4)
                search_end = min(len(rms), (i + 1) * split_size + split_size // 4)
                if search_start < search_end:
                    min_idx = search_start + np.argmin(rms[search_start:search_end])
                    split_sample = start + int(min_idx * sr * 0.01)
                else:
                    split_sample = start + int((i + 1) * split_size * sr * 0.01)

                split_sample = min(split_sample, end)
                if split_sample > sub_start:
                    split_intervals.append((sub_start, split_sample))
                    sub_start = split_sample

            if sub_start < end:
                split_intervals.append((sub_start, end))
        else:
            split_intervals.append((start, end))

    # Write segments to disk
    segments: list[Segment] = []
    source_stem = Path(wav_path).stem
    os.makedirs(output_dir, exist_ok=True)

    for idx, (start, end) in enumerate(split_intervals):
        duration = (end - start) / sr
        if duration < 1.0:
            # Skip extremely short segments
            continue

        segment_id = f"{source_stem}_{idx:04d}"
        seg_path = os.path.join(output_dir, f"{segment_id}.wav")

        # Add small padding (50ms) around the segment
        pad = int(0.05 * sr)
        padded_start = max(0, start - pad)
        padded_end = min(len(y), end + pad)
        segment_audio_data = y[padded_start:padded_end]

        sf.write(seg_path, segment_audio_data, sr)

        segments.append(Segment(
            source_file=wav_path,
            segment_id=segment_id,
            wav_path=seg_path,
            start_s=start / sr,
            end_s=end / sr,
            duration_s=duration,
        ))

    logger.info(
        "Segmented %s into %d segments (total %.1fs)",
        wav_path, len(segments), sum(s.duration_s for s in segments),
    )
    return segments


# ---------------------------------------------------------------------------
# Step 2: Transcription
# ---------------------------------------------------------------------------

def transcribe_segments(
    segments: list[Segment],
    model_size: str = "base",
    language: str = "en",
) -> str:
    """Transcribe audio segments using Whisper.

    Tries the OpenAI Whisper Python API first, falls back to the Whisper CLI.

    Args:
        segments: List of Segment objects with wav_path set.
        model_size: Whisper model size (tiny, base, small, medium, large).
        language: Language code for transcription.

    Returns:
        Name of transcription method used ("whisper-python" or "whisper-cli").
    """
    method = _try_whisper_python(segments, model_size, language)
    if method:
        return method

    method = _try_whisper_cli(segments, model_size, language)
    if method:
        return method

    # Last resort: empty transcripts (user must fill in manually)
    logger.warning(
        "No Whisper installation found. Segments will have empty transcripts. "
        "Install with: pip install openai-whisper"
    )
    for seg in segments:
        seg.transcript = ""
        seg.needs_review = True
        seg.review_reasons.append("no_transcription_available")
    return "none"


def _try_whisper_python(
    segments: list[Segment],
    model_size: str,
    language: str,
) -> str | None:
    """Attempt transcription using the whisper Python package."""
    try:
        import whisper  # type: ignore[import-untyped]
    except ImportError:
        return None

    logger.info("Using Whisper Python API (model=%s, lang=%s)", model_size, language)

    try:
        model = whisper.load_model(model_size)
    except Exception as exc:
        logger.warning("Failed to load Whisper model: %s", exc)
        return None

    for seg in segments:
        try:
            result = model.transcribe(
                seg.wav_path,
                language=language,
                task="transcribe",
                fp16=False,
            )
            seg.transcript = result.get("text", "").strip()
            if not seg.transcript:
                seg.needs_review = True
                seg.review_reasons.append("empty_transcript")
        except Exception as exc:
            logger.warning("Transcription failed for %s: %s", seg.segment_id, exc)
            seg.transcript = ""
            seg.needs_review = True
            seg.review_reasons.append(f"transcription_error: {exc}")

    return "whisper-python"


def _try_whisper_cli(
    segments: list[Segment],
    model_size: str,
    language: str,
) -> str | None:
    """Attempt transcription using the whisper CLI."""
    whisper_bin = shutil.which("whisper")
    if whisper_bin is None:
        return None

    logger.info("Using Whisper CLI: %s (model=%s)", whisper_bin, model_size)

    for seg in segments:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    [
                        whisper_bin, seg.wav_path,
                        "--model", model_size,
                        "--language", language,
                        "--output_format", "json",
                        "--output_dir", tmpdir,
                    ],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    logger.warning(
                        "Whisper CLI failed for %s: %s",
                        seg.segment_id, result.stderr,
                    )
                    seg.needs_review = True
                    seg.review_reasons.append("whisper_cli_error")
                    continue

                # Read the JSON output
                json_files = list(Path(tmpdir).glob("*.json"))
                if json_files:
                    data = json.loads(json_files[0].read_text(encoding="utf-8"))
                    seg.transcript = data.get("text", "").strip()
                    if not seg.transcript:
                        seg.needs_review = True
                        seg.review_reasons.append("empty_transcript")
                else:
                    seg.needs_review = True
                    seg.review_reasons.append("no_whisper_output")
        except subprocess.TimeoutExpired:
            logger.warning("Whisper CLI timed out for %s", seg.segment_id)
            seg.needs_review = True
            seg.review_reasons.append("transcription_timeout")
        except Exception as exc:
            logger.warning("Whisper CLI error for %s: %s", seg.segment_id, exc)
            seg.needs_review = True
            seg.review_reasons.append(f"whisper_cli_exception: {exc}")

    return "whisper-cli"


# ---------------------------------------------------------------------------
# Step 3: Phoneme alignment
# ---------------------------------------------------------------------------

def align_phonemes(
    segments: list[Segment],
    dataset_dir: str,
    language: str = "en",
) -> str:
    """Align phonemes to audio using SOFA or MFA.

    Tries SOFA (Singing-Oriented Forced Aligner) first since it handles
    singing better than speech aligners. Falls back to MFA if SOFA is
    unavailable.

    Args:
        segments: Segments with transcript already filled in.
        dataset_dir: Base dataset directory for intermediate files.
        language: Language code.

    Returns:
        Name of alignment method used.
    """
    method = _try_sofa_alignment(segments, dataset_dir, language)
    if method:
        return method

    method = _try_mfa_alignment(segments, dataset_dir, language)
    if method:
        return method

    # Fallback: simple equal-duration phoneme estimation
    logger.warning(
        "No aligner (SOFA or MFA) available. Using equal-duration estimation. "
        "Results will need manual correction."
    )
    for seg in segments:
        if seg.transcript:
            phonemes = _simple_g2p(seg.transcript)
            seg.phonemes = phonemes
            # Equal duration allocation
            if phonemes:
                dur_per_phone = seg.duration_s / len(phonemes)
                seg.phone_durations = [dur_per_phone] * len(phonemes)
            seg.needs_review = True
            seg.review_reasons.append("estimated_alignment_only")
    return "equal-duration-estimate"


def _try_sofa_alignment(
    segments: list[Segment],
    dataset_dir: str,
    language: str,
) -> str | None:
    """Attempt alignment using SOFA (Singing-Oriented Forced Aligner)."""
    sofa_bin = shutil.which("sofa")
    sofa_dir = Path(PROJECT_ROOT) / "models" / "sofa"

    # Check for SOFA as Python module or CLI
    sofa_available = False
    sofa_script = None

    if sofa_bin:
        sofa_available = True
    elif sofa_dir.is_dir():
        # Look for SOFA's inference script
        candidates = list(sofa_dir.glob("**/infer.py")) + list(sofa_dir.glob("**/inference.py"))
        if candidates:
            sofa_script = str(candidates[0])
            sofa_available = True

    if not sofa_available:
        try:
            import sofa  # type: ignore[import-untyped]
            sofa_available = True
        except ImportError:
            pass

    if not sofa_available:
        logger.info("SOFA not available, will try MFA fallback.")
        return None

    logger.info("Using SOFA for phoneme alignment")
    align_dir = os.path.join(dataset_dir, "sofa_align")
    os.makedirs(align_dir, exist_ok=True)

    for seg in segments:
        if not seg.transcript:
            continue

        # Prepare SOFA input: a text file with transcript alongside WAV
        lab_path = os.path.join(align_dir, f"{seg.segment_id}.txt")
        Path(lab_path).write_text(seg.transcript, encoding="utf-8")

        try:
            cmd: list[str]
            if sofa_bin:
                cmd = [
                    sofa_bin,
                    "--wav", seg.wav_path,
                    "--text", lab_path,
                    "--output", os.path.join(align_dir, f"{seg.segment_id}.TextGrid"),
                    "--language", language,
                ]
            elif sofa_script:
                cmd = [
                    sys.executable, sofa_script,
                    "--wav", seg.wav_path,
                    "--text", lab_path,
                    "--output", os.path.join(align_dir, f"{seg.segment_id}.TextGrid"),
                ]
            else:
                # Use Python module
                cmd = [
                    sys.executable, "-m", "sofa",
                    "--wav", seg.wav_path,
                    "--text", lab_path,
                    "--output", os.path.join(align_dir, f"{seg.segment_id}.TextGrid"),
                ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )

            if result.returncode == 0:
                # Parse TextGrid output
                tg_path = os.path.join(align_dir, f"{seg.segment_id}.TextGrid")
                if os.path.exists(tg_path):
                    phonemes, durations = _parse_textgrid(tg_path)
                    seg.phonemes = phonemes
                    seg.phone_durations = durations
                else:
                    seg.needs_review = True
                    seg.review_reasons.append("sofa_no_output")
            else:
                logger.warning(
                    "SOFA failed for %s: %s", seg.segment_id, result.stderr[:200],
                )
                seg.needs_review = True
                seg.review_reasons.append("sofa_alignment_failed")

        except subprocess.TimeoutExpired:
            logger.warning("SOFA timed out for %s", seg.segment_id)
            seg.needs_review = True
            seg.review_reasons.append("sofa_timeout")
        except Exception as exc:
            logger.warning("SOFA error for %s: %s", seg.segment_id, exc)
            seg.needs_review = True
            seg.review_reasons.append(f"sofa_error: {exc}")

    return "sofa"


def _try_mfa_alignment(
    segments: list[Segment],
    dataset_dir: str,
    language: str,
) -> str | None:
    """Attempt alignment using Montreal Forced Aligner."""
    mfa_bin = shutil.which("mfa")
    if mfa_bin is None:
        logger.info("MFA not available.")
        return None

    logger.info("Using Montreal Forced Aligner")
    mfa_input = os.path.join(dataset_dir, "mfa_input")
    mfa_output = os.path.join(dataset_dir, "mfa_output")
    os.makedirs(mfa_input, exist_ok=True)
    os.makedirs(mfa_output, exist_ok=True)

    # Prepare MFA corpus: WAV + .lab files in the same directory
    for seg in segments:
        if not seg.transcript:
            continue
        # Symlink WAV into MFA input dir
        link_path = os.path.join(mfa_input, f"{seg.segment_id}.wav")
        if not os.path.exists(link_path):
            try:
                os.symlink(os.path.abspath(seg.wav_path), link_path)
            except OSError:
                shutil.copy2(seg.wav_path, link_path)

        lab_path = os.path.join(mfa_input, f"{seg.segment_id}.lab")
        Path(lab_path).write_text(seg.transcript, encoding="utf-8")

    # Run MFA alignment
    try:
        # Determine acoustic model and dictionary
        dict_name = "english_us_arpa" if language == "en" else f"{language}_mfa"
        acoustic_model = "english_us_arpa" if language == "en" else f"{language}_mfa"

        result = subprocess.run(
            [
                mfa_bin, "align",
                mfa_input,
                dict_name,
                acoustic_model,
                mfa_output,
                "--clean",
                "--overwrite",
            ],
            capture_output=True, text=True, timeout=600,
        )

        if result.returncode != 0:
            logger.warning("MFA alignment failed: %s", result.stderr[:500])
            return None

        # Parse TextGrid outputs
        for seg in segments:
            if not seg.transcript:
                continue
            tg_path = os.path.join(mfa_output, f"{seg.segment_id}.TextGrid")
            if os.path.exists(tg_path):
                phonemes, durations = _parse_textgrid(tg_path)
                seg.phonemes = phonemes
                seg.phone_durations = durations
            else:
                seg.needs_review = True
                seg.review_reasons.append("mfa_no_output")

        return "mfa"

    except subprocess.TimeoutExpired:
        logger.warning("MFA alignment timed out")
        return None
    except Exception as exc:
        logger.warning("MFA error: %s", exc)
        return None


def _parse_textgrid(tg_path: str) -> tuple[list[str], list[float]]:
    """Parse a Praat TextGrid file to extract phonemes and durations.

    Supports both short and long TextGrid formats. Looks for the 'phones'
    or 'phonemes' tier.

    Returns:
        Tuple of (phoneme_list, duration_list) in seconds.
    """
    phonemes: list[str] = []
    durations: list[float] = []

    try:
        # Try tgt library first (common TextGrid parser)
        import tgt  # type: ignore[import-untyped]
        tg = tgt.io.read_textgrid(tg_path)

        # Find the phones tier
        phone_tier = None
        for tier_name in ("phones", "phonemes", "phone", "phoneme"):
            try:
                phone_tier = tg.get_tier_by_name(tier_name)
                break
            except ValueError:
                continue

        if phone_tier is None:
            # Use the first interval tier
            for tier in tg.tiers:
                if hasattr(tier, "intervals"):
                    phone_tier = tier
                    break

        if phone_tier is not None:
            for interval in phone_tier.intervals:
                text = interval.text.strip()
                if text:
                    phonemes.append(text)
                    durations.append(interval.end_time - interval.start_time)
                else:
                    # Silent interval
                    phonemes.append("SP")
                    durations.append(interval.end_time - interval.start_time)

        return phonemes, durations

    except ImportError:
        pass

    # Fallback: manual TextGrid parsing
    try:
        content = Path(tg_path).read_text(encoding="utf-8")
        lines = content.strip().split("\n")

        in_phones_tier = False
        i = 0
        while i < len(lines):
            line = lines[i].strip().strip('"')
            if line in ("phones", "phonemes", "phone"):
                in_phones_tier = True
                i += 1
                continue

            if in_phones_tier:
                # Look for interval patterns
                if line.startswith("xmin"):
                    xmin = float(line.split("=")[1].strip())
                    i += 1
                    if i < len(lines):
                        xmax_line = lines[i].strip()
                        if xmax_line.startswith("xmax"):
                            xmax = float(xmax_line.split("=")[1].strip())
                            i += 1
                            if i < len(lines):
                                text_line = lines[i].strip()
                                if text_line.startswith("text"):
                                    text = text_line.split("=")[1].strip().strip('"')
                                    phonemes.append(text if text else "SP")
                                    durations.append(xmax - xmin)
            i += 1

    except Exception as exc:
        logger.warning("Failed to parse TextGrid %s: %s", tg_path, exc)

    return phonemes, durations


def _simple_g2p(text: str) -> list[str]:
    """Very basic grapheme-to-phoneme conversion.

    In production, use a proper G2P tool. This is a fallback that
    produces a rough approximation using common English phoneme mappings.
    """
    # Try g2p_en if available
    try:
        from g2p_en import G2p  # type: ignore[import-untyped]
        g2p = G2p()
        phonemes = g2p(text)
        return [p for p in phonemes if p.strip()]
    except ImportError:
        pass

    # Very basic fallback: split into syllable-like units
    words = text.lower().split()
    phonemes: list[str] = []
    for word in words:
        # Simple heuristic: vowels create phoneme boundaries
        current = ""
        for char in word:
            current += char
            if char in "aeiou":
                phonemes.append(current)
                current = ""
        if current:
            phonemes.append(current)
        phonemes.append("SP")  # Space between words

    # Remove trailing SP
    if phonemes and phonemes[-1] == "SP":
        phonemes.pop()

    return phonemes if phonemes else ["SP"]


# ---------------------------------------------------------------------------
# Step 4: F0 extraction
# ---------------------------------------------------------------------------

def extract_f0(
    segments: list[Segment],
    sample_rate: int = 44100,
    hop_length_s: float = 0.005,
) -> str:
    """Extract fundamental frequency (F0) curves from segments.

    Tries SOME (Singing-Oriented MIDI Extractor) first for better
    singing pitch tracking, falls back to librosa.pyin.

    Args:
        segments: Segments with wav_path set.
        sample_rate: Audio sample rate.
        hop_length_s: Time step between F0 values in seconds.

    Returns:
        Name of F0 extraction method used.
    """
    method = _try_some_f0(segments, sample_rate, hop_length_s)
    if method:
        return method

    method = _try_crepe_f0(segments, sample_rate, hop_length_s)
    if method:
        return method

    return _extract_f0_pyin(segments, sample_rate, hop_length_s)


def _try_some_f0(
    segments: list[Segment],
    sample_rate: int,
    hop_length_s: float,
) -> str | None:
    """Try SOME (Singing-Oriented MIDI Extractor) for F0 extraction."""
    some_bin = shutil.which("some")
    some_dir = Path(PROJECT_ROOT) / "models" / "some"

    some_available = False
    some_script = None

    if some_bin:
        some_available = True
    elif some_dir.is_dir():
        candidates = list(some_dir.glob("**/infer.py"))
        if candidates:
            some_script = str(candidates[0])
            some_available = True

    if not some_available:
        try:
            import some  # type: ignore[import-untyped]
            some_available = True
        except ImportError:
            pass

    if not some_available:
        return None

    logger.info("Using SOME for F0 extraction")

    for seg in segments:
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                f0_output = tmp.name

            cmd: list[str]
            if some_bin:
                cmd = [some_bin, seg.wav_path, "--output", f0_output]
            elif some_script:
                cmd = [sys.executable, some_script, seg.wav_path, "--output", f0_output]
            else:
                cmd = [sys.executable, "-m", "some", seg.wav_path, "--output", f0_output]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )

            if result.returncode == 0 and os.path.exists(f0_output):
                data = json.loads(Path(f0_output).read_text(encoding="utf-8"))
                seg.f0_values = data.get("f0", [])
                seg.f0_timestep_s = data.get("timestep", hop_length_s)
            else:
                seg.needs_review = True
                seg.review_reasons.append("some_f0_failed")

            # Clean up
            try:
                os.unlink(f0_output)
            except OSError:
                pass

        except Exception as exc:
            logger.warning("SOME F0 error for %s: %s", seg.segment_id, exc)
            seg.needs_review = True
            seg.review_reasons.append(f"some_f0_error: {exc}")

    return "some"


def _try_crepe_f0(
    segments: list[Segment],
    sample_rate: int,
    hop_length_s: float,
) -> str | None:
    """Try CREPE for F0 extraction (neural pitch tracker)."""
    try:
        import crepe  # type: ignore[import-untyped]
        import librosa
        import numpy as np
    except ImportError:
        return None

    logger.info("Using CREPE for F0 extraction")
    hop_length = int(hop_length_s * sample_rate)

    for seg in segments:
        try:
            y, sr = librosa.load(seg.wav_path, sr=sample_rate, mono=True)
            _, frequency, confidence, _ = crepe.predict(
                y, sr,
                step_size=int(hop_length_s * 1000),  # step_size in ms
                viterbi=True,
            )

            # Zero out low-confidence predictions
            frequency[confidence < 0.5] = 0.0
            seg.f0_values = frequency.tolist()
            seg.f0_timestep_s = hop_length_s

            # Flag segments with too many unvoiced frames
            voiced_ratio = np.sum(frequency > 0) / len(frequency) if len(frequency) > 0 else 0
            if voiced_ratio < 0.3:
                seg.needs_review = True
                seg.review_reasons.append(f"low_voiced_ratio: {voiced_ratio:.2f}")

        except Exception as exc:
            logger.warning("CREPE F0 error for %s: %s", seg.segment_id, exc)
            seg.needs_review = True
            seg.review_reasons.append(f"crepe_f0_error: {exc}")

    return "crepe"


def _extract_f0_pyin(
    segments: list[Segment],
    sample_rate: int,
    hop_length_s: float,
) -> str:
    """Extract F0 using librosa's pyin algorithm (always available)."""
    import librosa
    import numpy as np

    logger.info("Using librosa.pyin for F0 extraction (fallback)")
    hop_length = int(hop_length_s * sample_rate)

    for seg in segments:
        try:
            y, sr = librosa.load(seg.wav_path, sr=sample_rate, mono=True)
            f0, voiced_flag, voiced_prob = librosa.pyin(
                y, sr=sr,
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C6"),
                hop_length=hop_length,
            )

            # Replace NaN with 0.0 (unvoiced)
            f0 = np.nan_to_num(f0, nan=0.0)
            seg.f0_values = f0.tolist()
            seg.f0_timestep_s = hop_length_s

            # Check voiced ratio
            voiced_ratio = float(np.sum(voiced_flag)) / len(voiced_flag) if len(voiced_flag) > 0 else 0
            if voiced_ratio < 0.3:
                seg.needs_review = True
                seg.review_reasons.append(f"low_voiced_ratio: {voiced_ratio:.2f}")

        except Exception as exc:
            logger.warning("pyin F0 error for %s: %s", seg.segment_id, exc)
            seg.f0_values = []
            seg.needs_review = True
            seg.review_reasons.append(f"f0_extraction_failed: {exc}")

    return "librosa-pyin"


# ---------------------------------------------------------------------------
# Step 5: Format conversion to DiffSinger .ds
# ---------------------------------------------------------------------------

def convert_to_ds_format(
    segments: list[Segment],
    output_dir: str,
    sample_rate: int = 44100,
) -> list[str]:
    """Convert aligned segments to DiffSinger .ds JSON format.

    The .ds format is a JSON file per segment containing:
    - offset: start time offset
    - text: space-separated phoneme sequence
    - ph_seq: phoneme sequence list
    - ph_dur: phoneme durations in seconds
    - ph_num: number of phonemes per note (for note-phoneme mapping)
    - note_seq: MIDI note names derived from F0
    - note_dur: note durations
    - f0_seq: raw F0 values for pitch curve
    - f0_timestep: time step of F0 values

    Args:
        segments: Fully processed segments.
        output_dir: Directory to write .ds files.

    Returns:
        List of paths to generated .ds files.
    """
    import numpy as np

    ds_dir = os.path.join(output_dir, "ds")
    os.makedirs(ds_dir, exist_ok=True)
    ds_paths: list[str] = []

    for seg in segments:
        ds_entry: dict[str, Any] = {
            "offset": 0.0,
            "text": seg.transcript,
            "ph_seq": seg.phonemes if seg.phonemes else ["SP"],
            "ph_dur": seg.phone_durations if seg.phone_durations else [seg.duration_s],
            "f0_seq": seg.f0_values,
            "f0_timestep": seg.f0_timestep_s,
            "input_type": "phoneme",
            "sample_rate": sample_rate,
        }

        # Derive note sequence from F0 values
        if seg.f0_values:
            f0_arr = np.array(seg.f0_values)
            note_seq, note_dur = _f0_to_note_sequence(f0_arr, seg.f0_timestep_s)
            ds_entry["note_seq"] = note_seq
            ds_entry["note_dur"] = note_dur

            # Map phonemes to notes (ph_num)
            if seg.phonemes and note_seq:
                ph_num = _map_phonemes_to_notes(
                    seg.phonemes, seg.phone_durations,
                    note_seq, note_dur,
                )
                ds_entry["ph_num"] = ph_num

        ds_path = os.path.join(ds_dir, f"{seg.segment_id}.ds")
        Path(ds_path).write_text(
            json.dumps([ds_entry], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        ds_paths.append(ds_path)

    logger.info("Generated %d .ds files in %s", len(ds_paths), ds_dir)
    return ds_paths


def _f0_to_note_sequence(
    f0: "np.ndarray",
    timestep: float,
) -> tuple[list[str], list[float]]:
    """Convert an F0 curve to a sequence of MIDI note names with durations.

    Groups consecutive F0 frames into notes based on semitone proximity,
    creating rest tokens for unvoiced regions.
    """
    import numpy as np
    import librosa

    notes: list[str] = []
    durations: list[float] = []

    if len(f0) == 0:
        return ["rest"], [0.0]

    # Convert F0 to MIDI note numbers
    midi = np.zeros_like(f0)
    voiced_mask = f0 > 0
    if np.any(voiced_mask):
        midi[voiced_mask] = librosa.hz_to_midi(f0[voiced_mask])

    # Group into notes (allow +/- 0.5 semitone variation within a note)
    current_note = 0.0
    current_start = 0
    is_rest = not voiced_mask[0]

    for i in range(len(midi)):
        if voiced_mask[i]:
            if is_rest:
                # End rest, start new note
                if current_start < i:
                    notes.append("rest")
                    durations.append((i - current_start) * timestep)
                current_note = midi[i]
                current_start = i
                is_rest = False
            elif abs(midi[i] - current_note) > 0.5:
                # New note
                notes.append(librosa.midi_to_note(round(current_note)))
                durations.append((i - current_start) * timestep)
                current_note = midi[i]
                current_start = i
        else:
            if not is_rest:
                # End note, start rest
                notes.append(librosa.midi_to_note(round(current_note)))
                durations.append((i - current_start) * timestep)
                current_start = i
                is_rest = True

    # Final segment
    remaining = (len(midi) - current_start) * timestep
    if remaining > 0:
        if is_rest:
            notes.append("rest")
        else:
            notes.append(librosa.midi_to_note(round(current_note)))
        durations.append(remaining)

    return notes, durations


def _map_phonemes_to_notes(
    phonemes: list[str],
    phone_durations: list[float],
    note_seq: list[str],
    note_dur: list[float],
) -> list[int]:
    """Map phonemes to notes based on temporal overlap.

    Returns a list of integers where each value is the number of
    phonemes that belong to the corresponding note.
    """
    if not phonemes or not note_seq:
        return [len(phonemes)] if note_seq else []

    ph_num = [0] * len(note_seq)

    # Build note time boundaries
    note_starts: list[float] = []
    note_ends: list[float] = []
    t = 0.0
    for dur in note_dur:
        note_starts.append(t)
        note_ends.append(t + dur)
        t += dur

    # For each phoneme, find the note it overlaps most with
    ph_time = 0.0
    for i, (ph, dur) in enumerate(zip(phonemes, phone_durations)):
        ph_center = ph_time + dur / 2.0
        # Find closest note
        best_note = 0
        best_dist = float("inf")
        for j in range(len(note_seq)):
            note_center = (note_starts[j] + note_ends[j]) / 2.0
            dist = abs(ph_center - note_center)
            if dist < best_dist:
                best_dist = dist
                best_note = j
        ph_num[best_note] += 1
        ph_time += dur

    # Ensure every note has at least 1 phoneme
    for j in range(len(ph_num)):
        if ph_num[j] == 0:
            ph_num[j] = 1

    return ph_num


# ---------------------------------------------------------------------------
# Step 6: Quality assessment
# ---------------------------------------------------------------------------

def assess_quality(
    segments: list[Segment],
    sample_rate: int = 44100,
) -> None:
    """Score each segment and flag those needing manual review.

    Checks for:
    - Clipping (peak amplitude near 1.0)
    - Very low energy (near-silent segments)
    - Excessive noise (low SNR estimate)
    - Missing or incomplete alignments
    - F0 tracking issues (too many unvoiced frames)
    """
    import librosa
    import numpy as np

    for seg in segments:
        score = 1.0  # Start at perfect

        try:
            y, sr = librosa.load(seg.wav_path, sr=sample_rate, mono=True)

            # Check clipping
            peak = float(np.max(np.abs(y)))
            if peak > 0.99:
                score -= 0.3
                seg.review_reasons.append("clipping_detected")
                seg.needs_review = True

            # Check energy
            rms = float(np.sqrt(np.mean(y ** 2)))
            if rms < 0.01:
                score -= 0.4
                seg.review_reasons.append("very_low_energy")
                seg.needs_review = True

            # Check duration
            if seg.duration_s < 2.0:
                score -= 0.2
                seg.review_reasons.append("very_short_segment")
            elif seg.duration_s > 20.0:
                score -= 0.1
                seg.review_reasons.append("very_long_segment")

        except Exception as exc:
            score = 0.0
            seg.review_reasons.append(f"audio_analysis_error: {exc}")
            seg.needs_review = True

        # Check alignment completeness
        if not seg.phonemes:
            score -= 0.3
            seg.review_reasons.append("no_phonemes")
            seg.needs_review = True

        if not seg.transcript:
            score -= 0.2
            seg.review_reasons.append("no_transcript")
            seg.needs_review = True

        if not seg.f0_values:
            score -= 0.2
            seg.review_reasons.append("no_f0")
            seg.needs_review = True

        # Deduplicate review reasons
        seg.review_reasons = list(dict.fromkeys(seg.review_reasons))
        seg.quality_score = max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    segments: list[Segment],
    report: DatasetReport,
    output_dir: str,
) -> str:
    """Write a JSON quality report and print a summary to the console.

    Returns the path to the report JSON file.
    """
    report.total_segments = len(segments)
    report.total_duration_s = sum(s.duration_s for s in segments)
    report.avg_segment_duration_s = (
        report.total_duration_s / report.total_segments
        if report.total_segments > 0 else 0.0
    )
    report.avg_quality_score = (
        sum(s.quality_score for s in segments) / len(segments)
        if segments else 0.0
    )
    report.segments_needing_review = sum(1 for s in segments if s.needs_review)

    # Write detailed report
    report_data = {
        "summary": asdict(report),
        "segments": [],
    }
    for seg in segments:
        report_data["segments"].append({
            "segment_id": seg.segment_id,
            "source_file": seg.source_file,
            "duration_s": round(seg.duration_s, 2),
            "transcript": seg.transcript,
            "num_phonemes": len(seg.phonemes),
            "num_f0_frames": len(seg.f0_values),
            "quality_score": round(seg.quality_score, 3),
            "needs_review": seg.needs_review,
            "review_reasons": seg.review_reasons,
        })

    report_path = os.path.join(output_dir, "quality_report.json")
    Path(report_path).write_text(
        json.dumps(report_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Print rich console summary
    console.print()
    console.print(Panel.fit(
        f"[bold]DiffSinger Dataset Preparation Report[/bold]\n"
        f"Voice: {report.voice_name}",
        border_style="green",
    ))

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value")
    table.add_row("Total recordings", str(report.total_recordings))
    table.add_row("Total segments", str(report.total_segments))
    table.add_row("Total duration", f"{report.total_duration_s:.1f}s ({report.total_duration_s / 60:.1f}min)")
    table.add_row("Avg segment duration", f"{report.avg_segment_duration_s:.1f}s")
    table.add_row("Avg quality score", f"{report.avg_quality_score:.3f}")
    table.add_row("Segments needing review", f"{report.segments_needing_review} / {report.total_segments}")
    table.add_row("Transcription method", report.transcription_method)
    table.add_row("Alignment method", report.alignment_method)
    table.add_row("F0 method", report.f0_method)
    console.print(table)

    if report.segments_needing_review > 0:
        console.print()
        console.print("[yellow]Segments needing manual review:[/yellow]")
        review_table = Table(show_header=True, header_style="bold yellow")
        review_table.add_column("Segment ID")
        review_table.add_column("Duration")
        review_table.add_column("Score")
        review_table.add_column("Issues")
        for seg in segments:
            if seg.needs_review:
                review_table.add_row(
                    seg.segment_id,
                    f"{seg.duration_s:.1f}s",
                    f"{seg.quality_score:.2f}",
                    ", ".join(seg.review_reasons),
                )
        console.print(review_table)

    if report.errors:
        console.print()
        console.print("[red]Errors:[/red]")
        for err in report.errors:
            console.print(f"  [red]- {err}[/red]")

    if report.warnings:
        console.print()
        console.print("[yellow]Warnings:[/yellow]")
        for warn in report.warnings:
            console.print(f"  [yellow]- {warn}[/yellow]")

    console.print()
    console.print(f"[green]Report saved to: {report_path}[/green]")

    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--input-dir", "-i",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory containing WAV recordings.",
)
@click.option(
    "--output-dir", "-o",
    required=True,
    type=click.Path(file_okay=False),
    help="Output directory for the DiffSinger dataset.",
)
@click.option(
    "--voice-name", "-n",
    required=True,
    help="Name for this voice dataset.",
)
@click.option(
    "--sample-rate", "-sr",
    default=44100,
    type=int,
    help="Target sample rate for audio segments.",
)
@click.option(
    "--whisper-model",
    default="base",
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    help="Whisper model size for transcription.",
)
@click.option(
    "--language", "-l",
    default="en",
    help="Language code for transcription and alignment.",
)
@click.option(
    "--min-duration",
    default=5.0,
    type=float,
    help="Minimum segment duration in seconds.",
)
@click.option(
    "--max-duration",
    default=15.0,
    type=float,
    help="Maximum segment duration in seconds.",
)
@click.option(
    "--silence-threshold",
    default=-40.0,
    type=float,
    help="Silence detection threshold in dB.",
)
@click.option(
    "--skip-transcription",
    is_flag=True,
    help="Skip transcription step (use if transcripts provided separately).",
)
@click.option(
    "--skip-alignment",
    is_flag=True,
    help="Skip phoneme alignment step.",
)
@click.option(
    "--skip-f0",
    is_flag=True,
    help="Skip F0 extraction step.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
def main(
    input_dir: str,
    output_dir: str,
    voice_name: str,
    sample_rate: int,
    whisper_model: str,
    language: str,
    min_duration: float,
    max_duration: float,
    silence_threshold: float,
    skip_transcription: bool,
    skip_alignment: bool,
    skip_f0: bool,
    verbose: bool,
) -> None:
    """Prepare vocal recordings for DiffSinger training.

    Takes a directory of WAV files and produces a DiffSinger-ready dataset
    with segmented audio, phoneme alignments, F0 curves, and .ds project files.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    console.print(Panel.fit(
        f"[bold cyan]DiffSinger Dataset Preparation[/bold cyan]\n"
        f"Voice: {voice_name}\n"
        f"Input: {input_dir}\n"
        f"Output: {output_dir}",
        border_style="cyan",
    ))

    # Discover input WAV files
    input_path = Path(input_dir)
    wav_files = sorted(
        list(input_path.glob("*.wav"))
        + list(input_path.glob("*.WAV"))
        + list(input_path.glob("**/*.wav"))
    )
    # Deduplicate (glob patterns may overlap)
    wav_files = sorted(set(wav_files))

    if not wav_files:
        console.print("[red]No WAV files found in input directory.[/red]")
        sys.exit(1)

    console.print(f"\nFound [bold]{len(wav_files)}[/bold] WAV file(s).\n")

    # Create output directory structure
    os.makedirs(output_dir, exist_ok=True)
    wavs_dir = os.path.join(output_dir, "wavs")
    os.makedirs(wavs_dir, exist_ok=True)

    report = DatasetReport(voice_name=voice_name, total_recordings=len(wav_files))
    all_segments: list[Segment] = []

    # Step 1: Segmentation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Segmenting recordings...", total=len(wav_files))
        for wav_file in wav_files:
            try:
                segments = segment_audio(
                    str(wav_file),
                    wavs_dir,
                    min_duration_s=min_duration,
                    max_duration_s=max_duration,
                    silence_threshold_db=silence_threshold,
                    sample_rate=sample_rate,
                )
                all_segments.extend(segments)
            except Exception as exc:
                err_msg = f"Failed to segment {wav_file.name}: {exc}"
                logger.error(err_msg)
                report.errors.append(err_msg)
            progress.advance(task)

    console.print(f"  Segmented into [bold]{len(all_segments)}[/bold] segments.\n")

    if not all_segments:
        console.print("[red]No segments produced. Check your input files.[/red]")
        sys.exit(1)

    # Step 2: Transcription
    if not skip_transcription:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Transcribing segments...", total=None)
            report.transcription_method = transcribe_segments(
                all_segments,
                model_size=whisper_model,
                language=language,
            )
            progress.update(task, completed=True)
        console.print(f"  Transcription method: [bold]{report.transcription_method}[/bold]\n")
    else:
        report.transcription_method = "skipped"
        console.print("  [dim]Transcription skipped.[/dim]\n")

    # Step 3: Phoneme alignment
    if not skip_alignment:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Aligning phonemes...", total=None)
            report.alignment_method = align_phonemes(
                all_segments,
                output_dir,
                language=language,
            )
            progress.update(task, completed=True)
        console.print(f"  Alignment method: [bold]{report.alignment_method}[/bold]\n")
    else:
        report.alignment_method = "skipped"
        console.print("  [dim]Alignment skipped.[/dim]\n")

    # Step 4: F0 extraction
    if not skip_f0:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Extracting F0 curves...", total=None)
            report.f0_method = extract_f0(
                all_segments,
                sample_rate=sample_rate,
            )
            progress.update(task, completed=True)
        console.print(f"  F0 method: [bold]{report.f0_method}[/bold]\n")
    else:
        report.f0_method = "skipped"
        console.print("  [dim]F0 extraction skipped.[/dim]\n")

    # Step 5: Format conversion
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Converting to .ds format...", total=None)
        ds_paths = convert_to_ds_format(all_segments, output_dir, sample_rate)
        progress.update(task, completed=True)
    console.print(f"  Generated [bold]{len(ds_paths)}[/bold] .ds files.\n")

    # Step 6: Quality assessment
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Assessing quality...", total=None)
        assess_quality(all_segments, sample_rate)
        progress.update(task, completed=True)

    # Write transcriptions file (for reference/editing)
    transcriptions_path = os.path.join(output_dir, "transcriptions.txt")
    with open(transcriptions_path, "w", encoding="utf-8") as f:
        for seg in all_segments:
            f.write(f"{seg.segment_id}|{seg.transcript}\n")
    console.print(f"  Transcriptions saved to: {transcriptions_path}\n")

    # Write metadata JSON
    metadata_path = os.path.join(output_dir, "metadata.json")
    metadata = {
        "voice_name": voice_name,
        "sample_rate": sample_rate,
        "language": language,
        "num_segments": len(all_segments),
        "total_duration_s": sum(s.duration_s for s in all_segments),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "transcription_method": report.transcription_method,
        "alignment_method": report.alignment_method,
        "f0_method": report.f0_method,
    }
    Path(metadata_path).write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    # Generate final report
    generate_report(all_segments, report, output_dir)

    console.print("[bold green]Dataset preparation complete.[/bold green]\n")


if __name__ == "__main__":
    main()
