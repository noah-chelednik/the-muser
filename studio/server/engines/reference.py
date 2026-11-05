"""Reference matching: Matchering 2, or the built-in spectral match."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from . import audio_io, dsp, loudness
from .errors import FriendlyError


def matchering(target: str, reference: str, out_path: str) -> None:
    import matchering as mg  # type: ignore

    mg.log(lambda *_: None)
    mg.process(target=target, reference=reference, results=[mg.pcm24(out_path)])


def builtin(x: np.ndarray, ref: np.ndarray, sr: int, amount: float = 1.0) -> np.ndarray:
    y = dsp.match_eq(x, ref, sr, amount=amount)
    gain = loudness.integrated_lufs(ref, sr) - loudness.integrated_lufs(y, sr)
    y = y * dsp.db2lin(float(np.clip(gain, -24, 24)))
    return dsp.true_peak_limit(y, sr, ceiling_db=-1.0)


def match(
    target: str, reference: str, out_path: str, engine: str = "auto", amount: float = 1.0
) -> str:
    from . import selector

    if engine == "auto":
        engine = selector.select("match").engine
    if engine == "matchering":
        with tempfile.TemporaryDirectory() as td:
            tmp = str(Path(td) / "m.wav")
            matchering(target, reference, tmp)
            y, sr = audio_io.read(tmp)
            if amount < 1.0:
                x, _ = audio_io.read(target, sr)
                n = min(len(x), len(y))
                y = y[:n] * amount + audio_io.to_stereo(x[:n]) * (1 - amount)
            audio_io.write(out_path, y, sr)
        return engine
    if engine == "builtin-dsp":
        x, sr = audio_io.read(target)
        ref, _ = audio_io.read(reference, sr)
        audio_io.write(out_path, builtin(x, ref, sr, amount), sr)
        return engine
    raise FriendlyError(f"'{engine}' can't match a reference.")
