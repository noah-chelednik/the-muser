"""Built-in DSP (MIT, numpy + scipy only).

This is the always-available fallback for every effect in a chain and the home
of the processors Pedalboard does not have (true-peak limiter, stereo width,
de-esser, tanh saturation). Signals are float32 arrays shaped (frames, channels).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import minimum_filter1d
from scipy.signal import lfilter, resample_poly


def db2lin(db: float) -> float:
    return float(10 ** (db / 20))


# ---------------------------------------------------------------------------
# Biquads (RBJ audio EQ cookbook)
# ---------------------------------------------------------------------------


def _biquad(kind: str, sr: int, f: float, q: float = 0.707, gain_db: float = 0.0):
    f = float(np.clip(f, 10, sr * 0.49))
    A = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f / sr
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * max(q, 1e-3))
    if kind == "lowpass":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "highpass":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lowshelf":
        sa = 2 * math.sqrt(A) * alpha
        b = [
            A * ((A + 1) - (A - 1) * cw + sa),
            2 * A * ((A - 1) - (A + 1) * cw),
            A * ((A + 1) - (A - 1) * cw - sa),
        ]
        a = [
            (A + 1) + (A - 1) * cw + sa,
            -2 * ((A - 1) + (A + 1) * cw),
            (A + 1) + (A - 1) * cw - sa,
        ]
    elif kind == "highshelf":
        sa = 2 * math.sqrt(A) * alpha
        b = [
            A * ((A + 1) + (A - 1) * cw + sa),
            -2 * A * ((A - 1) + (A + 1) * cw),
            A * ((A + 1) + (A - 1) * cw - sa),
        ]
        a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    else:  # pragma: no cover
        raise ValueError(kind)
    b, a = np.array(b) / a[0], np.array(a) / a[0]
    return b, a


def biquad(
    x: np.ndarray, sr: int, kind: str, f: float, q: float = 0.707, gain_db: float = 0.0
) -> np.ndarray:
    b, a = _biquad(kind, sr, f, q, gain_db)
    return lfilter(b, a, x, axis=0).astype(np.float32)


# ---------------------------------------------------------------------------
# Dynamics
# ---------------------------------------------------------------------------


def _smooth_gain(
    target_db: np.ndarray, sr: int, attack_ms: float, release_ms: float, hop: int
) -> np.ndarray:
    """Attack/release smoothing of a gain curve computed per hop (block loop, fast)."""
    rate = sr / hop
    att = math.exp(-1.0 / max(attack_ms * 1e-3 * rate, 1e-6))
    rel = math.exp(-1.0 / max(release_ms * 1e-3 * rate, 1e-6))
    out = np.empty_like(target_db)
    g = 0.0
    for i, t in enumerate(target_db):
        c = att if t < g else rel  # gain going down = attack
        g = c * g + (1 - c) * t
        out[i] = g
    return out


def compressor(
    x: np.ndarray,
    sr: int,
    threshold_db: float = -18,
    ratio: float = 3,
    attack_ms: float = 10,
    release_ms: float = 120,
    makeup_db: float = 0,
    knee_db: float = 6,
) -> np.ndarray:
    hop = 32
    mono = np.max(np.abs(x), axis=1) if x.ndim > 1 else np.abs(x)
    n = int(math.ceil(len(mono) / hop))
    pad = np.pad(mono, (0, n * hop - len(mono)))
    lvl = 20 * np.log10(np.maximum(pad.reshape(n, hop).max(axis=1), 1e-9))
    over = lvl - threshold_db
    k = max(knee_db, 1e-6)
    gr = np.where(
        over <= -k / 2,
        0.0,
        np.where(
            over >= k / 2, over * (1 / ratio - 1), (1 / ratio - 1) * (over + k / 2) ** 2 / (2 * k)
        ),
    )
    g = _smooth_gain(gr, sr, attack_ms, release_ms, hop)
    gain = np.repeat(10 ** ((g + makeup_db) / 20), hop)[: len(mono)]
    return (x * (gain[:, None] if x.ndim > 1 else gain)).astype(np.float32)


def gate(
    x: np.ndarray,
    sr: int,
    threshold_db: float = -50,
    ratio: float = 4,
    attack_ms: float = 1,
    release_ms: float = 100,
) -> np.ndarray:
    hop = 64
    mono = np.max(np.abs(x), axis=1)
    n = int(math.ceil(len(mono) / hop))
    lvl = 20 * np.log10(
        np.maximum(np.pad(mono, (0, n * hop - len(mono))).reshape(n, hop).max(axis=1), 1e-9)
    )
    under = np.minimum(lvl - threshold_db, 0)
    gr = under * (ratio - 1)
    g = _smooth_gain(np.maximum(gr, -80), sr, attack_ms, release_ms, hop)
    return (x * np.repeat(10 ** (g / 20), hop)[: len(mono)][:, None]).astype(np.float32)


def true_peak_limit(
    x: np.ndarray,
    sr: int,
    ceiling_db: float = -1.0,
    release_ms: float = 80,
    lookahead_ms: float = 1.5,
) -> np.ndarray:
    """Look-ahead brickwall limiter on the 4x oversampled peak (true-peak safe)."""
    if x.ndim == 1:
        x = x[:, None]
    n = x.shape[0]
    ceil = db2lin(ceiling_db)
    target = ceil * 0.97  # margin for inter-sample error of the estimate
    up = np.abs(resample_poly(x, 4, 1, axis=0)).max(axis=1)[: 4 * n]
    up = np.pad(up, (0, 4 * n - len(up))).reshape(n, 4).max(axis=1)
    peak = np.maximum(up, np.abs(x).max(axis=1))
    need = np.minimum(1.0, target / np.maximum(peak, 1e-12))
    if need.min() >= 1.0:
        return x.astype(np.float32)
    la = max(2, int(lookahead_ms * 1e-3 * sr))
    held = minimum_filter1d(need, size=2 * la + 1, mode="nearest")
    smooth = np.convolve(held, np.ones(la) / la, mode="same")
    red = 1.0 - np.minimum(smooth, held)
    # release: block-wise peak-hold with exponential recovery
    hop = 32
    nb = int(math.ceil(n / hop))
    rb = np.pad(red, (0, nb * hop - n)).reshape(nb, hop).max(axis=1)
    rel = math.exp(-hop / max(release_ms * 1e-3 * sr, 1))
    out = np.empty(nb)
    y = 0.0
    for i, r in enumerate(rb):
        y = r if r > y else rel * y
        out[i] = y
    rel_curve = np.convolve(np.repeat(out, hop)[:n], np.ones(hop) / hop, mode="same")
    gain = 1.0 - np.maximum(red, rel_curve)
    yv = x * gain[:, None]
    tp = float(np.abs(resample_poly(yv, 4, 1, axis=0)).max())
    if tp > ceil:
        yv *= ceil / tp * 0.999
    return yv.astype(np.float32)


def deesser(
    x: np.ndarray, sr: int, frequency_hz: float = 6500, threshold_db: float = -30, ratio: float = 4
) -> np.ndarray:
    hi = biquad(biquad(x, sr, "highpass", frequency_hz), sr, "highpass", frequency_hz)
    lo = x - hi
    return (
        lo + compressor(hi, sr, threshold_db, ratio, attack_ms=1, release_ms=60, knee_db=3)
    ).astype(np.float32)


# ---------------------------------------------------------------------------
# Colour / space
# ---------------------------------------------------------------------------


def saturation(x: np.ndarray, sr: int, drive_db: float = 6, mix: float = 1.0) -> np.ndarray:
    d = db2lin(drive_db)
    wet = np.tanh(x * d) / math.tanh(d) if d > 1e-3 else x
    return (x * (1 - mix) + wet * mix).astype(np.float32)


def bitcrush(x: np.ndarray, sr: int, bit_depth: float = 8, mix: float = 1.0) -> np.ndarray:
    steps = 2 ** (max(bit_depth, 1) - 1)
    wet = np.round(x * steps) / steps
    return (x * (1 - mix) + wet * mix).astype(np.float32)


def width(x: np.ndarray, sr: int, width: float = 1.0) -> np.ndarray:
    if x.shape[1] < 2:
        return x
    m = (x[:, 0] + x[:, 1]) / 2
    s = (x[:, 0] - x[:, 1]) / 2 * width
    return np.stack([m + s, m - s], axis=1).astype(np.float32)


def _fb_comb(x: np.ndarray, d: int, g: float, damp: float = 0.0) -> np.ndarray:
    """y[n] = x[n-d] + g * lp(y)[n-d], computed block-wise (d samples per step)."""
    n = x.shape[0]
    nb = int(math.ceil(n / d)) + 1
    shape = (nb * d,) + x.shape[1:]
    xp = np.zeros(shape, dtype=np.float64)
    xp[d : d + n] = x
    y = np.zeros(shape, dtype=np.float64)
    prev = np.zeros((d,) + x.shape[1:])
    for k in range(1, nb):
        blk = xp[k * d : (k + 1) * d]
        if damp > 0:
            sh = np.concatenate([prev[:1], prev[:-1]], axis=0)
            fbk = (1 - damp) * prev + damp * sh
        else:
            fbk = prev
        cur = blk + g * fbk
        y[k * d : (k + 1) * d] = cur
        prev = cur
    return y[:n]


def _allpass(x: np.ndarray, d: int, g: float = 0.5) -> np.ndarray:
    n = x.shape[0]
    nb = int(math.ceil(n / d))
    xp = np.zeros(((nb + 1) * d,) + x.shape[1:])
    xp[:n] = x
    y = np.zeros_like(xp)
    yprev = np.zeros((d,) + x.shape[1:])
    xprev = np.zeros_like(yprev)
    for k in range(nb):
        xb = xp[k * d : (k + 1) * d]
        yb = -g * xb + xprev + g * yprev
        y[k * d : (k + 1) * d] = yb
        xprev, yprev = xb, yb
    return y[:n]


def delay(
    x: np.ndarray, sr: int, time_ms: float = 250, feedback: float = 0.3, mix: float = 0.2
) -> np.ndarray:
    d = max(1, int(time_ms * 1e-3 * sr))
    wet = _fb_comb(x, d, min(feedback, 0.95))
    return (x * (1 - mix * 0.5) + wet * mix).astype(np.float32)


def chorus(
    x: np.ndarray,
    sr: int,
    rate_hz: float = 1.0,
    depth: float = 0.25,
    centre_delay_ms: float = 7,
    feedback: float = 0.0,
    mix: float = 0.5,
) -> np.ndarray:
    n = x.shape[0]
    t = np.arange(n) / sr
    out = np.empty_like(x)
    for ch in range(x.shape[1]):
        phase = ch * math.pi / 2
        dl = (
            (centre_delay_ms + depth * centre_delay_ms * np.sin(2 * math.pi * rate_hz * t + phase))
            * 1e-3
            * sr
        )
        idx = np.arange(n) - dl
        i0 = np.clip(np.floor(idx).astype(int), 0, n - 1)
        frac = idx - np.floor(idx)
        i1 = np.clip(i0 + 1, 0, n - 1)
        wet = x[i0, ch] * (1 - frac) + x[i1, ch] * frac
        out[:, ch] = x[:, ch] * (1 - mix) + wet * mix
    return out.astype(np.float32)


def reverb(
    x: np.ndarray,
    sr: int,
    room_size: float = 0.5,
    damping: float = 0.5,
    width: float = 1.0,
    mix: float = 0.25,
) -> np.ndarray:
    """Freeverb-style: 8 parallel damped combs + 4 series allpasses per channel.

    Returns the same length as the input (the tail beyond the end is dropped so
    stems stay aligned)."""
    scale = sr / 44100
    combs = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
    aps = [556, 441, 341, 225]
    fb = 0.7 + 0.28 * room_size
    damp = 0.05 + 0.4 * damping
    xin = x.astype(np.float64) * 0.015
    wet = np.zeros_like(xin)
    for ch in range(x.shape[1]):
        spread = 23 * (ch % 2)
        acc = np.zeros(xin.shape[0])
        for c in combs:
            acc += _fb_comb(xin[:, ch], int((c + spread) * scale), fb, damp)
        for ap in aps:
            acc = _allpass(acc, int((ap + spread) * scale))
        wet[:, ch] = acc
    if x.shape[1] >= 2:
        wet = width_fn(wet, width)
    y = x * (1 - mix * 0.4) + wet * mix * 3.0
    return y.astype(np.float32)


def width_fn(x: np.ndarray, w: float) -> np.ndarray:
    return width(x, 0, w)


def trim_tail(y: np.ndarray, n: int) -> np.ndarray:
    return y[:n] if y.shape[0] > n else np.pad(y, ((0, n - y.shape[0]), (0, 0)))


def match_eq(
    x: np.ndarray, ref: np.ndarray, sr: int, amount: float = 1.0, max_db: float = 12.0
) -> np.ndarray:
    """Built-in reference matching: smoothed long-term spectrum match (MIT)."""
    from scipy.signal import istft, stft, welch

    def spec(sig):
        mono = sig.mean(axis=1)
        f, p = welch(mono, sr, nperseg=4096)
        return f, p

    f, px = spec(x)
    _, pr = spec(ref)
    ratio_db = 10 * np.log10(np.maximum(pr, 1e-14) / np.maximum(px, 1e-14))
    # 1/3-octave-ish smoothing in log frequency
    sm = np.copy(ratio_db)
    for i, fi in enumerate(f):
        lo, hi = fi / 2 ** (1 / 6), fi * 2 ** (1 / 6)
        m = (f >= lo) & (f <= hi)
        sm[i] = ratio_db[m].mean() if m.any() else ratio_db[i]
    sm -= np.interp(1000, f, sm)  # match tone, not level
    sm = np.clip(sm * amount, -max_db, max_db)
    sm[f < 20] = sm[np.argmax(f >= 20)] if (f >= 20).any() else 0
    out = np.empty_like(x)
    for ch in range(x.shape[1]):
        ff, tt, Z = stft(x[:, ch], sr, nperseg=4096)
        g = 10 ** (np.interp(ff, f, sm) / 20)
        _, y = istft(Z * g[:, None], sr, nperseg=4096)
        out[:, ch] = trim_tail(y[:, None], x.shape[0])[:, 0]
    return out.astype(np.float32)


def spectral_gate(x: np.ndarray, sr: int, strength: float = 0.8) -> np.ndarray:
    """Built-in noise reduction: stationary spectral gating (MIT)."""
    from scipy.signal import istft, stft

    out = np.empty_like(x)
    for ch in range(x.shape[1]):
        f, t, Z = stft(x[:, ch], sr, nperseg=2048)
        mag = np.abs(Z)
        noise = np.percentile(mag, 15, axis=1, keepdims=True)
        thresh = noise * (1.5 + 2.5 * strength)
        mask = np.clip((mag - thresh) / np.maximum(mag, 1e-12), 0, 1)
        mask = np.maximum(mask, 1 - strength)  # floor keeps it natural
        from scipy.ndimage import uniform_filter

        mask = uniform_filter(mask, size=(3, 5))
        _, y = istft(Z * mask, sr, nperseg=2048)
        out[:, ch] = trim_tail(y[:, None], x.shape[0])[:, 0]
    return out.astype(np.float32)
