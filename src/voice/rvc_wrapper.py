"""RVC/Applio voice conversion wrapper.

Provides voice conversion using the Applio/RVC pipeline.
Supports pitch shifting and formant preservation for
cross-gender conversion.
"""

import logging
import subprocess
from pathlib import Path

from src.orchestrator.config import APPLIO_DIR

logger = logging.getLogger(__name__)


def convert_voice(
    input_audio: str,
    model_path: str,
    index_path: str = "",
    transpose: int = 0,
    f0_method: str = "rmvpe",
    output_path: str | None = None,
    formant_shift: bool = False,
    formant_quefrency: float = 8.0,
    formant_timbre: float = 1.0,
    index_rate: float = 0.75,
    filter_radius: int = 3,
    rms_mix_rate: float = 0.25,
    protect: float = 0.33,
) -> str:
    """Convert vocals to a target voice using RVC.

    Args:
        input_audio: Path to input vocal audio (WAV).
        model_path: Path to the RVC .pth model file.
        index_path: Path to the .index file (optional, improves quality).
        transpose: Pitch shift in semitones (positive=up, negative=down).
        f0_method: Pitch extraction method (rmvpe, crepe, pm, harvest).
        output_path: Output WAV path. Auto-generated if None.
        formant_shift: Enable formant preservation for cross-gender conversion.
        formant_quefrency: Quefrency threshold for formant envelope
            (higher = smoother). Only used when formant_shift is True.
        formant_timbre: Timbre scaling factor for formant shift
            (>1 = brighter/feminine). Only used when formant_shift is True.
        index_rate: Feature retrieval blend ratio (0 = no index, 1 = full index).
        filter_radius: Median filter radius for pitch smoothing.
        rms_mix_rate: RMS envelope mixing ratio (0 = source, 1 = target).
        protect: Consonant protection factor (0 = none, 0.5 = full).

    Returns:
        Path to the converted audio file.

    Raises:
        FileNotFoundError: If input audio or model file doesn't exist.
        RuntimeError: If conversion fails.
    """
    input_path = Path(input_audio)
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio not found: {input_audio}")

    model = Path(model_path)
    if not model.exists():
        raise FileNotFoundError(f"RVC model not found: {model_path}")

    if output_path is None:
        output_path = str(input_path.parent / f"{input_path.stem}_rvc{input_path.suffix}")

    logger.info(
        "RVC conversion: %s -> %s (model: %s, transpose: %d, f0: %s, formant_shift: %s)",
        input_audio,
        output_path,
        model.name,
        transpose,
        f0_method,
        formant_shift,
    )

    # Try Python API first (if Applio is available as a module)
    try:
        return _convert_via_python_api(
            input_audio,
            model_path,
            index_path,
            transpose,
            f0_method,
            output_path,
            formant_shift,
            formant_quefrency,
            formant_timbre,
            index_rate,
            filter_radius,
            rms_mix_rate,
            protect,
        )
    except ImportError:
        logger.info("Applio Python API not available, falling back to CLI")

    # Fall back to CLI invocation
    return _convert_via_cli(
        input_audio,
        model_path,
        index_path,
        transpose,
        f0_method,
        output_path,
        formant_shift,
        formant_quefrency,
        formant_timbre,
        index_rate,
        filter_radius,
        rms_mix_rate,
        protect,
    )


def _convert_via_python_api(
    input_audio: str,
    model_path: str,
    index_path: str,
    transpose: int,
    f0_method: str,
    output_path: str,
    formant_shift: bool,
    formant_quefrency: float,
    formant_timbre: float,
    index_rate: float,
    filter_radius: int,
    rms_mix_rate: float,
    protect: float,
) -> str:
    """Attempt conversion using Applio's Python API (VoiceConverter)."""
    import sys

    applio_path = str(APPLIO_DIR)
    if applio_path not in sys.path:
        sys.path.insert(0, applio_path)

    from rvc.infer.infer import VoiceConverter  # type: ignore

    converter = VoiceConverter()
    convert_kwargs = dict(
        audio_input_path=input_audio,
        audio_output_path=output_path,
        model_path=model_path,
        index_path=index_path,
        pitch=transpose,
        f0_method=f0_method,
        index_rate=index_rate,
        volume_envelope=rms_mix_rate,
        protect=protect,
        filter_radius=filter_radius,
        hop_length=128,
        split_audio=True,
        f0_autotune=formant_shift,
        f0_autotune_strength=0.8 if formant_shift else 1.0,
        clean_audio=False,
        export_format="WAV",
        embedder_model="contentvec",
    )

    if formant_shift:
        convert_kwargs["formant_shifting"] = True
        convert_kwargs["formant_qfrency"] = formant_quefrency
        convert_kwargs["formant_timbre"] = formant_timbre

    converter.convert_audio(**convert_kwargs)
    logger.info("RVC conversion complete (Python API): %s", output_path)
    return output_path


def _convert_via_cli(
    input_audio: str,
    model_path: str,
    index_path: str,
    transpose: int,
    f0_method: str,
    output_path: str,
    formant_shift: bool,
    formant_quefrency: float,
    formant_timbre: float,
    index_rate: float,
    filter_radius: int,
    rms_mix_rate: float,
    protect: float,
) -> str:
    """Attempt conversion using Applio CLI (core.py infer)."""
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
        index_path or "",
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
    ]

    if formant_shift:
        cmd.extend(
            [
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
        )

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

    logger.info("RVC conversion complete (CLI): %s", output_path)
    return output_path


def list_f0_methods() -> list[str]:
    """Return available pitch extraction methods."""
    return ["rmvpe", "crepe", "pm", "harvest"]
