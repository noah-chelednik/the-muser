"""Harmonic Content & Key — soft score dimension.

Measures key confidence, tonal stability across the track, and
consonance via chroma entropy.
"""

from __future__ import annotations

import logging
from typing import Any

import librosa
import numpy as np
from scipy.stats import entropy as scipy_entropy

from src.curation.models import DimensionResult

logger = logging.getLogger(__name__)

try:
    import essentia.standard as es

    HAS_ESSENTIA = True
except ImportError:
    HAS_ESSENTIA = False


# ── Krumhansl-Schmuckler key profiles ────────────────────────────────────
# 12 pitch classes: C, C#, D, D#, E, F, F#, G, G#, A, A#, B
_MAJOR_PROFILE = np.array(
    [
        6.35,
        2.23,
        3.48,
        2.33,
        4.38,
        4.09,
        2.52,
        5.19,
        2.39,
        3.66,
        2.29,
        2.88,
    ]
)
_MINOR_PROFILE = np.array(
    [
        6.33,
        2.68,
        3.52,
        5.38,
        2.60,
        3.53,
        2.54,
        4.75,
        3.98,
        2.69,
        3.34,
        3.17,
    ]
)

_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _build_key_profiles() -> list[tuple[str, str, np.ndarray]]:
    """Build all 24 key profiles (12 major + 12 minor)."""
    profiles = []
    for shift in range(12):
        major_shifted = np.roll(_MAJOR_PROFILE, shift)
        minor_shifted = np.roll(_MINOR_PROFILE, shift)
        profiles.append((_PITCH_NAMES[shift], "major", major_shifted))
        profiles.append((_PITCH_NAMES[shift], "minor", minor_shifted))
    return profiles


_KEY_PROFILES = _build_key_profiles()


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Analyse harmonic content and key confidence.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: soft_weights config dict.
        **kwargs: Optional ``genre`` (str), ``corpus_profile`` (dict).

    Returns:
        DimensionResult with harmony score.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _empty("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 1.0:
            return _empty("audio too short (<1 s)")

        # ── Key detection ────────────────────────────────────────────
        key, mode, key_confidence = _detect_key(samples, sr)

        # ── Tonal stability ──────────────────────────────────────────
        # Split into 8 windows, estimate key per window, count agreement
        n_windows = 8
        window_len = len(samples) // n_windows
        window_keys = []
        for i in range(n_windows):
            start = i * window_len
            end = start + window_len if i < n_windows - 1 else len(samples)
            segment = samples[start:end]
            if len(segment) > sr // 2:  # at least 0.5 seconds
                try:
                    wk, wm, _ = _detect_key(segment, sr)
                    window_keys.append(f"{wk}_{wm}")
                except Exception:
                    pass

        if len(window_keys) >= 2:
            # Agreement ratio: fraction of windows matching the global key
            global_key_label = f"{key}_{mode}"
            agreement_count = sum(1 for wk in window_keys if wk == global_key_label)
            tonal_stability = agreement_count / len(window_keys)
        else:
            tonal_stability = 1.0  # too short to evaluate, assume stable

        # ── Consonance via chroma entropy ────────────────────────────
        hop_length = 512
        chroma = librosa.feature.chroma_cqt(y=samples, sr=sr, hop_length=hop_length)
        # chroma shape: (12, T)

        # Per-frame entropy of the chroma distribution
        frame_entropies = []
        for frame_idx in range(chroma.shape[1]):
            frame = chroma[:, frame_idx]
            frame_sum = frame.sum()
            if frame_sum > 1e-10:
                frame_norm = frame / frame_sum
                ent = float(scipy_entropy(frame_norm + 1e-12))
            else:
                ent = 0.0
            frame_entropies.append(ent)

        frame_entropies = np.array(frame_entropies)
        mean_entropy = float(np.mean(frame_entropies)) if len(frame_entropies) > 0 else 0.0

        # Normalize entropy: max entropy for 12-class uniform = log(12) ~ 2.485
        max_entropy = float(np.log(12.0))
        # Lower entropy = more consonant = higher score
        consonance_score = float(np.clip(1.0 - mean_entropy / max_entropy, 0.0, 1.0))

        # ── Composite score ──────────────────────────────────────────
        score = 0.4 * key_confidence + 0.3 * tonal_stability + 0.3 * consonance_score
        score = float(np.clip(score, 0.0, 1.0))

        return DimensionResult(
            name="harmony",
            score=score,
            raw_metrics={
                "key": f"{key} {mode}",
                "key_confidence": round(key_confidence, 4),
                "tonal_stability": round(tonal_stability, 4),
                "mean_entropy": round(mean_entropy, 4),
                "mode": mode,
            },
        )

    except Exception as e:
        logger.exception("Harmony analysis failed")
        return DimensionResult(
            name="harmony",
            score=0.0,
            raw_metrics={"error": str(e)},
        )


def _detect_key(samples: np.ndarray, sr: int) -> tuple[str, str, float]:
    """Detect key, mode, and confidence.

    Uses essentia if available, otherwise falls back to
    Krumhansl-Schmuckler profile correlation on CQT chroma.
    """
    if HAS_ESSENTIA:
        try:
            extractor = es.KeyExtractor()
            key, mode, confidence = extractor(samples)
            return str(key), str(mode).lower(), float(np.clip(confidence, 0.0, 1.0))
        except Exception:
            logger.debug("Essentia key detection failed, falling back to librosa")

    # Librosa fallback: Krumhansl-Schmuckler
    chroma = librosa.feature.chroma_cqt(y=samples, sr=sr)
    chroma_mean = chroma.mean(axis=1)  # (12,)

    best_corr = -1.0
    best_key = "C"
    best_mode = "major"

    for pitch_name, mode, profile in _KEY_PROFILES:
        corr = float(np.corrcoef(chroma_mean, profile)[0, 1])
        if np.isnan(corr):
            corr = 0.0
        if corr > best_corr:
            best_corr = corr
            best_key = pitch_name
            best_mode = mode

    # Clamp correlation to [0, 1] range for confidence
    confidence = float(np.clip(best_corr, 0.0, 1.0))
    return best_key, best_mode, confidence


def _empty(reason: str) -> DimensionResult:
    """Return a zero-score result for degenerate inputs."""
    return DimensionResult(
        name="harmony",
        score=0.0,
        raw_metrics={"error": reason},
    )
