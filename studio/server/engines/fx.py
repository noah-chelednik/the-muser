"""Effect chains: a JSON list of plugins rendered with Pedalboard when it is
installed, and with the built-in DSP otherwise (same parameters, same names).

A chain looks like::

    [{"type": "highpass", "params": {"cutoff_hz": 30}},
     {"type": "compressor", "params": {"threshold_db": -20, "ratio": 3}},
     {"type": "reverb", "params": {"mix": 0.2}, "bypass": false}]
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import dsp

P = dict  # param spec: {min, max, default, unit, label}


def _p(
    lo: float, hi: float, default: float, unit: str = "", label: str = "", step: float | None = None
) -> dict:
    d = {"min": lo, "max": hi, "default": default, "unit": unit, "label": label}
    if step is not None:
        d["step"] = step
    return d


PLUGINS: dict[str, dict[str, Any]] = {
    "gain": {
        "label": "Gain",
        "group": "utility",
        "params": {"gain_db": _p(-24, 24, 0, "dB", "Gain")},
    },
    "highpass": {
        "label": "High-pass",
        "group": "eq",
        "params": {"cutoff_hz": _p(20, 2000, 30, "Hz", "Cutoff")},
    },
    "lowpass": {
        "label": "Low-pass",
        "group": "eq",
        "params": {"cutoff_hz": _p(500, 20000, 18000, "Hz", "Cutoff")},
    },
    "lowshelf": {
        "label": "Low shelf",
        "group": "eq",
        "params": {
            "cutoff_hz": _p(30, 600, 100, "Hz", "Freq"),
            "gain_db": _p(-18, 18, 0, "dB", "Gain"),
            "q": _p(0.3, 2, 0.7, "", "Q"),
        },
    },
    "peak": {
        "label": "Bell EQ",
        "group": "eq",
        "params": {
            "freq_hz": _p(40, 16000, 1000, "Hz", "Freq"),
            "gain_db": _p(-18, 18, 0, "dB", "Gain"),
            "q": _p(0.2, 10, 1.0, "", "Q"),
        },
    },
    "highshelf": {
        "label": "High shelf",
        "group": "eq",
        "params": {
            "cutoff_hz": _p(1500, 16000, 8000, "Hz", "Freq"),
            "gain_db": _p(-18, 18, 0, "dB", "Gain"),
            "q": _p(0.3, 2, 0.7, "", "Q"),
        },
    },
    "compressor": {
        "label": "Compressor",
        "group": "dynamics",
        "params": {
            "threshold_db": _p(-60, 0, -18, "dB", "Threshold"),
            "ratio": _p(1, 20, 3, ":1", "Ratio"),
            "attack_ms": _p(0.1, 200, 10, "ms", "Attack"),
            "release_ms": _p(10, 2000, 120, "ms", "Release"),
            "makeup_db": _p(0, 24, 0, "dB", "Makeup"),
        },
    },
    "gate": {
        "label": "Noise gate",
        "group": "dynamics",
        "params": {
            "threshold_db": _p(-100, 0, -50, "dB", "Threshold"),
            "ratio": _p(1, 10, 4, ":1", "Ratio"),
            "attack_ms": _p(0.1, 50, 1, "ms", "Attack"),
            "release_ms": _p(10, 1000, 100, "ms", "Release"),
        },
    },
    "deesser": {
        "label": "De-esser",
        "group": "dynamics",
        "params": {
            "frequency_hz": _p(3000, 12000, 6500, "Hz", "Freq"),
            "threshold_db": _p(-60, 0, -30, "dB", "Threshold"),
            "ratio": _p(1, 10, 4, ":1", "Ratio"),
        },
    },
    "saturation": {
        "label": "Saturation",
        "group": "color",
        "params": {"drive_db": _p(0, 36, 6, "dB", "Drive"), "mix": _p(0, 1, 1, "", "Mix")},
    },
    "bitcrush": {
        "label": "Bitcrush",
        "group": "color",
        "params": {"bit_depth": _p(2, 16, 8, "bit", "Bits", 1), "mix": _p(0, 1, 1, "", "Mix")},
    },
    "chorus": {
        "label": "Chorus",
        "group": "modulation",
        "params": {
            "rate_hz": _p(0.05, 10, 1, "Hz", "Rate"),
            "depth": _p(0, 1, 0.25, "", "Depth"),
            "centre_delay_ms": _p(1, 30, 7, "ms", "Delay"),
            "feedback": _p(-0.9, 0.9, 0, "", "Feedback"),
            "mix": _p(0, 1, 0.5, "", "Mix"),
        },
    },
    "phaser": {
        "label": "Phaser",
        "group": "modulation",
        "params": {
            "rate_hz": _p(0.05, 10, 1, "Hz", "Rate"),
            "depth": _p(0, 1, 0.5, "", "Depth"),
            "centre_frequency_hz": _p(100, 5000, 1300, "Hz", "Centre"),
            "feedback": _p(-0.9, 0.9, 0, "", "Feedback"),
            "mix": _p(0, 1, 0.5, "", "Mix"),
        },
    },
    "delay": {
        "label": "Delay",
        "group": "space",
        "params": {
            "time_ms": _p(10, 2000, 250, "ms", "Time"),
            "feedback": _p(0, 0.95, 0.3, "", "Feedback"),
            "mix": _p(0, 1, 0.2, "", "Mix"),
        },
    },
    "reverb": {
        "label": "Reverb",
        "group": "space",
        "params": {
            "room_size": _p(0, 1, 0.5, "", "Size"),
            "damping": _p(0, 1, 0.5, "", "Damping"),
            "width": _p(0, 1, 1, "", "Width"),
            "mix": _p(0, 1, 0.25, "", "Mix"),
        },
    },
    "width": {
        "label": "Stereo width",
        "group": "space",
        "params": {"width": _p(0, 2, 1, "x", "Width")},
    },
    "limiter": {
        "label": "True-peak limiter",
        "group": "dynamics",
        "params": {
            "ceiling_db": _p(-12, 0, -1, "dBTP", "Ceiling"),
            "release_ms": _p(1, 1000, 80, "ms", "Release"),
        },
    },
}


def normalize_chain(chain: list[dict] | None) -> list[dict]:
    """Validate a chain, fill defaults and clamp every value into range."""
    out = []
    for item in chain or []:
        t = item.get("type")
        if t not in PLUGINS:
            raise ValueError(f"Unknown effect type '{t}'")
        spec = PLUGINS[t]["params"]
        params = {}
        for k, ps in spec.items():
            v = (item.get("params") or {}).get(k, ps["default"])
            params[k] = float(np.clip(float(v), ps["min"], ps["max"]))
        extra = set(item.get("params") or {}) - set(spec)
        if extra:
            raise ValueError(f"Unknown parameter(s) {sorted(extra)} for '{t}'")
        out.append({"type": t, "params": params, "bypass": bool(item.get("bypass", False))})
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def pedalboard_available() -> bool:
    try:
        import pedalboard  # noqa: F401

        return True
    except Exception:
        return False


def _pb_plugin(t: str, p: dict):
    import pedalboard as pb

    if t == "gain":
        return pb.Gain(gain_db=p["gain_db"])
    if t == "highpass":
        return pb.HighpassFilter(cutoff_frequency_hz=p["cutoff_hz"])
    if t == "lowpass":
        return pb.LowpassFilter(cutoff_frequency_hz=p["cutoff_hz"])
    if t == "lowshelf":
        return pb.LowShelfFilter(cutoff_frequency_hz=p["cutoff_hz"], gain_db=p["gain_db"], q=p["q"])
    if t == "highshelf":
        return pb.HighShelfFilter(
            cutoff_frequency_hz=p["cutoff_hz"], gain_db=p["gain_db"], q=p["q"]
        )
    if t == "peak":
        return pb.PeakFilter(cutoff_frequency_hz=p["freq_hz"], gain_db=p["gain_db"], q=p["q"])
    if t == "compressor":
        return pb.Compressor(
            threshold_db=p["threshold_db"],
            ratio=p["ratio"],
            attack_ms=p["attack_ms"],
            release_ms=p["release_ms"],
        )
    if t == "gate":
        return pb.NoiseGate(
            threshold_db=p["threshold_db"],
            ratio=p["ratio"],
            attack_ms=p["attack_ms"],
            release_ms=p["release_ms"],
        )
    if t == "chorus":
        return pb.Chorus(
            rate_hz=p["rate_hz"],
            depth=p["depth"],
            centre_delay_ms=p["centre_delay_ms"],
            feedback=p["feedback"],
            mix=p["mix"],
        )
    if t == "phaser":
        return pb.Phaser(
            rate_hz=p["rate_hz"],
            depth=p["depth"],
            centre_frequency_hz=p["centre_frequency_hz"],
            feedback=p["feedback"],
            mix=p["mix"],
        )
    if t == "delay":
        return pb.Delay(delay_seconds=p["time_ms"] / 1000, feedback=p["feedback"], mix=p["mix"])
    if t == "reverb":
        return pb.Reverb(
            room_size=p["room_size"],
            damping=p["damping"],
            width=p["width"],
            wet_level=p["mix"] * 0.6,
            dry_level=1 - p["mix"] * 0.4,
        )
    if t == "bitcrush":
        return None  # builtin handles mix
    return None


def _builtin(x: np.ndarray, sr: int, t: str, p: dict) -> np.ndarray:
    if t == "gain":
        return (x * dsp.db2lin(p["gain_db"])).astype(np.float32)
    if t in ("highpass", "lowpass"):
        return dsp.biquad(x, sr, t, p["cutoff_hz"])
    if t in ("lowshelf", "highshelf"):
        return dsp.biquad(x, sr, t, p["cutoff_hz"], p["q"], p["gain_db"])
    if t == "peak":
        return dsp.biquad(x, sr, "peak", p["freq_hz"], p["q"], p["gain_db"])
    if t == "compressor":
        return dsp.compressor(
            x, sr, p["threshold_db"], p["ratio"], p["attack_ms"], p["release_ms"], p["makeup_db"]
        )
    if t == "gate":
        return dsp.gate(x, sr, p["threshold_db"], p["ratio"], p["attack_ms"], p["release_ms"])
    if t == "deesser":
        return dsp.deesser(x, sr, p["frequency_hz"], p["threshold_db"], p["ratio"])
    if t == "saturation":
        return dsp.saturation(x, sr, p["drive_db"], p["mix"])
    if t == "bitcrush":
        return dsp.bitcrush(x, sr, p["bit_depth"], p["mix"])
    if t in ("chorus", "phaser"):
        q = {k: p[k] for k in ("rate_hz", "depth", "feedback", "mix")}
        return dsp.chorus(x, sr, centre_delay_ms=p.get("centre_delay_ms", 4.0), **q)
    if t == "delay":
        return dsp.delay(x, sr, p["time_ms"], p["feedback"], p["mix"])
    if t == "reverb":
        return dsp.reverb(x, sr, p["room_size"], p["damping"], p["width"], p["mix"])
    if t == "width":
        return dsp.width(x, sr, p["width"])
    if t == "limiter":
        return dsp.true_peak_limit(x, sr, p["ceiling_db"], p["release_ms"])
    raise ValueError(t)  # pragma: no cover


def render_chain(
    x: np.ndarray, sr: int, chain: list[dict] | None, engine: str = "auto"
) -> tuple[np.ndarray, str]:
    """Run a chain. Returns (audio, engine_used) where engine_used is
    ``pedalboard``, ``builtin`` or ``pedalboard+builtin``."""
    chain = normalize_chain(chain)
    use_pb = engine in ("auto", "pedalboard") and pedalboard_available()
    used: set[str] = set()
    y = x.astype(np.float32)
    n = y.shape[0]
    pending: list = []

    def flush() -> None:
        nonlocal y, pending
        if pending:
            import pedalboard as pb

            out = pb.Pedalboard(pending)(y.T.copy(), sr, reset=True).T
            y = dsp.trim_tail(out.astype(np.float32), n)
            used.add("pedalboard")
            pending = []

    for item in chain:
        if item["bypass"]:
            continue
        t, p = item["type"], item["params"]
        plug = None
        if use_pb:
            plug = _pb_plugin(t, p)
            if plug is not None and t == "compressor" and p["makeup_db"]:
                pending.append(plug)
                import pedalboard as pb

                plug = pb.Gain(gain_db=p["makeup_db"])
        if plug is not None:
            pending.append(plug)
            continue
        flush()
        y = dsp.trim_tail(_builtin(y, sr, t, p), n)
        used.add("builtin")
    flush()
    y = np.nan_to_num(y)
    label = "+".join(sorted(used, reverse=True)) or "none"
    return y, label
