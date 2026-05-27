"""Voice model registry and selection.

Manages available voice models for RVC conversion and ACE-Step LoRA
generation. Each voice has a unique ID, type, paths, and metadata.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.orchestrator.config import VOICES_DIR

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, dict[str, Any]] = {}

# File-based registry path
_REGISTRY_FILE = VOICES_DIR / "registry.json"


def _load_custom_voices() -> None:
    """Load custom voices from the registry file."""
    if _REGISTRY_FILE.exists():
        try:
            custom = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
            _REGISTRY.update(custom)
            logger.info("Loaded %d custom voices from registry", len(custom))
        except Exception as e:
            logger.warning("Failed to load voice registry: %s", e)


def _save_custom_voices() -> None:
    """Save custom (non-default) voices to the registry file."""
    default_ids = {
        "noah-natural", "noah-classical", "noah-fem",
        "noah-fem-classical", "noah-lora",
    }
    custom = {k: v for k, v in _REGISTRY.items() if k not in default_ids}
    _REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_FILE.write_text(json.dumps(custom, indent=2), encoding="utf-8")


def list_voices() -> list[dict[str, Any]]:
    """List all available voice models.

    Returns:
        List of voice metadata dicts.
    """
    _load_custom_voices()
    return list(_REGISTRY.values())


def get_voice(voice_id: str) -> dict[str, Any] | None:
    """Get a voice model by ID.

    Args:
        voice_id: Voice model identifier.

    Returns:
        Voice metadata dict, or None if not found. Includes a "warning"
        key if the model file does not exist on disk.
    """
    _load_custom_voices()
    voice = _REGISTRY.get(voice_id)
    if voice and not Path(voice.get("model_path", "")).exists():
        logger.warning(
            "Voice '%s' registered but model file missing: %s",
            voice_id, voice.get("model_path"),
        )
        voice = dict(voice)
        voice["warning"] = f"model file not found: {voice.get('model_path', '')}"
    return voice


def list_available_voices() -> list[dict[str, Any]]:
    """List only voices whose model files actually exist on disk."""
    _load_custom_voices()
    return [
        v for v in _REGISTRY.values()
        if Path(v.get("model_path", "")).exists()
    ]


def register_voice(
    voice_id: str,
    name: str,
    voice_type: str,
    model_path: str,
    description: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Register a new voice model.

    Args:
        voice_id: Unique identifier for the voice.
        name: Display name.
        voice_type: "rvc" or "acestep_lora".
        model_path: Path to the model file.
        description: Human-readable description.
        **kwargs: Additional metadata (gender, range, use_cases, etc.).

    Returns:
        The registered voice metadata dict.
    """
    voice = {
        "id": voice_id,
        "name": name,
        "type": voice_type,
        "model_path": model_path,
        "description": description,
        **kwargs,
    }
    _REGISTRY[voice_id] = voice
    _save_custom_voices()
    logger.info("Registered voice: %s (%s)", voice_id, name)
    return voice


def remove_voice(voice_id: str) -> bool:
    """Remove a voice from the registry.

    Args:
        voice_id: Voice to remove.

    Returns:
        True if removed, False if not found.
    """
    if voice_id in _REGISTRY:
        del _REGISTRY[voice_id]
        _save_custom_voices()
        logger.info("Removed voice: %s", voice_id)
        return True
    return False
