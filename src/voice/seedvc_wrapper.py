"""Seed-VC zero-shot voice conversion wrapper.

Provides zero-shot voice conversion using Seed-VC, which converts vocals
to match a reference voice without requiring a trained model. Supports
both F0-conditioned (pitch-preserving) and non-conditioned modes.

Requires ~5 GB VRAM when loaded on GPU.
"""

import logging
import subprocess
from pathlib import Path

from src.orchestrator.config import SEEDVC_DIR

logger = logging.getLogger(__name__)


def convert_voice_seedvc(
    input_audio: str,
    reference_audio: str,
    output_path: str | None = None,
    f0_conditioned: bool = True,
    diffusion_steps: int = 10,
    length_adjust: float = 1.0,
) -> str:
    """Zero-shot voice conversion using Seed-VC.

    Converts the voice in ``input_audio`` to match the timbre of
    ``reference_audio`` without any model training.

    Args:
        input_audio: Path to input vocal audio (WAV).
        reference_audio: Path to reference voice sample (3-10 seconds recommended).
        output_path: Output WAV path. Auto-generated if None.
        f0_conditioned: If True, preserve the original pitch contour while
            converting timbre. Set False for full voice replacement including
            pitch characteristics.
        diffusion_steps: Number of diffusion inference steps. Higher values
            produce better quality but take longer (range: 1-50, default: 10).
        length_adjust: Speed adjustment factor. 1.0 = same speed, <1.0 = faster,
            >1.0 = slower. (range: 0.5-2.0, default: 1.0)

    Returns:
        Path to the converted audio file.

    Raises:
        FileNotFoundError: If input audio or reference audio does not exist.
        RuntimeError: If the conversion process fails.
    """
    # --- Validate inputs ---
    input_path = Path(input_audio)
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio not found: {input_audio}")

    ref_path = Path(reference_audio)
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

    # Clamp parameters to valid ranges
    diffusion_steps = max(1, min(diffusion_steps, 50))
    length_adjust = max(0.5, min(length_adjust, 2.0))

    # --- Determine output path ---
    if output_path is None:
        output_path = str(
            input_path.parent / f"{input_path.stem}_seedvc{input_path.suffix}"
        )

    logger.info(
        "Seed-VC conversion: %s -> %s (ref: %s, f0_cond: %s, steps: %d, len_adj: %.2f)",
        input_audio,
        output_path,
        ref_path.name,
        f0_conditioned,
        diffusion_steps,
        length_adjust,
    )

    # --- Try Python API first ---
    try:
        return _convert_via_python_api(
            input_audio=input_audio,
            reference_audio=reference_audio,
            output_path=output_path,
            f0_conditioned=f0_conditioned,
            diffusion_steps=diffusion_steps,
            length_adjust=length_adjust,
        )
    except ImportError:
        logger.info("Seed-VC Python API not available, falling back to CLI")
    except Exception as e:
        logger.warning("Seed-VC Python API failed (%s), falling back to CLI", e)

    # --- Fall back to CLI ---
    return _convert_via_cli(
        input_audio=input_audio,
        reference_audio=reference_audio,
        output_path=output_path,
        f0_conditioned=f0_conditioned,
        diffusion_steps=diffusion_steps,
        length_adjust=length_adjust,
    )


def _convert_via_python_api(
    input_audio: str,
    reference_audio: str,
    output_path: str,
    f0_conditioned: bool,
    diffusion_steps: int,
    length_adjust: float,
) -> str:
    """Convert using the Seed-VC Python API."""
    import sys

    seedvc_path = str(SEEDVC_DIR)
    if seedvc_path not in sys.path:
        sys.path.insert(0, seedvc_path)

    # Try canonical package import first, then alternative name
    try:
        from seed_vc import SeedVCInference  # type: ignore
    except ImportError:
        from seedvc import SeedVCInference  # type: ignore

    model = SeedVCInference(
        checkpoint_dir=seedvc_path,
        device="cuda",
    )

    result = model.convert(
        source=input_audio,
        reference=reference_audio,
        output=output_path,
        f0_conditioned=f0_conditioned,
        diffusion_steps=diffusion_steps,
        length_adjust=length_adjust,
    )

    # Some versions return the path, others return None
    actual_output = result if isinstance(result, str) else output_path

    if not Path(actual_output).exists():
        raise RuntimeError(
            f"Seed-VC Python API completed but output file not found: {actual_output}"
        )

    logger.info("Seed-VC conversion complete (Python API): %s", actual_output)
    return actual_output


def _convert_via_cli(
    input_audio: str,
    reference_audio: str,
    output_path: str,
    f0_conditioned: bool,
    diffusion_steps: int,
    length_adjust: float,
) -> str:
    """Convert using the Seed-VC CLI (subprocess fallback)."""
    cmd = [
        "python", "-m", "seed_vc",
        "--input", input_audio,
        "--reference", reference_audio,
        "--output", output_path,
        "--steps", str(diffusion_steps),
        "--length-adjust", str(length_adjust),
    ]

    if f0_conditioned:
        cmd.append("--f0-conditioned")

    logger.info("Running Seed-VC CLI: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(SEEDVC_DIR) if SEEDVC_DIR.exists() else None,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Seed-VC CLI failed (exit {result.returncode}): {result.stderr}"
        )

    if not Path(output_path).exists():
        raise RuntimeError(
            f"Seed-VC CLI completed but output file not found: {output_path}"
        )

    logger.info("Seed-VC conversion complete (CLI): %s", output_path)
    return output_path
