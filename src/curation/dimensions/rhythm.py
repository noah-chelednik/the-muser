"""Rhythmic Stability — soft score dimension.

Measures beat regularity, onset strength at beat positions, and
tempo consistency across the track.
"""

from __future__ import annotations

import logging
from typing import Any

import librosa
import numpy as np

from src.curation.models import DimensionResult

logger = logging.getLogger(__name__)

try:
    import essentia.standard as es

    HAS_ESSENTIA = True
except ImportError:
    HAS_ESSENTIA = False


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Analyse rhythmic stability of a track.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: soft_weights config dict.
        **kwargs: Optional ``genre`` (str), ``corpus_profile`` (dict).

    Returns:
        DimensionResult with rhythmic stability score.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _empty("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 1.0:
            return _empty("audio too short (<1 s)")

        # ── Beat detection ───────────────────────────────────────────
        bpm, beat_times = _detect_beats(samples, sr)

        beat_count = len(beat_times)

        # Handle no beats (ambient music)
        if beat_count < 2:
            return DimensionResult(
                name="rhythm",
                score=0.5,
                raw_metrics={
                    "bpm": round(float(bpm), 2) if bpm else 0.0,
                    "ibi_cv": 0.0,
                    "beat_strength": 0.0,
                    "tempo_drift_bpm": 0.0,
                    "beat_count": int(beat_count),
                    "note": "insufficient beats detected",
                },
            )

        # ── Inter-beat intervals ─────────────────────────────────────
        ibis = np.diff(beat_times)
        ibi_mean = float(np.mean(ibis))
        ibi_std = float(np.std(ibis))
        ibi_cv = ibi_std / max(ibi_mean, 1e-10)

        # Score: lower CV = more stable. CV < 0.05 is excellent, > 0.3 is poor.
        ibi_stability_score = float(np.clip(1.0 - ibi_cv / 0.3, 0.0, 1.0))

        # ── Beat strength ────────────────────────────────────────────
        onset_env = librosa.onset.onset_strength(y=samples, sr=sr)
        hop_length = 512  # librosa default
        beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop_length)
        beat_frames = beat_frames[beat_frames < len(onset_env)]

        if len(beat_frames) > 0:
            beat_strengths = onset_env[beat_frames]
            mean_beat_strength = float(np.mean(beat_strengths))
            # Normalize relative to overall onset strength
            overall_mean = float(np.mean(onset_env)) if len(onset_env) > 0 else 1e-10
            beat_strength_normalized = min(mean_beat_strength / max(overall_mean, 1e-10) / 2.0, 1.0)
        else:
            mean_beat_strength = 0.0
            beat_strength_normalized = 0.0

        # ── Tempo drift ──────────────────────────────────────────────
        # Split into 4 windows, estimate tempo per window
        n_windows = 4
        window_len = len(samples) // n_windows
        window_tempos = []
        for i in range(n_windows):
            start = i * window_len
            end = start + window_len if i < n_windows - 1 else len(samples)
            segment = samples[start:end]
            if len(segment) > sr:  # at least 1 second
                try:
                    seg_tempo = librosa.beat.beat_track(
                        y=segment,
                        sr=sr,
                        units="time",
                    )[0]
                    if isinstance(seg_tempo, np.ndarray):
                        seg_tempo = float(seg_tempo[0]) if len(seg_tempo) > 0 else 0.0
                    else:
                        seg_tempo = float(seg_tempo)
                    if seg_tempo > 0:
                        window_tempos.append(seg_tempo)
                except Exception:
                    pass

        if len(window_tempos) >= 2:
            median_tempo = float(np.median(window_tempos))
            tempo_drift_bpm = float(max(abs(t - median_tempo) for t in window_tempos))
        else:
            tempo_drift_bpm = 0.0

        # Score: drift < 2 BPM is excellent, > 15 BPM is poor
        tempo_drift_score = float(np.clip(1.0 - tempo_drift_bpm / 15.0, 0.0, 1.0))

        # ── Composite score ──────────────────────────────────────────
        score = 0.4 * ibi_stability_score + 0.3 * beat_strength_normalized + 0.3 * tempo_drift_score
        score = float(np.clip(score, 0.0, 1.0))

        return DimensionResult(
            name="rhythm",
            score=score,
            raw_metrics={
                "bpm": round(float(bpm), 2),
                "ibi_cv": round(ibi_cv, 4),
                "beat_strength": round(mean_beat_strength, 4),
                "tempo_drift_bpm": round(tempo_drift_bpm, 2),
                "beat_count": int(beat_count),
            },
        )

    except Exception as e:
        logger.exception("Rhythm analysis failed")
        return DimensionResult(
            name="rhythm",
            score=0.0,
            raw_metrics={"error": str(e)},
        )


def _detect_beats(samples: np.ndarray, sr: int) -> tuple[float, np.ndarray]:
    """Detect BPM and beat positions.

    Uses essentia if available, otherwise falls back to librosa.
    """
    if HAS_ESSENTIA:
        try:
            extractor = es.RhythmExtractor2013()
            bpm, beats, beats_confidence, _, _ = extractor(samples)
            return float(bpm), np.asarray(beats, dtype=np.float64)
        except Exception:
            logger.debug("Essentia beat detection failed, falling back to librosa")

    # Librosa fallback
    tempo, beat_frames = librosa.beat.beat_track(y=samples, sr=sr, units="time")
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0]) if len(tempo) > 0 else 0.0
    else:
        tempo = float(tempo)
    return tempo, np.asarray(beat_frames, dtype=np.float64)


def _empty(reason: str) -> DimensionResult:
    """Return a zero-score result for degenerate inputs."""
    return DimensionResult(
        name="rhythm",
        score=0.0,
        raw_metrics={"error": reason},
    )
