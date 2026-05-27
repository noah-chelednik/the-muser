"""Phase Cancellation — hard gate dimension.

Detects stereo phase issues by computing mid/side decomposition,
phase correlation, and stereo width. Mono input auto-passes with
a neutral score of 0.5.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from src.curation.models import DimensionResult, HardGateResult

logger = logging.getLogger(__name__)


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Detect phase cancellation in stereo audio.

    Args:
        samples: Stereo float32 waveform, shape ``(2, N)``.
                 Mono (1D) input auto-passes.
        sr: Sample rate.
        config: Hard-gate config dict (needs ``phase_correlation_min``).

    Returns:
        DimensionResult with phase score and hard gate.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None:
            return _fail("empty audio")

        samples = np.asarray(samples, dtype=np.float32)

        if samples.size == 0:
            return _fail("empty audio")

        # ── Mono detection: auto-pass ─────────────────────────────────
        if samples.ndim == 1:
            return DimensionResult(
                name="phase",
                score=1.0,
                hard_gate=HardGateResult(
                    passed=True,
                    value=1.0,
                    threshold=config.get("phase_correlation_min", -0.1),
                    reason="mono input — phase check not applicable",
                ),
                raw_metrics={"mono": True, "channels": 1},
            )

        # Handle (N, 2) shape — transpose to (2, N)
        if samples.ndim == 2 and samples.shape[0] != 2 and samples.shape[1] == 2:
            samples = samples.T

        if samples.ndim != 2 or samples.shape[0] != 2:
            return _fail(
                f"unexpected shape {samples.shape}, expected (2, N)"
            )

        if samples.shape[1] < 2:
            return _fail("audio too short")

        left = samples[0]
        right = samples[1]

        # ── Mid / Side decomposition ──────────────────────────────────
        mid = (left + right) / 2.0
        side = (left - right) / 2.0

        # ── Phase correlation ─────────────────────────────────────────
        # Pearson correlation between L and R
        phase_correlation = float(np.corrcoef(left, right)[0, 1])

        # Handle NaN (e.g. constant signal)
        if np.isnan(phase_correlation):
            phase_correlation = 0.0

        # ── Stereo width ──────────────────────────────────────────────
        rms_mid = float(np.sqrt(np.mean(mid ** 2)))
        rms_side = float(np.sqrt(np.mean(side ** 2)))
        stereo_width = rms_side / max(rms_mid, 1e-10)

        # ── Score ─────────────────────────────────────────────────────
        score = max(0.0, phase_correlation)
        score = float(np.clip(score, 0.0, 1.0))

        # ── Hard gate ─────────────────────────────────────────────────
        threshold = config.get("phase_correlation_min", -0.1)
        passed = phase_correlation >= threshold

        return DimensionResult(
            name="phase",
            score=score,
            hard_gate=HardGateResult(
                passed=passed,
                value=float(phase_correlation),
                threshold=float(threshold),
                reason="" if passed else (
                    f"phase_correlation={phase_correlation:.3f} below "
                    f"min {threshold}"
                ),
            ),
            raw_metrics={
                "phase_correlation": round(phase_correlation, 4),
                "stereo_width": round(stereo_width, 4),
                "rms_mid": round(rms_mid, 6),
                "rms_side": round(rms_side, 6),
                "mono": False,
                "channels": 2,
            },
        )

    except Exception as e:
        logger.exception("Phase analysis failed")
        return _fail(f"analysis_error: {e}")


def _fail(reason: str) -> DimensionResult:
    """Return a zero-score failing result."""
    return DimensionResult(
        name="phase",
        score=0.0,
        hard_gate=HardGateResult(
            passed=False,
            value=0.0,
            threshold=0.0,
            reason=reason,
        ),
    )
