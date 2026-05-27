"""Audio file validation for generated audio.

Checks for silence, clipping, and duration issues using ffprobe and ffmpeg.
Provides both a full validation function, a lightweight info-only query,
and a detailed quality scoring function using librosa-based metrics.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path

from src.orchestrator.config import FFMPEG_TIMEOUT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_SILENCE_FRACTION_THRESHOLD = 0.80   # Flag if > 80 % of the audio is silent.
_CLIPPING_DBFS_THRESHOLD = -0.5      # Peak above this dBFS is considered clipping.
_DURATION_TOLERANCE = 0.10           # 10 % tolerance for expected vs actual duration.
_SILENCE_DETECT_NOISE_DB = -50       # Noise floor for ffmpeg silencedetect filter.
_SILENCE_DETECT_DURATION = 0.5       # Minimum silent segment length (seconds).


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ffprobe_path() -> str | None:
    """Return the path to ffprobe, or *None* if it is not installed."""
    return shutil.which("ffprobe")


def _ffmpeg_path() -> str | None:
    """Return the path to ffmpeg, or *None* if it is not installed."""
    return shutil.which("ffmpeg")


def _run(cmd: list[str], timeout: int = FFMPEG_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with a timeout and return the result."""
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _probe_format(wav_path: str) -> dict:
    """Use ffprobe to extract duration, sample_rate, and channel count.

    Returns a dict with keys ``duration_s``, ``sample_rate``, ``channels``,
    or raises ``RuntimeError`` on failure.
    """
    ffprobe = _ffprobe_path()
    if ffprobe is None:
        raise RuntimeError("ffprobe is not installed or not found in PATH.")

    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        wav_path,
    ]
    result = _run(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed (rc={result.returncode}): {result.stderr.strip()}")

    data = json.loads(result.stdout)

    # Extract from format section.
    fmt = data.get("format", {})
    duration_s = float(fmt.get("duration", 0.0))

    # Extract from the first audio stream.
    sample_rate = 0
    channels = 0
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            sample_rate = int(s.get("sample_rate", 0))
            channels = int(s.get("channels", 0))
            # Prefer stream duration if format duration is zero.
            if duration_s == 0.0 and "duration" in s:
                duration_s = float(s["duration"])
            break

    return {
        "duration_s": duration_s,
        "sample_rate": sample_rate,
        "channels": channels,
    }


def _detect_silence(wav_path: str, duration_s: float) -> float:
    """Return the total fraction of the file that is silent.

    Uses the ffmpeg ``silencedetect`` audio filter.  Returns a float in [0, 1].
    """
    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        logger.warning("ffmpeg not found; skipping silence detection.")
        return 0.0

    cmd = [
        ffmpeg,
        "-i", wav_path,
        "-af", f"silencedetect=noise={_SILENCE_DETECT_NOISE_DB}dB:d={_SILENCE_DETECT_DURATION}",
        "-f", "null",
        "-",
    ]

    result = _run(cmd)
    # silencedetect output goes to stderr.
    output = result.stderr

    # Parse silence_duration lines.
    total_silence = 0.0
    for match in re.finditer(r"silence_duration:\s*([\d.]+)", output):
        total_silence += float(match.group(1))

    # Handle ongoing silence at end of file (silence_start without matching silence_end).
    starts = re.findall(r"silence_start:\s*([\d.]+)", output)
    ends = re.findall(r"silence_end:\s*([\d.]+)", output)
    if len(starts) > len(ends) and duration_s > 0:
        last_start = float(starts[-1])
        total_silence += duration_s - last_start

    if duration_s <= 0:
        return 0.0

    return min(total_silence / duration_s, 1.0)


def _detect_peak_dbfs(wav_path: str) -> float | None:
    """Return the peak volume in dBFS, or *None* if detection fails.

    Uses the ffmpeg ``volumedetect`` audio filter.
    """
    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        logger.warning("ffmpeg not found; skipping peak detection.")
        return None

    cmd = [
        ffmpeg,
        "-i", wav_path,
        "-af", "volumedetect",
        "-f", "null",
        "-",
    ]

    result = _run(cmd)
    output = result.stderr

    match = re.search(r"max_volume:\s*([-\d.]+)\s*dB", output)
    if match:
        return float(match.group(1))

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_audio_info(wav_path: str) -> dict:
    """Return basic audio metadata without performing validation.

    Parameters
    ----------
    wav_path:
        Path to an audio file (WAV, FLAC, MP3, etc.).

    Returns
    -------
    dict
        Keys: ``path``, ``duration_s``, ``sample_rate``, ``channels``.
        On error the dict will also contain an ``error`` key.
    """
    info: dict = {"path": wav_path}

    path = Path(wav_path)
    if not path.exists():
        info["error"] = f"File not found: {wav_path}"
        return info

    try:
        probe = _probe_format(wav_path)
        info.update(probe)
    except RuntimeError as exc:
        info["error"] = str(exc)

    return info


def check_audio(
    wav_path: str,
    expected_duration_s: float | None = None,
) -> dict:
    """Validate an audio file for common production issues.

    Parameters
    ----------
    wav_path:
        Path to an audio file (WAV, FLAC, MP3, etc.).
    expected_duration_s:
        If provided, the actual duration is compared against this value.
        A mismatch greater than 10 % is reported as an issue.

    Returns
    -------
    dict
        Keys: ``path``, ``duration_s``, ``sample_rate``, ``channels``,
        ``issues`` (list of human-readable strings), ``valid`` (bool).
    """
    issues: list[str] = []
    result: dict = {
        "path": wav_path,
        "duration_s": 0.0,
        "sample_rate": 0,
        "channels": 0,
        "issues": issues,
        "valid": False,
    }

    # --- File existence check ----------------------------------------------
    path = Path(wav_path)
    if not path.exists():
        issues.append(f"file_not_found: {wav_path}")
        return result

    # --- Probe format ------------------------------------------------------
    try:
        probe = _probe_format(wav_path)
    except RuntimeError as exc:
        issues.append(f"probe_error: {exc}")
        return result

    result["duration_s"] = probe["duration_s"]
    result["sample_rate"] = probe["sample_rate"]
    result["channels"] = probe["channels"]

    duration_s = probe["duration_s"]

    # --- Silence detection -------------------------------------------------
    try:
        silence_frac = _detect_silence(wav_path, duration_s)
        if silence_frac > _SILENCE_FRACTION_THRESHOLD:
            issues.append(
                f"mostly_silent: {silence_frac:.0%} of audio is silent "
                f"(threshold {_SILENCE_FRACTION_THRESHOLD:.0%})"
            )
    except Exception as exc:
        logger.warning("Silence detection failed: %s", exc)

    # --- Clipping detection ------------------------------------------------
    try:
        peak_db = _detect_peak_dbfs(wav_path)
        if peak_db is not None and peak_db > _CLIPPING_DBFS_THRESHOLD:
            issues.append(
                f"has_clipping: peak volume {peak_db:.1f} dBFS exceeds "
                f"threshold {_CLIPPING_DBFS_THRESHOLD:.1f} dBFS"
            )
    except Exception as exc:
        logger.warning("Clipping detection failed: %s", exc)

    # --- Duration mismatch -------------------------------------------------
    if expected_duration_s is not None and expected_duration_s > 0:
        if duration_s <= 0:
            issues.append(
                f"duration_mismatch: could not determine actual duration "
                f"(expected {expected_duration_s:.1f}s)"
            )
        else:
            ratio = abs(duration_s - expected_duration_s) / expected_duration_s
            if ratio > _DURATION_TOLERANCE:
                issues.append(
                    f"duration_mismatch: actual {duration_s:.1f}s vs "
                    f"expected {expected_duration_s:.1f}s "
                    f"(off by {ratio:.0%}, tolerance {_DURATION_TOLERANCE:.0%})"
                )

    result["valid"] = len(issues) == 0
    return result


# ---------------------------------------------------------------------------
# Quality scoring (expanded metrics)
# ---------------------------------------------------------------------------

@dataclass
class QualityReport:
    """Detailed audio quality report with per-metric scores and a composite."""

    energy_score: float
    dynamic_range_score: float
    spectral_richness: float
    spectral_centroid_consistency: float
    onset_density: float
    harmonic_to_noise_ratio: float
    loudness_range: float
    silence_ratio: float
    clipping_ratio: float
    composite_score: float
    grade: str  # "A" / "B" / "C" / "D" / "F"
    # Optional v1.5 alignment scores
    dit_lyrics_alignment: float | None = None
    pmi_text_alignment: float | None = None


QUALITY_WEIGHTS = {
    "energy_score": 0.15,
    "dynamic_range_score": 0.10,
    "spectral_richness": 0.15,
    "spectral_centroid_consistency": 0.20,
    "onset_density": 0.10,
    "harmonic_to_noise_ratio": 0.15,
    "loudness_range": 0.05,
    "silence_ratio": 0.05,
    "clipping_ratio": 0.05,
}


def _grade_from_score(score: float) -> str:
    """Map a composite score in [0, 1] to a letter grade."""
    if score >= 0.80:
        return "A"
    elif score >= 0.65:
        return "B"
    elif score >= 0.50:
        return "C"
    elif score >= 0.35:
        return "D"
    else:
        return "F"


def evaluate_quality(
    audio_path: str,
    tags: str = "",
    lyrics: str = "",
    alignment_scores: dict | None = None,
) -> QualityReport:
    """Compute a detailed quality report for an audio file.

    Uses librosa to analyse energy, dynamics, spectral content, onsets,
    harmonic balance, loudness range, silence, and clipping.

    Parameters
    ----------
    audio_path:
        Path to an audio file (WAV, FLAC, MP3, etc.).
    tags:
        Descriptive tags used during generation (reserved for future
        text-alignment scoring).
    lyrics:
        Lyrics used during generation (reserved for future lyrics-alignment
        scoring).
    alignment_scores:
        Optional dict with pre-computed alignment scores.  Recognised keys:
        ``dit_lyrics_alignment``, ``pmi_text_alignment``.

    Returns
    -------
    QualityReport
        Dataclass with individual metric scores, a weighted composite, and
        a letter grade.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(audio_path, sr=None, mono=True)

    # Guard against empty/silent audio
    if y is None or len(y) == 0:
        return QualityReport(
            energy_score=0.0,
            dynamic_range_score=0.0,
            spectral_richness=0.0,
            spectral_centroid_consistency=0.0,
            onset_density=0.0,
            harmonic_to_noise_ratio=0.0,
            loudness_range=0.0,
            silence_ratio=0.0,
            clipping_ratio=0.0,
            composite_score=0.0,
            grade="F",
        )

    duration_s = len(y) / sr if sr > 0 else 0.0

    # --- 1. Energy score ---------------------------------------------------
    rms = librosa.feature.rms(y=y)[0]
    rms_mean = float(rms.mean())
    if rms_mean < 1e-6:
        # Essentially silent – short-circuit with zeroes
        return QualityReport(
            energy_score=0.0,
            dynamic_range_score=0.0,
            spectral_richness=0.0,
            spectral_centroid_consistency=0.0,
            onset_density=0.0,
            harmonic_to_noise_ratio=0.0,
            loudness_range=0.0,
            silence_ratio=0.0,
            clipping_ratio=0.0,
            composite_score=0.0,
            grade="F",
        )
    energy_score = min(rms_mean / 0.1, 1.0)

    # --- 2. Dynamic range score --------------------------------------------
    rms_db = 20.0 * np.log10(rms + 1e-10)
    rms_db_std = float(rms_db.std())
    dynamic_range_score = min(rms_db_std / 15.0, 1.0)

    # --- 3. Spectral richness (coefficient of variation of centroid) -------
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    centroid_mean = float(centroid.mean())
    centroid_std = float(centroid.std())
    centroid_cv = centroid_std / (centroid_mean + 1e-10)
    spectral_richness = min(centroid_cv / 0.5, 1.0)

    # --- 4. Spectral centroid consistency ----------------------------------
    # Fraction of frames where the centroid jumps by > 2 standard deviations.
    centroid_diff = np.abs(np.diff(centroid))
    jump_threshold = 2.0 * centroid_std
    if jump_threshold > 0 and len(centroid_diff) > 0:
        large_jump_frac = float((centroid_diff > jump_threshold).mean())
    else:
        large_jump_frac = 0.0
    spectral_centroid_consistency = 1.0 - min(large_jump_frac / 0.15, 1.0)

    # --- 5. Onset density --------------------------------------------------
    onsets = librosa.onset.onset_detect(y=y, sr=sr)
    if duration_s > 0:
        onsets_per_sec = len(onsets) / duration_s
    else:
        onsets_per_sec = 0.0
    # Ideal range: 0.5 – 8 onsets/sec.  Map to 0–1.
    if onsets_per_sec < 0.5:
        onset_density = onsets_per_sec / 0.5  # ramp up from 0 to 1
    elif onsets_per_sec <= 8.0:
        onset_density = 1.0
    else:
        # Penalise excessive density (>8/sec), decaying toward 0 at 20/sec
        onset_density = max(1.0 - (onsets_per_sec - 8.0) / 12.0, 0.0)

    # --- 6. Harmonic-to-noise ratio ----------------------------------------
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    harmonic_energy = float(np.sum(y_harmonic ** 2))
    total_energy = float(np.sum(y ** 2))
    if total_energy > 0:
        hnr = harmonic_energy / total_energy
    else:
        hnr = 0.0
    harmonic_to_noise_ratio = min(hnr / 0.8, 1.0)

    # --- 7. Loudness range -------------------------------------------------
    rms_db_clean = rms_db[rms_db > -80]  # ignore near-silence frames
    if len(rms_db_clean) > 0:
        range_db = float(rms_db_clean.max() - rms_db_clean.min())
    else:
        range_db = 0.0
    loudness_range = min(range_db / 30.0, 1.0)

    # --- 8. Silence ratio --------------------------------------------------
    # Fraction of frames below -40 dB RMS.
    silence_threshold_db = -40.0
    if len(rms_db) > 0:
        silence_frac = float((rms_db < silence_threshold_db).mean())
    else:
        silence_frac = 1.0
    silence_ratio_score = 1.0 - silence_frac

    # --- 9. Clipping ratio -------------------------------------------------
    clip_frac = float((np.abs(y) > 0.95).mean())
    clipping_ratio_score = 1.0 - min(clip_frac * 100.0, 1.0)

    # --- Composite score ---------------------------------------------------
    metrics = {
        "energy_score": energy_score,
        "dynamic_range_score": dynamic_range_score,
        "spectral_richness": spectral_richness,
        "spectral_centroid_consistency": spectral_centroid_consistency,
        "onset_density": onset_density,
        "harmonic_to_noise_ratio": harmonic_to_noise_ratio,
        "loudness_range": loudness_range,
        "silence_ratio": silence_ratio_score,
        "clipping_ratio": clipping_ratio_score,
    }
    composite = sum(
        QUALITY_WEIGHTS[k] * v for k, v in metrics.items()
    )
    composite = round(composite, 4)

    # --- Optional alignment scores -----------------------------------------
    dit_lyrics = None
    pmi_text = None
    if alignment_scores:
        dit_lyrics = alignment_scores.get("dit_lyrics_alignment")
        pmi_text = alignment_scores.get("pmi_text_alignment")

    return QualityReport(
        energy_score=round(energy_score, 4),
        dynamic_range_score=round(dynamic_range_score, 4),
        spectral_richness=round(spectral_richness, 4),
        spectral_centroid_consistency=round(spectral_centroid_consistency, 4),
        onset_density=round(onset_density, 4),
        harmonic_to_noise_ratio=round(harmonic_to_noise_ratio, 4),
        loudness_range=round(loudness_range, 4),
        silence_ratio=round(silence_ratio_score, 4),
        clipping_ratio=round(clipping_ratio_score, 4),
        composite_score=composite,
        grade=_grade_from_score(composite),
        dit_lyrics_alignment=dit_lyrics,
        pmi_text_alignment=pmi_text,
    )
