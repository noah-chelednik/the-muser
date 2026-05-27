"""Phases 2-5 — Gate Filtering, Tournament, Dropout, and Cross-Validation.

Takes the per-candidate analysis results from Phase 1 and produces
a :class:`TrackSelection` for every track in the manifest.  Tracks whose
best candidate cannot pass all hard gates are dropped with a reason.
The old 9-metric scorer is run for cross-validation so that rank
disagreements can be flagged.
"""

from __future__ import annotations

import logging

from src.curation.models import (
    CandidateAnalysis,
    DuplicatePair,
    PipelineConfig,
    TrackSelection,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Old scorer import (best-effort)
# ---------------------------------------------------------------------------

try:
    from src.audio.audio_validator import evaluate_quality

    def _get_old_score(wav_path: str) -> float:
        """Run the legacy 9-metric quality scorer."""
        try:
            report = evaluate_quality(wav_path)
            return float(report.composite_score)
        except Exception as exc:
            logger.debug("Old scorer failed for %s: %s", wav_path, exc)
            return 0.0
except ImportError:
    logger.debug("audio_validator not available; old scorer disabled")

    def _get_old_score(wav_path: str) -> float:  # noqa: ARG001
        return 0.0


# ---------------------------------------------------------------------------
# Main selection pipeline
# ---------------------------------------------------------------------------

def select_tracks(
    analyses: dict[str, list[CandidateAnalysis]],
    manifest_tracks: dict,
    config: PipelineConfig,
) -> tuple[dict[str, TrackSelection], list[DuplicatePair]]:
    """Run selection phases 2 through 5 and return results.

    Parameters
    ----------
    analyses:
        ``{track_id: [CandidateAnalysis, ...]}`` — all analyzed candidates
        grouped by track.
    manifest_tracks:
        Raw manifest dict keyed by track_id, used to pull title/genre/tags.
    config:
        Pipeline configuration.

    Returns
    -------
    tuple[dict[str, TrackSelection], list[DuplicatePair]]
        Final track selections and any duplicate pairs detected.
    """
    selections: dict[str, TrackSelection] = {}

    # Collect all track IDs from both analyses and manifest
    all_track_ids = set(analyses.keys()) | set(manifest_tracks.keys())

    for track_id in sorted(all_track_ids):
        candidates = analyses.get(track_id, [])
        manifest_entry = manifest_tracks.get(track_id, {})

        title = manifest_entry.get("title", "")
        genre = manifest_entry.get("genre", "")
        category = manifest_entry.get("category", "")
        tags = manifest_entry.get("tags", "")

        selection = _select_one_track(
            track_id=track_id,
            candidates=candidates,
            title=title,
            genre=genre,
            category=category,
            tags=tags,
        )
        selections[track_id] = selection

    # ------------------------------------------------------------------
    # Phase 5 — Cross-Validation
    # ------------------------------------------------------------------
    _cross_validate(selections)

    # ------------------------------------------------------------------
    # Phase 6 — Deduplication (delegated)
    # ------------------------------------------------------------------
    selections, duplicate_pairs = apply_dedup(selections, config)

    survived = sum(1 for s in selections.values() if not s.dropped)
    dropped = sum(1 for s in selections.values() if s.dropped)
    logger.info(
        "Selection complete: %d survived, %d dropped, %d duplicates removed",
        survived, dropped, len(duplicate_pairs),
    )

    return selections, duplicate_pairs


# ---------------------------------------------------------------------------
# Per-track selection (Phases 2-4)
# ---------------------------------------------------------------------------

def _select_one_track(
    track_id: str,
    candidates: list[CandidateAnalysis],
    title: str = "",
    genre: str = "",
    category: str = "",
    tags: str = "",
) -> TrackSelection:
    """Phase 2-4 for a single track: gate, tournament, dropout."""

    selection = TrackSelection(
        track_id=track_id,
        title=title,
        genre=genre,
        category=category,
        tags=tags,
        all_candidates=candidates,
    )

    if not candidates:
        selection.dropped = True
        selection.drop_reason = "no candidates found"
        logger.warning("Track %s dropped: no candidates", track_id)
        return selection

    # ------------------------------------------------------------------
    # Phase 2 — Hard gate filtering
    # ------------------------------------------------------------------
    passed_candidates = [c for c in candidates if c.hard_gates_passed]

    # ------------------------------------------------------------------
    # Phase 3 — Tournament (pick highest composite score)
    # ------------------------------------------------------------------
    if passed_candidates:
        best = max(passed_candidates, key=lambda c: c.composite_score)
        selection.selected_candidate = best
        selection.new_score = best.composite_score
        selection.duration_s = best.duration_s
    else:
        # ------------------------------------------------------------------
        # Phase 4 — Dropout
        # ------------------------------------------------------------------
        selection.dropped = True

        # Build detailed failure reason
        failure_details: list[str] = []
        for c in candidates:
            failures = ", ".join(c.gate_failures) if c.gate_failures else "unknown"
            failure_details.append(f"{c.candidate_id}: {failures}")
        selection.drop_reason = (
            f"all {len(candidates)} candidates failed hard gates: "
            + "; ".join(failure_details)
        )
        logger.info("Track %s dropped: %s", track_id, selection.drop_reason)

    return selection


# ---------------------------------------------------------------------------
# Phase 5 — Cross-Validation with old scorer
# ---------------------------------------------------------------------------

def _cross_validate(selections: dict[str, TrackSelection]) -> None:
    """Run old scorer on selected tracks, flag rank disagreements.

    Mutates ``selections`` in place: sets ``old_score`` and ``confidence``.
    """
    # Collect tracks that have a selected candidate
    selected = {
        tid: sel for tid, sel in selections.items()
        if not sel.dropped and sel.selected_candidate is not None
    }
    if not selected:
        return

    corpus_size = len(selected)
    if corpus_size < 3:
        logger.debug("Too few tracks (%d) for meaningful cross-validation", corpus_size)
        return

    # Compute old scores
    for tid, sel in selected.items():
        assert sel.selected_candidate is not None
        sel.old_score = _get_old_score(sel.selected_candidate.wav_path)

    # Rank by new score (descending)
    new_ranked = sorted(selected.keys(), key=lambda t: selected[t].new_score, reverse=True)
    new_rank_map = {tid: rank for rank, tid in enumerate(new_ranked)}

    # Rank by old score (descending)
    old_ranked = sorted(selected.keys(), key=lambda t: selected[t].old_score, reverse=True)
    old_rank_map = {tid: rank for rank, tid in enumerate(old_ranked)}

    # Flag rank disagreements > 20% of corpus
    threshold = 0.20 * corpus_size
    uncertain_count = 0

    for tid in selected:
        rank_diff = abs(new_rank_map[tid] - old_rank_map[tid])
        if rank_diff > threshold:
            selections[tid].confidence = "uncertain"
            uncertain_count += 1
            logger.debug(
                "Track %s flagged uncertain: new_rank=%d old_rank=%d diff=%d (threshold=%.1f)",
                tid, new_rank_map[tid], old_rank_map[tid], rank_diff, threshold,
            )

    if uncertain_count > 0:
        logger.info(
            "Cross-validation: %d/%d tracks flagged as uncertain (threshold=%.1f)",
            uncertain_count, corpus_size, threshold,
        )


# ---------------------------------------------------------------------------
# Phase 6 — Deduplication wrapper
# ---------------------------------------------------------------------------

def apply_dedup(
    selections: dict[str, TrackSelection],
    config: PipelineConfig,
) -> tuple[dict[str, TrackSelection], list[DuplicatePair]]:
    """Run duplicate detection and remove duplicates from selections.

    Parameters
    ----------
    selections:
        Current track selections (may be mutated).
    config:
        Pipeline configuration with duplicate_detection thresholds.

    Returns
    -------
    tuple[dict[str, TrackSelection], list[DuplicatePair]]
        Updated selections (dropped duplicates marked) and duplicate pairs.
    """
    try:
        from src.curation.deduplicator import find_duplicates
    except ImportError:
        logger.warning("Deduplicator not available; skipping duplicate detection")
        return selections, []

    # Only check non-dropped tracks
    active_selections = {
        tid: sel for tid, sel in selections.items() if not sel.dropped
    }

    if len(active_selections) < 2:
        return selections, []

    duplicate_pairs = find_duplicates(active_selections, config)

    # Mark dropped duplicates
    for pair in duplicate_pairs:
        if pair.dropped_id in selections:
            selections[pair.dropped_id].dropped = True
            selections[pair.dropped_id].drop_reason = (
                f"duplicate of {pair.kept_id} (similarity={pair.similarity:.4f}, "
                f"same_genre={pair.same_genre})"
            )
            logger.info(
                "Dedup: dropped %s (dup of %s, sim=%.4f)",
                pair.dropped_id, pair.kept_id, pair.similarity,
            )

    return selections, duplicate_pairs
