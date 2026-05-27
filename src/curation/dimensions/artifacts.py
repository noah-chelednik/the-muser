"""Artifact Detection — hard gate dimension.

Detects non-musical transient spikes (clicks, pops, digital glitches)
by comparing first-order diff magnitude against local statistics,
then cross-referencing with librosa onset detection to exclude
legitimate musical transients.
"""

from __future__ import annotations

import logging
from typing import Any

import librosa
import numpy as np

from src.curation.models import DimensionResult, HardGateResult

logger = logging.getLogger(__name__)


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Detect non-musical artifacts in waveform.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: Hard-gate config dict (needs ``artifact_count_per_min``).

    Returns:
        DimensionResult with artifact score and hard gate.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _fail("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 0.1:
            return _fail("audio too short (<0.1 s)")

        # ── First-order diff ──────────────────────────────────────────
        diff = np.diff(samples)
        abs_diff = np.abs(diff)

        # Local σ in 500 ms sliding windows
        window_len = int(0.5 * sr)
        if window_len < 2:
            window_len = len(abs_diff)

        # Compute rolling mean and std via cumsum trick
        pad = np.zeros(window_len, dtype=np.float32)
        padded = np.concatenate([pad, abs_diff])
        cs = np.cumsum(padded)
        cs2 = np.cumsum(padded**2)

        n = window_len
        local_mean = (cs[n:] - cs[:-n]) / n
        local_var = (cs2[n:] - cs2[:-n]) / n - local_mean**2
        local_var = np.clip(local_var, 0, None)
        local_std = np.sqrt(local_var)

        # Trim to match abs_diff length
        local_mean = local_mean[: len(abs_diff)]
        local_std = local_std[: len(abs_diff)]

        # Spike mask: |diff| > local_mean + 6σ, with minimum absolute floor
        # The floor prevents quiet passages (where local std ≈ 0) from
        # generating massive false-positive counts.
        global_std = float(np.std(abs_diff))
        min_threshold = max(0.02, global_std * 2.0)  # absolute floor
        threshold = np.maximum(
            local_mean + 6.0 * np.maximum(local_std, 1e-10),
            min_threshold,
        )
        spike_indices = np.where(abs_diff > threshold)[0]

        # Skip the first window_len indices — zero-padding biases local stats
        spike_indices = spike_indices[spike_indices >= window_len]

        # ── Onset detection ───────────────────────────────────────────
        onset_frames = librosa.onset.onset_detect(
            y=samples,
            sr=sr,
            units="samples",
            backtrack=True,
        )
        onset_count = len(onset_frames)

        # Build a tolerance zone around each onset (±5 ms)
        tolerance = int(0.005 * sr)
        musical_mask = np.zeros(len(abs_diff), dtype=bool)
        for onset in onset_frames:
            lo = max(0, onset - tolerance)
            hi = min(len(abs_diff), onset + tolerance)
            musical_mask[lo:hi] = True

        # Artifacts = spikes NOT aligned with any onset
        artifact_mask = np.isin(spike_indices, np.where(~musical_mask)[0])
        artifact_indices = spike_indices[artifact_mask]
        artifact_count = len(artifact_indices)

        # ── Scoring ───────────────────────────────────────────────────
        # Normalize against per-minute allowance for meaningful granularity
        artifacts_per_min = artifact_count / max(duration / 60.0, 0.001)
        allowed_per_min = config.get("artifact_count_per_min", 10)
        score = 1.0 - min(1.0, artifacts_per_min / max(allowed_per_min, 1))
        score = float(np.clip(score, 0.0, 1.0))

        # Hard gate
        max_allowed = config.get("artifact_count_per_min", 10) * (duration / 60.0)
        passed = artifact_count <= max_allowed

        return DimensionResult(
            name="artifacts",
            score=score,
            hard_gate=HardGateResult(
                passed=passed,
                value=float(artifact_count),
                threshold=float(max_allowed),
                reason=""
                if passed
                else (
                    f"artifact_count={artifact_count} exceeds "
                    f"{max_allowed:.1f} (limit {config.get('artifact_count_per_min', 10)}/min)"
                ),
            ),
            raw_metrics={
                "artifact_count": int(artifact_count),
                "onset_count": int(onset_count),
                "spike_count_total": int(len(spike_indices)),
                "duration_s": round(duration, 2),
                "artifacts_per_min": round(artifact_count / max(duration / 60.0, 0.001), 2),
            },
        )

    except Exception as e:
        logger.exception("Artifact analysis failed")
        return _fail(f"analysis_error: {e}")


def _fail(reason: str) -> DimensionResult:
    """Return a zero-score failing result."""
    return DimensionResult(
        name="artifacts",
        score=0.0,
        hard_gate=HardGateResult(
            passed=False,
            value=0.0,
            threshold=0.0,
            reason=reason,
        ),
    )
