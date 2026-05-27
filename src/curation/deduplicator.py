"""Phase 6 — Duplicate Detection.

Computes chroma + onset-strength fingerprints for each selected track
and finds near-duplicate pairs using cosine distance.  Includes a
self-test mode that verifies thresholds can distinguish same-track
candidates from same-genre different tracks.
"""

from __future__ import annotations

import logging
from typing import Optional

import librosa
import numpy as np
from scipy.spatial.distance import cdist

from src.curation.models import DuplicatePair, PipelineConfig, TrackSelection

logger = logging.getLogger(__name__)

# Fingerprint dimensionality: 12 chroma bins + 16 onset histogram bins = 28
CHROMA_BINS = 12
ONSET_HIST_BINS = 16
FINGERPRINT_DIM = CHROMA_BINS + ONSET_HIST_BINS


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

def compute_fingerprint(wav_path: str) -> np.ndarray:
    """Compute a 28-dimensional fingerprint for a WAV file.

    The fingerprint concatenates:
    - 12 chroma CQT bins (mean across time)
    - 16-bin histogram of onset strength values

    Parameters
    ----------
    wav_path:
        Path to a WAV file.

    Returns
    -------
    np.ndarray
        Shape ``(28,)`` float64 fingerprint vector.
    """
    try:
        y, sr = librosa.load(wav_path, sr=22050, mono=True)
    except Exception as exc:
        logger.warning("Cannot load %s for fingerprinting: %s", wav_path, exc)
        return np.zeros(FINGERPRINT_DIM, dtype=np.float64)

    if y is None or len(y) < sr:
        logger.warning("Audio too short for fingerprinting: %s", wav_path)
        return np.zeros(FINGERPRINT_DIM, dtype=np.float64)

    # ------------------------------------------------------------------
    # Chroma CQT — mean across time → 12-dim
    # ------------------------------------------------------------------
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
        chroma_mean = np.mean(chroma, axis=1)  # (12,)
    except Exception as exc:
        logger.warning("Chroma extraction failed for %s: %s", wav_path, exc)
        chroma_mean = np.zeros(CHROMA_BINS, dtype=np.float64)

    # ------------------------------------------------------------------
    # Onset strength histogram — 16 bins
    # ------------------------------------------------------------------
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
        if len(onset_env) > 0 and np.max(onset_env) > 0:
            # Normalize to [0, 1] before histogramming
            onset_norm = onset_env / np.max(onset_env)
            hist, _ = np.histogram(onset_norm, bins=ONSET_HIST_BINS, range=(0.0, 1.0))
            hist = hist.astype(np.float64)
            hist_sum = hist.sum()
            if hist_sum > 0:
                hist = hist / hist_sum  # normalize to PDF
        else:
            hist = np.zeros(ONSET_HIST_BINS, dtype=np.float64)
    except Exception as exc:
        logger.warning("Onset extraction failed for %s: %s", wav_path, exc)
        hist = np.zeros(ONSET_HIST_BINS, dtype=np.float64)

    fingerprint = np.concatenate([chroma_mean, hist]).astype(np.float64)
    return fingerprint


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates(
    tracks: dict[str, TrackSelection],
    config: PipelineConfig,
) -> list[DuplicatePair]:
    """Find near-duplicate pairs among selected tracks.

    Parameters
    ----------
    tracks:
        ``{track_id: TrackSelection}`` for non-dropped tracks.
    config:
        Pipeline configuration with ``duplicate_detection`` thresholds.

    Returns
    -------
    list[DuplicatePair]
        Pairs flagged as duplicates, with the weaker track marked for dropping.
    """
    dedup_cfg = config.duplicate_detection
    within_threshold = dedup_cfg.get("within_genre_threshold", 0.06)
    cross_threshold = dedup_cfg.get("cross_genre_threshold", 0.03)
    do_self_test = dedup_cfg.get("self_test", True)

    # Filter to tracks with selected candidates
    active: list[tuple[str, TrackSelection]] = [
        (tid, sel) for tid, sel in tracks.items()
        if not sel.dropped and sel.selected_candidate is not None
    ]

    if len(active) < 2:
        logger.debug("Fewer than 2 active tracks; skipping dedup")
        return []

    logger.info("Computing fingerprints for %d tracks", len(active))

    # Compute fingerprints
    track_ids: list[str] = []
    genres: list[str] = []
    scores: list[float] = []
    fingerprints: list[np.ndarray] = []

    for tid, sel in active:
        assert sel.selected_candidate is not None
        fp = compute_fingerprint(sel.selected_candidate.wav_path)
        track_ids.append(tid)
        genres.append(sel.genre)
        scores.append(sel.selected_candidate.composite_score)
        fingerprints.append(fp)

    fp_matrix = np.array(fingerprints)  # (N, 28)

    # ------------------------------------------------------------------
    # Pairwise cosine distance
    # ------------------------------------------------------------------
    # cosine distance = 1 - cosine_similarity; range [0, 2]
    dist_matrix = cdist(fp_matrix, fp_matrix, metric="cosine")

    # ------------------------------------------------------------------
    # Find duplicate pairs
    # ------------------------------------------------------------------
    n = len(track_ids)
    pairs: list[DuplicatePair] = []
    already_dropped: set[str] = set()

    # Process pairs in order of increasing distance (most similar first)
    pair_list: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            pair_list.append((dist_matrix[i, j], i, j))

    pair_list.sort(key=lambda x: x[0])

    for dist, i, j in pair_list:
        tid_i, tid_j = track_ids[i], track_ids[j]

        # Skip if either already dropped
        if tid_i in already_dropped or tid_j in already_dropped:
            continue

        same_genre = genres[i] == genres[j]
        threshold = within_threshold if same_genre else cross_threshold

        # Similarity = 1 - cosine_distance
        similarity = 1.0 - dist

        if dist <= threshold:
            # Keep the one with the higher composite score
            if scores[i] >= scores[j]:
                kept, dropped = tid_i, tid_j
            else:
                kept, dropped = tid_j, tid_i

            pairs.append(DuplicatePair(
                kept_id=kept,
                dropped_id=dropped,
                similarity=round(similarity, 6),
                same_genre=same_genre,
            ))
            already_dropped.add(dropped)

            logger.info(
                "Duplicate pair: %s <-> %s (dist=%.4f, threshold=%.4f, same_genre=%s) -> drop %s",
                tid_i, tid_j, dist, threshold, same_genre, dropped,
            )

    # ------------------------------------------------------------------
    # Self-test
    # ------------------------------------------------------------------
    if do_self_test:
        _run_self_test(active, within_threshold, cross_threshold)

    logger.info("Dedup complete: %d pairs flagged", len(pairs))
    return pairs


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test(
    active: list[tuple[str, TrackSelection]],
    within_threshold: float,
    cross_threshold: float,
) -> None:
    """Validate thresholds by comparing same-track candidates vs different tracks.

    Logs warnings if thresholds cannot distinguish duplicates from distinct tracks.
    """
    # Find a track that has multiple candidates
    multi_candidate_track: Optional[TrackSelection] = None
    for _, sel in active:
        if len(sel.all_candidates) >= 2:
            multi_candidate_track = sel
            break

    if multi_candidate_track is None:
        logger.debug("Self-test skipped: no track with multiple candidates")
        return

    # Find two tracks of the same genre
    genre_groups: dict[str, list[tuple[str, TrackSelection]]] = {}
    for tid, sel in active:
        g = sel.genre
        if g not in genre_groups:
            genre_groups[g] = []
        genre_groups[g].append((tid, sel))

    same_genre_pair: Optional[tuple[TrackSelection, TrackSelection]] = None
    for g, members in genre_groups.items():
        if len(members) >= 2:
            same_genre_pair = (members[0][1], members[1][1])
            break

    # Test 1: Same-track candidates should be similar
    c1 = multi_candidate_track.all_candidates[0]
    c2 = multi_candidate_track.all_candidates[1]
    try:
        fp1 = compute_fingerprint(c1.wav_path)
        fp2 = compute_fingerprint(c2.wav_path)
        same_track_dist = float(cdist([fp1], [fp2], metric="cosine")[0, 0])
        logger.info(
            "Self-test: same-track candidates distance=%.4f (should be < %.4f)",
            same_track_dist, within_threshold,
        )
        if same_track_dist > within_threshold:
            logger.warning(
                "Self-test WARN: same-track candidates (%.4f) are more distant than "
                "within_genre_threshold (%.4f) — threshold may be too tight",
                same_track_dist, within_threshold,
            )
    except Exception as exc:
        logger.warning("Self-test same-track comparison failed: %s", exc)

    # Test 2: Different tracks of same genre should be distinct
    if same_genre_pair is not None:
        s1, s2 = same_genre_pair
        if s1.selected_candidate and s2.selected_candidate:
            try:
                fp_a = compute_fingerprint(s1.selected_candidate.wav_path)
                fp_b = compute_fingerprint(s2.selected_candidate.wav_path)
                diff_track_dist = float(cdist([fp_a], [fp_b], metric="cosine")[0, 0])
                logger.info(
                    "Self-test: different tracks same genre distance=%.4f (should be > %.4f)",
                    diff_track_dist, within_threshold,
                )
                if diff_track_dist <= within_threshold:
                    logger.warning(
                        "Self-test WARN: different tracks same genre (%.4f) are within "
                        "within_genre_threshold (%.4f) — threshold may be too loose",
                        diff_track_dist, within_threshold,
                    )
            except Exception as exc:
                logger.warning("Self-test different-track comparison failed: %s", exc)
    else:
        logger.debug("Self-test: no same-genre pair available for inter-track test")
