"""Temporal Evolution — soft score dimension.

Measures how a track's timbral and dynamic features change over time.
Tracks that are too static or too chaotic score lower; moderate
evolution is ideal.
"""

from __future__ import annotations

import logging
from typing import Any

import librosa
import numpy as np
from scipy.spatial.distance import cosine as cosine_distance

from src.curation.models import DimensionResult

logger = logging.getLogger(__name__)


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Analyse temporal evolution of a track.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: soft_weights config dict.
        **kwargs: Optional ``genre`` (str), ``corpus_profile`` (dict).

    Returns:
        DimensionResult with evolution score.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _empty("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 1.0:
            return _empty("audio too short (<1 s)")

        # ── Window setup ─────────────────────────────────────────────
        window_seconds = 10.0
        n_windows = max(4, int(duration / window_seconds))
        window_samples = len(samples) // n_windows

        # ── Per-window feature vectors ───────────────────────────────
        # Each vector: [rms_mean, spectral_centroid_mean, 13 mfcc_means] = 15-dim
        feature_vectors = []
        hop_length = 512

        for i in range(n_windows):
            start = i * window_samples
            end = start + window_samples if i < n_windows - 1 else len(samples)
            segment = samples[start:end]

            if len(segment) < hop_length * 2:
                continue

            # RMS
            rms = librosa.feature.rms(y=segment, hop_length=hop_length)[0]
            rms_mean = float(np.mean(rms))

            # Spectral centroid
            cent = librosa.feature.spectral_centroid(
                y=segment, sr=sr, hop_length=hop_length,
            )[0]
            cent_mean = float(np.mean(cent))

            # MFCCs
            mfcc = librosa.feature.mfcc(
                y=segment, sr=sr, n_mfcc=13, hop_length=hop_length,
            )
            mfcc_means = mfcc.mean(axis=1).tolist()  # 13 values

            vec = [rms_mean, cent_mean] + mfcc_means
            feature_vectors.append(np.array(vec, dtype=np.float64))

        if len(feature_vectors) < 2:
            return DimensionResult(
                name="evolution",
                score=0.5,
                raw_metrics={
                    "evolution_distance": 0.0,
                    "trajectory_variance": 0.0,
                    "window_count": len(feature_vectors),
                    "note": "too few windows for evolution analysis",
                },
            )

        # ── Consecutive cosine distances ─────────────────────────────
        consecutive_distances = []
        for i in range(len(feature_vectors) - 1):
            a = feature_vectors[i]
            b = feature_vectors[i + 1]
            # Avoid NaN from zero vectors
            if np.linalg.norm(a) < 1e-10 or np.linalg.norm(b) < 1e-10:
                consecutive_distances.append(0.0)
            else:
                dist = float(cosine_distance(a, b))
                consecutive_distances.append(dist)

        evolution_distance = float(np.mean(consecutive_distances))

        # ── Trajectory variance ──────────────────────────────────────
        all_vecs = np.array(feature_vectors)
        trajectory_variance = float(np.std(all_vecs))

        # ── Scoring via bell curve ───────────────────────────────────
        corpus_profile = kwargs.get("corpus_profile")

        if corpus_profile and isinstance(corpus_profile, dict):
            evo_stats = corpus_profile.get("evolution_distance")
            if evo_stats and isinstance(evo_stats, dict):
                center = evo_stats.get("mean", 0.14)
                sigma = evo_stats.get("std", 0.10)
            else:
                center = 0.14
                sigma = 0.10
        else:
            center = 0.14
            sigma = 0.10

        # Prevent zero sigma
        sigma = max(sigma, 0.01)

        score = float(np.exp(-((evolution_distance - center) / sigma) ** 2))
        score = float(np.clip(score, 0.0, 1.0))

        return DimensionResult(
            name="evolution",
            score=score,
            raw_metrics={
                "evolution_distance": round(evolution_distance, 4),
                "trajectory_variance": round(trajectory_variance, 4),
                "window_count": len(feature_vectors),
            },
        )

    except Exception as e:
        logger.exception("Evolution analysis failed")
        return DimensionResult(
            name="evolution",
            score=0.0,
            raw_metrics={"error": str(e)},
        )


def _empty(reason: str) -> DimensionResult:
    """Return a zero-score result for degenerate inputs."""
    return DimensionResult(
        name="evolution",
        score=0.0,
        raw_metrics={"error": reason},
    )
