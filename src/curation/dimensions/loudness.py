"""Extreme Loudness — hard gate dimension.

Measures integrated LUFS and true peak via ffmpeg's loudnorm filter.
Falls back to a numpy-only estimate when ffmpeg is unavailable or
no wav_path is provided.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any

import numpy as np

from src.curation.models import DimensionResult, HardGateResult

logger = logging.getLogger(__name__)

# Bell curve centred at -14 LUFS, σ = 10
LUFS_CENTER = -14.0
LUFS_SIGMA = 10.0


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Measure integrated loudness and true peak.

    Args:
        samples: Mono float32 waveform (used for fallback estimation).
        sr: Sample rate.
        config: Hard-gate config dict (needs ``lufs_min``, ``lufs_max``,
                ``true_peak_max_dbtp``).
        wav_path: Path to WAV file for ffmpeg analysis.

    Returns:
        DimensionResult with loudness score and hard gate.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _fail("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 0.1:
            return _fail("audio too short (<0.1 s)")

        wav_path = kwargs.get("wav_path")
        lufs: float | None = None
        true_peak_dbtp: float | None = None
        measurement_method = "ffmpeg"

        # ── Try ffmpeg loudnorm ───────────────────────────────────────
        if wav_path:
            lufs, true_peak_dbtp = _ffmpeg_loudnorm(str(wav_path))

        # ── Fallback: numpy estimate ──────────────────────────────────
        if lufs is None:
            measurement_method = "numpy_estimate"
            lufs, true_peak_dbtp = _numpy_loudness(samples, sr)

        # ── Score: bell curve centred at -14 LUFS ─────────────────────
        score = np.exp(-0.5 * ((lufs - LUFS_CENTER) / LUFS_SIGMA) ** 2)
        score = float(np.clip(score, 0.0, 1.0))

        # ── Hard gate ─────────────────────────────────────────────────
        lufs_min = config.get("lufs_min", -40)
        lufs_max = config.get("lufs_max", -4)
        tp_max = config.get("true_peak_max_dbtp", 2.0)

        reasons: list[str] = []
        if lufs < lufs_min:
            reasons.append(f"LUFS={lufs:.1f} below min {lufs_min}")
        if lufs > lufs_max:
            reasons.append(f"LUFS={lufs:.1f} above max {lufs_max}")
        if true_peak_dbtp > tp_max:
            reasons.append(
                f"true_peak={true_peak_dbtp:.1f} dBTP exceeds max {tp_max}"
            )

        passed = len(reasons) == 0

        return DimensionResult(
            name="loudness",
            score=score,
            hard_gate=HardGateResult(
                passed=passed,
                value=float(lufs),
                threshold=float(lufs_max),
                reason="; ".join(reasons) if reasons else "",
            ),
            raw_metrics={
                "lufs_integrated": round(lufs, 2),
                "true_peak_dbtp": round(true_peak_dbtp, 2),
                "measurement_method": measurement_method,
                "duration_s": round(duration, 2),
            },
        )

    except Exception as e:
        logger.exception("Loudness analysis failed")
        return _fail(f"analysis_error: {e}")


# ─── Helpers ──────────────────────────────────────────────────────────────


def _ffmpeg_loudnorm(wav_path: str) -> tuple[float | None, float | None]:
    """Run ffmpeg loudnorm and parse JSON output from stderr."""
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-nostats",
            "-i", wav_path,
            "-af", "loudnorm=print_format=json",
            "-f", "null", "-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        stderr = result.stderr

        # Extract the JSON block from ffmpeg stderr
        # loudnorm prints a JSON object at the end of stderr
        json_match = re.search(
            r"\{[^{}]*\"input_i\"[^{}]*\}",
            stderr,
            re.DOTALL,
        )
        if not json_match:
            logger.warning("Could not find loudnorm JSON in ffmpeg output")
            return None, None

        data = json.loads(json_match.group())

        lufs = float(data.get("input_i", -70))
        true_peak = float(data.get("input_tp", 0.0))

        return lufs, true_peak

    except FileNotFoundError:
        logger.debug("ffmpeg not found, falling back to numpy estimate")
        return None, None
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg loudnorm timed out")
        return None, None
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to parse ffmpeg loudnorm output: %s", e)
        return None, None


def _numpy_loudness(
    samples: np.ndarray,
    sr: int,
) -> tuple[float, float]:
    """Rough LUFS estimate using RMS (no K-weighting).

    This is a simplified approximation. True EBU R128 requires
    K-weighting and gating, but this is adequate for hard-gate
    screening when ffmpeg is unavailable.
    """
    # RMS power
    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < 1e-10:
        return -70.0, -70.0

    # Approximate LUFS as dBFS - 0.691 (K-weight offset for speech/music)
    lufs_estimate = max(-70.0, 20.0 * np.log10(rms) - 0.691)

    # True peak (sample peak in dBFS, no upsampling)
    peak = float(np.max(np.abs(samples)))
    if peak < 1e-10:
        true_peak_db = -70.0
    else:
        true_peak_db = 20.0 * np.log10(peak)

    return lufs_estimate, true_peak_db


def _fail(reason: str) -> DimensionResult:
    """Return a zero-score failing result."""
    return DimensionResult(
        name="loudness",
        score=0.0,
        hard_gate=HardGateResult(
            passed=False,
            value=0.0,
            threshold=0.0,
            reason=reason,
        ),
    )
