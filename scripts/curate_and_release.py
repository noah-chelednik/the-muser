#!/usr/bin/env python3
"""
THE MUSER — Automated Curation & Release Packaging Pipeline
============================================================

Analyzes ~2500 candidate WAV files across 12 dimensions, selects the best
candidate per track via hard-gate rejection + soft-score tournament, masters
survivors, and packages them into upload-ready folders for DistroKid, Gumroad,
Fiverr, and Ko-fi.

Usage:
    python scripts/curate_and_release.py --run 20260228_2240
    python scripts/curate_and_release.py --run 20260228_2240 --phase analysis
    python scripts/curate_and_release.py --run 20260228_2240 --phase package
    python scripts/curate_and_release.py --run 20260228_2240 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.curation.config import load_config
from src.curation.models import (
    CandidateAnalysis,
    PipelineConfig,
    TrackSelection,
    DuplicatePair,
)

log = logging.getLogger("muser.curation")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------

def load_manifest(run_dir: Path) -> dict:
    """Load the production manifest."""
    manifest_path = run_dir / "production_manifest.json"
    if not manifest_path.exists():
        log.error("Manifest not found: %s", manifest_path)
        sys.exit(1)
    with open(manifest_path) as f:
        data = json.load(f)
    tracks = data.get("tracks", data)
    log.info("Loaded manifest: %d tracks", len(tracks))
    return tracks


def discover_candidates(run_dir: Path, manifest: dict) -> list[tuple[str, str, str]]:
    """Discover all candidate WAV files.

    Returns list of (wav_path, track_id, genre).
    """
    candidates_dir = run_dir / "candidates"
    found = []
    for track_id, track_data in manifest.items():
        genre = track_data.get("genre", "unknown")
        track_dir = candidates_dir / track_id
        if track_dir.is_dir():
            for wav in sorted(track_dir.glob("*.wav")):
                found.append((str(wav), track_id, genre))
        else:
            # Maybe the best_candidate is directly referenced
            best = track_data.get("best_candidate", "")
            if best and Path(best).exists():
                found.append((best, track_id, genre))
    log.info("Discovered %d candidate WAVs across %d tracks", len(found), len(manifest))
    return found


def run_analysis(
    candidates: list[tuple[str, str, str]],
    run_dir: Path,
    config: PipelineConfig,
) -> dict[str, list[CandidateAnalysis]]:
    """Phase 1: Run 12-dimension analysis on all candidates."""
    from src.curation.analyzer import analyze_candidate
    from src.curation.corpus_profiler import build_profiles_fast

    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # Build corpus profiles first (fast pass)
    log.info("Building corpus profiles...")
    wav_genre_pairs = [(wav, genre) for wav, _, genre in candidates]
    profiles = build_profiles_fast(wav_genre_pairs, config)
    profiles_path = analysis_dir / "corpus_profiles.json"
    with open(profiles_path, "w") as f:
        json.dump({g: p.model_dump() for g, p in profiles.items()}, f, indent=2)
    log.info("Corpus profiles built for %d genres.", len(profiles))

    # Full analysis with checkpointing
    results: dict[str, list[CandidateAnalysis]] = {}
    total = len(candidates)
    done = 0
    errors = 0

    for wav_path, track_id, genre in candidates:
        candidate_id = Path(wav_path).stem
        cache_path = analysis_dir / f"{candidate_id}.json"

        # Checkpoint: skip if already analyzed
        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    cached = CandidateAnalysis.model_validate_json(f.read())
                results.setdefault(track_id, []).append(cached)
                done += 1
                continue
            except Exception:
                pass  # Re-analyze if cache is corrupt

        try:
            profile = profiles.get(genre)
            analysis = analyze_candidate(wav_path, genre, config, corpus_profile=profile)
            # Save checkpoint
            cache_path.write_text(analysis.model_dump_json(indent=2))
            results.setdefault(track_id, []).append(analysis)
        except Exception as e:
            log.error("Analysis failed for %s: %s", candidate_id, e)
            errors += 1

        done += 1
        if done % 50 == 0:
            log.info("Analyzed %d/%d candidates (%d errors)...", done, total, errors)

    log.info("Analysis complete: %d candidates, %d errors.", done, errors)
    return results


def run_selection(
    analyses: dict[str, list[CandidateAnalysis]],
    manifest: dict,
    run_dir: Path,
    config: PipelineConfig,
) -> tuple[dict[str, TrackSelection], list[DuplicatePair]]:
    """Phases 2-6: Selection, dropout, cross-validation, dedup."""
    from src.curation.selector import select_tracks

    selections, duplicates = select_tracks(analyses, manifest, config)

    # Save selection report
    report_path = run_dir / "selection_report.json"
    report = {
        "selected": {
            tid: s.model_dump()
            for tid, s in selections.items()
            if not s.dropped
        },
        "dropped": {
            tid: s.model_dump()
            for tid, s in selections.items()
            if s.dropped
        },
        "duplicates": [d.model_dump() for d in duplicates],
        "stats": {
            "total_tracks": len(selections),
            "surviving": sum(1 for s in selections.values() if not s.dropped),
            "dropped": sum(1 for s in selections.values() if s.dropped),
            "duplicates_removed": len(duplicates),
        },
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info(
        "Selection: %d surviving, %d dropped, %d duplicates removed.",
        report["stats"]["surviving"],
        report["stats"]["dropped"],
        report["stats"]["duplicates_removed"],
    )
    return selections, duplicates


def run_mastering(
    selections: dict[str, TrackSelection],
    output_dir: Path,
    config: PipelineConfig,
) -> dict[str, str]:
    """Phase 7: Master all selected tracks."""
    from src.curation.mastering import master_all
    return master_all(selections, output_dir, config)


def run_metadata(
    selections: dict[str, TrackSelection],
    output_dir: Path,
    config: PipelineConfig,
) -> dict:
    """Phase 8: Generate metadata."""
    from src.curation.metadata import generate_metadata

    metadata = generate_metadata(selections, config)

    # Save metadata files
    meta_dir = output_dir / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    for tid, meta in metadata.items():
        with open(meta_dir / f"{tid}.json", "w") as f:
            f.write(meta.model_dump_json(indent=2))

    return metadata


def run_packaging(
    selections: dict[str, TrackSelection],
    metadata: dict,
    mastered_paths: dict[str, str],
    output_dir: Path,
    config: PipelineConfig,
) -> dict:
    """Phase 9: Package for all platforms."""
    from src.curation.packager import package_all
    return package_all(selections, metadata, mastered_paths, output_dir, config)


def run_report(
    selections: dict[str, TrackSelection],
    metadata: dict,
    duplicates: list[DuplicatePair],
    mastered_paths: dict[str, str],
    package_summary: dict,
    output_dir: Path,
    config: PipelineConfig,
) -> Path:
    """Phase 10: Generate HTML report."""
    from src.curation.report import generate_report
    return generate_report(
        selections, metadata, duplicates, mastered_paths,
        package_summary, output_dir / "report.html", config,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(args: argparse.Namespace) -> None:
    config = load_config(args.config, args.run)
    run_dir = Path(config.production_run_dir)
    output_dir = run_dir / "release"

    if not run_dir.exists():
        log.error("Production run not found: %s", run_dir)
        sys.exit(1)

    manifest = load_manifest(run_dir)

    # Filter to specific tracks if requested
    if args.tracks:
        track_filter = set(args.tracks.split(","))
        manifest = {k: v for k, v in manifest.items() if k in track_filter}
        log.info("Filtered to %d tracks: %s", len(manifest), ", ".join(sorted(manifest.keys())))

    candidates = discover_candidates(run_dir, manifest)

    if args.dry_run:
        log.info("DRY RUN — would analyze %d candidates from %d tracks.",
                 len(candidates), len(manifest))
        log.info("Output would go to: %s", output_dir)
        return

    phase = args.phase or "all"
    start = time.time()

    # --- Analysis ---
    if phase in ("all", "analysis"):
        log.info("=" * 60)
        log.info("PHASE 1: ANALYSIS")
        log.info("=" * 60)
        analyses = run_analysis(candidates, run_dir, config)
    else:
        # Load cached analyses
        log.info("Loading cached analyses...")
        analyses = _load_cached_analyses(run_dir)

    # --- Selection ---
    if phase in ("all", "analysis", "select"):
        log.info("=" * 60)
        log.info("PHASES 2-6: SELECTION + DEDUP")
        log.info("=" * 60)
        selections, duplicates = run_selection(analyses, manifest, run_dir, config)
    else:
        selections, duplicates = _load_cached_selections(run_dir)

    if phase == "analysis":
        elapsed = time.time() - start
        log.info("Analysis phase complete in %.1f min.", elapsed / 60)
        return

    # --- Mastering ---
    if phase in ("all", "package"):
        log.info("=" * 60)
        log.info("PHASE 7: MASTERING")
        log.info("=" * 60)
        mastered_paths = run_mastering(selections, output_dir, config)
    else:
        mastered_paths = _discover_mastered(output_dir)

    # --- Metadata ---
    if phase in ("all", "package"):
        log.info("=" * 60)
        log.info("PHASE 8: METADATA")
        log.info("=" * 60)
        metadata = run_metadata(selections, output_dir, config)
    else:
        metadata = _load_cached_metadata(output_dir)

    # --- Packaging ---
    if phase in ("all", "package"):
        log.info("=" * 60)
        log.info("PHASE 9: PACKAGING")
        log.info("=" * 60)
        package_summary = run_packaging(selections, metadata, mastered_paths, output_dir, config)
    else:
        package_summary = {}

    # --- Report ---
    log.info("=" * 60)
    log.info("PHASE 10: REPORT")
    log.info("=" * 60)
    report_path = run_report(
        selections, metadata, duplicates, mastered_paths,
        package_summary, output_dir, config,
    )

    elapsed = time.time() - start
    surviving = sum(1 for s in selections.values() if not s.dropped)
    log.info("=" * 60)
    log.info("PIPELINE COMPLETE in %.1f minutes", elapsed / 60)
    log.info("  %d tracks surviving → %s", surviving, output_dir)
    log.info("  Report: %s", report_path)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Cache loaders
# ---------------------------------------------------------------------------

def _load_cached_analyses(run_dir: Path) -> dict[str, list[CandidateAnalysis]]:
    analysis_dir = run_dir / "analysis"
    results: dict[str, list[CandidateAnalysis]] = {}
    if not analysis_dir.exists():
        return results
    for f in analysis_dir.glob("*.json"):
        if f.name == "corpus_profiles.json":
            continue
        try:
            analysis = CandidateAnalysis.model_validate_json(f.read_text())
            results.setdefault(analysis.track_id, []).append(analysis)
        except Exception:
            continue
    log.info("Loaded %d cached analyses.", sum(len(v) for v in results.values()))
    return results


def _load_cached_selections(run_dir: Path) -> tuple[dict[str, TrackSelection], list[DuplicatePair]]:
    report_path = run_dir / "selection_report.json"
    if not report_path.exists():
        return {}, []
    with open(report_path) as f:
        data = json.load(f)
    selections = {}
    for group in ("selected", "dropped"):
        for tid, sdata in data.get(group, {}).items():
            selections[tid] = TrackSelection.model_validate(sdata)
    duplicates = [DuplicatePair.model_validate(d) for d in data.get("duplicates", [])]
    log.info("Loaded cached selections: %d tracks.", len(selections))
    return selections, duplicates


def _discover_mastered(output_dir: Path) -> dict[str, str]:
    manifest_path = output_dir / "mastered" / "mastered_manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return {}


def _load_cached_metadata(output_dir: Path) -> dict:
    from src.curation.models import TrackMetadata
    meta_dir = output_dir / "metadata"
    if not meta_dir.exists():
        return {}
    metadata = {}
    for f in meta_dir.glob("*.json"):
        try:
            meta = TrackMetadata.model_validate_json(f.read_text())
            metadata[meta.track_id] = meta
        except Exception:
            continue
    return metadata


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Muser Automated Curation & Release Packaging Pipeline",
    )
    parser.add_argument(
        "--run", required=True,
        help="Production run ID (directory name under production_run/)",
    )
    parser.add_argument(
        "--phase", choices=["analysis", "select", "package", "all"],
        default="all",
        help="Run only a specific phase (default: all)",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to curation_config.json (default: project root)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen without writing files",
    )
    parser.add_argument(
        "--tracks",
        help="Comma-separated track IDs to re-analyze (e.g., P1-A01,P1-B02)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()
    setup_logging(args.verbose)

    log.info("Muser Curation Pipeline — run: %s, phase: %s", args.run, args.phase or "all")
    run_pipeline(args)


if __name__ == "__main__":
    main()
