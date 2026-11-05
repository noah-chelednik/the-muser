"""Hardware detection used by the auto-selector and the setup recommendations."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field

_CACHE: tuple[float, Hardware] | None = None


@dataclass
class Hardware:
    os: str
    cpu_count: int
    ram_gb: float
    gpu: str = ""
    vram_gb: float = 0.0
    cuda: bool = False
    source: str = "none"  # nvidia-smi | torch | env | none
    notes: list[str] = field(default_factory=list)
    compute_cap: str = ""  # e.g. "7.5" for Turing (RTX 20), "8.6" for Ampere (RTX 30)

    @property
    def cc(self) -> float:
        try:
            return float(self.compute_cap)
        except ValueError:
            return 0.0

    @property
    def bf16(self) -> bool:
        """Native bfloat16 needs Ampere (8.0) or newer. Turing falls back to fp16."""
        return self.cc >= 8.0

    @property
    def flash_attn(self) -> bool:
        """FlashAttention 2 also needs Ampere or newer."""
        return self.cc >= 8.0

    @property
    def usable_vram_gb(self) -> float:
        """VRAM left for models after the desktop and display take their share."""
        if self.vram_gb <= 0:
            return 0.0
        return round(max(self.vram_gb - 0.5, 0.0), 1)

    @property
    def has_gpu(self) -> bool:
        return self.vram_gb > 0

    def tier(self) -> str:
        if self.vram_gb >= 20:
            return "studio-gpu"
        if self.vram_gb >= 10:
            return "gpu"
        if self.vram_gb >= 6:
            return "entry-gpu"
        if self.vram_gb > 0:
            return "small-gpu"
        return "cpu"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier"] = self.tier()
        d["has_gpu"] = self.has_gpu
        d["bf16"] = self.bf16
        d["flash_attn"] = self.flash_attn
        d["usable_vram_gb"] = self.usable_vram_gb
        return d


def _ram_gb() -> float:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().total / 2**30, 1)
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 2**20, 1)
    except Exception:
        pass
    if platform.system() == "Windows":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                ] + [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]

            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
            return round(m.ullTotalPhys / 2**30, 1)
        except Exception:
            pass
    return 0.0


def detect(force: bool = False) -> Hardware:
    global _CACHE
    if _CACHE and not force and time.time() - _CACHE[0] < 60:
        return _CACHE[1]
    hw = Hardware(
        os=platform.system() or "unknown", cpu_count=os.cpu_count() or 1, ram_gb=_ram_gb()
    )
    forced = os.environ.get("MUSER_FORCE_VRAM_GB")
    if forced is not None:
        hw.vram_gb = float(forced)
        hw.gpu = "forced via MUSER_FORCE_VRAM_GB" if hw.vram_gb else ""
        hw.cuda = hw.vram_gb > 0
        hw.source = "env"
        hw.compute_cap = os.environ.get("MUSER_FORCE_COMPUTE_CAP", "")
    elif shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=8,
            ).stdout.strip()
            if out:
                best = max(
                    (line.split(",") for line in out.splitlines()), key=lambda p: float(p[1])
                )
                hw.gpu, hw.vram_gb, hw.cuda, hw.source = (
                    best[0].strip(),
                    round(float(best[1]) / 1024, 1),
                    True,
                    "nvidia-smi",
                )
                cap = subprocess.run(
                    ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                ).stdout.strip()
                if cap and cap[0].isdigit():
                    hw.compute_cap = cap.splitlines()[0].strip()
        except Exception as e:  # pragma: no cover
            hw.notes.append(f"nvidia-smi failed: {e}")
    if hw.source == "none":
        try:
            import importlib.util

            if importlib.util.find_spec("torch") is not None:
                import torch

                if torch.cuda.is_available():
                    p = torch.cuda.get_device_properties(0)
                    hw.gpu, hw.vram_gb, hw.cuda, hw.source = (
                        p.name,
                        round(p.total_memory / 2**30, 1),
                        True,
                        "torch",
                    )
                    hw.compute_cap = f"{p.major}.{p.minor}"
        except Exception:
            pass
    if hw.has_gpu and hw.compute_cap and not hw.bf16:
        hw.notes.append(
            "RTX 20 series or older: models run in fp16 (no bf16 or FlashAttention 2 on this GPU)."
        )
    if 0 < hw.vram_gb < 10:
        hw.notes.append(
            f"{hw.vram_gb:g} GB card: the Studio picks low-memory settings and hides models that won't fit."
        )
    if not hw.has_gpu:
        hw.notes.append(
            "No NVIDIA GPU found: heavy AI models are skipped and CPU-friendly engines are used."
        )
    _CACHE = (time.time(), hw)
    return hw
