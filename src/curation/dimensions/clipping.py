"""Clipping & Digital Ceiling — hard gate dimension.

Detects hard clipping (|sample| >= 0.999), sustained soft clipping
(runs of >10 consecutive samples above 0.95), and true-peak
clipping via 4x upsampling.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from scipy.signal import resample

from src.curation.models import DimensionResult, HardGateResult

logger = logging.getLogger(__name__)

# Detection thresholds
HARD_CLIP_THRESHOLD = 0.999
SOFT_CLIP_THRESHOLD = 0.95
SOFT_CLIP_MIN_RUN = 10
TRUE_PEAK_THRESHOLD = 0.999
TRUE_PEAK_UPSAMPLE = 4
TRUE_PEAK_WINDOW_MS = 50  # analyse in short windows to limit memory


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Detect clipping in waveform.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: Hard-gate config dict (needs ``clipped_ratio_max``).

    Returns:
        DimensionResult with clipping score and hard gate.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _fail("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        total = len(samples)

        if total < 2:
            return _fail("audio too short")

        abs_samples = np.abs(samples)

        # ── Hard clip count ───────────────────────────────────────────
        hard_clip_mask = abs_samples >= HARD_CLIP_THRESHOLD
        hard_clip_count = int(np.sum(hard_clip_mask))

        # ── Soft clip: sustained runs > 10 consecutive above 0.95 ────
        soft_mask = abs_samples > SOFT_CLIP_THRESHOLD
        soft_clip_runs = 0
        soft_clip_samples = 0

        if np.any(soft_mask):
            # Find run lengths via diff of mask
            changes = np.diff(soft_mask.astype(np.int8))
            starts = np.where(changes == 1)[0] + 1
            ends = np.where(changes == -1)[0] + 1

            # Handle edge cases where mask starts or ends True
            if soft_mask[0]:
                starts = np.concatenate([[0], starts])
            if soft_mask[-1]:
                ends = np.concatenate([ends, [total]])

            for s, e in zip(starts, ends):
                run_len = e - s
                if run_len > SOFT_CLIP_MIN_RUN:
                    soft_clip_runs += 1
                    soft_clip_samples += run_len

        # ── True peak via 4x upsampling ──────────────────────────────
        true_peak_linear = 0.0
        window_samples = int(TRUE_PEAK_WINDOW_MS / 1000.0 * sr)
        window_samples = max(window_samples, 64)

        # Only check windows that contain high-energy content
        for start in range(0, total, window_samples):
            chunk = samples[start : start + window_samples]
            if len(chunk) < 4:
                continue
            # Skip low-energy windows for speed
            if np.max(np.abs(chunk)) < 0.8:
                continue
            upsampled = resample(chunk, len(chunk) * TRUE_PEAK_UPSAMPLE)
            peak = float(np.max(np.abs(upsampled)))
            if peak > true_peak_linear:
                true_peak_linear = peak

        # If we never found a high-energy window, use original peak
        if true_peak_linear == 0.0:
            true_peak_linear = float(np.max(abs_samples))

        true_peak_clipped = true_peak_linear >= TRUE_PEAK_THRESHOLD

        # ── Clipped ratio ─────────────────────────────────────────────
        clipped_count = hard_clip_count + soft_clip_samples
        clipped_ratio = clipped_count / total

        # ── Score ─────────────────────────────────────────────────────
        # Scale linearly: 1.0 at zero clipping, 0.0 at gate threshold
        max_ratio = config.get("clipped_ratio_max", 0.001)
        score = 1.0 - min(1.0, clipped_ratio / max(max_ratio, 1e-10))
        score = float(np.clip(score, 0.0, 1.0))

        # Hard gate
        max_ratio = config.get("clipped_ratio_max", 0.001)
        passed = clipped_ratio <= max_ratio

        return DimensionResult(
            name="clipping",
            score=score,
            hard_gate=HardGateResult(
                passed=passed,
                value=float(clipped_ratio),
                threshold=float(max_ratio),
                reason="" if passed else (
                    f"clipped_ratio={clipped_ratio:.6f} exceeds "
                    f"max {max_ratio}"
                ),
            ),
            raw_metrics={
                "hard_clip_count": int(hard_clip_count),
                "soft_clip_runs": int(soft_clip_runs),
                "soft_clip_samples": int(soft_clip_samples),
                "clipped_ratio": round(clipped_ratio, 8),
                "true_peak_linear": round(true_peak_linear, 6),
                "true_peak_dbfs": round(
                    20.0 * np.log10(max(true_peak_linear, 1e-10)), 2
                ),
                "true_peak_clipped": true_peak_clipped,
                "total_samples": total,
            },
        )

    except Exception as e:
        logger.exception("Clipping analysis failed")
        return _fail(f"analysis_error: {e}")


def _fail(reason: str) -> DimensionResult:
    """Return a zero-score failing result."""
    return DimensionResult(
        name="clipping",
        score=0.0,
        hard_gate=HardGateResult(
            passed=False,
            value=0.0,
            threshold=0.0,
            reason=reason,
        ),
    )
