"""Self-Calibrating Genre Profiles.

Builds statistical profiles per genre from either full analysis results or
a quick feature-extraction pass, so that soft-score dimensions can compare
each candidate against the corpus norms for its genre.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import librosa
import numpy as np

from src.curation.models import (
    BandStats,
    CandidateAnalysis,
    CorpusProfile,
    PipelineConfig,
)

logger = logging.getLogger(__name__)

# 6-band frequency split points (Hz) — must match frequency_balance.py _BANDS
BAND_EDGES = [20, 60, 250, 1000, 4000, 8000, 20000]
BAND_NAMES = ["sub", "bass", "low_mid", "high_mid", "presence", "air"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _band_stats(values: list[float]) -> BandStats:
    """Compute mean and std from a list of floats."""
    if not values:
        return BandStats()
    arr = np.array(values, dtype=np.float64)
    return BandStats(mean=round(float(np.mean(arr)), 6), std=round(float(np.std(arr)), 6))


# ---------------------------------------------------------------------------
# From full analysis results
# ---------------------------------------------------------------------------


def build_corpus_profiles(
    candidates: list[tuple[CandidateAnalysis, str]],
) -> dict[str, CorpusProfile]:
    """Build corpus profiles from pre-computed analysis results.

    Parameters
    ----------
    candidates:
        List of ``(CandidateAnalysis, genre)`` tuples.

    Returns
    -------
    dict[str, CorpusProfile]
        One profile per genre found in the data.
    """
    # Group by genre
    genre_groups: dict[str, list[CandidateAnalysis]] = defaultdict(list)
    for ca, genre in candidates:
        genre_groups[genre].append(ca)

    profiles: dict[str, CorpusProfile] = {}

    for genre, analyses in genre_groups.items():
        freq_bands: dict[str, list[float]] = defaultdict(list)
        evolution_distances: list[float] = []
        stereo_widths: list[float] = []
        spectral_centroids: list[float] = []

        for ca in analyses:
            # Frequency balance raw metrics
            fb = ca.dimensions.get("freq_balance")
            if fb and fb.raw_metrics:
                for band_name in BAND_NAMES:
                    val = fb.raw_metrics.get(f"band_{band_name}")
                    if val is not None:
                        freq_bands[band_name].append(float(val))
                    # Also check direct band_energy keys
                    val2 = fb.raw_metrics.get(band_name)
                    if val2 is not None and val is None:
                        freq_bands[band_name].append(float(val2))

            # Evolution raw metrics
            ev = ca.dimensions.get("evolution")
            if ev and ev.raw_metrics:
                dist = ev.raw_metrics.get("mean_distance") or ev.raw_metrics.get(
                    "evolution_distance"
                )
                if dist is not None:
                    evolution_distances.append(float(dist))

            # Stereo mix raw metrics
            sm = ca.dimensions.get("stereo_mix")
            if sm and sm.raw_metrics:
                width = sm.raw_metrics.get("stereo_width") or sm.raw_metrics.get("mean_width")
                if width is not None:
                    stereo_widths.append(float(width))

            # Spectral centroid from any available raw metrics
            for dim_name in ("freq_balance", "harmony", "structure"):
                dim = ca.dimensions.get(dim_name)
                if dim and dim.raw_metrics:
                    sc = dim.raw_metrics.get("spectral_centroid") or dim.raw_metrics.get(
                        "mean_spectral_centroid"
                    )
                    if sc is not None:
                        spectral_centroids.append(float(sc))
                        break

        profiles[genre] = CorpusProfile(
            genre=genre,
            track_count=len(analyses),
            frequency_bands={band: _band_stats(vals) for band, vals in freq_bands.items()},
            evolution_distance=_band_stats(evolution_distances),
            stereo_width=_band_stats(stereo_widths),
            spectral_centroid=_band_stats(spectral_centroids),
        )

        logger.info(
            "Corpus profile for %s: %d tracks, %d bands populated",
            genre,
            len(analyses),
            sum(1 for v in freq_bands.values() if v),
        )

    return profiles


# ---------------------------------------------------------------------------
# Fast feature extraction (pre-analysis pass)
# ---------------------------------------------------------------------------


def _extract_features_fast(wav_path: str) -> dict:
    """Extract lightweight features for corpus profiling.

    Returns a dict with:
        - band_energies: {band_name: float}  (6 bands)
        - evolution_distance: float
        - stereo_width: float
        - spectral_centroid: float
    """
    result: dict = {
        "band_energies": {},
        "evolution_distance": 0.0,
        "stereo_width": 0.0,
        "spectral_centroid": 0.0,
    }

    try:
        # Load mono for spectral features
        y_mono, sr = librosa.load(wav_path, sr=None, mono=True)
        if y_mono is None or len(y_mono) == 0:
            return result

        # ------------------------------------------------------------------
        # 6-band frequency energy via mel spectrogram
        # ------------------------------------------------------------------
        S = np.abs(librosa.stft(y_mono, n_fft=2048, hop_length=512))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

        for i, band_name in enumerate(BAND_NAMES):
            lo = BAND_EDGES[i]
            hi = BAND_EDGES[i + 1]
            mask = (freqs >= lo) & (freqs < hi)
            if np.any(mask):
                band_energy = float(np.mean(S[mask, :] ** 2))
                result["band_energies"][band_name] = band_energy

        # ------------------------------------------------------------------
        # MFCC evolution distance
        # ------------------------------------------------------------------
        mfcc = librosa.feature.mfcc(y=y_mono, sr=sr, n_mfcc=13, hop_length=512)
        if mfcc.shape[1] >= 4:
            # Split into 4 equal segments, compute mean MFCC per segment
            n_frames = mfcc.shape[1]
            seg_size = n_frames // 4
            seg_means = []
            for s in range(4):
                start = s * seg_size
                end = start + seg_size if s < 3 else n_frames
                seg_means.append(mfcc[:, start:end].mean(axis=1))

            # Average pairwise distance between consecutive segments
            distances = []
            for j in range(len(seg_means) - 1):
                dist = float(np.linalg.norm(seg_means[j + 1] - seg_means[j]))
                distances.append(dist)
            result["evolution_distance"] = float(np.mean(distances)) if distances else 0.0

        # ------------------------------------------------------------------
        # Spectral centroid (mean)
        # ------------------------------------------------------------------
        sc = librosa.feature.spectral_centroid(y=y_mono, sr=sr, hop_length=512)
        if sc is not None and sc.size > 0:
            result["spectral_centroid"] = float(np.mean(sc))

        # ------------------------------------------------------------------
        # Stereo width
        # ------------------------------------------------------------------
        try:
            y_stereo, _ = librosa.load(wav_path, sr=None, mono=False)
            if y_stereo.ndim == 2 and y_stereo.shape[0] >= 2:
                left = y_stereo[0]
                right = y_stereo[1]
                mid = (left + right) / 2.0
                side = (left - right) / 2.0
                mid_energy = float(np.mean(mid**2))
                side_energy = float(np.mean(side**2))
                if mid_energy > 1e-10:
                    result["stereo_width"] = side_energy / mid_energy
                else:
                    result["stereo_width"] = 0.0
            else:
                result["stereo_width"] = 0.0
        except Exception:
            result["stereo_width"] = 0.0

    except Exception as exc:
        logger.warning("Fast feature extraction failed for %s: %s", wav_path, exc)

    return result


def _extract_wrapper(args: tuple) -> tuple[str, str, dict]:
    """Pickle-friendly wrapper for ProcessPoolExecutor."""
    wav_path, genre = args
    features = _extract_features_fast(wav_path)
    return wav_path, genre, features


def build_profiles_fast(
    wav_paths: list[tuple[str, str]],
    config: PipelineConfig,
) -> dict[str, CorpusProfile]:
    """Build corpus profiles via quick feature extraction (no full analysis).

    This is designed to run BEFORE the full analysis pass so that
    corpus-relative scoring can use per-genre norms.

    Parameters
    ----------
    wav_paths:
        List of ``(wav_path, genre)`` tuples.
    config:
        Pipeline configuration (used for ``parallel_workers``).

    Returns
    -------
    dict[str, CorpusProfile]
        One profile per genre.
    """
    if not wav_paths:
        return {}

    logger.info("Building fast corpus profiles from %d files", len(wav_paths))

    # Extract features in parallel
    all_features: list[tuple[str, str, dict]] = []
    max_workers = min(config.parallel_workers, len(wav_paths))

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_extract_wrapper, item): item for item in wav_paths}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    all_features.append(result)
                except Exception as exc:
                    item = futures[future]
                    logger.warning("Feature extraction failed for %s: %s", item[0], exc)
    except Exception as exc:
        logger.error("Parallel extraction failed, falling back to sequential: %s", exc)
        for item in wav_paths:
            try:
                result = _extract_wrapper(item)
                all_features.append(result)
            except Exception as inner_exc:
                logger.warning("Sequential extraction failed for %s: %s", item[0], inner_exc)

    # Group by genre
    genre_features: dict[str, list[dict]] = defaultdict(list)
    for _, genre, features in all_features:
        genre_features[genre].append(features)

    # Build profiles
    profiles: dict[str, CorpusProfile] = {}

    for genre, feature_list in genre_features.items():
        freq_bands: dict[str, list[float]] = defaultdict(list)
        evolution_distances: list[float] = []
        stereo_widths: list[float] = []
        spectral_centroids: list[float] = []

        for feat in feature_list:
            for band_name, val in feat.get("band_energies", {}).items():
                freq_bands[band_name].append(val)

            ed = feat.get("evolution_distance", 0.0)
            if ed > 0:
                evolution_distances.append(ed)

            sw = feat.get("stereo_width", 0.0)
            stereo_widths.append(sw)

            sc = feat.get("spectral_centroid", 0.0)
            if sc > 0:
                spectral_centroids.append(sc)

        profiles[genre] = CorpusProfile(
            genre=genre,
            track_count=len(feature_list),
            frequency_bands={band: _band_stats(vals) for band, vals in freq_bands.items()},
            evolution_distance=_band_stats(evolution_distances),
            stereo_width=_band_stats(stereo_widths),
            spectral_centroid=_band_stats(spectral_centroids),
        )

        logger.info(
            "Fast profile for %s: %d files, centroid_mean=%.1f, width_mean=%.4f",
            genre,
            len(feature_list),
            profiles[genre].spectral_centroid.mean,
            profiles[genre].stereo_width.mean,
        )

    return profiles
