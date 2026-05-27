"""Phase 7: Genre-aware post-production and mastering."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .models import PipelineConfig, TrackSelection

log = logging.getLogger(__name__)

# Loudness targets per post-production preset
_LUFS_TARGETS = {
    "classical": -18,
    "default": -14,
    "pop": -14,
    "rock": -14,
    "electronic": -12,
}


def _master_one(
    track: TrackSelection,
    output_dir: Path,
    config: PipelineConfig,
) -> tuple[str, str | None]:
    """Master a single track. Returns (track_id, output_wav_path | None)."""
    try:
        from src.audio.postproduction import apply_postproduction
        from src.audio.export import (
            normalize_loudness,
            convert_to_mp3,
            add_metadata,
        )
    except ImportError:
        log.error("Cannot import audio modules — is the Muser venv active?")
        return (track.track_id, None)

    if not track.selected_candidate:
        return (track.track_id, None)

    src_wav = Path(track.selected_candidate.wav_path)
    if not src_wav.exists():
        log.warning("Source WAV missing: %s", src_wav)
        return (track.track_id, None)

    genre_map = config.postproduction.get("genre_preset_map", {})
    preset = genre_map.get(track.genre, "default")
    target_lufs = _LUFS_TARGETS.get(preset, -14)

    mastered_dir = output_dir / "mastered"
    mastered_dir.mkdir(parents=True, exist_ok=True)

    # Clean filename
    safe_title = _safe_filename(track.title or track.track_id)
    wav_out = mastered_dir / f"{safe_title}_{track.track_id}.wav"
    mp3_out = mastered_dir / f"{safe_title}_{track.track_id}.mp3"

    try:
        # Step 1: genre post-production
        intermediate = mastered_dir / f"_tmp_{track.track_id}.wav"
        apply_postproduction(
            str(src_wav),
            str(intermediate),
            genre=preset,
        )

        # Step 2: loudness normalize
        normalize_loudness(str(intermediate), str(wav_out), target_lufs=target_lufs)
        if intermediate.exists():
            intermediate.unlink()

        # Step 3: MP3
        convert_to_mp3(str(wav_out), str(mp3_out))

        # Step 4: metadata tagging
        meta = {
            "title": track.title or track.track_id,
            "artist": config.artist_name,
            "genre": track.genre,
            "year": str(config.release_year),
        }
        add_metadata(str(wav_out), **meta)
        add_metadata(str(mp3_out), **meta)

        log.info("Mastered: %s → %s", track.track_id, wav_out.name)
        return (track.track_id, str(wav_out))

    except Exception as e:
        log.error("Mastering failed for %s: %s", track.track_id, e)
        # Clean up partial outputs including intermediate
        for f in (wav_out, mp3_out, intermediate):
            if f.exists():
                f.unlink()
        return (track.track_id, None)


def master_all(
    selections: dict[str, TrackSelection],
    output_dir: Path,
    config: PipelineConfig,
) -> dict[str, str]:
    """Master all selected tracks. Returns {track_id: mastered_wav_path}."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    tracks_to_master = [t for t in selections.values() if not t.dropped and t.selected_candidate]
    log.info(
        "Mastering %d tracks with %d workers...", len(tracks_to_master), config.parallel_workers
    )

    with ProcessPoolExecutor(max_workers=config.parallel_workers) as pool:
        futures = {
            pool.submit(_master_one, track, output_dir, config): track.track_id
            for track in tracks_to_master
        }
        for future in as_completed(futures):
            tid = futures[future]
            try:
                track_id, wav_path = future.result()
                if wav_path:
                    results[track_id] = wav_path
            except Exception as e:
                log.error("Worker error for %s: %s", tid, e)

    # Save mastered manifest for cache reload
    import json

    manifest_path = output_dir / "mastered" / "mastered_manifest.json"
    if results:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(results, f, indent=2)

    log.info("Mastered %d of %d tracks successfully.", len(results), len(tracks_to_master))
    return results


def _safe_filename(title: str) -> str:
    """Convert a track title to a filesystem-safe name."""
    safe = title.replace(" ", "_")
    safe = "".join(c for c in safe if c.isalnum() or c in ("_", "-"))
    return safe[:80] or "untitled"
