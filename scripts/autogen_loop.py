#!/usr/bin/env python3
"""AutoGen continuous generation loop for The Muser.

Generates batches of audio candidates in a loop, scoring each and maintaining
a sorted leaderboard.  Supports early termination above a quality threshold
and writes incremental results for review while running.

Usage::

    python scripts/autogen_loop.py \
        --tags "A warm jazz piano trio with walking bass and brush drums" \
        --target-count 20 \
        --quality-threshold 0.75 \
        --batch-size 4 \
        --output-dir output/autogen_jazz

The loop continues until either:
- ``target-count`` candidates have been generated, or
- ``max-rounds`` batches have been produced, or
- the user interrupts with Ctrl+C (partial results are saved).
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator.config import (
    ACESTEP_INFER_STEP,
    ACESTEP_GUIDANCE_SCALE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("muser.autogen")


# ---------------------------------------------------------------------------
# Audio quality scoring (same as batch script)
# ---------------------------------------------------------------------------

def get_audio_quality_score(wav_path: str) -> float:
    """Score audio quality using expanded metrics from audio_validator.

    Returns a composite score in [0, 1] where higher is better.
    Falls back to simple 3-metric scoring if evaluate_quality is unavailable.
    """
    try:
        from src.audio.audio_validator import evaluate_quality

        report = evaluate_quality(wav_path)
        return report.composite_score

    except Exception:
        # Fallback: simple 3-metric scoring (backwards compatible)
        try:
            import librosa
            import numpy as np

            y, sr = librosa.load(wav_path, sr=None, mono=True)
            if y is None or len(y) == 0:
                return 0.0

            rms = librosa.feature.rms(y=y)[0]
            rms_mean = float(rms.mean())
            if rms_mean < 1e-6:
                return 0.0
            rms_score = min(rms_mean / 0.1, 1.0)

            rms_db = 20 * np.log10(rms + 1e-10)
            dynamic_range = float(rms_db.std())
            dr_score = min(dynamic_range / 15.0, 1.0)

            centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            centroid_var = float(centroid.std() / (centroid.mean() + 1e-10))
            sc_score = min(centroid_var / 0.5, 1.0)

            score = 0.4 * rms_score + 0.3 * dr_score + 0.3 * sc_score
            return round(score, 4)

        except Exception as exc:
            logger.warning("Quality scoring failed for %s: %s", wav_path, exc)
            return 0.0


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """A single generated audio candidate."""
    path: str
    score: float
    seed: int
    round_idx: int
    generation_time_s: float


class Leaderboard:
    """Sorted list of candidates, best first."""

    def __init__(self) -> None:
        self._entries: list[Candidate] = []

    def add(self, candidate: Candidate) -> int:
        """Add a candidate and return its rank (0-based)."""
        self._entries.append(candidate)
        self._entries.sort(key=lambda c: c.score, reverse=True)
        return self._entries.index(candidate)

    @property
    def best(self) -> Candidate | None:
        return self._entries[0] if self._entries else None

    @property
    def count(self) -> int:
        return len(self._entries)

    def top(self, n: int) -> list[Candidate]:
        return self._entries[:n]

    def to_list(self) -> list[dict]:
        return [asdict(c) for c in self._entries]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_stop_requested = False


def _handle_signal(signum, frame):
    global _stop_requested
    logger.info("Interrupt received, finishing current round...")
    _stop_requested = True


def run_autogen(
    tags: str,
    lyrics: str,
    duration_s: int,
    target_count: int,
    max_rounds: int,
    batch_size: int,
    quality_threshold: float,
    infer_step: int,
    guidance_scale: float,
    output_dir: Path,
    base_seed: int,
    bpm: int | None,
    key_scale: str,
) -> Leaderboard:
    """Run the continuous generation loop."""
    from src.generation.acestep_wrapper import generate_audio

    leaderboard = Leaderboard()
    output_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = output_dir / "leaderboard.json"

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    total_start = time.time()

    for round_idx in range(max_rounds):
        if _stop_requested:
            logger.info("Stop requested, exiting loop.")
            break

        if leaderboard.count >= target_count:
            logger.info(
                "Target count %d reached (%d candidates), stopping.",
                target_count, leaderboard.count,
            )
            break

        # Check if quality threshold met for top candidate
        if quality_threshold > 0 and leaderboard.best and leaderboard.best.score >= quality_threshold:
            logger.info(
                "Quality threshold %.4f met (best=%.4f), stopping.",
                quality_threshold, leaderboard.best.score,
            )
            break

        seed = base_seed + round_idx * batch_size
        logger.info(
            "=== Round %d/%d | Candidates: %d/%d | Best: %.4f | Seed: %d ===",
            round_idx + 1, max_rounds,
            leaderboard.count, target_count,
            leaderboard.best.score if leaderboard.best else 0.0,
            seed,
        )

        gen_start = time.time()
        try:
            paths = generate_audio(
                tags=tags,
                lyrics=lyrics,
                duration_s=duration_s,
                num_candidates=batch_size,
                seed=seed,
                infer_step=infer_step,
                guidance_scale=guidance_scale,
                bpm=bpm,
                key_scale=key_scale,
            )
        except Exception as exc:
            logger.error("Generation failed in round %d: %s", round_idx, exc)
            continue
        gen_time = time.time() - gen_start

        if not paths:
            logger.warning("No output in round %d", round_idx)
            continue

        # Score and add to leaderboard
        for j, wav_path in enumerate(paths):
            score = get_audio_quality_score(wav_path)
            candidate = Candidate(
                path=wav_path,
                score=score,
                seed=seed + j,
                round_idx=round_idx,
                generation_time_s=round(gen_time / len(paths), 2),
            )
            rank = leaderboard.add(candidate)
            logger.info(
                "  Candidate %d: score=%.4f, rank=#%d, seed=%d",
                leaderboard.count, score, rank + 1, seed + j,
            )

        # Write incremental leaderboard
        _save_leaderboard(leaderboard, leaderboard_path, total_start)

        # GPU memory cleanup between rounds
        try:
            import gc
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    return leaderboard


def _save_leaderboard(leaderboard: Leaderboard, path: Path, start_time: float):
    """Write the current leaderboard to disk."""
    data = {
        "total_candidates": leaderboard.count,
        "best_score": leaderboard.best.score if leaderboard.best else 0.0,
        "elapsed_s": round(time.time() - start_time, 1),
        "candidates": leaderboard.to_list(),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="AutoGen continuous generation loop for The Muser"
    )
    parser.add_argument(
        "--tags", required=True,
        help="Descriptive caption / tags for generation",
    )
    parser.add_argument(
        "--lyrics", default="[instrumental]",
        help="Lyrics (default: [instrumental])",
    )
    parser.add_argument(
        "--duration", type=int, default=60,
        help="Duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--target-count", type=int, default=50,
        help="Stop after generating this many candidates (default: 50)",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=100,
        help="Maximum number of generation rounds (default: 100)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=4,
        help="Candidates per round (default: 4)",
    )
    parser.add_argument(
        "--quality-threshold", type=float, default=0.0,
        help="Stop early if best score exceeds this (default: 0 = disabled)",
    )
    parser.add_argument(
        "--infer-step", type=int, default=ACESTEP_INFER_STEP,
        help=f"Diffusion inference steps (default: {ACESTEP_INFER_STEP})",
    )
    parser.add_argument(
        "--guidance-scale", type=float, default=ACESTEP_GUIDANCE_SCALE,
        help=f"CFG guidance scale (default: {ACESTEP_GUIDANCE_SCALE})",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: output/autogen_YYYYMMDD_HHMM)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Base random seed (default: 42)",
    )
    parser.add_argument(
        "--bpm", type=int, default=None,
        help="Target BPM (v1.5 only)",
    )
    parser.add_argument(
        "--key", default="",
        help="Target key (v1.5 only, e.g., 'C major')",
    )

    args = parser.parse_args()

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        output_dir = PROJECT_ROOT / "output" / f"autogen_{timestamp}"

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("AutoGen Continuous Generation Loop")
    logger.info("=" * 60)
    logger.info("Tags: %s", args.tags[:100])
    logger.info("Duration: %ds, Batch: %d, Target: %d, Max rounds: %d",
                args.duration, args.batch_size, args.target_count, args.max_rounds)
    logger.info("Quality threshold: %.4f", args.quality_threshold)
    logger.info("Output: %s", output_dir)
    logger.info("=" * 60)

    start = time.time()
    leaderboard = run_autogen(
        tags=args.tags,
        lyrics=args.lyrics,
        duration_s=args.duration,
        target_count=args.target_count,
        max_rounds=args.max_rounds,
        batch_size=args.batch_size,
        quality_threshold=args.quality_threshold,
        infer_step=args.infer_step,
        guidance_scale=args.guidance_scale,
        output_dir=output_dir,
        base_seed=args.seed,
        bpm=args.bpm,
        key_scale=args.key,
    )
    total_time = time.time() - start

    logger.info("=" * 60)
    logger.info("AutoGen complete!")
    logger.info("  Total candidates: %d", leaderboard.count)
    if leaderboard.best:
        logger.info("  Best score: %.4f (%s)", leaderboard.best.score, leaderboard.best.path)
    logger.info("  Total time: %.1f minutes", total_time / 60)
    logger.info("  Top 5:")
    for i, c in enumerate(leaderboard.top(5), 1):
        logger.info("    #%d: %.4f (seed=%d) %s", i, c.score, c.seed, c.path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
