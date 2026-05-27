"""Silence & Dead Air — hard gate dimension.

Detects prolonged silence or dead air in the interior of the track
(first/last 2 seconds are exempt as fade regions). Uses RMS energy
in 50 ms frames with a -50 dBFS threshold.
"""

from __future__ import annotations

import logging
from typing import Any

import librosa
import numpy as np

from src.curation.models import DimensionResult, HardGateResult

logger = logging.getLogger(__name__)

# -50 dBFS as linear amplitude
SILENCE_THRESHOLD_LINEAR = 10.0 ** (-50.0 / 20.0)  # ~3.16e-3
FRAME_MS = 50
FADE_EXEMPT_S = 2.0


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Detect silence gaps in waveform.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: Hard-gate config dict (needs ``silence_gap_max_s``,
                ``silence_total_ratio_max``).

    Returns:
        DimensionResult with silence score and hard gate.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _fail("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 0.1:
            return _fail("audio too short (<0.1 s)")

        # ── RMS in 50 ms frames ──────────────────────────────────────
        hop_length = int(FRAME_MS / 1000.0 * sr)
        hop_length = max(hop_length, 1)
        frame_length = hop_length  # non-overlapping

        rms = librosa.feature.rms(
            y=samples,
            frame_length=frame_length,
            hop_length=hop_length,
            center=False,
        )[0]

        frame_duration = hop_length / sr  # seconds per frame

        # ── Mark silent frames ────────────────────────────────────────
        silent_mask = rms < SILENCE_THRESHOLD_LINEAR

        # Exempt fade regions (first/last 2 seconds)
        fade_frames = int(FADE_EXEMPT_S / frame_duration)
        if fade_frames > 0:
            silent_mask[:fade_frames] = False
        if fade_frames > 0 and len(silent_mask) > fade_frames:
            silent_mask[-fade_frames:] = False

        # ── Find contiguous silent runs ───────────────────────────────
        gaps: list[float] = []
        total_silent_frames = 0

        if np.any(silent_mask):
            changes = np.diff(silent_mask.astype(np.int8))
            starts = np.where(changes == 1)[0] + 1
            ends = np.where(changes == -1)[0] + 1

            if silent_mask[0]:
                starts = np.concatenate([[0], starts])
            if silent_mask[-1]:
                ends = np.concatenate([ends, [len(silent_mask)]])

            for s, e in zip(starts, ends):
                run_len = e - s
                total_silent_frames += run_len
                gaps.append(float(run_len * frame_duration))

        max_gap = max(gaps) if gaps else 0.0
        total_silence_s = total_silent_frames * frame_duration
        silence_ratio = total_silence_s / max(duration, 0.001)

        # ── Score ─────────────────────────────────────────────────────
        score = 1.0 - (total_silence_s / max(duration, 0.001))
        score = float(np.clip(score, 0.0, 1.0))

        # Hard gate
        gap_limit = config.get("silence_gap_max_s", 2.0)
        ratio_limit = config.get("silence_total_ratio_max", 0.15)

        gap_ok = max_gap <= gap_limit
        ratio_ok = silence_ratio <= ratio_limit
        passed = gap_ok and ratio_ok

        reasons: list[str] = []
        if not gap_ok:
            reasons.append(
                f"max_gap={max_gap:.2f}s exceeds {gap_limit}s"
            )
        if not ratio_ok:
            reasons.append(
                f"silence_ratio={silence_ratio:.3f} exceeds {ratio_limit}"
            )

        # Report the metric that actually failed (or max_gap if both pass)
        if not gap_ok:
            gate_value = float(max_gap)
            gate_threshold = float(gap_limit)
        elif not ratio_ok:
            gate_value = float(silence_ratio)
            gate_threshold = float(ratio_limit)
        else:
            gate_value = float(max_gap)
            gate_threshold = float(gap_limit)

        return DimensionResult(
            name="silence",
            score=score,
            hard_gate=HardGateResult(
                passed=passed,
                value=gate_value,
                threshold=gate_threshold,
                reason="; ".join(reasons) if reasons else "",
            ),
            raw_metrics={
                "max_gap_s": round(max_gap, 3),
                "gap_count": len(gaps),
                "total_silence_s": round(total_silence_s, 3),
                "silence_ratio": round(silence_ratio, 4),
                "duration_s": round(duration, 2),
                "silent_frames": int(total_silent_frames),
                "total_frames": int(len(rms)),
            },
        )

    except Exception as e:
        logger.exception("Silence analysis failed")
        return _fail(f"analysis_error: {e}")


def _fail(reason: str) -> DimensionResult:
    """Return a zero-score failing result."""
    return DimensionResult(
        name="silence",
        score=0.0,
        hard_gate=HardGateResult(
            passed=False,
            value=0.0,
            threshold=0.0,
            reason=reason,
        ),
    )
