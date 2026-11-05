"""Noise cleanup engines: DeepFilterNet, noisereduce, built-in spectral gate."""

from __future__ import annotations

import numpy as np

from . import audio_io, dsp
from .errors import FriendlyError

_DF_STATE: dict = {}


def deepfilternet(x: np.ndarray, sr: int, strength: float = 1.0) -> np.ndarray:
    import torch
    from df.enhance import enhance, init_df  # type: ignore

    if "model" not in _DF_STATE:
        model, state, _ = init_df(log_level="ERROR")
        _DF_STATE.update(model=model, state=state)
    model, state = _DF_STATE["model"], _DF_STATE["state"]
    dsr = state.sr()
    y = audio_io.resample(x, sr, dsr)
    atten = None if strength >= 1 else float(6 + 54 * strength)  # dB limit for gentler settings
    out = (
        enhance(model, state, torch.from_numpy(np.ascontiguousarray(y.T)), atten_lim_db=atten)
        .numpy()
        .T
    )
    out = audio_io.resample(out.astype(np.float32), dsr, sr)
    n = min(len(out), len(x))
    res = x.copy()
    res[:n] = out[:n]
    return res


def noisereduce(x: np.ndarray, sr: int, strength: float = 1.0) -> np.ndarray:
    import noisereduce as nr  # type: ignore

    y = nr.reduce_noise(
        y=x.T, sr=sr, prop_decrease=float(np.clip(strength, 0.05, 1.0)), stationary=False
    )
    return np.asarray(y, dtype=np.float32).T.reshape(x.shape)


def clean(
    x: np.ndarray, sr: int, engine: str = "auto", strength: float = 0.8
) -> tuple[np.ndarray, str]:
    from . import selector

    if engine == "auto":
        engine = selector.select("denoise").engine
    if engine == "deepfilternet":
        return deepfilternet(x, sr, strength), engine
    if engine == "noisereduce":
        return noisereduce(x, sr, strength), engine
    if engine == "builtin-dsp":
        return dsp.spectral_gate(x, sr, strength), engine
    raise FriendlyError(f"'{engine}' can't clean up noise.")
