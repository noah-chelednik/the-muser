"""Stereo Width & Mix Quality — soft score dimension.

Measures stereo width via mid/side decomposition and evaluates
mix balance. Falls back gracefully if audio is mono.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from src.curation.models import DimensionResult

logger = logging.getLogger(__name__)


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Analyse stereo width and mix quality.

    Args:
        samples: Mono float32 waveform (default channel).
        sr: Sample rate.
        config: soft_weights config dict.
        **kwargs: Optional ``samples_stereo`` (np.ndarray, shape (2, N) or (N, 2)),
                  ``genre`` (str), ``corpus_profile`` (dict).

    Returns:
        DimensionResult with stereo mix score.
    """
    try:
        # ── Get stereo data ──────────────────────────────────────────
        stereo = kwargs.get("samples_stereo")

        if stereo is not None:
            stereo = np.asarray(stereo, dtype=np.float32)
            # Normalize to shape (2, N)
            if stereo.ndim == 1:
                # Mono disguised as stereo
                stereo = None
            elif stereo.ndim == 2:
                if stereo.shape[0] == 2:
                    pass  # already (2, N)
                elif stereo.shape[1] == 2:
                    stereo = stereo.T  # (N, 2) -> (2, N)
                elif stereo.shape[0] == 1 or stereo.shape[1] == 1:
                    stereo = None  # mono
                else:
                    stereo = None
            else:
                stereo = None

        # ── Mono fallback ────────────────────────────────────────────
        if stereo is None:
            return DimensionResult(
                name="stereo_mix",
                score=0.5,
                raw_metrics={
                    "stereo_width": 0.0,
                    "mid_side_ratio": 0.0,
                    "phase_correlation": 1.0,
                    "note": "mono input",
                },
            )

        # Edge cases
        if stereo.shape[1] == 0:
            return _empty("empty audio")

        duration = stereo.shape[1] / max(sr, 1)
        if duration < 1.0:
            return _empty("audio too short (<1 s)")

        left = stereo[0]
        right = stereo[1]

        # ── Mid/Side decomposition ───────────────────────────────────
        mid = (left + right) / 2.0
        side = (left - right) / 2.0

        rms_mid = float(np.sqrt(np.mean(mid**2)))
        rms_side = float(np.sqrt(np.mean(side**2)))

        stereo_width = rms_side / max(rms_mid, 1e-10)
        mid_side_ratio = rms_mid / max(rms_side, 1e-10)

        # ── Phase correlation ────────────────────────────────────────
        # Pearson correlation between L and R
        if len(left) > 1:
            l_centered = left - np.mean(left)
            r_centered = right - np.mean(right)
            norm_l = np.linalg.norm(l_centered)
            norm_r = np.linalg.norm(r_centered)
            if norm_l > 1e-10 and norm_r > 1e-10:
                phase_correlation = float(np.dot(l_centered, r_centered) / (norm_l * norm_r))
            else:
                phase_correlation = 1.0
        else:
            phase_correlation = 1.0

        # ── Scoring ──────────────────────────────────────────────────
        corpus_profile = kwargs.get("corpus_profile")

        # Width score: bell curve
        if corpus_profile and isinstance(corpus_profile, dict):
            sw_stats = corpus_profile.get("stereo_width")
            if sw_stats and isinstance(sw_stats, dict):
                width_center = sw_stats.get("mean", 0.4)
                width_sigma = sw_stats.get("std", 0.25)
            else:
                width_center = 0.4
                width_sigma = 0.25
        else:
            width_center = 0.4
            width_sigma = 0.25

        width_sigma = max(width_sigma, 0.01)
        width_score = float(np.exp(-(((stereo_width - width_center) / width_sigma) ** 2)))

        # Mid/side balance score: bell curve centered at 3.0, sigma 2.0
        ms_center = 3.0
        ms_sigma = 2.0
        ms_score = float(np.exp(-(((mid_side_ratio - ms_center) / ms_sigma) ** 2)))

        # Composite
        score = 0.5 * width_score + 0.5 * ms_score
        score = float(np.clip(score, 0.0, 1.0))

        return DimensionResult(
            name="stereo_mix",
            score=score,
            raw_metrics={
                "stereo_width": round(stereo_width, 4),
                "mid_side_ratio": round(mid_side_ratio, 4),
                "phase_correlation": round(phase_correlation, 4),
            },
        )

    except Exception as e:
        logger.exception("Stereo mix analysis failed")
        return DimensionResult(
            name="stereo_mix",
            score=0.0,
            raw_metrics={"error": str(e)},
        )


def _empty(reason: str) -> DimensionResult:
    """Return a zero-score result for degenerate inputs."""
    return DimensionResult(
        name="stereo_mix",
        score=0.0,
        raw_metrics={"error": reason},
    )
