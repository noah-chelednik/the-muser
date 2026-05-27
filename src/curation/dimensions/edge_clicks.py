"""Edge Clicks — hard gate dimension.

Detects clicks at the very start and end of the audio file, as well
as abrupt endings where the outro energy is still high relative to
the track average.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from src.curation.models import DimensionResult, HardGateResult

logger = logging.getLogger(__name__)

EDGE_REGION_MS = 100  # check first/last 100 ms
ABRUPT_ENDING_RATIO = 0.75  # outro > 75% of track average = abrupt


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Detect edge clicks and abrupt endings.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: Hard-gate config dict (needs ``edge_click_threshold``).

    Returns:
        DimensionResult with edge-click score and hard gate.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _fail("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        total = len(samples)
        duration = total / max(sr, 1)

        if duration < 0.05:
            return _fail("audio too short (<50 ms)")

        edge_threshold = config.get("edge_click_threshold", 0.3)
        edge_samples = int(EDGE_REGION_MS / 1000.0 * sr)
        edge_samples = max(edge_samples, 2)  # need at least 2 for diff

        # ── Intro region (first 100 ms) ───────────────────────────────
        intro = samples[: min(edge_samples, total)]
        intro_max_diff = float(np.max(np.abs(np.diff(intro)))) if len(intro) > 1 else 0.0
        intro_click = intro_max_diff > edge_threshold

        # ── Outro region (last 100 ms) ────────────────────────────────
        outro = samples[max(0, total - edge_samples) :]
        outro_max_diff = float(np.max(np.abs(np.diff(outro)))) if len(outro) > 1 else 0.0
        outro_click = outro_max_diff > edge_threshold

        # ── Abrupt ending check ───────────────────────────────────────
        # Compare outro RMS to track average RMS
        track_rms = float(np.sqrt(np.mean(samples**2)))
        outro_rms = float(np.sqrt(np.mean(outro**2)))
        abrupt_ending = outro_rms > (ABRUPT_ENDING_RATIO * track_rms) and track_rms > 1e-6

        # ── Sub-scores ────────────────────────────────────────────────
        # Intro quality: 1.0 if no click, scaled down by how far over threshold
        intro_quality = (
            1.0
            if not intro_click
            else max(0.0, 1.0 - (intro_max_diff - edge_threshold) / max(edge_threshold, 1e-6))
        )

        # Outro quality: penalise both clicks and abrupt endings
        outro_quality = 1.0
        if outro_click:
            outro_quality *= max(
                0.0, 1.0 - (outro_max_diff - edge_threshold) / max(edge_threshold, 1e-6)
            )
        if abrupt_ending:
            # Scale penalty by how much over the threshold
            ending_penalty = min(1.0, (outro_rms / max(track_rms, 1e-6)) - ABRUPT_ENDING_RATIO)
            outro_quality *= max(0.0, 1.0 - ending_penalty)

        # Click-free edges: binary
        click_free = 1.0 if (not intro_click and not outro_click) else 0.0

        # ── Composite score ───────────────────────────────────────────
        # Weighted: intro 0.3, outro 0.5, click-free 0.2
        score = 0.3 * intro_quality + 0.5 * outro_quality + 0.2 * click_free
        score = float(np.clip(score, 0.0, 1.0))

        # ── Hard gate ─────────────────────────────────────────────────
        has_click = intro_click or outro_click
        passed = not has_click

        reasons: list[str] = []
        if intro_click:
            reasons.append(f"intro_click: max_diff={intro_max_diff:.3f} > {edge_threshold}")
        if outro_click:
            reasons.append(f"outro_click: max_diff={outro_max_diff:.3f} > {edge_threshold}")

        return DimensionResult(
            name="edge_clicks",
            score=score,
            hard_gate=HardGateResult(
                passed=passed,
                value=float(max(intro_max_diff, outro_max_diff)),
                threshold=float(edge_threshold),
                reason="; ".join(reasons) if reasons else "",
            ),
            raw_metrics={
                "intro_max_diff": round(intro_max_diff, 6),
                "outro_max_diff": round(outro_max_diff, 6),
                "intro_click": intro_click,
                "outro_click": outro_click,
                "abrupt_ending": abrupt_ending,
                "track_rms": round(track_rms, 6),
                "outro_rms": round(outro_rms, 6),
                "intro_quality": round(intro_quality, 4),
                "outro_quality": round(outro_quality, 4),
                "click_free": click_free,
                "duration_s": round(duration, 2),
            },
        )

    except Exception as e:
        logger.exception("Edge click analysis failed")
        return _fail(f"analysis_error: {e}")


def _fail(reason: str) -> DimensionResult:
    """Return a zero-score failing result."""
    return DimensionResult(
        name="edge_clicks",
        score=0.0,
        hard_gate=HardGateResult(
            passed=False,
            value=0.0,
            threshold=0.0,
            reason=reason,
        ),
    )
