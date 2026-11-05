"""Loudness (ITU-R BS.1770-4 / EBU R128) and true-peak measurement.

Uses ``pyloudnorm`` (MIT) when installed and a built-in implementation of the
same K-weighted, gated algorithm otherwise, so mastering targets always work.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter, resample_poly


def _k_weight_coeffs(sr: int) -> list[tuple[np.ndarray, np.ndarray]]:
    # Pre-filter (high shelf) and RLB high-pass, re-derived for any sample rate
    # exactly as pyloudnorm / libebur128 do.
    import math

    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    K = math.tan(math.pi * fc / sr)
    Vh = 10 ** (G / 20)
    Vb = Vh**0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = np.array(
        [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0]
    )
    a1 = np.array([1.0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0])
    Q2, fc2 = 0.5003270373238773, 38.13547087602444
    K2 = math.tan(math.pi * fc2 / sr)
    a0b = 1 + K2 / Q2 + K2 * K2
    b2 = np.array([1.0, -2.0, 1.0])
    a2 = np.array([1.0, 2 * (K2 * K2 - 1) / a0b, (1 - K2 / Q2 + K2 * K2) / a0b])
    return [(b1, a1), (b2, a2)]


def integrated_lufs_builtin(x: np.ndarray, sr: int) -> float:
    if x.ndim == 1:
        x = x[:, None]
    y = x.astype(np.float64)
    for b, a in _k_weight_coeffs(sr):
        y = lfilter(b, a, y, axis=0)
    block, hop = int(0.4 * sr), int(0.1 * sr)
    if y.shape[0] < block:
        y = np.pad(y, ((0, block - y.shape[0]), (0, 0)))
    n = 1 + (y.shape[0] - block) // hop
    idx = np.arange(block)[None, :] + hop * np.arange(n)[:, None]
    z = np.mean(y[idx] ** 2, axis=1)  # (blocks, ch)
    g = np.ones(z.shape[1])  # L, R (surround weights not needed here)
    lk = -0.691 + 10 * np.log10(np.maximum((z * g).sum(axis=1), 1e-20))
    z_abs = z[lk > -70]
    if not len(z_abs):
        return -float("inf")
    rel = -0.691 + 10 * np.log10(max((z_abs.mean(axis=0) * g).sum(), 1e-20)) - 10
    keep = (lk > -70) & (lk > rel)
    if not keep.any():
        return -float("inf")
    return float(-0.691 + 10 * np.log10(max((z[keep].mean(axis=0) * g).sum(), 1e-20)))


def integrated_lufs(x: np.ndarray, sr: int) -> float:
    try:
        import pyloudnorm as pyln

        data = x if x.ndim > 1 else x[:, None]
        if data.shape[0] < int(0.4 * sr):
            data = np.pad(data, ((0, int(0.4 * sr) - data.shape[0]), (0, 0)))
        return float(pyln.Meter(sr).integrated_loudness(data.astype(np.float64)))
    except ImportError:
        return integrated_lufs_builtin(x, sr)


def true_peak_db(x: np.ndarray, sr: int = 44100, oversample: int = 4) -> float:
    """dBTP estimate via 4x polyphase oversampling (BS.1770 Annex 2 style)."""
    if not x.size:
        return -float("inf")
    y = resample_poly(x, oversample, 1, axis=0)
    p = max(float(np.max(np.abs(y))), float(np.max(np.abs(x))))
    return 20 * np.log10(max(p, 1e-12))


def analyze(x: np.ndarray, sr: int) -> dict:
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if x.size else 0.0
    lufs = integrated_lufs(x, sr)
    return {
        "lufs": round(lufs, 2) if np.isfinite(lufs) else None,
        "true_peak_db": round(true_peak_db(x, sr), 2),
        "peak_db": round(20 * np.log10(max(float(np.max(np.abs(x))), 1e-12)), 2),
        "rms_db": round(20 * np.log10(max(rms, 1e-12)), 2),
        "duration_s": round(x.shape[0] / sr, 3),
        "sample_rate": sr,
        "channels": int(x.shape[1]) if x.ndim > 1 else 1,
    }
