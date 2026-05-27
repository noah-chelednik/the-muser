#!/usr/bin/env python3
"""Layered 3-stage voice feminization pipeline for The Muser.

Three-stage architecture:
  Stage 1 — External formant pre-shift (before RVC):
      Uses parselmouth (Praat Python bindings) to apply a gentle formant ratio
      shift, moving formant frequencies upward to seed femininity cues before
      RVC conversion.

  Stage 2 — RVC conversion with extended parameters:
      Passes pre-shifted audio through RVC with formant shifting enabled.
      Full parameter control: quefrency, timbre, transpose, index_rate,
      filter_radius, rms_mix_rate, protect, f0_method.

  Stage 3 — Post-processing formant-aware EQ:
      Boosts 2.5-4kHz presence region (female vocal presence), attenuates
      800-1200Hz (male chest resonance), optional shaped noise injection
      in 4-8kHz for breathy archetypes. Applied via ffmpeg filter chain.

Modes:
  mode-a (inference-time): Apply the 3-stage pipeline to a single audio file
      using an existing RVC model. Fast, iterative, adjustable.

  mode-b (dedicated model): Create a synthetic female dataset from male
      recordings using the 3-stage pipeline, then train a new RVC model on it.

Usage::

    # Mode A: 3-stage feminization at inference time
    python scripts/feminize_voice.py mode-a \\
        --source-model voices/noah.pth \\
        --input-audio test.wav \\
        --output voices/noah-fem-test.wav \\
        --preset powerful_mezzo

    # Mode A: Custom parameters
    python scripts/feminize_voice.py mode-a \\
        --source-model voices/noah.pth \\
        --input-audio test.wav \\
        --output voices/noah-fem-test.wav \\
        --transpose 8 --pre-formant-ratio 1.08 --add-breathiness

    # Mode B: Create synthetic dataset + train dedicated female model
    python scripts/feminize_voice.py mode-b \\
        --source-model voices/noah.pth \\
        --voice-name noah-fem \\
        --preset soft_feminine \\
        --epochs 200
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("muser.feminize")


# ---------------------------------------------------------------------------
# Feminization presets
# ---------------------------------------------------------------------------
FEMINIZATION_PRESETS = {
    "powerful_mezzo": {
        "pre_formant_ratio": 1.07,
        "transpose": 4,
        "formant_timbre": 1.20,
        "f0_method": "rmvpe",
        "presence_boost_db": 1.5,
        "chest_cut_db": 1.0,
        "add_breathiness": False,
    },
    "soft_feminine": {
        "pre_formant_ratio": 1.08,
        "transpose": 8,
        "formant_timbre": 1.15,
        "f0_method": "rmvpe",
        "presence_boost_db": 2.0,
        "chest_cut_db": 1.5,
        "add_breathiness": True,
    },
    "androgynous": {
        "pre_formant_ratio": 1.04,
        "transpose": 3,
        "formant_timbre": 1.10,
        "f0_method": "rmvpe",
        "presence_boost_db": 1.0,
        "chest_cut_db": 0.5,
        "add_breathiness": False,
    },
    "natural_male": {
        "pre_formant_ratio": 1.0,
        "transpose": 0,
        "formant_timbre": 1.0,
        "f0_method": "rmvpe",
        "presence_boost_db": 0.0,
        "chest_cut_db": 0.0,
        "add_breathiness": False,
    },
    "deep_male": {
        "pre_formant_ratio": 0.97,
        "transpose": -3,
        "formant_timbre": 0.95,
        "f0_method": "rmvpe",
        "presence_boost_db": 0.0,
        "chest_cut_db": 0.0,
        "add_breathiness": False,
    },
}


# ---------------------------------------------------------------------------
# Stage 1: External formant pre-shift via parselmouth (Praat)
# ---------------------------------------------------------------------------


def _stage1_formant_preshift(
    input_audio: str,
    output_path: str,
    formant_ratio: float = 1.07,
) -> str:
    """Apply gentle formant frequency shift via Praat.

    Supports two backends controlled by MUSER_FEMINIZE_BACKEND env var:
      - "praat_cli" (default): subprocess call to Praat binary (GPL-safe)
      - "parselmouth": direct Python bindings (GPL v3 — user must opt in)

    Args:
        input_audio: Path to input WAV file.
        output_path: Path to write pre-shifted WAV.
        formant_ratio: Ratio to multiply formant frequencies by.

    Returns:
        Path to the pre-shifted audio file.
    """
    if abs(formant_ratio - 1.0) < 0.005:
        logger.info("Stage 1: formant_ratio ~1.0, copying input unchanged")
        shutil.copy2(input_audio, output_path)
        return output_path

    backend = os.environ.get("MUSER_FEMINIZE_BACKEND", "praat_cli")

    if backend == "parselmouth":
        logger.warning(
            "Using parselmouth (GPL v3) for formant shifting. "
            "This may affect the license of your output."
        )
        return _formant_shift_parselmouth(input_audio, output_path, formant_ratio)

    return _formant_shift_praat_cli(input_audio, output_path, formant_ratio)


def _formant_shift_praat_cli(
    input_audio: str,
    output_path: str,
    formant_ratio: float,
) -> str:
    """Formant shift via Praat CLI subprocess (GPL-safe)."""
    praat_bin = shutil.which("praat") or shutil.which("praat-barren")
    if praat_bin is None:
        logger.warning(
            "Praat CLI not found. Install Praat or set "
            "MUSER_FEMINIZE_BACKEND=parselmouth. Skipping formant shift."
        )
        shutil.copy2(input_audio, output_path)
        return output_path

    script = (
        f'Read from file: "{input_audio}"\n'
        f"Change gender: 75, 600, {formant_ratio}, 0, 1, 1\n"
        f'Save as WAV file: "{output_path}"\n'
    )

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".praat", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        logger.info("Stage 1: Praat CLI formant shift (ratio=%.3f)", formant_ratio)
        subprocess.run(
            [praat_bin, "--run", script_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        logger.info("Stage 1 complete: %s", output_path)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("Praat CLI failed: %s. Copying input unchanged.", exc)
        shutil.copy2(input_audio, output_path)
    finally:
        os.unlink(script_path)

    return output_path


def _formant_shift_parselmouth(
    input_audio: str,
    output_path: str,
    formant_ratio: float,
) -> str:
    """Formant shift via parselmouth Python bindings (GPL v3)."""
    import parselmouth
    from parselmouth.praat import call

    logger.info(
        "Stage 1: Formant pre-shift via parselmouth (ratio=%.3f) %s -> %s",
        formant_ratio,
        input_audio,
        output_path,
    )

    sound = parselmouth.Sound(input_audio)
    shifted = call(
        sound,
        "Change gender",
        75.0,
        600.0,
        formant_ratio,
        0.0,
        1.0,
        1.0,
    )

    shifted.save(output_path, parselmouth.SoundFileFormat.WAV)
    logger.info("Stage 1 complete: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Stage 2: RVC conversion with extended formant parameters
# ---------------------------------------------------------------------------


def _stage2_rvc_conversion(
    input_audio: str,
    output_path: str,
    rvc_model_path: str,
    rvc_index_path: str | None = None,
    transpose: int = 6,
    formant_quefrency: float = 8.0,
    formant_timbre: float = 1.15,
    index_rate: float = 0.5,
    filter_radius: int = 4,
    rms_mix_rate: float = 0.1,
    protect: float = 0.25,
    f0_method: str = "rmvpe",
) -> str:
    """Pass pre-shifted audio through RVC with formant shifting enabled.

    Uses the Applio/RVC VoiceConverter with extended formant parameters for
    precise feminization control.

    Args:
        input_audio: Path to pre-shifted WAV from Stage 1.
        output_path: Path to write converted WAV.
        rvc_model_path: Path to the RVC .pth model.
        rvc_index_path: Path to .index file (optional).
        transpose: Semitone pitch shift (positive=up).
        formant_quefrency: Quefrency threshold for formant envelope (higher=smoother).
        formant_timbre: Timbre scaling factor (>1=brighter/feminine).
        index_rate: Feature retrieval blend ratio (0=no index, 1=full index).
        filter_radius: Median filter radius for pitch smoothing.
        rms_mix_rate: RMS envelope mixing ratio (0=source, 1=target).
        protect: Consonant protection (0=none, 0.5=full).
        f0_method: Pitch extraction method (rmvpe, crepe, pm, harvest).

    Returns:
        Path to the RVC-converted audio file.
    """

    input_path = Path(input_audio)
    if not input_path.exists():
        raise FileNotFoundError(f"Stage 2 input not found: {input_audio}")

    model = Path(rvc_model_path)
    if not model.exists():
        raise FileNotFoundError(f"RVC model not found: {rvc_model_path}")

    logger.info(
        "Stage 2: RVC conversion (transpose=%+d, timbre=%.2f, quefrency=%.1f, f0=%s) %s -> %s",
        transpose,
        formant_timbre,
        formant_quefrency,
        f0_method,
        input_audio,
        output_path,
    )

    # Try Python API first
    try:
        return _rvc_convert_python(
            input_audio=input_audio,
            output_path=output_path,
            model_path=rvc_model_path,
            index_path=rvc_index_path or "",
            transpose=transpose,
            formant_quefrency=formant_quefrency,
            formant_timbre=formant_timbre,
            index_rate=index_rate,
            filter_radius=filter_radius,
            rms_mix_rate=rms_mix_rate,
            protect=protect,
            f0_method=f0_method,
        )
    except ImportError:
        logger.info("Applio Python API not available, falling back to CLI")

    # Fall back to CLI
    return _rvc_convert_cli(
        input_audio=input_audio,
        output_path=output_path,
        model_path=rvc_model_path,
        index_path=rvc_index_path or "",
        transpose=transpose,
        formant_quefrency=formant_quefrency,
        formant_timbre=formant_timbre,
        index_rate=index_rate,
        filter_radius=filter_radius,
        rms_mix_rate=rms_mix_rate,
        protect=protect,
        f0_method=f0_method,
    )


def _rvc_convert_python(
    input_audio: str,
    output_path: str,
    model_path: str,
    index_path: str,
    transpose: int,
    formant_quefrency: float,
    formant_timbre: float,
    index_rate: float,
    filter_radius: int,
    rms_mix_rate: float,
    protect: float,
    f0_method: str,
) -> str:
    """RVC conversion via Applio Python API with extended formant params."""
    from src.orchestrator.config import APPLIO_DIR

    applio_path = str(APPLIO_DIR)
    if applio_path not in sys.path:
        sys.path.insert(0, applio_path)

    from rvc.infer.infer import VoiceConverter  # type: ignore

    converter = VoiceConverter()
    converter.convert_audio(
        audio_input_path=input_audio,
        audio_output_path=output_path,
        model_path=model_path,
        index_path=index_path,
        pitch=transpose,
        f0_method=f0_method,
        index_rate=index_rate,
        volume_envelope=rms_mix_rate,
        protect=protect,
        hop_length=128,
        split_audio=True,
        f0_autotune=True,
        f0_autotune_strength=0.8,
        filter_radius=filter_radius,
        clean_audio=False,
        export_format="WAV",
        embedder_model="contentvec",
        formant_shifting=True,
        formant_qfrency=formant_quefrency,
        formant_timbre=formant_timbre,
    )
    logger.info("Stage 2 complete (Python API): %s", output_path)
    return output_path


def _rvc_convert_cli(
    input_audio: str,
    output_path: str,
    model_path: str,
    index_path: str,
    transpose: int,
    formant_quefrency: float,
    formant_timbre: float,
    index_rate: float,
    filter_radius: int,
    rms_mix_rate: float,
    protect: float,
    f0_method: str,
) -> str:
    """RVC conversion via Applio CLI with extended formant params."""
    from src.orchestrator.config import APPLIO_DIR

    cmd = [
        "python",
        str(APPLIO_DIR / "core.py"),
        "infer",
        "--input_path",
        input_audio,
        "--output_path",
        output_path,
        "--pth_path",
        model_path,
        "--index_path",
        index_path,
        "--pitch",
        str(transpose),
        "--f0_method",
        f0_method,
        "--index_rate",
        str(index_rate),
        "--filter_radius",
        str(filter_radius),
        "--volume_envelope",
        str(rms_mix_rate),
        "--protect",
        str(protect),
        "--export_format",
        "WAV",
        "--split_audio",
        "true",
        "--f0_autotune",
        "true",
        "--f0_autotune_strength",
        "0.8",
        "--formant_shifting",
        "true",
        "--formant_qfrency",
        str(formant_quefrency),
        "--formant_timbre",
        str(formant_timbre),
    ]

    logger.info("Running RVC CLI: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(APPLIO_DIR),
    )

    if result.returncode != 0:
        raise RuntimeError(f"RVC CLI failed (exit {result.returncode}): {result.stderr}")

    logger.info("Stage 2 complete (CLI): %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Stage 3: Post-processing formant-aware EQ via ffmpeg
# ---------------------------------------------------------------------------


def _stage3_postprocess_eq(
    input_audio: str,
    output_path: str,
    presence_boost_db: float = 1.5,
    chest_cut_db: float = 1.0,
    add_breathiness: bool = False,
) -> str:
    """Apply formant-aware EQ post-processing via ffmpeg filter chain.

    - Boosts 2.5-4kHz presence region (female vocal presence / singer's formant)
    - Attenuates 800-1200Hz (male chest resonance)
    - Optionally injects shaped noise in 4-8kHz for breathy archetypes

    Args:
        input_audio: Path to RVC-converted WAV from Stage 2.
        output_path: Path to write final processed WAV.
        presence_boost_db: dB boost for 2.5-4kHz band (0=off).
        chest_cut_db: dB cut for 800-1200Hz band (0=off).
        add_breathiness: If True, add shaped noise in 4-8kHz for airy quality.

    Returns:
        Path to the final processed audio file.
    """
    # If all EQ parameters are essentially zero, just copy
    if abs(presence_boost_db) < 0.1 and abs(chest_cut_db) < 0.1 and not add_breathiness:
        logger.info("Stage 3: No EQ adjustments needed, copying input")
        shutil.copy2(input_audio, output_path)
        return output_path

    logger.info(
        "Stage 3: Post-processing EQ (presence=+%.1fdB, chest=-%.1fdB, breathiness=%s) %s -> %s",
        presence_boost_db,
        chest_cut_db,
        add_breathiness,
        input_audio,
        output_path,
    )

    # Build ffmpeg filter chain
    filters = []

    # Presence boost: peak EQ centered at 3.2kHz, Q=1.2, spanning ~2.5-4kHz
    if abs(presence_boost_db) >= 0.1:
        filters.append(f"equalizer=f=3200:t=q:w=1.2:g={presence_boost_db}")

    # Chest resonance cut: peak EQ centered at 1000Hz, Q=0.8, spanning ~800-1200Hz
    if abs(chest_cut_db) >= 0.1:
        filters.append(f"equalizer=f=1000:t=q:w=0.8:g={-chest_cut_db}")

    # Breathiness: mix in band-limited noise for airy quality
    if add_breathiness:
        # Generate pink-ish noise, bandpass 4-8kHz, mix at -30dB below signal.
        # This uses ffmpeg's anoisesrc + bandpass + amix approach.
        # We build it as a complex filter graph.
        result = _stage3_with_breathiness(
            input_audio,
            output_path,
            filters,
        )
        return result

    # Simple EQ-only path (no breathiness)
    filter_chain = ",".join(filters)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_audio,
        "-af",
        filter_chain,
        "-c:a",
        "pcm_s16le",
        output_path,
    ]

    logger.info("Running ffmpeg EQ: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg EQ failed (exit {result.returncode}): {result.stderr}")

    logger.info("Stage 3 complete: %s", output_path)
    return output_path


def _stage3_with_breathiness(
    input_audio: str,
    output_path: str,
    eq_filters: list[str],
) -> str:
    """Stage 3 variant that injects shaped noise for breathiness.

    Uses ffmpeg complex filter graph to:
    1. Apply EQ filters to the input
    2. Generate pink noise, bandpass filter to 4-8kHz
    3. Mix noise at -30dB below the signal level
    """
    # Build the EQ portion for the main audio stream
    eq_chain = ",".join(eq_filters) if eq_filters else "anull"

    # Complex filtergraph:
    #   [0:a] -> EQ -> [main]
    #   anoisesrc -> bandpass 4-8kHz -> volume -30dB -> [breath]
    #   [main][breath] -> amix -> output
    filtergraph = (
        f"[0:a]{eq_chain}[main];"
        f"anoisesrc=color=pink:duration=9999:sample_rate=44100,"
        f"bandpass=f=6000:width_type=h:w=4000,"
        f"volume=-30dB[breath];"
        f"[main][breath]amix=inputs=2:duration=first:dropout_transition=0[out]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_audio,
        "-filter_complex",
        filtergraph,
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        output_path,
    ]

    logger.info("Running ffmpeg EQ + breathiness: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg breathiness filter failed (exit {result.returncode}): {result.stderr}"
        )

    logger.info("Stage 3 complete (with breathiness): %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Main pipeline: feminize_audio()
# ---------------------------------------------------------------------------


def feminize_audio(
    input_audio: str,
    output_path: str,
    rvc_model_path: str,
    rvc_index_path: str | None = None,
    # Stage 1
    pre_formant_ratio: float = 1.07,
    # Stage 2
    transpose: int = 6,
    formant_quefrency: float = 8.0,
    formant_timbre: float = 1.15,
    index_rate: float = 0.5,
    filter_radius: int = 4,
    rms_mix_rate: float = 0.1,
    protect: float = 0.25,
    f0_method: str = "rmvpe",
    # Stage 3
    presence_boost_db: float = 1.5,
    chest_cut_db: float = 1.0,
    add_breathiness: bool = False,
) -> str:
    """Run the full 3-stage feminization pipeline.

    Stage 1: Formant pre-shift via parselmouth (Praat) to seed femininity cues.
    Stage 2: RVC voice conversion with formant shifting and extended parameters.
    Stage 3: Post-processing formant-aware EQ via ffmpeg.

    Args:
        input_audio: Path to input WAV file.
        output_path: Path to write final feminized WAV.
        rvc_model_path: Path to the RVC .pth model.
        rvc_index_path: Path to .index file (optional).
        pre_formant_ratio: Formant frequency ratio for Stage 1 (>1 = feminine).
        transpose: Semitone pitch shift for Stage 2.
        formant_quefrency: Quefrency threshold for RVC formant envelope.
        formant_timbre: Timbre scaling for RVC formant shift.
        index_rate: Feature retrieval blend ratio.
        filter_radius: Median filter radius for pitch smoothing.
        rms_mix_rate: RMS envelope mixing ratio.
        protect: Consonant protection factor.
        f0_method: Pitch extraction method.
        presence_boost_db: dB boost for 2.5-4kHz presence region.
        chest_cut_db: dB cut for 800-1200Hz chest resonance.
        add_breathiness: Inject shaped noise in 4-8kHz for airy quality.

    Returns:
        Path to the final feminized audio file.
    """
    input_path = Path(input_audio)
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio not found: {input_audio}")

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("3-Stage Feminization Pipeline")
    logger.info("  Input:  %s", input_audio)
    logger.info("  Output: %s", output_path)
    logger.info("  Stage 1: formant_ratio=%.3f", pre_formant_ratio)
    logger.info(
        "  Stage 2: transpose=%+d, timbre=%.2f, quefrency=%.1f, f0=%s",
        transpose,
        formant_timbre,
        formant_quefrency,
        f0_method,
    )
    logger.info(
        "  Stage 3: presence=+%.1fdB, chest=-%.1fdB, breathiness=%s",
        presence_boost_db,
        chest_cut_db,
        add_breathiness,
    )
    logger.info("=" * 60)

    # Create temp directory for intermediate files
    with tempfile.TemporaryDirectory(prefix="muser_fem_") as tmpdir:
        tmp = Path(tmpdir)
        stem = input_path.stem

        # --- Stage 1: Formant pre-shift ---
        stage1_out = str(tmp / f"{stem}_s1_preshift.wav")
        _stage1_formant_preshift(
            input_audio=input_audio,
            output_path=stage1_out,
            formant_ratio=pre_formant_ratio,
        )

        # --- Stage 2: RVC conversion ---
        stage2_out = str(tmp / f"{stem}_s2_rvc.wav")
        _stage2_rvc_conversion(
            input_audio=stage1_out,
            output_path=stage2_out,
            rvc_model_path=rvc_model_path,
            rvc_index_path=rvc_index_path,
            transpose=transpose,
            formant_quefrency=formant_quefrency,
            formant_timbre=formant_timbre,
            index_rate=index_rate,
            filter_radius=filter_radius,
            rms_mix_rate=rms_mix_rate,
            protect=protect,
            f0_method=f0_method,
        )

        # --- Stage 3: Post-processing EQ ---
        _stage3_postprocess_eq(
            input_audio=stage2_out,
            output_path=output_path,
            presence_boost_db=presence_boost_db,
            chest_cut_db=chest_cut_db,
            add_breathiness=add_breathiness,
        )

    logger.info("Feminization pipeline complete: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Mode B: Dedicated female model training (uses feminize_audio)
# ---------------------------------------------------------------------------


def mode_b_create_dataset(
    source_model: str,
    index_path: str | None,
    segments_dir: str,
    output_dir: str,
    preset_name: str | None = None,
    **fem_kwargs,
) -> int:
    """Create synthetic female dataset by applying the 3-stage pipeline
    to all training segments.

    Args:
        source_model: Path to source RVC .pth model.
        index_path: Path to .index file (optional).
        segments_dir: Directory containing source WAV segments.
        output_dir: Directory to write feminized segments.
        preset_name: Optional preset name to use as base parameters.
        **fem_kwargs: Override parameters for feminize_audio().

    Returns:
        Number of segments processed.
    """
    seg_dir = Path(segments_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wav_files = sorted(seg_dir.glob("*.wav"))
    if not wav_files:
        raise FileNotFoundError(f"No WAV files found in {segments_dir}")

    # Resolve parameters: preset as base, then overrides
    params = {}
    if preset_name and preset_name in FEMINIZATION_PRESETS:
        params.update(FEMINIZATION_PRESETS[preset_name])
    params.update(fem_kwargs)

    logger.info(
        "Creating synthetic female dataset: %d segments, preset=%s",
        len(wav_files),
        preset_name or "(custom)",
    )

    processed = 0
    for i, wav_path in enumerate(wav_files, 1):
        out_path = out_dir / wav_path.name
        if out_path.exists():
            logger.debug("Skipping (exists): %s", out_path.name)
            processed += 1
            continue

        logger.info("[%d/%d] Feminizing: %s", i, len(wav_files), wav_path.name)
        try:
            feminize_audio(
                input_audio=str(wav_path),
                output_path=str(out_path),
                rvc_model_path=source_model,
                rvc_index_path=index_path,
                **params,
            )
            processed += 1
        except Exception as exc:
            logger.error("Failed to feminize %s: %s", wav_path.name, exc)

    logger.info(
        "Synthetic dataset: %d/%d segments processed",
        processed,
        len(wav_files),
    )
    return processed


def mode_b_train(
    voice_name: str,
    epochs: int = 200,
    batch_size: int = 8,
) -> None:
    """Train a dedicated female RVC model on the synthetic dataset."""
    train_script = PROJECT_ROOT / "scripts" / "train_rvc.sh"

    logger.info(
        "Training female model '%s': %d epochs, batch_size=%d",
        voice_name,
        epochs,
        batch_size,
    )

    result = subprocess.run(
        ["bash", str(train_script), voice_name, str(epochs), str(batch_size)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        raise RuntimeError(f"Training failed (exit {result.returncode}): {result.stderr}")

    logger.info("Female model training complete: %s", voice_name)


def register_feminized_voice(
    voice_name: str,
    source_voice: str,
    preset_name: str | None,
    mode: str,
) -> None:
    """Register the feminized voice in the voice registry."""
    from src.voice.voice_registry import register_voice

    voices_dir = PROJECT_ROOT / "voices"
    model_path = voices_dir / f"{voice_name}.pth"
    index_path = voices_dir / f"{voice_name}.index"

    register_voice(
        voice_id=voice_name,
        name=voice_name,
        voice_type="rvc",
        model_path=str(model_path) if model_path.exists() else "",
        index_path=str(index_path) if index_path.exists() else "",
        metadata={
            "feminization_mode": mode,
            "feminization_preset": preset_name,
            "source_voice": source_voice,
            "pipeline": "3-stage (formant-preshift + RVC + EQ)",
            "is_feminized": True,
        },
    )
    logger.info("Registered feminized voice: %s", voice_name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_common_feminization_args(parser: argparse.ArgumentParser) -> None:
    """Add feminization parameter arguments common to mode-a and mode-b."""
    parser.add_argument(
        "--preset",
        choices=list(FEMINIZATION_PRESETS.keys()),
        default=None,
        help="Feminization preset (overridden by explicit params)",
    )

    # Stage 1
    stage1 = parser.add_argument_group("Stage 1: Formant pre-shift")
    stage1.add_argument(
        "--pre-formant-ratio",
        type=float,
        default=None,
        help="Formant frequency ratio (default: 1.07, >1=feminine)",
    )

    # Stage 2
    stage2 = parser.add_argument_group("Stage 2: RVC conversion")
    stage2.add_argument(
        "--transpose",
        type=int,
        default=None,
        help="Semitones up (default: 6, range: -12 to +12)",
    )
    stage2.add_argument(
        "--formant-quefrency",
        type=float,
        default=None,
        help="Quefrency threshold for formant envelope (default: 8.0)",
    )
    stage2.add_argument(
        "--formant-timbre",
        type=float,
        default=None,
        help="Timbre scaling factor (default: 1.15, >1=brighter)",
    )
    stage2.add_argument(
        "--index-rate",
        type=float,
        default=None,
        help="Feature retrieval blend ratio (default: 0.5)",
    )
    stage2.add_argument(
        "--filter-radius",
        type=int,
        default=None,
        help="Median filter radius for pitch (default: 4)",
    )
    stage2.add_argument(
        "--rms-mix-rate",
        type=float,
        default=None,
        help="RMS envelope mix ratio (default: 0.1)",
    )
    stage2.add_argument(
        "--protect",
        type=float,
        default=None,
        help="Consonant protection (default: 0.25)",
    )
    stage2.add_argument(
        "--f0-method",
        default=None,
        help="Pitch extraction method (default: rmvpe)",
    )

    # Stage 3
    stage3 = parser.add_argument_group("Stage 3: Post-processing EQ")
    stage3.add_argument(
        "--presence-boost-db",
        type=float,
        default=None,
        help="dB boost for 2.5-4kHz presence (default: 1.5)",
    )
    stage3.add_argument(
        "--chest-cut-db",
        type=float,
        default=None,
        help="dB cut for 800-1200Hz chest resonance (default: 1.0)",
    )
    stage3.add_argument(
        "--add-breathiness",
        action="store_true",
        default=None,
        help="Add shaped noise in 4-8kHz for airy quality",
    )


def _resolve_feminization_params(args: argparse.Namespace) -> dict:
    """Resolve feminization parameters from preset + explicit CLI overrides.

    Preset provides base values; any explicitly-set CLI argument overrides
    the preset value. Arguments not set by either remain absent (letting
    feminize_audio() use its defaults).
    """
    # Start with preset values if a preset was selected
    params = {}
    if args.preset and args.preset in FEMINIZATION_PRESETS:
        params.update(FEMINIZATION_PRESETS[args.preset])

    # Map CLI argument names to feminize_audio parameter names
    cli_mapping = {
        "pre_formant_ratio": "pre_formant_ratio",
        "transpose": "transpose",
        "formant_quefrency": "formant_quefrency",
        "formant_timbre": "formant_timbre",
        "index_rate": "index_rate",
        "filter_radius": "filter_radius",
        "rms_mix_rate": "rms_mix_rate",
        "protect": "protect",
        "f0_method": "f0_method",
        "presence_boost_db": "presence_boost_db",
        "chest_cut_db": "chest_cut_db",
        "add_breathiness": "add_breathiness",
    }

    for cli_name, param_name in cli_mapping.items():
        value = getattr(args, cli_name, None)
        if value is not None:
            params[param_name] = value

    return params


def main():
    parser = argparse.ArgumentParser(
        description="3-stage voice feminization pipeline for The Muser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Presets:\n"
            + "\n".join(
                f"  {name:20s} transpose={p['transpose']:+d}, "
                f"formant={p['pre_formant_ratio']:.2f}, "
                f"timbre={p['formant_timbre']:.2f}"
                for name, p in FEMINIZATION_PRESETS.items()
            )
        ),
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # Mode A: Inference-time 3-stage feminization
    mode_a = subparsers.add_parser(
        "mode-a",
        help="3-stage feminization at inference time",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_a.add_argument(
        "--source-model",
        required=True,
        help="Path to source RVC .pth model",
    )
    mode_a.add_argument(
        "--index-path",
        default=None,
        help="Path to .index file (optional)",
    )
    mode_a.add_argument(
        "--input-audio",
        required=True,
        help="Input audio to feminize",
    )
    mode_a.add_argument(
        "--output",
        required=True,
        help="Output audio path",
    )
    _add_common_feminization_args(mode_a)

    # Mode B: Dedicated female model training
    mode_b = subparsers.add_parser(
        "mode-b",
        help="Train a dedicated female voice model via 3-stage pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_b.add_argument(
        "--source-model",
        required=True,
        help="Path to source RVC .pth model",
    )
    mode_b.add_argument(
        "--index-path",
        default=None,
        help="Path to source .index file (optional)",
    )
    mode_b.add_argument(
        "--voice-name",
        default="noah-fem",
        help="Name for the female voice model",
    )
    mode_b.add_argument(
        "--epochs",
        type=int,
        default=200,
        help="Training epochs",
    )
    mode_b.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Training batch size",
    )
    mode_b.add_argument(
        "--segments-dir",
        default=None,
        help="Source segments directory (default: training_data/processed/segments/)",
    )
    mode_b.add_argument(
        "--skip-dataset",
        action="store_true",
        help="Skip dataset creation, go straight to training",
    )
    mode_b.add_argument(
        "--skip-training",
        action="store_true",
        help="Only create dataset, don't train",
    )
    _add_common_feminization_args(mode_b)

    args = parser.parse_args()

    if args.mode == "mode-a":
        fem_params = _resolve_feminization_params(args)

        result = feminize_audio(
            input_audio=args.input_audio,
            output_path=args.output,
            rvc_model_path=args.source_model,
            rvc_index_path=args.index_path,
            **fem_params,
        )
        print(f"Feminized audio: {result}")

    elif args.mode == "mode-b":
        fem_params = _resolve_feminization_params(args)

        segments_dir = args.segments_dir or str(
            PROJECT_ROOT / "training_data" / "processed" / "segments"
        )
        fem_dataset_dir = str(PROJECT_ROOT / "training_data" / "processed" / "segments_feminized")

        # Step 1: Create synthetic female dataset
        if not args.skip_dataset:
            logger.info("=== Step 1: Creating synthetic female dataset ===")
            count = mode_b_create_dataset(
                source_model=args.source_model,
                index_path=args.index_path,
                segments_dir=segments_dir,
                output_dir=fem_dataset_dir,
                preset_name=args.preset,
                **fem_params,
            )
            logger.info("Created %d feminized segments", count)

            # Swap the segments directory so train_rvc.sh picks up feminized data
            real_segments = PROJECT_ROOT / "training_data" / "processed" / "segments"
            backup = PROJECT_ROOT / "training_data" / "processed" / "segments_original"
            if not backup.exists():
                real_segments.rename(backup)
            # Symlink feminized data as the segments dir
            if real_segments.exists() or real_segments.is_symlink():
                real_segments.unlink()
            real_segments.symlink_to(Path(fem_dataset_dir).resolve())
            logger.info("Swapped segments dir to feminized data")

        if args.skip_training:
            logger.info(
                "Skipping training (--skip-training). Dataset ready at %s",
                fem_dataset_dir,
            )
            return

        # Step 2: Train dedicated female model
        try:
            logger.info("=== Step 2: Training female RVC model ===")
            mode_b_train(
                voice_name=args.voice_name,
                epochs=args.epochs,
                batch_size=args.batch_size,
            )
        finally:
            # Restore original segments directory
            real_segments = PROJECT_ROOT / "training_data" / "processed" / "segments"
            backup = PROJECT_ROOT / "training_data" / "processed" / "segments_original"
            if backup.exists():
                if real_segments.exists() or real_segments.is_symlink():
                    real_segments.unlink()
                backup.rename(real_segments)
                logger.info("Restored original segments directory")

        # Step 3: Register
        register_feminized_voice(
            voice_name=args.voice_name,
            source_voice=args.source_model,
            preset_name=args.preset,
            mode="dedicated_model",
        )

        logger.info("=== Feminization Complete ===")
        logger.info("Voice: %s", args.voice_name)
        logger.info("Use with: muser --voice %s", args.voice_name)


if __name__ == "__main__":
    main()
