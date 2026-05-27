"""Frequency Band Distribution — soft score dimension.

Measures how well the spectral energy is distributed across six
frequency bands, optionally comparing against a corpus profile.
"""

from __future__ import annotations

import logging
from typing import Any

import librosa
import numpy as np

from src.curation.models import DimensionResult

logger = logging.getLogger(__name__)

# Band definitions: (name, low_hz, high_hz)
_BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 250),
    ("low_mid", 250, 1000),
    ("high_mid", 1000, 4000),
    ("presence", 4000, 8000),
    ("air", 8000, 20000),
]


def analyze(
    samples: np.ndarray,
    sr: int,
    config: dict,
    **kwargs: Any,
) -> DimensionResult:
    """Analyse frequency band distribution.

    Args:
        samples: Mono float32 waveform.
        sr: Sample rate.
        config: soft_weights config dict.
        **kwargs: Optional ``genre`` (str), ``corpus_profile`` (dict).

    Returns:
        DimensionResult with frequency balance score.
    """
    try:
        # ── Edge cases ────────────────────────────────────────────────
        if samples is None or len(samples) == 0:
            return _empty("empty audio")

        samples = np.asarray(samples, dtype=np.float32).ravel()
        duration = len(samples) / max(sr, 1)

        if duration < 1.0:
            return _empty("audio too short (<1 s)")

        # ── STFT ─────────────────────────────────────────────────────
        n_fft = 2048
        hop_length = 512
        stft = librosa.stft(y=samples, n_fft=n_fft, hop_length=hop_length)
        magnitude = np.abs(stft)
        power = magnitude ** 2

        # Frequency axis
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        # ── Sum energy per band ──────────────────────────────────────
        band_energies = {}
        for band_name, lo_hz, hi_hz in _BANDS:
            mask = (freqs >= lo_hz) & (freqs < hi_hz)
            if mask.any():
                band_energies[band_name] = float(np.sum(power[mask, :]))
            else:
                band_energies[band_name] = 0.0

        total_energy = sum(band_energies.values())
        if total_energy < 1e-20:
            return _empty("silent audio (no spectral energy)")

        # Normalize as fractions
        band_fractions = {
            name: energy / total_energy
            for name, energy in band_energies.items()
        }

        # ── Build vectors for cosine similarity ──────────────────────
        band_names = [b[0] for b in _BANDS]
        actual_vec = np.array([band_fractions[name] for name in band_names])

        corpus_profile = kwargs.get("corpus_profile")
        if corpus_profile and isinstance(corpus_profile, dict):
            # Try to extract frequency band profile
            freq_bands = corpus_profile.get("frequency_bands")
            if freq_bands and isinstance(freq_bands, dict):
                reference_vec = np.array([
                    freq_bands.get(name, {}).get("mean", 1.0 / 6.0)
                    if isinstance(freq_bands.get(name), dict)
                    else 1.0 / 6.0
                    for name in band_names
                ])
            else:
                reference_vec = np.ones(6) / 6.0
        else:
            # Flat balanced reference
            reference_vec = np.ones(6) / 6.0

        # ── Cosine similarity ────────────────────────────────────────
        cosine_sim = _cosine_similarity(actual_vec, reference_vec)
        score = float(np.clip(cosine_sim, 0.0, 1.0))

        return DimensionResult(
            name="freq_balance",
            score=score,
            raw_metrics={
                "band_energies": {
                    name: round(band_fractions[name], 6) for name in band_names
                },
                "cosine_sim": round(cosine_sim, 4),
            },
        )

    except Exception as e:
        logger.exception("Frequency balance analysis failed")
        return DimensionResult(
            name="freq_balance",
            score=0.0,
            raw_metrics={"error": str(e)},
        )


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot = float(np.dot(a, b))
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-20 or norm_b < 1e-20:
        return 0.0
    return dot / (norm_a * norm_b)


def _empty(reason: str) -> DimensionResult:
    """Return a zero-score result for degenerate inputs."""
    return DimensionResult(
        name="freq_balance",
        score=0.0,
        raw_metrics={"error": reason},
    )
