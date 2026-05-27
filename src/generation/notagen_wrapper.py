"""Wrapper around the NotaGen symbolic-music generation model.

Provides a single high-level entry point — ``generate_symbolic`` — that
loads the model (if not already loaded), runs generation with a timeout
guard, and returns a structured result dictionary.

Usage::

    from src.generation.notagen_wrapper import generate_symbolic

    result = generate_symbolic(
        period="Romantic",
        composer="Chopin",
        instrumentation="Piano",
        max_length=1024,
    )
    print(result["abc"])       # ABC notation string
    print(result["metadata"])  # generation parameters
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any

from src.orchestrator.config import (
    NOTAGEN_DIR,
    NOTAGEN_MAX_LENGTH,
    NOTAGEN_TIMEOUT_S,
)
from src.utils.model_manager import get_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _GenerationResult:
    """Thread-safe container for the generation output."""

    def __init__(self) -> None:
        self.abc: str = ""
        self.error: str | None = None


def _get_patchilizer():
    """Return a Patchilizer instance, importing from NotaGen's inference dir."""
    inference_path = str(NOTAGEN_DIR / "inference")
    if inference_path not in sys.path:
        sys.path.insert(0, inference_path)
    from utils import Patchilizer  # type: ignore[import-untyped]
    from config import PATCH_SIZE  # type: ignore[import-untyped]

    return Patchilizer(), PATCH_SIZE


def _run_generation(
    model: Any,
    period: str,
    composer: str,
    instrumentation: str,
    max_length: int,
    result: _GenerationResult,
) -> None:
    """Execute model generation in a worker thread.

    Uses NotaGen's patch-based generation: the Patchilizer encodes a
    metadata prompt into patches, then the model generates one patch at
    a time in an auto-regressive loop until it emits an end-of-sequence
    patch or hits the max_length limit.
    """
    try:
        import torch  # noqa: F811
        from config import (  # type: ignore[import-untyped]
            PATCH_SIZE,
            TOP_K,
            TOP_P,
            TEMPERATURE,
        )

        patchilizer, _ = _get_patchilizer()

        # Build the metadata prompt lines (NotaGen ABC format).
        prompt_lines = [
            f"%%period {period}\n",
            f"%%composer {composer}\n",
            f"%%instrumentation {instrumentation}\n",
        ]

        bos_patch = [patchilizer.bos_token_id] * (PATCH_SIZE - 1) + [patchilizer.eos_token_id]

        prompt_patches = patchilizer.patchilize_metadata(prompt_lines)
        byte_list = list("".join(prompt_lines))

        prompt_patches = [
            [ord(c) for c in patch] + [patchilizer.special_token_id] * (PATCH_SIZE - len(patch))
            for patch in prompt_patches
        ]
        prompt_patches.insert(0, bos_patch)

        device = next(model.parameters()).device
        input_patches = torch.tensor(prompt_patches, device=device).reshape(1, -1)

        with torch.no_grad():
            while True:
                predicted_patch = model.generate(
                    input_patches.unsqueeze(0),
                    top_k=TOP_K,
                    top_p=TOP_P,
                    temperature=TEMPERATURE,
                )

                # End-of-sequence: BOS followed by EOS.
                if (
                    predicted_patch[0] == patchilizer.bos_token_id
                    and predicted_patch[1] == patchilizer.eos_token_id
                ):
                    break

                next_text = patchilizer.decode([predicted_patch])
                for char in next_text:
                    byte_list.append(char)

                # Pad patch after EOS for consistent tensor shape.
                patch_end_flag = False
                for j in range(len(predicted_patch)):
                    if patch_end_flag:
                        predicted_patch[j] = patchilizer.special_token_id
                    if predicted_patch[j] == patchilizer.eos_token_id:
                        patch_end_flag = True

                predicted_patch_t = torch.tensor([predicted_patch], device=device)
                input_patches = torch.cat([input_patches, predicted_patch_t], dim=1)

                # Safety limits.
                if len(byte_list) > max_length * 100:
                    break
                if input_patches.shape[1] >= max_length * PATCH_SIZE:
                    break

        result.abc = "".join(byte_list)

    except Exception as exc:  # noqa: BLE001
        logger.error("NotaGen generation failed in worker thread: %s", exc)
        result.error = str(exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_symbolic(
    period: str = "Romantic",
    composer: str = "Chopin",
    instrumentation: str = "Piano",
    max_length: int | None = None,
) -> dict[str, Any]:
    """Generate a symbolic music piece in ABC notation using NotaGen.

    Parameters
    ----------
    period:
        Musical period / era (e.g. ``"Baroque"``, ``"Classical"``,
        ``"Romantic"``, ``"Modern"``).
    composer:
        Composer name used for style conditioning (e.g. ``"Chopin"``,
        ``"Bach"``).
    instrumentation:
        Instrumentation hint (e.g. ``"Piano"``, ``"String Quartet"``).
    max_length:
        Maximum patch-sequence length for generation.  Defaults to the
        ``NOTAGEN_MAX_LENGTH`` config value.

    Returns
    -------
    dict
        A dictionary with keys:

        - ``abc`` (*str*) — the generated ABC notation (empty on failure).
        - ``metadata`` (*dict*) — echo of the generation parameters.
        - ``generation_time_s`` (*float*) — wall-clock time in seconds.
        - ``error`` (*str*, optional) — present only when generation failed.
    """
    if max_length is None:
        max_length = NOTAGEN_MAX_LENGTH

    metadata: dict[str, Any] = {
        "period": period,
        "composer": composer,
        "instrumentation": instrumentation,
        "max_length": max_length,
    }

    t0 = time.monotonic()

    # -- Load model ---------------------------------------------------------
    try:
        mgr = get_manager()
        model = mgr.load_notagen()
    except (RuntimeError, ImportError, FileNotFoundError, OSError) as exc:
        elapsed = time.monotonic() - t0
        logger.error("Could not load NotaGen model: %s", exc)
        return {
            "abc": "",
            "error": f"Model load failure: {exc}",
            "metadata": metadata,
            "generation_time_s": round(elapsed, 3),
        }

    # -- Run generation with timeout ----------------------------------------
    result = _GenerationResult()
    worker = threading.Thread(
        target=_run_generation,
        args=(model, period, composer, instrumentation, max_length, result),
        daemon=True,
    )

    logger.info(
        "Starting NotaGen generation (period=%s, composer=%s, "
        "instrumentation=%s, max_length=%d, timeout=%ds).",
        period,
        composer,
        instrumentation,
        max_length,
        NOTAGEN_TIMEOUT_S,
    )

    worker.start()
    worker.join(timeout=NOTAGEN_TIMEOUT_S)

    elapsed = time.monotonic() - t0

    if worker.is_alive():
        logger.warning("NotaGen generation timed out after %d s.", NOTAGEN_TIMEOUT_S)
        return {
            "abc": "",
            "error": f"Generation timed out after {NOTAGEN_TIMEOUT_S}s",
            "metadata": metadata,
            "generation_time_s": round(elapsed, 3),
        }

    if result.error is not None:
        logger.error("NotaGen generation error: %s", result.error)
        return {
            "abc": "",
            "error": result.error,
            "metadata": metadata,
            "generation_time_s": round(elapsed, 3),
        }

    logger.info(
        "NotaGen generation completed in %.1f s (%d chars of ABC).",
        elapsed,
        len(result.abc),
    )

    return {
        "abc": result.abc,
        "metadata": metadata,
        "generation_time_s": round(elapsed, 3),
    }
