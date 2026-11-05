"""Voice conversion and enhancement adapters (GPU models, untested here)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .errors import FriendlyError


def convert(
    engine: str, src: str, out: str, model_path: str = "", reference: str = "", transpose: int = 0
) -> str:
    if engine == "applio":
        from src.voice.rvc_wrapper import convert_voice

        if not model_path:
            raise FriendlyError("Pick a voice model (.pth) first.")
        res = convert_voice(src, model_path, transpose=transpose, output_path=out)
        return res.get("output_path", out) if isinstance(res, dict) else out
    if engine == "seed-vc":
        from src.voice.seedvc_wrapper import convert_voice_seedvc

        if not reference:
            raise FriendlyError("Add a short reference clip of the target voice first.")
        res = convert_voice_seedvc(src, reference, output_path=out)
        return res.get("output_path", out) if isinstance(res, dict) else out
    raise FriendlyError(f"'{engine}' can't convert voices.")


def enhance(engine: str, src: str, out: str) -> str:
    if engine == "audiosr":
        import soundfile as sf
        from audiosr import build_model, super_resolution  # type: ignore

        model = build_model(model_name="basic", device="auto")
        wav = super_resolution(model, src, guidance_scale=3.5, ddim_steps=50)
        sf.write(out, wav.squeeze().T if wav.ndim > 1 else wav, 48000)
        return out
    if engine == "resemble-enhance":
        exe = shutil.which("resemble-enhance")
        if not exe:
            raise FriendlyError("Resemble Enhance is not installed.")
        with tempfile.TemporaryDirectory() as ind, tempfile.TemporaryDirectory() as outd:
            shutil.copy(src, Path(ind) / "in.wav")
            subprocess.run([exe, ind, outd], check=True, capture_output=True)
            shutil.copy(next(Path(outd).rglob("*.wav")), out)
        return out
    raise FriendlyError(f"'{engine}' can't enhance audio.")
