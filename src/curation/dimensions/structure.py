"""Structural Coherence — soft score dimension.

Measures how well a track is organized into coherent sections by
analysing self-similarity, novelty curves, segment diversity, and
energy arc.
"""

from __future__ import annotations

import logging
from typing import Any

import librosa
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from scipy.spatial.distance import cdist

from src.curation.models import DimensionResult

logger = logging.getLogger(__name__)


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Analyse structural coherence of a track.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: soft_weights config dict.
        **kwargs: Optional ``genre`` (str), ``corpus_profile`` (dict).

    Returns:
        DimensionResult with structural coherence score.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _empty("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 1.0:
            return _empty("audio too short (<1 s)")

        # ── Mel spectrogram & MFCCs ──────────────────────────────────
        hop_length = 512
        n_mfcc = 13
        mel_spec = librosa.feature.melspectrogram(
            y=samples, sr=sr, hop_length=hop_length, n_mels=128,
        )
        mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel_spec), n_mfcc=n_mfcc)
        # mfcc shape: (n_mfcc, T)

        # ── Self-similarity matrix ───────────────────────────────────
        # Downsample frames for efficiency (target ~200 frames)
        n_frames = mfcc.shape[1]
        step = max(1, n_frames // 200)
        mfcc_ds = mfcc[:, ::step].T  # (N, n_mfcc)

        if len(mfcc_ds) < 4:
            return _empty("too few MFCC frames")

        ssm = 1.0 - cdist(mfcc_ds, mfcc_ds, metric="cosine")

        # ── Novelty curve from SSM ───────────────────────────────────
        # Checkerboard kernel along diagonal
        n = len(ssm)
        novelty = np.zeros(n)
        kernel_size = min(16, n // 4) if n >= 8 else 2
        for i in range(kernel_size, n - kernel_size):
            tl = ssm[i - kernel_size:i, i - kernel_size:i].mean()
            br = ssm[i:i + kernel_size, i:i + kernel_size].mean()
            tr = ssm[i - kernel_size:i, i:i + kernel_size].mean()
            bl = ssm[i:i + kernel_size, i - kernel_size:i].mean()
            novelty[i] = (tl + br) - (tr + bl)

        # Smooth and peak-pick
        if len(novelty) > 3:
            novelty_smooth = gaussian_filter1d(novelty, sigma=max(1.0, len(novelty) / 50))
        else:
            novelty_smooth = novelty

        prominence = max(np.std(novelty_smooth) * 0.5, 1e-6)
        peaks, _ = find_peaks(novelty_smooth, prominence=prominence)
        segment_count = len(peaks) + 1  # peaks mark boundaries

        # ── Segment diversity ────────────────────────────────────────
        # Split MFCC frames into segments at boundary peaks
        boundary_frames = np.sort(peaks)
        boundaries = [0] + boundary_frames.tolist() + [len(mfcc_ds)]
        segment_means = []
        for i in range(len(boundaries) - 1):
            start, end = boundaries[i], boundaries[i + 1]
            if end > start:
                seg_mean = mfcc_ds[start:end].mean(axis=0)
                segment_means.append(seg_mean)

        if len(segment_means) >= 2:
            segment_means_arr = np.array(segment_means)
            segment_diversity = float(np.std(segment_means_arr))
        else:
            segment_diversity = 0.0

        # ── Energy arc ───────────────────────────────────────────────
        rms = librosa.feature.rms(y=samples, hop_length=hop_length)[0]
        if len(rms) >= 3:
            t = np.linspace(0, 1, len(rms))
            coeffs = np.polyfit(t, rms, 2)
            rms_fit = np.polyval(coeffs, t)
            # R-squared
            ss_res = np.sum((rms - rms_fit) ** 2)
            ss_tot = np.sum((rms - rms.mean()) ** 2)
            energy_arc_r2 = float(1.0 - ss_res / max(ss_tot, 1e-10))
            energy_arc_r2 = max(0.0, energy_arc_r2)
        else:
            energy_arc_r2 = 0.0

        # ── Scoring ──────────────────────────────────────────────────
        # Segment count bell curve: ideal 3-8 for 60-180s
        # Bell centered at 5.5 with sigma 2.5
        ideal_center = 5.5
        ideal_sigma = 2.5
        seg_score = float(np.exp(-((segment_count - ideal_center) / ideal_sigma) ** 2))

        # Diversity normalized (0-1), capped at reasonable range
        diversity_normalized = min(segment_diversity / 5.0, 1.0)

        # Composite
        score = (
            0.3 * seg_score
            + 0.3 * diversity_normalized
            + 0.4 * energy_arc_r2
        )
        score = float(np.clip(score, 0.0, 1.0))

        # Genre weight adjustments are handled at the composite level
        # by PipelineConfig.genre_weight_overrides, not here.

        return DimensionResult(
            name="structure",
            score=score,
            raw_metrics={
                "segment_count": int(segment_count),
                "segment_diversity": round(segment_diversity, 4),
                "energy_arc_r2": round(energy_arc_r2, 4),
                "seg_score": round(seg_score, 4),
                "diversity_normalized": round(diversity_normalized, 4),
                "duration_s": round(duration, 2),
            },
        )

    except Exception as e:
        logger.exception("Structure analysis failed")
        return DimensionResult(
            name="structure",
            score=0.0,
            raw_metrics={"error": str(e)},
        )


def _empty(reason: str) -> DimensionResult:
    """Return a zero-score result for degenerate inputs."""
    return DimensionResult(
        name="structure",
        score=0.0,
        raw_metrics={"error": reason},
    )
