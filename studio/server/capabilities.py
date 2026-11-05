"""Detect which parts of The Muser pipeline can actually run on this machine.

Every check is cheap, never raises, and returns a human-readable message so
the UI can show exactly what is missing instead of failing mysteriously.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.orchestrator import config as muser_config


@dataclass
class Capability:
    key: str
    label: str
    available: bool
    detail: str
    hint: str = ""


@dataclass
class Capabilities:
    demo_forced: bool
    mode: str  # "demo" | "hybrid" | "full"
    items: dict[str, Capability] = field(default_factory=dict)
    ollama_models: list[str] = field(default_factory=list)
    llm_models: list[str] = field(default_factory=list)
    checked_at: float = 0.0

    def ok(self, key: str) -> bool:
        item = self.items.get(key)
        return bool(item and item.available)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "demo_forced": self.demo_forced,
            "items": {k: asdict(v) for k, v in self.items.items()},
            "ollama_models": self.ollama_models,
            "llm_models": self.llm_models,
            "checked_at": self.checked_at,
        }


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _check_ffmpeg() -> Capability:
    path = shutil.which("ffmpeg")
    if path:
        return Capability("ffmpeg", "ffmpeg", True, f"Found at {path}")
    return Capability(
        "ffmpeg",
        "ffmpeg",
        False,
        "ffmpeg not found on PATH - server-side effects, mixdown and export are disabled.",
        "Windows: winget install Gyan.FFmpeg  (then reopen the terminal)",
    )


def _check_gpu() -> Capability:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return Capability(
            "gpu",
            "NVIDIA GPU",
            False,
            "nvidia-smi not found - no NVIDIA GPU/driver detected. CPU can run LLM orchestration only.",
            "AI generation wants an NVIDIA GPU. 8 GB (RTX 2080 / 3060 Ti / 4060) runs ACE-Step 1.5 "
            "with low-memory settings; 24 GB unlocks every model at full quality.",
        )
    try:
        out = subprocess.run(
            [smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return Capability("gpu", "NVIDIA GPU", bool(out), out or "nvidia-smi returned nothing")
    except Exception as e:  # pragma: no cover - hardware specific
        return Capability("gpu", "NVIDIA GPU", False, f"nvidia-smi failed: {e}")


def _check_torch_cuda() -> Capability:
    if not _has_module("torch"):
        return Capability(
            "torch",
            "PyTorch",
            False,
            "PyTorch not installed - ACE-Step / NotaGen / DiffSinger cannot run.",
            'pip install -e ".[gpu,voice]" (use the CUDA wheel from pytorch.org on Windows)',
        )
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            return Capability("torch", "PyTorch CUDA", True, f"{name} ({vram:.0f} GB)")
        return Capability(
            "torch",
            "PyTorch CUDA",
            False,
            f"PyTorch {torch.__version__} installed but CUDA is not available (CPU build).",
            "Install the CUDA build of torch from https://pytorch.org/get-started/locally/",
        )
    except Exception as e:  # pragma: no cover
        return Capability("torch", "PyTorch", False, f"torch import failed: {e}")


def _check_demucs() -> Capability:
    if _has_module("demucs"):
        return Capability(
            "demucs",
            "Demucs stems",
            True,
            "Demucs installed - real stem separation available (slow on CPU, fast on GPU).",
        )
    return Capability(
        "demucs",
        "Demucs stems",
        False,
        "Demucs not installed - splitting uses a frequency-band fallback (not true stems).",
        'pip install -e ".[voice]"',
    )


def _check_acestep() -> Capability:
    api = os.environ.get("MUSER_ACESTEP_API_URL", "")
    if api:
        return Capability("acestep", "ACE-Step", True, f"REST API mode: {api}")
    version = getattr(muser_config, "ACESTEP_VERSION", "v15")
    model_dir = muser_config.ACESTEP_V15_DIR if version == "v15" else muser_config.ACESTEP_DIR
    has_weights = (
        model_dir.exists() and any(p for p in model_dir.iterdir() if not p.name.startswith("."))
        if model_dir.exists()
        else False
    )
    if not has_weights:
        return Capability(
            "acestep",
            "ACE-Step",
            False,
            f"No ACE-Step weights in {model_dir.relative_to(muser_config.PROJECT_ROOT)}.",
            "Run scripts/setup_models.sh (Git Bash/WSL) or download the weights manually.",
        )
    return Capability("acestep", "ACE-Step", True, f"Weights found in {model_dir.name}")


def _check_ollama() -> tuple[Capability, list[str]]:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        import httpx

        r = httpx.get(f"{host}/api/tags", timeout=1.5)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
        if not models:
            return (
                Capability(
                    "ollama",
                    "Ollama LLM",
                    False,
                    f"Ollama is running at {host} but has no models pulled.",
                    "ollama pull qwen3:30b-a3b   (or qwen3:8b on smaller machines)",
                ),
                [],
            )
        return Capability("ollama", "Ollama LLM", True, f"{host} - {len(models)} model(s)"), models
    except Exception:
        hint = "Install from https://ollama.com then: ollama pull qwen3:8b"
        if shutil.which("ollama"):
            hint = "Ollama is installed but not running. Start it with: ollama serve"
        return Capability(
            "ollama", "Ollama LLM", False, f"Ollama not reachable at {host}.", hint
        ), []


def _cloud_llms() -> list[str]:
    out = []
    if os.environ.get("GROQ_API_KEY"):
        out.append("groq/llama-3.3-70b-versatile")
    if os.environ.get("CEREBRAS_API_KEY"):
        out.append("cerebras/llama-3.3-70b")
    if os.environ.get("GOOGLE_API_KEY"):
        out.append("gemini/gemini-2.0-flash")
    if os.environ.get("ANTHROPIC_API_KEY"):
        out.append("anthropic/claude-sonnet-4-5-20250929")
    return out


_cache: Capabilities | None = None
_CACHE_TTL_S = 10.0


def detect(force: bool = False) -> Capabilities:
    """Return detected capabilities (cached for a few seconds)."""
    global _cache
    if _cache and not force and time.time() - _cache.checked_at < _CACHE_TTL_S:
        return _cache

    demo_forced = os.environ.get("MUSER_STUDIO_DEMO", "").lower() in ("1", "true", "yes")
    ollama_cap, ollama_models = _check_ollama()
    cloud = _cloud_llms()
    items = {
        c.key: c
        for c in [
            ollama_cap,
            _check_ffmpeg(),
            _check_gpu(),
            _check_torch_cuda(),
            _check_acestep(),
            _check_demucs(),
        ]
    }
    if cloud:
        items["cloud_llm"] = Capability(
            "cloud_llm",
            "Cloud LLM",
            True,
            "API key(s) set: " + ", ".join(m.split("/")[0] for m in cloud),
        )

    llm_models = [f"ollama_chat/{m}" for m in ollama_models] + cloud
    llm_ok = bool(llm_models)
    gen_ok = items["acestep"].available and (
        items["torch"].available or bool(os.environ.get("MUSER_ACESTEP_API_URL"))
    )

    if demo_forced or not llm_ok:
        mode = "demo"
    elif gen_ok:
        mode = "full"
    else:
        mode = "hybrid"  # LLM works, audio models missing -> generation falls back to demo synth

    _cache = Capabilities(
        demo_forced=demo_forced,
        mode=mode,
        items=items,
        ollama_models=ollama_models,
        llm_models=llm_models,
        checked_at=time.time(),
    )
    return _cache


def project_root() -> Path:
    return muser_config.PROJECT_ROOT
