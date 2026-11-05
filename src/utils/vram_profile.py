"""Pick ACE-Step v1.5 memory settings that fit the local GPU.

The upstream ACE-Step 1.5 GPU tiers (docs/en/GPU_COMPATIBILITY.md) say:

* 6-8 GB  : 2B turbo DiT, 0.6B LM on the ``pt`` backend, CPU offload + INT8.
* 8-12 GB : 2B turbo DiT + 0.6B LM, offload VAE / text encoder, INT8.
* 12-16 GB: 2B turbo/sft + 1.7B LM, DiT stays on the GPU.
* 20 GB+  : no offload, no quantization (the original Muser default).

Env vars always win: MUSER_ACESTEP_DIT_MODEL, MUSER_ACESTEP_LM_MODEL,
MUSER_ACESTEP_OFFLOAD (true/false), MUSER_ACESTEP_OFFLOAD_DIT (true/false),
MUSER_ACESTEP_QUANT (int8_weight_only, fp8_weight_only, none) and
MUSER_ACESTEP_VRAM_BUDGET (GB checked before loading).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass
class AceStepProfile:
    tier: str
    dit_model: str
    lm_model: str
    lm_backend: str
    offload_to_cpu: bool
    offload_dit_to_cpu: bool
    quantization: str | None
    budget_gb: float
    max_duration_s: int
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def _flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def acestep_profile(total_vram_gb: float) -> AceStepProfile:
    if total_vram_gb <= 0:
        p = AceStepProfile(
            "cpu",
            "acestep-v15-turbo",
            "",
            "pt",
            True,
            True,
            None,
            0.0,
            120,
            "No NVIDIA GPU: very slow CPU mode, the Studio uses the sketch synth instead.",
        )
    elif total_vram_gb < 8.5:
        # 8 GB cards (RTX 2070/2080/3060 Ti/4060) report 7.6-8.0 GB.
        p = AceStepProfile(
            "8gb",
            "acestep-v15-turbo",
            "acestep-5Hz-lm-0.6B",
            "pt",
            True,
            True,
            "int8_weight_only",
            3.5,
            480,
            "8 GB profile: 2B turbo DiT, 0.6B LM (pt backend), CPU offload, INT8 weights.",
        )
    elif total_vram_gb < 12:
        p = AceStepProfile(
            "8-12gb",
            "acestep-v15-turbo",
            "acestep-5Hz-lm-0.6B",
            "pt",
            True,
            False,
            "int8_weight_only",
            6.0,
            480,
            "8-12 GB profile: DiT on GPU, VAE and text encoder offloaded, INT8 weights.",
        )
    elif total_vram_gb < 20:
        p = AceStepProfile(
            "12-20gb",
            "acestep-v15-turbo",
            "acestep-5Hz-lm-1.7B",
            "pt",
            False,
            False,
            "int8_weight_only",
            9.0,
            480,
            "12-20 GB profile: 1.7B LM, no offload.",
        )
    else:
        p = AceStepProfile(
            "20gb+",
            "acestep-v15-sft",
            "acestep-5Hz-lm-1.7B",
            "pt",
            False,
            False,
            None,
            22.0,
            600,
            "Full quality profile (original Muser default).",
        )
    env = os.environ
    p.dit_model = env.get("MUSER_ACESTEP_DIT_MODEL") or p.dit_model
    p.lm_model = env.get("MUSER_ACESTEP_LM_MODEL") or p.lm_model
    p.offload_to_cpu = _flag("MUSER_ACESTEP_OFFLOAD", p.offload_to_cpu)
    p.offload_dit_to_cpu = _flag("MUSER_ACESTEP_OFFLOAD_DIT", p.offload_dit_to_cpu)
    q = env.get("MUSER_ACESTEP_QUANT")
    if q is not None:
        p.quantization = None if q.strip().lower() in ("", "none", "off", "false") else q.strip()
    if env.get("MUSER_ACESTEP_VRAM_BUDGET"):
        p.budget_gb = float(env["MUSER_ACESTEP_VRAM_BUDGET"])
    return p


def cuda_total_vram_gb() -> float:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / 2**30
    except Exception:
        pass
    return 0.0
