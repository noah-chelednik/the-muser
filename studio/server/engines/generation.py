"""Generation adapters for heavy GPU models.

These follow each project's documented CLI / Python API. They are written and
type-checked here but NOT run on this CPU-only build box, so the registry marks
them ``adapter`` and the UI shows "untested here". Each adapter writes a WAV and
returns its path; every failure becomes a friendly message.

Repo-based models run in their own venv (``models/<key>/.venv``) as a separate
process, which also keeps GPL / custom-licence code out of the Studio process.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import registry
from .errors import FriendlyError

Progress = Callable[[str], None]


@dataclass
class GenParams:
    prompt: str
    lyrics: str = ""
    duration_s: float = 30.0
    steps: int = 0  # 0 = engine default
    guidance: float = 0.0  # 0 = engine default
    seed: int = -1
    temperature: float = 1.0

    def clamp(self) -> GenParams:
        self.duration_s = float(min(max(self.duration_s, 5), 285))
        self.steps = int(min(max(self.steps, 0), 500))
        self.guidance = float(min(max(self.guidance, 0), 20))
        self.temperature = float(min(max(self.temperature, 0.1), 2.0))
        return self


def _repo(key: str) -> Path:
    env = os.environ.get(f"MUSER_{key.upper().replace('-', '_')}_DIR")
    p = Path(env) if env else Path(registry.MODELS_DIR) / key
    if not p.exists():
        raise FriendlyError(
            f"{registry.get(key).name} is not installed.", "Open System and press Install."
        )
    return p


def _venv_python(repo: Path) -> str:
    for c in (repo / ".venv" / "Scripts" / "python.exe", repo / ".venv" / "bin" / "python"):
        if c.exists():
            return str(c)
    return sys.executable


def _run(
    cmd: list[str],
    cwd: Path,
    progress: Progress | None,
    env: dict | None = None,
    timeout: int = 3600,
) -> None:
    if progress:
        progress(
            "Running "
            + Path(cmd[1] if len(cmd) > 1 else cmd[0]).name
            + " (this can take a few minutes) ..."
        )
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, **(env or {})},
    )
    tail: list[str] = []
    assert proc.stdout is not None
    start = time.time()
    for line in proc.stdout:
        tail = (tail + [line.rstrip()])[-40:]
        if progress and line.strip():
            progress(line.strip()[-160:])
        if time.time() - start > timeout:
            proc.kill()
            raise FriendlyError("The model took too long and was stopped.")
    if proc.wait() != 0:
        raise RuntimeError("\n".join(tail[-15:]))


def _newest_audio(d: Path, prefer: str = "") -> Path:
    files = [p for p in d.rglob("*") if p.suffix.lower() in (".wav", ".mp3", ".flac")]
    if prefer:
        files = [p for p in files if prefer in p.name.lower()] or files
    if not files:
        raise FriendlyError("The model finished but no audio file appeared.")
    return max(files, key=lambda p: p.stat().st_mtime)


def _to_wav(src: Path, out: Path) -> str:
    from . import audio_io

    x, sr = audio_io.read(src)
    audio_io.write(out, x, sr)
    return str(out)


def lyrics_to_lrc(lyrics: str, duration_s: float) -> str:
    """DiffRhythm wants timestamped LRC. Spread lines evenly after a short intro."""
    lines = [
        ln.strip() for ln in lyrics.splitlines() if ln.strip() and not ln.strip().startswith("[")
    ]
    if not lines:
        return ""
    start, end = min(10.0, duration_s * 0.1), duration_s * 0.92
    step = (end - start) / max(len(lines), 1)
    out = []
    for i, ln in enumerate(lines):
        t = start + i * step
        out.append(f"[{int(t // 60):02d}:{t % 60:05.2f}]{ln}")
    return "\n".join(out)


# --------------------------------------------------------------------------- adapters


def diffrhythm(p: GenParams, out: Path, progress: Progress | None, vram_gb: float) -> str:
    repo = _repo("diffrhythm")
    work = out.parent / "diffrhythm_work"
    work.mkdir(parents=True, exist_ok=True)
    lrc = work / "lyrics.lrc"
    lrc.write_text(lyrics_to_lrc(p.lyrics, p.duration_s), encoding="utf-8")
    full = p.duration_s > 95
    cmd = [
        _venv_python(repo),
        "infer/infer.py",
        "--lrc-path",
        str(lrc),
        "--ref-prompt",
        p.prompt,
        "--audio-length",
        str(int(p.duration_s) if full else 95),
        "--repo-id",
        "ASLP-lab/DiffRhythm-full" if full else "ASLP-lab/DiffRhythm-1_2",
        "--output-dir",
        str(work),
    ]
    if vram_gb < 12:
        cmd.append("--chunked")
    _run(cmd, repo, progress)
    return _to_wav(_newest_audio(work), out)


def yue(p: GenParams, out: Path, progress: Progress | None, vram_gb: float) -> str:
    if 0 < vram_gb < 16:
        raise FriendlyError(
            f"YuE is not recommended for your {vram_gb:g} GB card: the official code needs 24 GB.",
            "Use ACE-Step 1.5 for full songs with vocals on 8 to 12 GB cards.",
        )
    repo = _repo("yue")
    work = out.parent / "yue_work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "genre.txt").write_text(p.prompt, encoding="utf-8")
    (work / "lyrics.txt").write_text(p.lyrics or "[verse]\nla la la", encoding="utf-8")
    segments = 2 if vram_gb < 24 else max(2, min(6, int(p.duration_s // 30)))
    cmd = [
        _venv_python(repo),
        "infer.py",
        "--cuda_idx",
        "0",
        "--stage1_model",
        "m-a-p/YuE-s1-7B-anneal-en-cot",
        "--stage2_model",
        "m-a-p/YuE-s2-1B-general",
        "--genre_txt",
        str(work / "genre.txt"),
        "--lyrics_txt",
        str(work / "lyrics.txt"),
        "--run_n_segments",
        str(segments),
        "--stage2_batch_size",
        "4" if vram_gb >= 24 else "2",
        "--output_dir",
        str(work),
        "--max_new_tokens",
        "3000",
        "--repetition_penalty",
        "1.1",
    ]
    if p.seed >= 0:
        cmd += ["--seed", str(p.seed)]
    _run(cmd, repo / "inference", progress)
    return _to_wav(_newest_audio(work, prefer="mix"), out)


def songgeneration(p: GenParams, out: Path, progress: Progress | None, vram_gb: float) -> str:
    repo = _repo("songgeneration")
    work = out.parent / "levo_work"
    work.mkdir(parents=True, exist_ok=True)
    lyric = (
        " ; ".join(f"[verse] {ln.strip()}" for ln in p.lyrics.splitlines() if ln.strip())
        or "[inst-medium]"
    )
    (work / "in.jsonl").write_text(
        json.dumps({"idx": "muser", "gt_lyric": lyric, "descriptions": p.prompt}) + "\n",
        encoding="utf-8",
    )
    bash = shutil.which("bash") or "bash"
    _run(
        [
            bash,
            "generate.sh",
            str(repo / "ckpt" / "songgeneration_base"),
            str(work / "in.jsonl"),
            str(work / "out"),
            # Low memory mode (about 10 GB) and plain attention so RTX 20 cards work.
            *(["--low_mem"] if vram_gb < 20 else []),
            "--not_use_flash_attn",
        ],
        repo,
        progress,
    )
    return _to_wav(_newest_audio(work / "out"), out)


def _seed(p: GenParams):
    import torch

    g = torch.Generator("cuda" if torch.cuda.is_available() else "cpu")
    return g.manual_seed(p.seed if p.seed >= 0 else int(time.time()) % 2**31)


def stable_audio_open(p: GenParams, out: Path, progress: Progress | None, vram_gb: float) -> str:
    import soundfile as sf
    import torch
    from diffusers import StableAudioPipeline  # type: ignore

    if progress:
        progress(
            "Loading Stable Audio Open (gated model: accept the licence on Hugging Face first) ..."
        )
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = StableAudioPipeline.from_pretrained(
        "stabilityai/stable-audio-open-1.0",
        torch_dtype=torch.float16 if dev == "cuda" else torch.float32,
    ).to(dev)
    audio = pipe(
        p.prompt,
        negative_prompt="low quality",
        num_inference_steps=p.steps or 100,
        guidance_scale=p.guidance or 7.0,
        audio_end_in_s=min(p.duration_s, 47.0),
        num_waveforms_per_prompt=1,
        generator=_seed(p),
    ).audios
    sf.write(str(out), audio[0].T.float().cpu().numpy(), pipe.vae.sampling_rate)
    return str(out)


def musicgen(p: GenParams, out: Path, progress: Progress | None, vram_gb: float) -> str:
    import soundfile as sf
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration  # type: ignore

    name = "facebook/musicgen-medium" if vram_gb >= 12 else "facebook/musicgen-small"
    if progress:
        progress(f"Loading {name} ...")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    proc = AutoProcessor.from_pretrained(name)
    model = MusicgenForConditionalGeneration.from_pretrained(name).to(dev)
    if p.seed >= 0:
        torch.manual_seed(p.seed)
    inputs = proc(text=[p.prompt], padding=True, return_tensors="pt").to(dev)
    wav = model.generate(
        **inputs,
        do_sample=True,
        guidance_scale=p.guidance or 3.0,
        temperature=p.temperature,
        max_new_tokens=int(min(p.duration_s, 30) * 50),
    )
    sf.write(str(out), wav[0, 0].cpu().numpy(), model.config.audio_encoder.sampling_rate)
    return str(out)


def audioldm2(p: GenParams, out: Path, progress: Progress | None, vram_gb: float) -> str:
    import soundfile as sf
    import torch
    from diffusers import AudioLDM2Pipeline  # type: ignore

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = AudioLDM2Pipeline.from_pretrained(
        "cvssp/audioldm2-music", torch_dtype=torch.float16 if dev == "cuda" else torch.float32
    ).to(dev)
    audio = pipe(
        p.prompt,
        num_inference_steps=p.steps or 200,
        audio_length_in_s=min(p.duration_s, 30),
        guidance_scale=p.guidance or 3.5,
        generator=_seed(p),
    ).audios[0]
    sf.write(str(out), audio, 16000)
    return str(out)


ADAPTERS: dict[str, Callable[[GenParams, Path, Progress | None, float], str]] = {
    "diffrhythm": diffrhythm,
    "yue": yue,
    "songgeneration": songgeneration,
    "stable-audio-open": stable_audio_open,
    "musicgen": musicgen,
    "audioldm2": audioldm2,
}


def run(engine: str, params: GenParams, out: Path, progress: Progress | None = None) -> str:
    from . import hardware

    if engine not in ADAPTERS:
        raise FriendlyError(f"'{engine}' is not a generation adapter.")
    hw = hardware.detect()
    out.parent.mkdir(parents=True, exist_ok=True)
    return ADAPTERS[engine](params.clamp(), out, progress, hw.vram_gb)
