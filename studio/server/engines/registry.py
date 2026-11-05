"""The engine registry: every open-source audio tool the Studio knows about.

Each entry records what the tool can do (capability tags), its licences (code
and weights separately), whether its *output* is safe for commercial release,
hardware needs, how to install it, and how to check that it works.

``verified`` is honest:
  * ``working``  - wrapper exercised end-to-end on this codebase (CPU box).
  * ``adapter``  - structured adapter written to the tool's documented CLI/API,
                   but not run here (needs a big NVIDIA GPU). Marked
                   "untested here" in the UI.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from src.orchestrator.config import MODELS_DIR
except Exception:  # pragma: no cover
    MODELS_DIR = Path(__file__).resolve().parents[3] / "models"

TASKS = {
    "generate": "Make a song from a description",
    "separate": "Split a song into stems",
    "denoise": "Clean up noise",
    "match": "Match a reference track",
    "midi": "Turn audio into MIDI",
    "fx": "Effects and mixing chains",
    "master": "Mastering to a loudness target",
    "loudness": "Loudness metering",
    "voice": "Voice conversion",
    "enhance": "Restore or upscale audio",
}


@dataclass
class Install:
    kind: str  # builtin | pip | repo | app
    pip: list[str] = field(default_factory=list)
    no_deps: list[str] = field(default_factory=list)
    index_url: str = ""
    repo: str = ""
    requirements: str = "requirements.txt"
    python: str = ""
    steps: list[str] = field(default_factory=list)  # human readable extra steps
    prefetch: str = ""  # name of a weight-prefetch hook in installer.PREFETCH
    download_gb: float = 0.0


@dataclass
class VramProfile:
    """One real way to run a GPU model, with its measured or documented VRAM need."""

    id: str
    label: str
    vram_gb: float
    how: str  # the actual flags or settings
    quality: str = "full"  # full | reduced
    wired: bool = True  # False = documented upstream but not applied by the Studio adapter
    source: str = ""


@dataclass
class EngineSpec:
    key: str
    name: str
    tasks: list[str]
    summary: str
    homepage: str
    code_license: str
    weights_license: str
    commercial: str  # yes | conditional | no
    commercial_note: str
    tier: str  # builtin | core | optional | heavy
    install: Install
    quality: dict[str, int]
    min_vram_gb: float = 0.0  # 0 = CPU is fine
    cpu_ok: bool = True
    windows: str = "native"  # native | partial | wsl | separate-app
    verified: str = "working"  # working | adapter
    modules: list[str] = field(default_factory=list)
    binaries: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    gpl_note: str = ""
    archived: bool = False
    vram_profiles: list[VramProfile] = field(default_factory=list)
    vram_caveat: str = ""  # known out-of-memory reports, Turing limits, etc.
    needs_flash_attn: bool = False  # FlashAttention 2 needs an RTX 30 series or newer

    @property
    def vram_full_gb(self) -> float:
        """VRAM for full quality (the biggest profile)."""
        return max((p.vram_gb for p in self.vram_profiles), default=self.min_vram_gb)

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d["untested_here"] = self.verified != "working"
        d["vram_full_gb"] = self.vram_full_gb
        return d


def _md(*parts: str) -> str:
    return str(MODELS_DIR.joinpath(*parts))


ENGINES: list[EngineSpec] = [
    # ------------------------------------------------------------------ built in
    EngineSpec(
        key="demo-synth",
        name="Sketch Synth (built in)",
        tasks=["generate"],
        summary="Instant multitrack sketch from your description. Not AI: a fast placeholder that always works.",
        homepage="",
        code_license="MIT",
        weights_license="none",
        commercial="yes",
        commercial_note="Your sketches are yours.",
        tier="builtin",
        install=Install("builtin"),
        quality={"generate": 1},
    ),
    EngineSpec(
        key="band-split",
        name="Band Split (built in)",
        tasks=["separate"],
        summary="Crossover split into low/mid/high bands. Fallback when no AI splitter is installed.",
        homepage="",
        code_license="MIT",
        weights_license="none",
        commercial="yes",
        commercial_note="",
        tier="builtin",
        install=Install("builtin"),
        quality={"separate": 1},
    ),
    EngineSpec(
        key="builtin-dsp",
        name="Studio DSP (built in)",
        tasks=["fx", "match", "denoise", "master", "loudness"],
        summary="EQ, compressor, saturation, reverb, delay, chorus, width, de-esser, true-peak limiter, spectral reference match, spectral noise gate and BS.1770 loudness meter. Pure numpy/scipy.",
        homepage="",
        code_license="MIT",
        weights_license="none",
        commercial="yes",
        commercial_note="",
        tier="builtin",
        install=Install("builtin"),
        quality={"fx": 5, "match": 5, "denoise": 2, "master": 8, "loudness": 6},
    ),
    EngineSpec(
        key="pyin-midi",
        name="Pitch Tracker (built in)",
        tasks=["midi"],
        summary="Monophonic melody to MIDI using librosa pYIN. Fallback when Basic Pitch is missing.",
        homepage="https://librosa.org",
        code_license="ISC (librosa)",
        weights_license="none",
        commercial="yes",
        commercial_note="",
        tier="builtin",
        install=Install("builtin"),
        quality={"midi": 2},
        modules=["librosa"],
    ),
    # ------------------------------------------------------------------ core (installed by default)
    EngineSpec(
        key="pedalboard",
        name="Pedalboard (Spotify)",
        tasks=["fx"],
        summary="Studio-quality effects engine (JUCE). Runs every chain faster and closer to pro plugins.",
        homepage="https://github.com/spotify/pedalboard",
        code_license="GPL-3.0",
        weights_license="none",
        commercial="yes",
        commercial_note="GPL covers the library code only. Audio you process is yours and can be sold.",
        tier="core",
        install=Install("pip", pip=["pedalboard>=0.9"]),
        quality={"fx": 9},
        modules=["pedalboard"],
        gpl_note="Optional separate package, not bundled with The Muser's MIT code.",
    ),
    EngineSpec(
        key="pyloudnorm",
        name="pyloudnorm",
        tasks=["loudness"],
        summary="ITU-R BS.1770 loudness meter used to hit streaming targets.",
        homepage="https://github.com/csteinmetz1/pyloudnorm",
        code_license="MIT",
        weights_license="none",
        commercial="yes",
        commercial_note="",
        tier="core",
        install=Install("pip", pip=["pyloudnorm>=0.1"]),
        quality={"loudness": 9},
        modules=["pyloudnorm"],
    ),
    EngineSpec(
        key="noisereduce",
        name="noisereduce",
        tasks=["denoise"],
        summary="Spectral gating noise reduction. Light and CPU friendly.",
        homepage="https://github.com/timsainb/noisereduce",
        code_license="MIT",
        weights_license="none",
        commercial="yes",
        commercial_note="",
        tier="core",
        install=Install("pip", pip=["noisereduce>=3.0"]),
        quality={"denoise": 5},
        modules=["noisereduce"],
    ),
    EngineSpec(
        key="basic-pitch",
        name="Basic Pitch (Spotify)",
        tasks=["midi"],
        summary="Polyphonic audio to MIDI with pitch bends. Runs its bundled ONNX model on CPU.",
        homepage="https://github.com/spotify/basic-pitch",
        code_license="Apache-2.0",
        weights_license="Apache-2.0",
        commercial="yes",
        commercial_note="",
        tier="core",
        install=Install(
            "pip",
            pip=[
                "onnxruntime>=1.16",
                "mir_eval>=0.6",
                "resampy>=0.2.2,<0.4.3",
                "scikit-learn",
                "setuptools<81",
            ],
            no_deps=["basic-pitch>=0.4"],
            steps=["Installed without TensorFlow; the bundled ONNX model is used instead."],
        ),
        quality={"midi": 9},
        modules=["basic_pitch", "onnxruntime"],
    ),
    EngineSpec(
        key="matchering",
        name="Matchering 2",
        tasks=["match"],
        summary="Reference mastering: matches loudness, tone and stereo width to a song you love.",
        homepage="https://github.com/sergree/matchering",
        code_license="GPL-3.0",
        weights_license="none",
        commercial="yes",
        commercial_note="GPL covers the library code only. Your mastered audio is yours.",
        tier="core",
        install=Install("pip", pip=["matchering>=2.0"]),
        quality={"match": 9},
        modules=["matchering"],
        gpl_note="Optional separate package, not bundled with The Muser's MIT code.",
    ),
    # ------------------------------------------------------------------ optional AI (light enough for CPU)
    EngineSpec(
        key="audio-separator",
        name="Audio Separator (UVR models)",
        tasks=["separate"],
        summary="The best open stem splitters (MDX-Net, BS-Roformer, Mel-Roformer, Demucs) behind one command. MDX models run fine on CPU.",
        homepage="https://github.com/nomadkaraoke/python-audio-separator",
        code_license="MIT",
        weights_license="varies per model (most UVR community models are MIT or unspecified)",
        commercial="conditional",
        commercial_note="Tool is MIT. Check each separation model's licence before commercial release of separated stems.",
        tier="optional",
        install=Install(
            "pip",
            pip=["audio-separator[cpu]>=0.30", "torch", "onnxruntime>=1.16"],
            prefetch="audio_separator",
            download_gb=0.1,
            steps=[
                "GPU users: the setup script installs CUDA torch first; audio-separator then uses it automatically."
            ],
        ),
        quality={"separate": 9},
        modules=["audio_separator", "onnxruntime"],
    ),
    EngineSpec(
        key="demucs",
        name="Demucs v4 (Meta)",
        tasks=["separate"],
        summary="Hybrid Transformer Demucs 4-stem separation (vocals, drums, bass, other).",
        homepage="https://github.com/adefossez/demucs",
        code_license="MIT",
        weights_license="MIT",
        commercial="yes",
        commercial_note="",
        tier="optional",
        install=Install("pip", pip=["demucs>=4.0"], download_gb=0.3),
        quality={"separate": 7},
        modules=["demucs"],
        archived=False,
    ),
    EngineSpec(
        key="deepfilternet",
        name="DeepFilterNet 3",
        tasks=["denoise"],
        summary="Real-time AI noise suppression for voice and acoustic recordings (48 kHz).",
        homepage="https://github.com/Rikorose/DeepFilterNet",
        code_license="MIT OR Apache-2.0",
        weights_license="MIT OR Apache-2.0",
        commercial="yes",
        commercial_note="",
        tier="optional",
        install=Install(
            "pip",
            pip=["deepfilternet>=0.5", "torch", "torchaudio<2.9"],
            prefetch="deepfilternet",
            download_gb=0.05,
            steps=["Needs torchaudio older than 2.9 (2.9 removed an API DeepFilterNet uses)."],
        ),
        quality={"denoise": 9},
        modules=["df", "torch"],
    ),
    # ------------------------------------------------------------------ heavy GPU generation (adapters)
    EngineSpec(
        key="acestep",
        name="ACE-Step 1.5",
        tasks=["generate"],
        summary="Full songs with vocals and lyrics in many languages. The Muser's main generator.",
        homepage="https://github.com/ace-step/ACE-Step-1.5",
        code_license="MIT",
        weights_license="MIT",
        commercial="yes",
        commercial_note="Open licence; review the model card for training-data notes.",
        tier="heavy",
        min_vram_gb=4,
        cpu_ok=False,
        windows="native",
        verified="adapter",
        install=Install(
            "repo",
            repo="https://github.com/ace-step/ACE-Step-1.5",
            python="3.11-3.12",
            download_gb=10,
            steps=[
                "Run setup_windows.ps1 -Gpu, then follow docs/ace-step-v15.md (The Muser's existing integration)."
            ],
        ),
        quality={"generate": 8},
        paths=[_md("ace-step-v15")],
    ),
    EngineSpec(
        key="diffrhythm",
        name="DiffRhythm",
        tasks=["generate"],
        summary="Fast full-length songs (up to about 4:45) with vocals from lyrics plus a style prompt or reference.",
        homepage="https://github.com/ASLP-lab/DiffRhythm",
        code_license="Apache-2.0",
        weights_license="Apache-2.0",
        commercial="yes",
        commercial_note="Apache-2.0 code and weights.",
        tier="heavy",
        min_vram_gb=8,
        cpu_ok=False,
        windows="partial",
        verified="adapter",
        install=Install(
            "repo",
            repo="https://github.com/ASLP-lab/DiffRhythm",
            python="3.10",
            download_gb=8,
            steps=[
                "Windows: install espeak-ng and set PHONEMIZER_ESPEAK_LIBRARY and PHONEMIZER_ESPEAK_PATH.",
                "8 GB cards: the adapter passes --chunked automatically.",
            ],
        ),
        quality={"generate": 7},
        paths=[_md("diffrhythm", "infer", "infer.py")],
    ),
    EngineSpec(
        key="yue",
        name="YuE",
        tasks=["generate"],
        summary="Lyrics-to-song foundation model with strong vocals and long-form structure.",
        homepage="https://github.com/multimodal-art-projection/YuE",
        code_license="Apache-2.0",
        weights_license="CC BY-NC 4.0 (see model card)",
        commercial="conditional",
        commercial_note="Model card: individuals may monetize outputs with attribution; companies need a licence. Off by default in commercial-safe mode.",
        tier="heavy",
        min_vram_gb=16,
        cpu_ok=False,
        windows="wsl",
        verified="adapter",
        install=Install(
            "repo",
            repo="https://github.com/multimodal-art-projection/YuE",
            python="3.10-3.12",
            download_gb=25,
            steps=[
                "Linux or WSL2 recommended (flash-attention). 24 GB VRAM for full songs; about 11 GB peak for short clips."
            ],
        ),
        quality={"generate": 8},
        paths=[_md("yue", "inference", "infer.py")],
    ),
    EngineSpec(
        key="songgeneration",
        name="SongGeneration / LeVo (Tencent)",
        tasks=["generate"],
        summary="High quality songs with vocals and accompaniment tracks.",
        homepage="https://github.com/tencent-ailab/SongGeneration",
        code_license="Custom (Tencent)",
        weights_license="Custom, research and education only",
        commercial="no",
        commercial_note="Licence forbids commercial use. Hidden unless you allow non-commercial engines.",
        tier="heavy",
        min_vram_gb=10,
        cpu_ok=False,
        windows="wsl",
        verified="adapter",
        install=Install(
            "repo",
            repo="https://github.com/tencent-ailab/SongGeneration",
            python="3.10",
            download_gb=20,
        ),
        quality={"generate": 9},
        paths=[_md("songgeneration", "generate.sh")],
    ),
    EngineSpec(
        key="stable-audio-open",
        name="Stable Audio Open",
        tasks=["generate"],
        summary="Instrumental loops, textures and sound effects up to 47 s (1.0) or 11 s (Small).",
        homepage="https://huggingface.co/stabilityai/stable-audio-open-1.0",
        code_license="MIT (stable-audio-tools)",
        weights_license="Stability AI Community License",
        commercial="conditional",
        commercial_note="Free commercial use under USD 1M annual revenue after registering with Stability AI.",
        tier="heavy",
        min_vram_gb=6,
        cpu_ok=False,
        windows="native",
        verified="adapter",
        install=Install(
            "pip",
            pip=["diffusers>=0.32", "transformers>=4.40", "torchsde", "accelerate"],
            download_gb=5,
            steps=[
                "Accept the licence on Hugging Face and run `huggingface-cli login` once (gated model)."
            ],
        ),
        quality={"generate": 5},
        modules=["diffusers", "torch"],
    ),
    EngineSpec(
        key="musicgen",
        name="MusicGen (Meta AudioCraft)",
        tasks=["generate"],
        summary="Instrumental music from text, melody conditioning. Small model runs on modest GPUs.",
        homepage="https://github.com/facebookresearch/audiocraft",
        code_license="MIT",
        weights_license="CC BY-NC 4.0",
        commercial="no",
        commercial_note="Weights are non-commercial. Hidden unless you allow non-commercial engines.",
        tier="heavy",
        min_vram_gb=4,
        cpu_ok=False,
        windows="native",
        verified="adapter",
        install=Install("pip", pip=["transformers>=4.40", "torch"], download_gb=2.5),
        quality={"generate": 4},
        modules=["transformers", "torch"],
    ),
    EngineSpec(
        key="audioldm2",
        name="AudioLDM 2",
        tasks=["generate"],
        summary="Text to sound effects and ambience.",
        homepage="https://github.com/haoheliu/AudioLDM2",
        code_license="MIT",
        weights_license="CC BY-NC-SA 4.0",
        commercial="no",
        commercial_note="Weights are non-commercial.",
        tier="heavy",
        min_vram_gb=6,
        cpu_ok=False,
        verified="adapter",
        install=Install(
            "pip", pip=["diffusers>=0.32", "transformers>=4.40", "torch"], download_gb=4
        ),
        quality={"generate": 3},
        modules=["diffusers", "torch"],
    ),
    # ------------------------------------------------------------------ voice / enhance (adapters)
    EngineSpec(
        key="applio",
        name="Applio (RVC)",
        tasks=["voice"],
        summary="Train or use RVC voice models to change a vocal into another voice.",
        homepage="https://github.com/IAHispano/Applio",
        code_license="MIT",
        weights_license="per voice model",
        commercial="conditional",
        commercial_note="Only use voices you own or have permission to use.",
        tier="heavy",
        min_vram_gb=4,
        cpu_ok=True,
        windows="separate-app",
        verified="adapter",
        install=Install(
            "app",
            repo="https://github.com/IAHispano/Applio",
            download_gb=3,
            steps=[
                "Windows: download the Applio installer from the releases page and install into models/applio."
            ],
        ),
        quality={"voice": 8},
        paths=[_md("applio", "core.py")],
    ),
    EngineSpec(
        key="seed-vc",
        name="Seed-VC",
        tasks=["voice"],
        summary="Zero-shot singing voice conversion from a short reference clip.",
        homepage="https://github.com/Plachtaa/seed-vc",
        code_license="GPL-3.0",
        weights_license="GPL-3.0",
        commercial="conditional",
        commercial_note="Run as a separate program. Use only voices you have permission to use. Project archived Nov 2025.",
        tier="heavy",
        min_vram_gb=5,
        cpu_ok=False,
        windows="native",
        verified="adapter",
        archived=True,
        install=Install(
            "repo", repo="https://github.com/Plachtaa/seed-vc", python="3.10", download_gb=2
        ),
        quality={"voice": 7},
        paths=[_md("seed-vc", "inference.py")],
        gpl_note="Called as a separate process only.",
    ),
    EngineSpec(
        key="audiosr",
        name="AudioSR",
        tasks=["enhance"],
        summary="Upscales low quality audio to 48 kHz full bandwidth.",
        homepage="https://github.com/haoheliu/versatile_audio_super_resolution",
        code_license="MIT",
        weights_license="MIT",
        commercial="yes",
        commercial_note="",
        tier="heavy",
        min_vram_gb=8,
        cpu_ok=False,
        verified="adapter",
        install=Install("pip", pip=["audiosr"], download_gb=6),
        quality={"enhance": 8},
        modules=["audiosr"],
    ),
    EngineSpec(
        key="resemble-enhance",
        name="Resemble Enhance",
        tasks=["enhance", "denoise"],
        summary="Speech and vocal restoration: denoise plus bandwidth enhancement.",
        homepage="https://github.com/resemble-ai/resemble-enhance",
        code_license="MIT",
        weights_license="MIT",
        commercial="yes",
        commercial_note="",
        tier="heavy",
        min_vram_gb=4,
        cpu_ok=False,
        verified="adapter",
        install=Install("pip", pip=["resemble-enhance"], download_gb=1),
        quality={"enhance": 7, "denoise": 7},
        modules=["resemble_enhance"],
    ),
]

BY_KEY: dict[str, EngineSpec] = {e.key: e for e in ENGINES}


# Real VRAM needs, largest first. Sources: each project's README or issue tracker
# (checked Oct 2026). "wired" profiles are applied automatically by the Studio.
_P = VramProfile
VRAM_PROFILES: dict[str, list[VramProfile]] = {
    "acestep": [
        _P(
            "full",
            "Full quality",
            20,
            "sft DiT + 1.7B LM, bf16, no offload",
            wired=True,
            source="ACE-Step 1.5 GPU_COMPATIBILITY tier 6",
        ),
        _P(
            "12gb",
            "12-20 GB",
            12,
            "2B turbo DiT + 1.7B LM, INT8, no offload",
            "reduced",
            source="ACE-Step 1.5 gpu_config tier5",
        ),
        _P(
            "8gb",
            "8 GB card",
            6,
            "2B turbo DiT + 0.6B LM (pt backend), CPU offload, INT8 weights, fp16",
            "reduced",
            source="ACE-Step 1.5 gpu_config tier3/tier4",
        ),
        _P(
            "4gb",
            "4-6 GB card",
            4,
            "2B turbo DiT only (no LM), full CPU offload, INT8",
            "reduced",
            wired=False,
            source="ACE-Step 1.5 README: DiT-only mode",
        ),
    ],
    "diffrhythm": [
        _P("full", "Full quality", 12, "default decode", source="DiffRhythm README"),
        _P(
            "chunked",
            "8 GB card",
            8,
            "--chunked VAE decode",
            "reduced",
            source="DiffRhythm README: min 8 GB with --chunked",
        ),
    ],
    "yue": [
        _P(
            "full",
            "Official",
            24,
            "2 sessions; 80 GB+ for 4+ sessions / full songs",
            source="YuE README hardware section",
        ),
        _P(
            "exl2",
            "8 GB (community)",
            8,
            "YuE-exllamav2 4-bit stage 1 + Q4 cache, about 60 s per run",
            "reduced",
            wired=False,
            source="sgsdxzy/YuE-exllamav2",
        ),
    ],
    "songgeneration": [
        _P(
            "full",
            "With prompt audio",
            16,
            "--low_mem with a reference prompt",
            source="SongGeneration README",
        ),
        _P(
            "lowmem",
            "Low memory",
            10,
            "--low_mem --not_use_flash_attn, no prompt audio",
            "reduced",
            source="SongGeneration README",
        ),
    ],
    "stable-audio-open": [
        _P(
            "fp16",
            "fp16",
            6,
            "fp16 weights, clips up to 47 s, VAE decode peak near 6 GB",
            source="diffusers StableAudioPipeline",
        ),
    ],
    "musicgen": [
        _P("large", "Large", 16, "musicgen-large", source="audiocraft README"),
        _P(
            "medium",
            "Medium",
            8,
            "musicgen-medium",
            "reduced",
            wired=False,
            source="audiocraft README",
        ),
        _P(
            "small",
            "Small",
            4,
            "musicgen-small (auto on cards under 12 GB)",
            "reduced",
            source="audiocraft README",
        ),
    ],
    "audioldm2": [
        _P("fp16", "fp16", 6, "torch_dtype=float16", source="diffusers AudioLDM2Pipeline"),
    ],
    "applio": [
        _P(
            "infer",
            "Voice conversion",
            4,
            "RVC inference (training wants 6 GB+)",
            source="Applio docs",
        ),
    ],
    "seed-vc": [
        _P(
            "sing",
            "Singing (44 kHz)",
            6,
            "--fp16 True, f0-conditioned model",
            source="Seed-VC README",
        ),
        _P("speech", "Speech", 4, "--fp16 True, 22 kHz model", "reduced", source="Seed-VC README"),
    ],
    "audiosr": [
        _P("full", "Full", 8, "fp32 48 kHz upscaler", source="AudioSR issues"),
        _P("fp16", "fp16", 6, "fp16, short chunks", "reduced", source="AudioSR issues"),
    ],
    "resemble-enhance": [
        _P("full", "Full", 4, "enhancer + denoiser", source="resemble-enhance README"),
    ],
    "demucs": [
        _P(
            "gpu", "GPU", 4, "htdemucs, --segment 7 on small cards (or CPU)", source="demucs README"
        ),
    ],
    "audio-separator": [
        _P(
            "gpu",
            "GPU",
            3,
            "ONNX / MDX / Roformer models (or CPU)",
            source="audio-separator README",
        ),
    ],
}
VRAM_CAVEATS: dict[str, str] = {
    "audiosr": "Users report out-of-memory on 8 GB cards (RTX 2060 Super) even in fp16.",
    "yue": "Official code needs 24 GB+ and FlashAttention 2 (RTX 30 or newer). The 8 GB route is a community 4-bit fork the Studio does not install.",
    "songgeneration": "Needs 10 GB even in low memory mode.",
    "diffrhythm": "8 GB is the stated minimum: close other GPU apps (browser, games) first.",
    "stable-audio-open": "Keep clips short on 8 GB cards; long renders can spike during decoding.",
}
for _spec in ENGINES:
    if _spec.key in VRAM_PROFILES:
        _spec.vram_profiles = VRAM_PROFILES[_spec.key]
        if _spec.tier == "heavy":
            # Lowest need among the profiles the Studio actually applies.
            _spec.min_vram_gb = min(p.vram_gb for p in _spec.vram_profiles if p.wired)
    _spec.vram_caveat = VRAM_CAVEATS.get(_spec.key, "")
    _spec.needs_flash_attn = _spec.key == "yue"


def get(key: str) -> EngineSpec:
    if key not in BY_KEY:
        raise KeyError(f"Unknown engine '{key}'")
    return BY_KEY[key]


def health(spec: EngineSpec, deep: bool = False) -> dict[str, Any]:
    """Cheap install/health check. ``deep`` actually imports the modules."""
    if spec.install.kind == "builtin" and not spec.modules:
        return {"installed": True, "healthy": True, "detail": "Built in"}
    missing = [m for m in spec.modules if importlib.util.find_spec(m) is None]
    if spec.modules and missing:
        return {
            "installed": False,
            "healthy": False,
            "detail": f"Not installed (missing {', '.join(missing)})",
        }
    if spec.paths and not any(Path(p).exists() for p in spec.paths):
        env = os.environ.get(f"MUSER_{spec.key.upper().replace('-', '_')}_DIR")
        if not (env and Path(env).exists()):
            return {
                "installed": False,
                "healthy": False,
                "detail": f"Not installed (expected {spec.paths[0]})",
            }
    if spec.binaries and not any(shutil.which(b) for b in spec.binaries):
        return {
            "installed": False,
            "healthy": False,
            "detail": f"Missing program {spec.binaries[0]}",
        }
    if deep:
        for m in spec.modules:
            try:
                importlib.import_module(m)
            except Exception as e:  # pragma: no cover - environment dependent
                return {
                    "installed": True,
                    "healthy": False,
                    "detail": f"Installed but broken: {type(e).__name__}: {e}",
                }
    return {
        "installed": True,
        "healthy": True,
        "detail": "Ready" if spec.verified == "working" else "Installed (adapter, untested here)",
    }
