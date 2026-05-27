#!/usr/bin/env python3
"""Voice recording preprocessing pipeline for The Muser.

Takes raw vocal recordings, isolates vocals via Demucs, normalizes loudness,
removes silence, segments into training clips, and filters by quality.

Outputs to two directories:
  - training_data/processed/segments/   — 5-15s isolated vocal clips for RVC training
  - training_data/processed/acestep/    — full recordings with sidecar metadata for ACE-Step LoRA

Usage::

    python scripts/preprocess_voice.py \\
        --input-dir training_data/raw/ \\
        --voice-name noah \\
        --target-lufs -18 \\
        --min-segment 5 \\
        --max-segment 15
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("muser.preprocess")


def isolate_vocals(input_path: str, output_dir: str, two_stems: bool = True) -> str:
    """Isolate vocals from a recording using Demucs.

    Returns path to the isolated vocal WAV.
    """
    from src.voice.demucs_wrapper import separate_stems

    result = separate_stems(
        input_audio=input_path,
        output_dir=output_dir,
        two_stems=two_stems,
    )
    vocals_path = result.get("vocals", "")
    if not vocals_path or not Path(vocals_path).exists():
        raise RuntimeError(f"Demucs did not produce vocals for {input_path}")
    return vocals_path


def normalize_loudness(audio: np.ndarray, sr: int, target_lufs: float = -18.0) -> np.ndarray:
    """Normalize audio to target LUFS using simple RMS-based approximation."""
    if len(audio) == 0:
        return audio

    # Calculate current RMS
    rms = np.sqrt(np.mean(audio**2))
    if rms < 1e-10:
        return audio

    # Approximate LUFS from RMS (simplified: LUFS ≈ 20*log10(RMS) - 0.691)
    current_lufs = 20.0 * np.log10(rms + 1e-10) - 0.691
    gain_db = target_lufs - current_lufs
    gain_linear = 10.0 ** (gain_db / 20.0)

    normalized = audio * gain_linear
    # Prevent clipping
    peak = np.max(np.abs(normalized))
    if peak > 0.99:
        normalized = normalized * (0.99 / peak)

    return normalized


def remove_silence(
    audio: np.ndarray,
    sr: int,
    threshold_db: float = -40.0,
    min_silence_ms: int = 300,
) -> np.ndarray:
    """Remove long silent passages from audio.

    Keeps short silences (< min_silence_ms) for natural phrasing.
    """
    frame_length = int(sr * 0.025)  # 25ms frames
    hop_length = int(sr * 0.010)  # 10ms hop
    min_silence_frames = int(min_silence_ms / 10)

    # Calculate frame energies
    n_frames = (len(audio) - frame_length) // hop_length + 1
    if n_frames <= 0:
        return audio

    energies = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_length
        frame = audio[start : start + frame_length]
        rms = np.sqrt(np.mean(frame**2) + 1e-10)
        energies[i] = 20.0 * np.log10(rms + 1e-10)

    # Find non-silent regions
    is_active = energies > threshold_db

    # Keep short silences
    silence_count = 0
    for i in range(len(is_active)):
        if not is_active[i]:
            silence_count += 1
        else:
            if silence_count > 0 and silence_count < min_silence_frames:
                # Short silence — keep it
                is_active[i - silence_count : i] = True
            silence_count = 0

    # Build output from active regions
    chunks = []
    in_active = False
    start_frame = 0

    for i in range(len(is_active)):
        if is_active[i] and not in_active:
            start_frame = i
            in_active = True
        elif not is_active[i] and in_active:
            # Add a small buffer on each side
            buf = min(5, start_frame)  # 50ms buffer
            start_sample = max(0, (start_frame - buf) * hop_length)
            end_sample = min(len(audio), (i + buf) * hop_length)
            chunks.append(audio[start_sample:end_sample])
            in_active = False

    if in_active:
        start_sample = max(0, (start_frame - 5) * hop_length)
        chunks.append(audio[start_sample:])

    if not chunks:
        return audio

    # Join with short crossfade
    result = chunks[0]
    crossfade_len = min(int(sr * 0.02), 512)  # 20ms crossfade
    for chunk in chunks[1:]:
        if len(result) >= crossfade_len and len(chunk) >= crossfade_len:
            fade_out = np.linspace(1, 0, crossfade_len)
            fade_in = np.linspace(0, 1, crossfade_len)
            result[-crossfade_len:] *= fade_out
            chunk[:crossfade_len] *= fade_in
            result[-crossfade_len:] += chunk[:crossfade_len]
            result = np.concatenate([result, chunk[crossfade_len:]])
        else:
            result = np.concatenate([result, chunk])

    return result


def segment_audio(
    audio: np.ndarray,
    sr: int,
    min_segment_s: float = 5.0,
    max_segment_s: float = 15.0,
    silence_threshold_db: float = -35.0,
) -> list[np.ndarray]:
    """Split audio into segments of min_segment_s to max_segment_s duration.

    Tries to split at silence boundaries for natural phrasing.
    """
    min_samples = int(min_segment_s * sr)
    max_samples = int(max_segment_s * sr)

    if len(audio) <= max_samples:
        if len(audio) >= min_samples:
            return [audio]
        return []

    segments = []
    pos = 0

    while pos < len(audio):
        remaining = len(audio) - pos
        if remaining < min_samples:
            break

        # Try to find a silence point between min and max
        end = min(pos + max_samples, len(audio))
        best_split = end

        if end < len(audio):
            # Search backward from max for a quiet spot
            search_start = pos + min_samples
            search_end = end
            frame_len = int(sr * 0.05)

            min_energy = float("inf")
            for check in range(search_end, search_start, -int(sr * 0.1)):
                frame = audio[max(0, check - frame_len) : check]
                if len(frame) == 0:
                    continue
                energy = 20.0 * np.log10(np.sqrt(np.mean(frame**2)) + 1e-10)
                if energy < min_energy:
                    min_energy = energy
                    best_split = check
                if energy < silence_threshold_db:
                    break

        segment = audio[pos:best_split]
        if len(segment) >= min_samples:
            segments.append(segment)
        pos = best_split

    return segments


def get_rms_db(audio: np.ndarray) -> float:
    """Calculate RMS in dB."""
    rms = np.sqrt(np.mean(audio**2))
    return 20.0 * np.log10(rms + 1e-10)


def main():
    parser = argparse.ArgumentParser(description="Preprocess voice recordings for training")
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing raw vocal recordings (WAV/FLAC/MP3)",
    )
    parser.add_argument(
        "--voice-name",
        default="noah",
        help="Voice name for output organization (default: noah)",
    )
    parser.add_argument(
        "--target-lufs",
        type=float,
        default=-18.0,
        help="Target loudness in LUFS (default: -18)",
    )
    parser.add_argument(
        "--min-segment",
        type=float,
        default=5.0,
        help="Minimum segment length in seconds (default: 5)",
    )
    parser.add_argument(
        "--max-segment",
        type=float,
        default=15.0,
        help="Maximum segment length in seconds (default: 15)",
    )
    parser.add_argument(
        "--min-rms-db",
        type=float,
        default=-35.0,
        help="Discard segments with RMS below this (default: -35 dB)",
    )
    parser.add_argument(
        "--skip-demucs",
        action="store_true",
        help="Skip Demucs separation (input is already isolated vocals)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=48000,
        help="Output sample rate (default: 48000)",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        logger.error("Input directory not found: %s", input_dir)
        sys.exit(1)

    # Output directories
    segments_dir = PROJECT_ROOT / "training_data" / "processed" / "segments"
    acestep_dir = PROJECT_ROOT / "training_data" / "processed" / "acestep"
    demucs_tmp = PROJECT_ROOT / "training_data" / "processed" / "demucs_tmp"

    segments_dir.mkdir(parents=True, exist_ok=True)
    acestep_dir.mkdir(parents=True, exist_ok=True)
    demucs_tmp.mkdir(parents=True, exist_ok=True)

    # Find audio files
    audio_exts = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}
    audio_files = sorted(f for f in input_dir.rglob("*") if f.suffix.lower() in audio_exts)

    if not audio_files:
        logger.error("No audio files found in %s", input_dir)
        sys.exit(1)

    logger.info("Found %d audio file(s) in %s", len(audio_files), input_dir)

    total_segments = 0
    total_discarded = 0
    manifest = []

    for i, audio_file in enumerate(audio_files, 1):
        logger.info("[%d/%d] Processing: %s", i, len(audio_files), audio_file.name)

        try:
            # Step 1: Isolate vocals (unless skipped)
            if args.skip_demucs:
                vocals_path = str(audio_file)
            else:
                logger.info("  Isolating vocals with Demucs...")
                vocals_path = isolate_vocals(str(audio_file), str(demucs_tmp), two_stems=True)

            # Step 2: Load audio
            import librosa

            audio, sr = librosa.load(vocals_path, sr=args.sample_rate, mono=True)

            if len(audio) == 0:
                logger.warning("  Empty audio, skipping")
                continue

            # Step 3: Normalize loudness
            audio = normalize_loudness(audio, sr, target_lufs=args.target_lufs)

            # Step 4: Remove silence
            audio_cleaned = remove_silence(audio, sr)
            removed_pct = (1 - len(audio_cleaned) / len(audio)) * 100
            logger.info(
                "  Silence removed: %.1f%% (%.1fs -> %.1fs)",
                removed_pct,
                len(audio) / sr,
                len(audio_cleaned) / sr,
            )

            # Step 5: Save full recording for ACE-Step LoRA
            stem = audio_file.stem
            full_path = acestep_dir / f"{stem}.wav"
            sf.write(str(full_path), audio_cleaned, sr)

            # Create sidecar files for ACE-Step LoRA training
            prompt_path = acestep_dir / f"{stem}_prompt.txt"
            lyrics_path = acestep_dir / f"{stem}_lyrics.txt"
            if not prompt_path.exists():
                prompt_path.write_text(
                    f"A vocal performance by {args.voice_name}, natural singing voice, "
                    f"clear articulation, expressive dynamics"
                )
            if not lyrics_path.exists():
                lyrics_path.write_text("[lyrics to be transcribed]")

            # Step 6: Segment for RVC training
            segments = segment_audio(
                audio_cleaned,
                sr,
                min_segment_s=args.min_segment,
                max_segment_s=args.max_segment,
            )

            # Step 7: Quality filter
            kept = 0
            for j, seg in enumerate(segments):
                rms_db = get_rms_db(seg)
                if rms_db < args.min_rms_db:
                    total_discarded += 1
                    continue

                seg_name = f"{args.voice_name}_{stem}_{j:04d}.wav"
                seg_path = segments_dir / seg_name
                sf.write(str(seg_path), seg, sr)
                kept += 1
                total_segments += 1

            logger.info(
                "  Segments: %d kept, %d discarded (RMS < %.0f dB)",
                kept,
                len(segments) - kept,
                args.min_rms_db,
            )

            manifest.append(
                {
                    "source": str(audio_file),
                    "full_recording": str(full_path),
                    "segments_kept": kept,
                    "segments_discarded": len(segments) - kept,
                    "duration_s": round(len(audio_cleaned) / sr, 1),
                }
            )

        except Exception as exc:
            logger.error("  Failed: %s", exc)
            manifest.append(
                {
                    "source": str(audio_file),
                    "status": "error",
                    "error": str(exc),
                }
            )

    # Write manifest
    manifest_path = PROJECT_ROOT / "training_data" / "processed" / "preprocess_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(
            {
                "voice_name": args.voice_name,
                "total_files": len(audio_files),
                "total_segments": total_segments,
                "total_discarded": total_discarded,
                "target_lufs": args.target_lufs,
                "sample_rate": args.sample_rate,
                "files": manifest,
            },
            f,
            indent=2,
        )

    logger.info("=" * 60)
    logger.info("Preprocessing complete!")
    logger.info("  Segments: %d (discarded %d)", total_segments, total_discarded)
    logger.info("  RVC training data: %s", segments_dir)
    logger.info("  ACE-Step LoRA data: %s", acestep_dir)
    logger.info("  Manifest: %s", manifest_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
