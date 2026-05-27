"""Wrapper around the ACE-Step music audio generation model.

Supports both ACE-Step v1.0 and v1.5 pipelines with automatic version dispatch.

v1.0: Uses ACEStepPipeline directly with tags-based conditioning.
v1.5: Uses AceStepHandler + LLMHandler with descriptive captions, BPM/key metadata,
      chain-of-thought planning, and batch generation. Also supports repaint, cover,
      and extend operations.

Usage::

    from src.generation.acestep_wrapper import generate_audio

    wav_paths = generate_audio(
        tags="A bright upbeat pop track with female vocals...",
        lyrics="Hello world, this is a song...",
        duration_s=60,
        num_candidates=2,
    )

The ACE-Step pipeline natively outputs 48 kHz audio files.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from src.orchestrator.config import (
    ACESTEP_DEFAULT_DURATION_S,
    ACESTEP_DIR,
    ACESTEP_INFER_STEP,
    ACESTEP_GUIDANCE_SCALE,
    ACESTEP_MAX_RETRIES,
    ACESTEP_SAMPLE_RATE,
    ACESTEP_VERSION,
    ACESTEP_V15_DIR,
    ACESTEP_V15_DIT_MODEL,
    ACESTEP_V15_BATCH_SIZE,
    ACESTEP_V15_THINKING_MODE,
    ACESTEP_V15_LM_TEMPERATURE,
    ACESTEP_V15_LM_CFG_SCALE,
    ACESTEP_V15_API_URL,
    ACESTEP_V15_API_KEY,
)
from src.utils.model_manager import get_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_temp_output_dir() -> str:
    """Create and return a unique temporary directory for audio outputs."""
    base = Path(tempfile.gettempdir()) / "muser_acestep"
    base.mkdir(parents=True, exist_ok=True)
    out_dir = tempfile.mkdtemp(prefix="gen_", dir=str(base))
    logger.debug("Created temporary output directory: %s", out_dir)
    return out_dir


def _is_silent(wav_path: str, threshold_db: float = -50.0) -> bool:
    """Check whether an audio file is effectively silent."""
    try:
        import librosa
        import numpy as np

        y, _sr = librosa.load(wav_path, sr=None, mono=True)

        if y is None or len(y) == 0:
            logger.warning("Empty audio data in %s", wav_path)
            return True

        rms = librosa.feature.rms(y=y)[0]

        if rms.max() == 0:
            return True

        peak_db = float(20.0 * np.log10(rms.max() + 1e-10))
        is_silent = peak_db < threshold_db

        if is_silent:
            logger.info(
                "Silence detected in %s (peak RMS %.1f dB < %.1f dB threshold).",
                wav_path, peak_db, threshold_db,
            )
        return is_silent

    except ImportError:
        logger.warning(
            "librosa is not installed; skipping silence detection for %s.", wav_path,
        )
        return False

    except Exception as exc:
        logger.warning(
            "Could not analyse %s for silence: %s. Treating as silent.", wav_path, exc,
        )
        return True


# ---------------------------------------------------------------------------
# v1.0 implementation
# ---------------------------------------------------------------------------


def _run_acestep_inference_v10(
    pipeline: Any,
    tags: str,
    lyrics: str,
    duration_s: float,
    seed: int,
    output_dir: str,
    infer_step: int = ACESTEP_INFER_STEP,
    guidance_scale: float = ACESTEP_GUIDANCE_SCALE,
    lora_path: str | None = None,
) -> list[str]:
    """Execute a single ACE-Step v1.0 inference pass and return WAV file paths."""
    if not lyrics or not lyrics.strip():
        lyrics = "[instrumental]"

    lora = lora_path if lora_path else "none"

    logger.info(
        "ACE-Step v1.0 inference: duration=%.1fs, seed=%d, infer_step=%d, "
        "guidance=%.1f, lora=%s",
        duration_s, seed, infer_step, guidance_scale, lora,
    )

    result = None
    try:
        result = pipeline(
            audio_duration=float(duration_s),
            prompt=tags,
            lyrics=lyrics,
            infer_step=infer_step,
            guidance_scale=guidance_scale,
            scheduler_type="euler",
            cfg_type="apg",
            omega_scale=10.0,
            manual_seeds=[seed],
            guidance_interval=0.5,
            use_erg_tag=True,
            use_erg_lyric=True,
            use_erg_diffusion=True,
            save_path=output_dir,
            batch_size=1,
            format="wav",
            lora_name_or_path=lora,
        )
    except Exception as exc:
        logger.warning(
            "ACE-Step v1.0 pipeline raised %s after saving; scanning output directory.",
            exc,
        )

    wav_paths: list[str] = []
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, str) and item.endswith(".wav") and os.path.isfile(item):
                wav_paths.append(item)

    if not wav_paths:
        for fname in sorted(os.listdir(output_dir)):
            fpath = os.path.join(output_dir, fname)
            if fname.endswith(".wav") and os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
                wav_paths.append(fpath)
        if wav_paths:
            logger.info("Found %d WAV file(s) via directory scan.", len(wav_paths))

    logger.debug("ACE-Step v1.0 returned %d WAV file(s)", len(wav_paths))
    return wav_paths


def _generate_audio_v10(
    tags: str,
    lyrics: str,
    duration_s: float,
    num_candidates: int,
    seed: int,
    infer_step: int,
    guidance_scale: float,
    lora_path: str | None,
) -> list[str]:
    """Generate audio using ACE-Step v1.0 pipeline."""
    try:
        import torch as _torch
        mgr = get_manager()
        cpu_offload = not _torch.cuda.is_available()
        pipeline = mgr.load_acestep(cpu_offload=cpu_offload)
    except (RuntimeError, ImportError, FileNotFoundError, OSError) as exc:
        logger.error("Could not load ACE-Step v1.0 model: %s", exc)
        return []

    output_dir = _get_temp_output_dir()
    good_paths: list[str] = []
    current_seed = seed

    for attempt in range(1, ACESTEP_MAX_RETRIES + 1):
        remaining = num_candidates - len(good_paths)
        if remaining <= 0:
            break

        logger.info(
            "ACE-Step v1.0 attempt %d/%d (seed=%d, need %d more).",
            attempt, ACESTEP_MAX_RETRIES, current_seed, remaining,
        )

        try:
            wav_paths = _run_acestep_inference_v10(
                pipeline=pipeline,
                tags=tags,
                lyrics=lyrics,
                duration_s=duration_s,
                seed=current_seed,
                output_dir=output_dir,
                infer_step=infer_step,
                guidance_scale=guidance_scale,
                lora_path=lora_path if attempt == 1 else None,
            )
        except Exception as exc:
            logger.error("ACE-Step v1.0 inference failed on attempt %d: %s", attempt, exc)
            current_seed += 1
            continue

        for wp in wav_paths:
            if _is_silent(wp):
                logger.info("Discarding silent candidate: %s", wp)
                try:
                    os.remove(wp)
                except OSError:
                    pass
            else:
                good_paths.append(wp)

        if len(good_paths) >= num_candidates:
            break
        current_seed += 1

    return good_paths


# ---------------------------------------------------------------------------
# v1.5 implementation
# ---------------------------------------------------------------------------


def _generate_audio_v15(
    tags: str,
    lyrics: str,
    duration_s: float,
    num_candidates: int,
    seed: int,
    infer_step: int,
    guidance_scale: float,
    lora_path: str | None = None,
    bpm: int | None = None,
    key_scale: str = "",
    time_signature: str = "",
    task_type: str = "text2music",
    src_audio: str | None = None,
    repainting_start: float = 0.0,
    repainting_end: float | None = None,
    audio_cover_strength: float = 1.0,
) -> list[str]:
    """Generate audio using ACE-Step v1.5 handler API."""
    import sys
    v15_path = str(ACESTEP_V15_DIR)
    if v15_path not in sys.path:
        sys.path.insert(0, v15_path)

    try:
        mgr = get_manager()
        dit_handler, llm_handler = mgr.load_acestep_v15()
    except (RuntimeError, ImportError, FileNotFoundError, OSError) as exc:
        logger.error("Could not load ACE-Step v1.5 model: %s", exc)
        return []

    try:
        from acestep.inference import generate_music, GenerationParams, GenerationConfig
    except ImportError as exc:
        logger.error("ACE-Step v1.5 inference module not found: %s", exc)
        return []

    if not lyrics or not lyrics.strip():
        lyrics = "[instrumental]"

    # Build params
    params = GenerationParams(
        caption=tags,
        lyrics=lyrics,
        instrumental=(lyrics.strip().lower() == "[instrumental]"),
        duration=float(duration_s) if duration_s > 0 else -1.0,
        inference_steps=infer_step,
        guidance_scale=guidance_scale,
        seed=seed,
        thinking=ACESTEP_V15_THINKING_MODE,
        lm_temperature=ACESTEP_V15_LM_TEMPERATURE,
        lm_cfg_scale=ACESTEP_V15_LM_CFG_SCALE,
        task_type=task_type,
        vocal_language="en",
    )

    if bpm is not None:
        params.bpm = bpm
    if key_scale:
        params.keyscale = key_scale
    if time_signature:
        params.timesignature = time_signature

    # Audio-to-audio parameters
    if src_audio:
        params.src_audio = src_audio
    if repainting_start > 0:
        params.repainting_start = repainting_start
    if repainting_end is not None:
        params.repainting_end = repainting_end
    if audio_cover_strength < 1.0:
        params.audio_cover_strength = audio_cover_strength

    seeds = None
    if seed >= 0:
        seeds = [seed + i for i in range(num_candidates)]

    config = GenerationConfig(
        batch_size=min(num_candidates, ACESTEP_V15_BATCH_SIZE),
        use_random_seed=(seed < 0),
        seeds=seeds,
        audio_format="wav",
    )

    output_dir = _get_temp_output_dir()

    logger.info(
        "ACE-Step v1.5 generate: task=%s, duration=%.1fs, steps=%d, "
        "guidance=%.1f, batch=%d, seed=%d, thinking=%s",
        task_type, duration_s, infer_step, guidance_scale,
        config.batch_size, seed, ACESTEP_V15_THINKING_MODE,
    )

    try:
        result = generate_music(
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            params=params,
            config=config,
            save_dir=output_dir,
        )
    except Exception as exc:
        logger.error("ACE-Step v1.5 generation failed: %s", exc)
        return []

    if not result.success:
        logger.error("ACE-Step v1.5 generation error: %s", result.error or result.status_message)
        return []

    # Collect output paths
    good_paths: list[str] = []
    for audio_info in result.audios:
        path = audio_info.get("path", "")
        if path and os.path.isfile(path):
            if not _is_silent(path):
                good_paths.append(path)
            else:
                logger.info("Discarding silent v1.5 candidate: %s", path)

    # Fallback: scan output dir
    if not good_paths:
        for fname in sorted(os.listdir(output_dir)):
            fpath = os.path.join(output_dir, fname)
            if os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
                if fname.endswith((".wav", ".flac", ".mp3")):
                    if not _is_silent(fpath):
                        good_paths.append(fpath)

    logger.info("ACE-Step v1.5: %d non-silent candidate(s)", len(good_paths))
    return good_paths


def _generate_audio_v15_api(
    tags: str,
    lyrics: str,
    duration_s: float,
    num_candidates: int,
    seed: int,
    infer_step: int,
    guidance_scale: float,
    bpm: int | None = None,
    key_scale: str = "",
    time_signature: str = "",
    task_type: str = "text2music",
    src_audio: str | None = None,
    repainting_start: float = 0.0,
    repainting_end: float | None = None,
    audio_cover_strength: float = 1.0,
) -> list[str]:
    """Generate audio via ACE-Step v1.5 REST API (async server mode)."""
    import json
    import urllib.request
    import urllib.error

    api_url = ACESTEP_V15_API_URL.rstrip("/")
    if not api_url:
        raise RuntimeError("MUSER_ACESTEP_API_URL not set; cannot use API mode")

    headers = {"Content-Type": "application/json"}
    if ACESTEP_V15_API_KEY:
        headers["Authorization"] = f"Bearer {ACESTEP_V15_API_KEY}"

    payload = {
        "caption": tags,
        "lyrics": lyrics,
        "duration": float(duration_s),
        "inference_steps": infer_step,
        "guidance_scale": guidance_scale,
        "seed": seed,
        "batch_size": num_candidates,
        "task_type": task_type,
        "audio_format": "wav",
    }
    if bpm is not None:
        payload["bpm"] = bpm
    if key_scale:
        payload["keyscale"] = key_scale
    if time_signature:
        payload["timesignature"] = time_signature
    if src_audio:
        payload["src_audio"] = src_audio
    if repainting_start > 0:
        payload["repainting_start"] = repainting_start
    if repainting_end is not None:
        payload["repainting_end"] = repainting_end

    logger.info("ACE-Step v1.5 API request: %s/release_task", api_url)

    # Submit task
    req = urllib.request.Request(
        f"{api_url}/release_task",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        task_data = json.loads(resp.read())

    task_id = task_data.get("task_id")
    if not task_id:
        raise RuntimeError(f"API did not return task_id: {task_data}")

    # Poll for results
    output_dir = _get_temp_output_dir()
    good_paths: list[str] = []
    max_wait = 600  # 10 minutes
    poll_interval = 5

    for _ in range(max_wait // poll_interval):
        time.sleep(poll_interval)
        query_req = urllib.request.Request(
            f"{api_url}/query_result",
            data=json.dumps({"task_ids": [task_id]}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(query_req, timeout=30) as resp:
                results = json.loads(resp.read())
        except urllib.error.URLError:
            continue

        task_result = results.get(task_id, {})
        status = task_result.get("status", "pending")

        if status == "completed":
            # Download audio files
            for audio_info in task_result.get("audios", []):
                audio_url = audio_info.get("url", "")
                if not audio_url:
                    continue
                fname = audio_info.get("filename", f"gen_{len(good_paths)}.wav")
                local_path = os.path.join(output_dir, fname)
                urllib.request.urlretrieve(
                    f"{api_url}/v1/audio?path={audio_url}",
                    local_path,
                )
                if os.path.isfile(local_path) and not _is_silent(local_path):
                    good_paths.append(local_path)
            break
        elif status == "failed":
            logger.error("API task failed: %s", task_result.get("error", "unknown"))
            break

    return good_paths


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_audio(
    tags: str,
    lyrics: str = "",
    duration_s: float | None = None,
    num_candidates: int = 1,
    seed: int | None = None,
    infer_step: int | None = None,
    guidance_scale: float | None = None,
    lora_path: str | None = None,
    bpm: int | None = None,
    key_scale: str = "",
    time_signature: str = "",
) -> list[str]:
    """Generate music audio using ACE-Step (dispatches by ACESTEP_VERSION).

    Parameters
    ----------
    tags:
        Descriptive paragraph or comma-separated tags for conditioning.
    lyrics:
        Optional lyrics text. Use ``"[instrumental]"`` for instrumental tracks.
    duration_s:
        Target audio duration in seconds.
    num_candidates:
        Number of audio candidates to generate.
    seed:
        Random seed. If ``None``, uses current timestamp.
    infer_step:
        Diffusion inference steps. v1.0: 27=fast/50=quality. v1.5: 8=turbo/50=quality.
    guidance_scale:
        Classifier-free guidance scale. v1.0: 4.0 optimal. v1.5: 7.0 default.
    lora_path:
        Optional path to a LoRA adapter checkpoint.
    bpm:
        Target BPM (v1.5 only, auto-detected if None).
    key_scale:
        Target key (v1.5 only, e.g., "C major").
    time_signature:
        Target time signature (v1.5 only, e.g., "4").

    Returns
    -------
    list[str]
        Paths to generated non-silent audio files.
    """
    if duration_s is None:
        duration_s = ACESTEP_DEFAULT_DURATION_S
    if seed is None:
        seed = int(time.time()) % (2 ** 31)
    if infer_step is None:
        infer_step = ACESTEP_INFER_STEP if ACESTEP_VERSION == "v10" else 8
    if guidance_scale is None:
        guidance_scale = ACESTEP_GUIDANCE_SCALE if ACESTEP_VERSION == "v10" else 7.0

    logger.info(
        "generate_audio [%s]: tags=%r, lyrics_len=%d, duration=%.0fs, "
        "candidates=%d, seed=%d, steps=%d, guidance=%.1f",
        ACESTEP_VERSION, tags[:80], len(lyrics), duration_s,
        num_candidates, seed, infer_step, guidance_scale,
    )

    if ACESTEP_VERSION == "v10":
        return _generate_audio_v10(
            tags=tags,
            lyrics=lyrics,
            duration_s=duration_s,
            num_candidates=num_candidates,
            seed=seed,
            infer_step=infer_step,
            guidance_scale=guidance_scale,
            lora_path=lora_path,
        )

    # v1.5: prefer API mode if configured, otherwise direct Python
    if ACESTEP_V15_API_URL:
        return _generate_audio_v15_api(
            tags=tags,
            lyrics=lyrics,
            duration_s=duration_s,
            num_candidates=num_candidates,
            seed=seed,
            infer_step=infer_step,
            guidance_scale=guidance_scale,
            bpm=bpm,
            key_scale=key_scale,
            time_signature=time_signature,
        )

    return _generate_audio_v15(
        tags=tags,
        lyrics=lyrics,
        duration_s=duration_s,
        num_candidates=num_candidates,
        seed=seed,
        infer_step=infer_step,
        guidance_scale=guidance_scale,
        lora_path=lora_path,
        bpm=bpm,
        key_scale=key_scale,
        time_signature=time_signature,
    )


def repaint_audio(
    src_audio: str,
    tags: str,
    start_s: float,
    end_s: float,
    lyrics: str = "",
    infer_step: int = 50,
    guidance_scale: float = 7.0,
    seed: int | None = None,
) -> list[str]:
    """Regenerate a time interval of existing audio (v1.5 only).

    Parameters
    ----------
    src_audio: Path to the source audio file.
    tags: Descriptive paragraph for the repainting.
    start_s: Start of the region to repaint (seconds).
    end_s: End of the region to repaint (seconds).
    """
    if seed is None:
        seed = int(time.time()) % (2 ** 31)

    if ACESTEP_V15_API_URL:
        return _generate_audio_v15_api(
            tags=tags, lyrics=lyrics, duration_s=-1, num_candidates=1,
            seed=seed, infer_step=infer_step, guidance_scale=guidance_scale,
            task_type="repaint", src_audio=src_audio,
            repainting_start=start_s, repainting_end=end_s,
        )

    return _generate_audio_v15(
        tags=tags, lyrics=lyrics, duration_s=-1, num_candidates=1,
        seed=seed, infer_step=infer_step, guidance_scale=guidance_scale,
        task_type="repaint", src_audio=src_audio,
        repainting_start=start_s, repainting_end=end_s,
    )


def cover_audio(
    src_audio: str,
    tags: str,
    cover_strength: float = 0.5,
    lyrics: str = "",
    infer_step: int = 50,
    guidance_scale: float = 7.0,
    seed: int | None = None,
) -> list[str]:
    """Style transfer on existing audio, preserving melody/structure (v1.5 only).

    Parameters
    ----------
    src_audio: Path to the source audio file.
    tags: Descriptive paragraph for the new style.
    cover_strength: 0.0=identical, 1.0=fully regenerated (default: 0.5).
    """
    if seed is None:
        seed = int(time.time()) % (2 ** 31)

    if ACESTEP_V15_API_URL:
        return _generate_audio_v15_api(
            tags=tags, lyrics=lyrics, duration_s=-1, num_candidates=1,
            seed=seed, infer_step=infer_step, guidance_scale=guidance_scale,
            task_type="cover", src_audio=src_audio,
            audio_cover_strength=cover_strength,
        )

    return _generate_audio_v15(
        tags=tags, lyrics=lyrics, duration_s=-1, num_candidates=1,
        seed=seed, infer_step=infer_step, guidance_scale=guidance_scale,
        task_type="cover", src_audio=src_audio,
        audio_cover_strength=cover_strength,
    )


def extend_audio(
    src_audio: str,
    tags: str,
    extend_s: float = 30.0,
    lyrics: str = "",
    infer_step: int = 50,
    guidance_scale: float = 7.0,
    seed: int | None = None,
) -> list[str]:
    """Extend existing audio by appending new content (v1.5 only).

    Uses the 'complete' task type to auto-complete from the end of src_audio.

    Parameters
    ----------
    src_audio: Path to the source audio file to extend.
    tags: Descriptive paragraph for the extension.
    extend_s: Duration of content to add (seconds).
    """
    if seed is None:
        seed = int(time.time()) % (2 ** 31)

    # Get source duration to set repaint region at the end
    try:
        import librosa
        y, sr = librosa.load(src_audio, sr=None, mono=True)
        src_duration = len(y) / sr
    except Exception:
        src_duration = 60.0

    total_duration = src_duration + extend_s

    if ACESTEP_V15_API_URL:
        return _generate_audio_v15_api(
            tags=tags, lyrics=lyrics, duration_s=total_duration, num_candidates=1,
            seed=seed, infer_step=infer_step, guidance_scale=guidance_scale,
            task_type="complete", src_audio=src_audio,
            repainting_start=src_duration, repainting_end=total_duration,
        )

    return _generate_audio_v15(
        tags=tags, lyrics=lyrics, duration_s=total_duration, num_candidates=1,
        seed=seed, infer_step=infer_step, guidance_scale=guidance_scale,
        task_type="complete", src_audio=src_audio,
        repainting_start=src_duration, repainting_end=total_duration,
    )
