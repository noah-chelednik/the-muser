"""Phase 1 — Analysis Orchestrator.

Loads each candidate WAV, runs all 12 dimension analyzers (6 hard gates +
6 soft scores), computes a genre-aware composite score, and returns a
:class:`CandidateAnalysis` for each file.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

import librosa
import numpy as np

from src.curation.models import (
    CandidateAnalysis,
    CorpusProfile,
    DimensionResult,
    PipelineConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dimension module registry
# ---------------------------------------------------------------------------

HARD_GATE_DIMS = ["artifacts", "clipping", "silence", "loudness", "phase", "edge_clicks"]
SOFT_SCORE_DIMS = ["structure", "rhythm", "harmony", "freq_balance", "evolution", "stereo_mix"]

_FILENAME_RE = re.compile(r"^(?P<track_id>.+?)_c(?P<cnum>\d+)\.wav$", re.IGNORECASE)


_DIM_MODULE_MAP = {
    "freq_balance": "frequency_balance",
}


def _import_dimension(name: str):
    """Lazily import a dimension module from src.curation.dimensions.<name>."""
    import importlib

    module_name = _DIM_MODULE_MAP.get(name, name)
    mod = importlib.import_module(f"src.curation.dimensions.{module_name}")
    return mod


def _parse_candidate_filename(wav_path: str) -> tuple[str, str]:
    """Extract (track_id, candidate_id) from a path like ``.../<track_id>_c<NN>.wav``."""
    m = _FILENAME_RE.match(Path(wav_path).name)
    if m:
        track_id = m.group("track_id")
        candidate_id = f"{track_id}_c{m.group('cnum')}"
        return track_id, candidate_id
    # Fallback: use whole stem as both
    stem = Path(wav_path).stem
    return stem, stem


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


def compute_composite(
    dimensions: dict[str, DimensionResult],
    config: PipelineConfig,
    genre: str,
) -> float:
    """Compute genre-aware weighted composite from soft dimension scores."""
    weights = dict(config.soft_weights)
    overrides = config.genre_weight_overrides.get(genre, {})
    for k, v in overrides.items():
        if k in weights:
            weights[k] = v
    total_w = sum(weights.values())
    if total_w == 0:
        return 0.0
    weights = {k: v / total_w for k, v in weights.items()}

    soft_dims = ["structure", "rhythm", "harmony", "freq_balance", "evolution", "stereo_mix"]
    score = sum(
        dimensions.get(d, DimensionResult(name=d)).score * weights.get(d, 0) for d in soft_dims
    )
    return round(score, 4)


# ---------------------------------------------------------------------------
# Single candidate analysis
# ---------------------------------------------------------------------------


def analyze_candidate(
    wav_path: str,
    genre: str,
    config: PipelineConfig,
    corpus_profile: Optional[CorpusProfile] = None,
) -> CandidateAnalysis:
    """Run all 12 dimension analyzers on one candidate WAV.

    Parameters
    ----------
    wav_path:
        Path to a candidate WAV file (pattern ``<track_id>_c<NN>.wav``).
    genre:
        Genre tag for this track (used for weight overrides and corpus comparison).
    config:
        Pipeline configuration.
    corpus_profile:
        Optional pre-computed corpus profile for this genre.

    Returns
    -------
    CandidateAnalysis
        Fully populated analysis including all dimension results, gate status,
        and composite score.
    """
    track_id, candidate_id = _parse_candidate_filename(wav_path)
    logger.info("Analyzing candidate %s (%s)", candidate_id, genre)

    # ------------------------------------------------------------------
    # Load audio
    # ------------------------------------------------------------------
    try:
        samples_mono, sr = librosa.load(wav_path, sr=None, mono=True)
    except Exception as exc:
        logger.error("Failed to load %s: %s", wav_path, exc)
        return CandidateAnalysis(
            track_id=track_id,
            candidate_id=candidate_id,
            wav_path=str(wav_path),
        )

    # Stereo load (needed by phase and stereo_mix)
    try:
        samples_stereo, sr_stereo = librosa.load(wav_path, sr=None, mono=False)
        if samples_stereo.ndim == 1:
            # Mono file: duplicate into 2-channel for compatibility
            samples_stereo = np.stack([samples_stereo, samples_stereo])
        channels = samples_stereo.shape[0]
    except Exception:
        samples_stereo = np.stack([samples_mono, samples_mono])
        channels = 1

    duration_s = len(samples_mono) / max(sr, 1)

    # ------------------------------------------------------------------
    # Run hard gate dimensions
    # ------------------------------------------------------------------
    dimensions: dict[str, DimensionResult] = {}

    for dim_name in HARD_GATE_DIMS:
        try:
            mod = _import_dimension(dim_name)
            kwargs: dict[str, Any] = {}

            # Loudness needs the file path for integrated LUFS measurement
            if dim_name == "loudness":
                kwargs["wav_path"] = wav_path

            # Phase needs stereo samples
            if dim_name == "phase":
                result = mod.analyze(samples_stereo, sr, config.hard_gates, **kwargs)
            else:
                result = mod.analyze(samples_mono, sr, config.hard_gates, **kwargs)

            dimensions[dim_name] = result
        except Exception as exc:
            logger.warning("Hard gate %s failed for %s: %s", dim_name, candidate_id, exc)
            dimensions[dim_name] = DimensionResult(
                name=dim_name,
                score=0.0,
                hard_gate=None,
                raw_metrics={"error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Run soft score dimensions
    # ------------------------------------------------------------------
    for dim_name in SOFT_SCORE_DIMS:
        try:
            mod = _import_dimension(dim_name)
            kwargs = {
                "genre": genre,
                "corpus_profile": corpus_profile.model_dump() if corpus_profile else None,
            }

            # Stereo mix needs the stereo waveform
            if dim_name == "stereo_mix":
                kwargs["samples_stereo"] = samples_stereo

            result = mod.analyze(samples_mono, sr, config.soft_weights, **kwargs)
            dimensions[dim_name] = result
        except Exception as exc:
            logger.warning("Soft dim %s failed for %s: %s", dim_name, candidate_id, exc)
            dimensions[dim_name] = DimensionResult(
                name=dim_name,
                score=0.0,
                raw_metrics={"error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Check hard gates
    # ------------------------------------------------------------------
    gate_failures: list[str] = []
    for dim_name in HARD_GATE_DIMS:
        dr = dimensions.get(dim_name)
        if dr is None or dr.hard_gate is None:
            gate_failures.append(f"{dim_name}: no result")
            continue
        if not dr.hard_gate.passed:
            reason = dr.hard_gate.reason or f"{dim_name} failed"
            gate_failures.append(reason)

    hard_gates_passed = len(gate_failures) == 0

    # ------------------------------------------------------------------
    # Composite score
    # ------------------------------------------------------------------
    composite = compute_composite(dimensions, config, genre)

    return CandidateAnalysis(
        track_id=track_id,
        candidate_id=candidate_id,
        wav_path=str(wav_path),
        duration_s=round(duration_s, 2),
        sample_rate=int(sr),
        channels=int(channels),
        dimensions=dimensions,
        hard_gates_passed=hard_gates_passed,
        gate_failures=gate_failures,
        composite_score=composite,
    )


# ---------------------------------------------------------------------------
# Batch analysis with checkpointing
# ---------------------------------------------------------------------------


def _analyze_one(args: tuple) -> CandidateAnalysis:
    """Top-level wrapper so ProcessPoolExecutor can pickle the call."""
    wav_path, genre, config_dict, profile_dict = args
    config = PipelineConfig(**config_dict)
    profile = CorpusProfile(**profile_dict) if profile_dict else None
    return analyze_candidate(wav_path, genre, config, corpus_profile=profile)


def analyze_batch(
    candidates: list[tuple[str, str]],
    config: PipelineConfig,
    corpus_profiles: dict[str, CorpusProfile] | None = None,
) -> list[CandidateAnalysis]:
    """Analyze a batch of candidates in parallel with checkpointing.

    Parameters
    ----------
    candidates:
        List of ``(wav_path, genre)`` tuples.
    config:
        Pipeline configuration.
    corpus_profiles:
        Optional mapping of genre -> CorpusProfile for corpus-relative scoring.

    Returns
    -------
    list[CandidateAnalysis]
        One analysis per candidate.
    """
    if corpus_profiles is None:
        corpus_profiles = {}

    # Checkpoint directory
    run_dir = Path(config.production_run_dir) if config.production_run_dir else None
    analysis_dir = run_dir / "analysis" if run_dir else None
    if analysis_dir:
        analysis_dir.mkdir(parents=True, exist_ok=True)

    results: list[CandidateAnalysis] = []
    pending: list[tuple[int, tuple[str, str]]] = []

    # Check for existing checkpoints
    for idx, (wav_path, genre) in enumerate(candidates):
        _, candidate_id = _parse_candidate_filename(wav_path)
        checkpoint = analysis_dir / f"{candidate_id}.json" if analysis_dir else None
        if checkpoint and checkpoint.exists():
            try:
                data = json.loads(checkpoint.read_text())
                ca = CandidateAnalysis(**data)
                results.append(ca)
                logger.debug("Loaded checkpoint for %s", candidate_id)
                continue
            except Exception as exc:
                logger.warning("Bad checkpoint for %s, re-analyzing: %s", candidate_id, exc)
        pending.append((idx, (wav_path, genre)))

    if not pending:
        logger.info("All %d candidates already checkpointed", len(candidates))
        return results

    logger.info(
        "Analyzing %d candidates (%d cached) with %d workers",
        len(pending),
        len(results),
        config.parallel_workers,
    )

    # Serialize config and profiles for pickling
    config_dict = config.model_dump()
    profile_dicts = {g: p.model_dump() for g, p in corpus_profiles.items()}

    # Build argument tuples
    work_items: list[tuple] = []
    pending_indices: list[int] = []
    for idx, (wav_path, genre) in pending:
        prof = profile_dicts.get(genre)
        work_items.append((wav_path, genre, config_dict, prof))
        pending_indices.append(idx)

    # Execute in parallel
    new_results: dict[int, CandidateAnalysis] = {}
    max_workers = min(config.parallel_workers, len(work_items))

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_analyze_one, item): i
                for i, item in zip(pending_indices, work_items)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    ca = future.result()
                    new_results[idx] = ca
                    # Save checkpoint
                    if analysis_dir:
                        out_path = analysis_dir / f"{ca.candidate_id}.json"
                        out_path.write_text(ca.model_dump_json(indent=2))
                except Exception as exc:
                    wav_path, genre = candidates[idx]
                    _, cid = _parse_candidate_filename(wav_path)
                    logger.error("Analysis failed for %s: %s", cid, exc)
                    new_results[idx] = CandidateAnalysis(
                        track_id=cid,
                        candidate_id=cid,
                        wav_path=wav_path,
                    )
    except Exception as exc:
        logger.error("ProcessPoolExecutor failed, falling back to sequential: %s", exc)
        for i, item in zip(pending_indices, work_items):
            try:
                ca = _analyze_one(item)
                new_results[i] = ca
                if analysis_dir:
                    out_path = analysis_dir / f"{ca.candidate_id}.json"
                    out_path.write_text(ca.model_dump_json(indent=2))
            except Exception as inner_exc:
                wav_path = item[0]
                _, cid = _parse_candidate_filename(wav_path)
                logger.error("Sequential analysis failed for %s: %s", cid, inner_exc)
                new_results[i] = CandidateAnalysis(
                    track_id=cid,
                    candidate_id=cid,
                    wav_path=wav_path,
                )

    results.extend(new_results[i] for i in sorted(new_results))
    logger.info("Analysis complete: %d total candidates", len(results))
    return results
