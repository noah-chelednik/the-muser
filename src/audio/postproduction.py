"""Automated mixing and mastering chain.

Provides genre-aware post-production presets implemented as ffmpeg audio
filter chains.  Each preset targets a particular sonic aesthetic and
loudness standard while remaining fully configurable.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from src.orchestrator.config import FFMPEG_TIMEOUT, TARGET_LUFS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Genre presets
#
# Each preset is a dict with:
#   "filters" -- list of ffmpeg -af filter strings to apply in order
#   "target_lufs" -- final loudness target (LUFS)
#   "description" -- human-readable summary
# ---------------------------------------------------------------------------
GENRE_PRESETS: dict[str, dict] = {
    "default": {
        "filters": [],
        "target_lufs": TARGET_LUFS,
        "description": "Basic loudness normalization only.",
    },
    "classical": {
        "filters": [
            # Gentle dynamic compression to preserve wide dynamic range.
            "acompressor=threshold=-30dB:ratio=1.5:attack=50:release=500:knee=6",
            # Soft limiter to catch peaks without audible pumping.
            "alimiter=limit=0.95:attack=20:release=200:level=false",
        ],
        "target_lufs": -18.0,
        "description": "Gentle limiting, wide dynamic range (target -18 LUFS).",
    },
    "pop": {
        "filters": [
            # Medium compression for consistent vocal/instrument levels.
            "acompressor=threshold=-20dB:ratio=3:attack=10:release=200:knee=4",
            # Brick-wall limiter for competitive loudness.
            "alimiter=limit=0.98:attack=5:release=50:level=true",
        ],
        "target_lufs": -14.0,
        "description": "Compression + limiting + loudness norm (-14 LUFS).",
    },
    "rock": {
        "filters": [
            # Heavier compression for punch and sustain.
            "acompressor=threshold=-18dB:ratio=4:attack=5:release=150:knee=3",
            # Mild harmonic saturation via soft-clip (atan curve).
            # Uses the 'atanh' soft clipping mode of the limiter instead of
            # afir which requires an impulse response file.
            "acompressor=threshold=-8dB:ratio=8:attack=1:release=50:knee=2",
            # Hard limiter.
            "alimiter=limit=0.97:attack=3:release=30:level=true",
        ],
        "target_lufs": -14.0,
        "description": "Heavier compression + saturation hints.",
    },
    "electronic": {
        "filters": [
            # Aggressive multi-band-style compression via cascaded compressors.
            "acompressor=threshold=-15dB:ratio=5:attack=2:release=100:knee=2",
            # Bass boost via low-shelf EQ.
            "equalizer=f=80:t=q:w=1.0:g=4",
            # Aggressive brick-wall limiter.
            "alimiter=limit=0.99:attack=1:release=20:level=true",
        ],
        "target_lufs": -12.0,
        "description": "Aggressive limiting + bass boost.",
    },
}


def _require_ffmpeg() -> None:
    """Raise FileNotFoundError if ffmpeg is not on PATH."""
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError(
            "ffmpeg not found. Install ffmpeg and ensure it is on PATH."
        )


def apply_postproduction(
    wav_path: str,
    output_path: str,
    genre: str = "default",
) -> str:
    """Apply a genre-aware post-production chain to an audio file.

    The processing pipeline is:

    1. Apply the genre-specific ffmpeg filter chain (compression,
       limiting, EQ, etc.).
    2. Apply EBU R128 loudness normalization to the genre's target LUFS.

    If the genre preset has no filters (e.g. ``"default"``), only the
    final loudness normalization step is applied.

    Args:
        wav_path: Path to the input WAV file.
        output_path: Desired path for the processed output WAV file.
        genre: Genre preset key from :data:`GENRE_PRESETS`.  Falls back
            to ``"default"`` if the key is not recognized (with a warning).

    Returns:
        The absolute path to the processed WAV file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If processing exceeds FFMPEG_TIMEOUT.
    """
    wav = Path(wav_path)
    if not wav.is_file():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _require_ffmpeg()

    if genre not in GENRE_PRESETS:
        logger.warning(
            "Unknown genre preset '%s', falling back to 'default'. "
            "Available: %s",
            genre, ", ".join(GENRE_PRESETS.keys()),
        )
        genre = "default"

    preset = GENRE_PRESETS[genre]
    filters: list[str] = list(preset["filters"])
    target_lufs: float = preset["target_lufs"]

    logger.info(
        "Applying post-production: genre=%s, target=%s LUFS, filters=%d",
        genre, target_lufs, len(filters),
    )

    # If there are genre-specific filters, apply them first to a temp file,
    # then normalize.  If not, normalize directly.
    if filters:
        intermediate = out.with_name(out.stem + "_pp_intermediate.wav")
        _apply_filters(str(wav), str(intermediate), filters)
        source_for_norm = intermediate
    else:
        source_for_norm = wav
        intermediate = None

    # Final loudness normalization (two-pass).
    from src.audio.export import normalize_loudness

    try:
        result_path = normalize_loudness(
            str(source_for_norm), str(out), target_lufs=target_lufs
        )
    finally:
        # Clean up intermediate file.
        if intermediate is not None and intermediate.is_file():
            intermediate.unlink()
            logger.debug("Removed intermediate file: %s", intermediate)

    logger.info("Post-production complete: %s", result_path)
    return result_path


def _apply_filters(wav_path: str, output_path: str, filters: list[str]) -> str:
    """Apply a chain of ffmpeg audio filters to a WAV file.

    Args:
        wav_path: Input WAV path.
        output_path: Output WAV path.
        filters: List of ffmpeg ``-af`` filter strings.

    Returns:
        The output path.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If processing exceeds FFMPEG_TIMEOUT.
    """
    # Combine filters into a single filtergraph separated by commas.
    # Filters that may not be available (like afir without impulse) are
    # replaced with safe alternatives at the preset level.
    filter_chain = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", wav_path,
        "-af", filter_chain,
        output_path,
    ]

    logger.debug("Running ffmpeg filter chain: %s", filter_chain)

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            "ffmpeg filter chain failed (rc=%d): %s", exc.returncode, exc.stderr
        )
        raise
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg filter chain timed out after %d seconds", FFMPEG_TIMEOUT)
        raise

    if not Path(output_path).is_file():
        raise RuntimeError(f"ffmpeg did not produce expected output: {output_path}")

    return output_path


# ---------------------------------------------------------------------------
# Vocal processing presets
#
# Each preset controls the 5-stage vocal processing chain:
#   1. De-essing (sibilance reduction)
#   2. Gentle compression (consistency)
#   3. Analog-modeled saturation (counteracts vocoder smoothing)
#   4. Early reflections (physical presence)
#   5. Style-specific reverb tail
# ---------------------------------------------------------------------------
VOCAL_PRESETS: dict[str, dict] = {
    "default": {
        "de_ess_threshold": -20,
        "compression_ratio": 3,
        "saturation_drive": 0.3,
        "early_reflection_delay_ms": 20,
        "early_reflection_decay": 0.3,
        "reverb_delays": "40|60|80",
        "reverb_decays": "0.25|0.2|0.15",
    },
    "intimate": {
        "de_ess_threshold": -18,
        "compression_ratio": 2,
        "saturation_drive": 0.2,
        "early_reflection_delay_ms": 12,
        "early_reflection_decay": 0.2,
        "reverb_delays": "30|45",
        "reverb_decays": "0.15|0.1",
    },
    "powerful": {
        "de_ess_threshold": -22,
        "compression_ratio": 4,
        "saturation_drive": 0.4,
        "early_reflection_delay_ms": 25,
        "early_reflection_decay": 0.35,
        "reverb_delays": "50|80|120",
        "reverb_decays": "0.3|0.25|0.2",
    },
    "ethereal": {
        "de_ess_threshold": -16,
        "compression_ratio": 2,
        "saturation_drive": 0.15,
        "early_reflection_delay_ms": 30,
        "early_reflection_decay": 0.4,
        "reverb_delays": "60|100|160|220",
        "reverb_decays": "0.4|0.35|0.3|0.25",
    },
}


def process_vocals(
    vocal_audio: str,
    output_path: str,
    style: str = "default",
) -> str:
    """Apply vocal-specific processing chain (runs BEFORE genre mastering).

    The 5-stage chain:

    1. **De-essing** -- reduce harsh sibilants via ffmpeg bandreject/compressor
       on the 5--8 kHz sibilance band.
    2. **Gentle compression** -- smooth out dynamic inconsistencies in the
       vocal performance for consistency.
    3. **Analog-modeled saturation** -- soft-knee compression that adds subtle
       harmonic warmth, counteracting the smoothing artifacts of AI vocoders.
    4. **Early reflections** (10--30 ms) -- short delays that add physical
       presence and space to the vocal.
    5. **Style-specific reverb tail** -- longer echo pattern tuned per style:
       *default* (medium room, ~0.6 s RT60), *intimate* (short room, ~0.3 s),
       *powerful* (medium hall, ~1.2 s), *ethereal* (long hall, ~2.5 s with
       high diffusion).

    Args:
        vocal_audio: Path to the input vocal WAV file.
        output_path: Desired path for the processed output WAV file.
        style: Vocal style preset key from :data:`VOCAL_PRESETS`.
            Falls back to ``"default"`` if the key is not recognised.

    Returns:
        The absolute path to the processed vocal WAV file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If processing exceeds FFMPEG_TIMEOUT.
    """
    wav = Path(vocal_audio)
    if not wav.is_file():
        raise FileNotFoundError(f"Vocal audio file not found: {vocal_audio}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _require_ffmpeg()

    if style not in VOCAL_PRESETS:
        logger.warning(
            "Unknown vocal style '%s', falling back to 'default'. "
            "Available: %s",
            style, ", ".join(VOCAL_PRESETS.keys()),
        )
        style = "default"

    preset = VOCAL_PRESETS[style]
    filters = _build_vocal_filter_chain(preset)

    logger.info(
        "Applying vocal processing: style=%s, filters=%d stages",
        style, len(filters),
    )

    _apply_filters(str(wav), str(out), filters)

    logger.info("Vocal processing complete: %s", out)
    return str(out.resolve())


def _build_vocal_filter_chain(preset: dict) -> list[str]:
    """Build the ffmpeg filter chain for vocal processing from a preset.

    Returns a list of ffmpeg filter strings that will be joined with commas
    into a single ``-af`` filter graph.
    """
    filters: list[str] = []

    # --- Stage 1: De-essing ---
    # Isolate the 5-8 kHz sibilance band via a bandpass, compress it
    # aggressively, then mix back.  Implemented as a targeted compressor
    # on the sibilance frequencies using the sidechainless approach:
    # highpass at 5 kHz -> detect energy -> compress the full signal when
    # sibilance is present.
    #
    # We use a narrow-band compressor: the equalizer boosts the sibilant
    # range so the compressor threshold catches it, then we attenuate back.
    de_ess_thresh = preset["de_ess_threshold"]
    filters.append(
        f"acompressor=threshold={de_ess_thresh}dB:ratio=6:attack=0.5:"
        f"release=50:knee=3:detection=peak"
    )
    # Notch the harsh sibilance band slightly after compression.
    filters.append(
        "equalizer=f=6500:t=q:w=2.0:g=-3"
    )

    # --- Stage 2: Gentle compression for vocal consistency ---
    comp_ratio = preset["compression_ratio"]
    filters.append(
        f"acompressor=threshold=-24dB:ratio={comp_ratio}:attack=15:"
        f"release=300:knee=6:makeup=2"
    )

    # --- Stage 3: Analog-modeled saturation ---
    # Use a soft-knee compressor with very low threshold to introduce subtle
    # harmonic distortion, mimicking analog tape saturation.  The drive
    # parameter controls how much the signal is pushed into compression.
    drive = preset["saturation_drive"]
    # Map drive (0.0-1.0) to a threshold: higher drive = lower threshold
    # = more saturation.  Range: -3 dB (drive=0) to -15 dB (drive=1.0).
    sat_threshold = round(-3 - (drive * 40), 1)
    filters.append(
        f"acompressor=threshold={sat_threshold}dB:ratio=2:attack=0.1:"
        f"release=10:knee=10"
    )

    # --- Stage 4: Early reflections for physical presence ---
    er_delay = preset["early_reflection_delay_ms"]
    er_decay = preset["early_reflection_decay"]
    # aecho: in_gain | out_gain | delays (ms) | decays (0-1)
    # Use 2-3 taps at short intervals for comb-like early reflections.
    er_delay_2 = er_delay + 8
    er_delay_3 = er_delay + 17
    er_decay_2 = round(er_decay * 0.6, 2)
    er_decay_3 = round(er_decay * 0.3, 2)
    filters.append(
        f"aecho=0.8:0.7:{er_delay}|{er_delay_2}|{er_delay_3}:"
        f"{er_decay}|{er_decay_2}|{er_decay_3}"
    )

    # --- Stage 5: Style-specific reverb tail ---
    reverb_delays = preset["reverb_delays"]
    reverb_decays = preset["reverb_decays"]
    # Use aecho with longer delay times to simulate a reverb tail.
    # in_gain=0.8 preserves dry signal, out_gain controlled by decay values.
    filters.append(
        f"aecho=0.8:0.65:{reverb_delays}:{reverb_decays}"
    )

    return filters


def remix_vocals_with_instrumental(
    vocal_path: str,
    instrumental_path: str,
    output_path: str,
    vocal_level_db: float = 0.0,
    vocal_pan: float = 0.0,
    apply_vocal_processing: bool = True,
    vocal_style: str = "default",
) -> str:
    """Mix processed vocals with instrumental backing.

    Optionally runs :func:`process_vocals` on the vocal track first, then
    combines it with the instrumental using ffmpeg.  Handles sample-rate
    matching automatically and supports vocal level adjustment and stereo
    panning.

    Args:
        vocal_path: Path to input vocal WAV file.
        instrumental_path: Path to input instrumental WAV file.
        output_path: Desired path for the mixed output WAV file.
        vocal_level_db: Gain adjustment for the vocal track in dB
            (positive = louder, negative = quieter).
        vocal_pan: Stereo panning for the vocal (-1.0 = hard left,
            0.0 = center, 1.0 = hard right).
        apply_vocal_processing: If True, runs :func:`process_vocals` on
            the vocal track before mixing.
        vocal_style: Vocal processing style preset (only used when
            *apply_vocal_processing* is True).

    Returns:
        The absolute path to the mixed output WAV file.

    Raises:
        FileNotFoundError: If any input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If processing exceeds FFMPEG_TIMEOUT.
    """
    voc = Path(vocal_path)
    inst = Path(instrumental_path)

    if not voc.is_file():
        raise FileNotFoundError(f"Vocal file not found: {vocal_path}")
    if not inst.is_file():
        raise FileNotFoundError(f"Instrumental file not found: {instrumental_path}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _require_ffmpeg()

    # --- Optionally process vocals first ---
    if apply_vocal_processing:
        processed_vocal = out.with_name(out.stem + "_vox_processed.wav")
        vocal_src = process_vocals(
            vocal_audio=str(voc),
            output_path=str(processed_vocal),
            style=vocal_style,
        )
    else:
        vocal_src = str(voc)
        processed_vocal = None

    # --- Build the mixing filter graph ---
    # Both inputs are resampled to 48 kHz stereo for consistency.
    # [0:a] = vocal, [1:a] = instrumental
    vocal_filters: list[str] = []
    inst_filters: list[str] = []

    # Resample both to 48 kHz stereo.
    vocal_filters.append("aresample=48000")
    vocal_filters.append("aformat=channel_layouts=stereo")
    inst_filters.append("aresample=48000")
    inst_filters.append("aformat=channel_layouts=stereo")

    # Apply vocal level adjustment.
    if vocal_level_db != 0.0:
        vocal_filters.append(f"volume={vocal_level_db}dB")

    # Apply vocal panning (stereopanner).
    # pan filter: for center (0.0) both channels equal;
    # for left (-1.0) all signal to left; for right (1.0) all to right.
    if vocal_pan != 0.0:
        # Convert -1..1 pan to left/right gains.
        # Center: L=0.5, R=0.5; Hard left: L=1.0, R=0.0
        left_gain = round(min(1.0, 0.5 - vocal_pan * 0.5), 3)
        right_gain = round(min(1.0, 0.5 + vocal_pan * 0.5), 3)
        vocal_filters.append(
            f"pan=stereo|c0={left_gain}*c0+{left_gain}*c1|"
            f"c1={right_gain}*c0+{right_gain}*c1"
        )

    # Build the complex filter graph.
    vf_chain = ",".join(vocal_filters)
    if_chain = ",".join(inst_filters)

    # amix with duration=longest ensures we get the full instrumental even
    # if the vocal is shorter.
    filter_complex = (
        f"[0:a]{vf_chain}[v];"
        f"[1:a]{if_chain}[i];"
        f"[v][i]amix=inputs=2:duration=longest:dropout_transition=2[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", vocal_src,
        "-i", str(inst),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        str(out),
    ]

    logger.info(
        "Mixing vocals with instrumental: vocal_db=%.1f, pan=%.2f, "
        "processing=%s, style=%s",
        vocal_level_db, vocal_pan, apply_vocal_processing, vocal_style,
    )
    logger.debug("ffmpeg remix command: %s", " ".join(cmd))

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            "ffmpeg remix failed (rc=%d): %s", exc.returncode, exc.stderr
        )
        raise
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg remix timed out after %d seconds", FFMPEG_TIMEOUT)
        raise
    finally:
        # Clean up intermediate processed vocal file.
        if processed_vocal is not None and Path(processed_vocal).is_file():
            Path(processed_vocal).unlink()
            logger.debug("Removed intermediate processed vocal: %s", processed_vocal)

    if not out.is_file():
        raise RuntimeError(f"ffmpeg did not produce expected output: {output_path}")

    logger.info("Remix complete: %s", out)
    return str(out.resolve())


def list_presets() -> list[str]:
    """Return available genre preset names.

    Returns:
        A sorted list of preset key strings.
    """
    return sorted(GENRE_PRESETS.keys())


def list_vocal_styles() -> list[str]:
    """Return available vocal processing style names.

    Returns:
        A sorted list of vocal style key strings.
    """
    return sorted(VOCAL_PRESETS.keys())
