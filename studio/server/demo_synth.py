"""Demo-mode multitrack synthesizer.

When no GPU / ACE-Step weights are available, the Studio still needs real
audio so every part of the UI (stems, knobs, mixdown, export) can be used.
This module renders a short, musically coherent loop from a text prompt using
plain numpy DSP: drums, bass, chords and lead are rendered as *separate stems*
and summed into a mix. It is clearly labelled "demo synth" everywhere - it is
NOT AI generation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100

NOTE_INDEX = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}

GENRES = {
    # name: (bpm, swing, drum_style, progression degrees (minor-ish), brightness)
    "lofi": (80, 0.18, "boombap", [0, 5, 3, 4], 0.35),
    "lo-fi": (80, 0.18, "boombap", [0, 5, 3, 4], 0.35),
    "hip hop": (90, 0.12, "boombap", [0, 3, 5, 4], 0.45),
    "trap": (140, 0.0, "trap", [0, 0, 5, 6], 0.5),
    "house": (124, 0.0, "four", [0, 5, 3, 6], 0.6),
    "techno": (128, 0.0, "four", [0, 0, 0, 6], 0.7),
    "edm": (126, 0.0, "four", [0, 5, 2, 6], 0.75),
    "synthwave": (100, 0.0, "four", [0, 5, 3, 6], 0.65),
    "ambient": (70, 0.0, "none", [0, 5, 3, 4], 0.25),
    "cinematic": (75, 0.0, "none", [0, 5, 2, 6], 0.4),
    "jazz": (96, 0.22, "boombap", [1, 4, 0, 5], 0.4),
    "rock": (118, 0.0, "rock", [0, 5, 3, 6], 0.7),
    "pop": (110, 0.0, "rock", [0, 4, 5, 3], 0.6),
    "drill": (142, 0.0, "trap", [0, 1, 5, 4], 0.5),
}


@dataclass
class DemoSpec:
    prompt: str
    bpm: int = 96
    key_root: int = 9  # A
    minor: bool = True
    genre: str = "lofi"
    swing: float = 0.1
    drum_style: str = "boombap"
    progression: list[int] = field(default_factory=lambda: [0, 5, 3, 4])
    brightness: float = 0.5
    bars: int = 8
    seed: int = 0

    @property
    def key_name(self) -> str:
        names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
        return f"{names[self.key_root]} {'minor' if self.minor else 'major'}"


def parse_prompt(
    prompt: str,
    bpm: int | None = None,
    key: str | None = None,
    duration_s: float | None = None,
) -> DemoSpec:
    """Derive tempo / key / style from a free-text prompt (deterministic)."""
    text = prompt.lower()
    seed = int(hashlib.sha1(prompt.encode()).hexdigest()[:8], 16)
    spec = DemoSpec(prompt=prompt, seed=seed)

    for name, (g_bpm, swing, drums, prog, bright) in GENRES.items():
        if name in text:
            spec.genre, spec.bpm, spec.swing = name, g_bpm, swing
            spec.drum_style, spec.progression, spec.brightness = drums, list(prog), bright
            break

    m = re.search(r"(\d{2,3})\s*bpm", text)
    if m:
        spec.bpm = int(m.group(1))
    if bpm:
        spec.bpm = int(bpm)
    spec.bpm = max(50, min(180, spec.bpm))

    if key:
        km = re.match(r"\s*([A-Ga-g])([#b]?)\s*(major|minor|maj|min|m)?", key)
    else:
        km = re.search(r"\bin\s+([A-G])([#b]?)\s*(major|minor|maj|min|m)?\b", prompt)
    if km:
        root = (km.group(1) + km.group(2)).upper()
        spec.key_root = NOTE_INDEX.get(root, spec.key_root)
        quality = (km.group(3) or "").lower()
        if quality in ("major", "maj"):
            spec.minor = False
        elif quality in ("minor", "min", "m"):
            spec.minor = True
    elif any(w in text for w in ("happy", "bright", "uplifting", "sunny")):
        spec.minor = False

    if "dark" in text or "sad" in text:
        spec.brightness = max(0.2, spec.brightness - 0.15)

    target = duration_s or 16.0
    bar_s = 4 * 60.0 / spec.bpm
    spec.bars = int(max(4, min(32, round(target / bar_s / 4) * 4 or 4)))
    return spec


# ---------------------------------------------------------------------------
# DSP primitives
# ---------------------------------------------------------------------------


def _midi_hz(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def _env(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(0, n - a_n - d_n - r_n)
    parts = [
        np.linspace(0, 1, max(a_n, 1), endpoint=False),
        np.linspace(1, s, max(d_n, 1), endpoint=False),
        np.full(s_n, s),
        np.linspace(s, 0, max(r_n, 1)),
    ]
    e = np.concatenate(parts)
    if len(e) < n:
        e = np.pad(e, (0, n - len(e)))
    return e[:n]


def _onepole_lp(x: np.ndarray, cutoff: float) -> np.ndarray:
    from scipy.signal import lfilter

    a = np.exp(-2 * np.pi * cutoff / SR)
    return lfilter([1 - a], [1, -a], x)


def _add(buf: np.ndarray, sig: np.ndarray, start: int) -> None:
    if start >= len(buf):
        return
    end = min(len(buf), start + len(sig))
    buf[start:end] += sig[: end - start]


def _kick(rng: np.random.Generator) -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.tanh(1.6 * np.sin(ph) * np.exp(-t * 7.5))


def _snare(rng: np.random.Generator) -> np.ndarray:
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - _onepole_lp(noise, 1500)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return 0.55 * (noise * np.exp(-t * 18) + 0.8 * body)


def _hat(rng: np.random.Generator, open_: bool = False) -> np.ndarray:
    n = int((0.25 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - _onepole_lp(noise, 7000)
    return 0.22 * noise * np.exp(-t * (12 if open_ else 70))


def _scale(minor: bool) -> list[int]:
    return [0, 2, 3, 5, 7, 8, 10] if minor else [0, 2, 4, 5, 7, 9, 11]


def _chord(root_deg: int, spec: DemoSpec) -> list[int]:
    sc = _scale(spec.minor)
    base = 48 + spec.key_root
    notes = []
    for step in (0, 2, 4, 6):
        deg = root_deg + step
        notes.append(base + sc[deg % 7] + 12 * (deg // 7))
    return notes


# ---------------------------------------------------------------------------
# Stem renderers
# ---------------------------------------------------------------------------


def _render_drums(spec: DemoSpec, total: int, rng: np.random.Generator) -> np.ndarray:
    buf = np.zeros(total)
    if spec.drum_style == "none":
        # soft shaker pulse for ambient / cinematic
        step = 60.0 / spec.bpm / 2
        for i in range(int(total / SR / step)):
            _add(buf, 0.35 * _hat(rng), int(i * step * SR))
        return buf
    sixteenth = 60.0 / spec.bpm / 4
    kick, snare = _kick(rng), _snare(rng)
    steps = spec.bars * 16
    for s in range(steps):
        pos = s % 16
        t = s * sixteenth
        if pos % 2 == 1:
            t += spec.swing * sixteenth
        i = int(t * SR)
        style = spec.drum_style
        if style == "four":
            if pos % 4 == 0:
                _add(buf, kick, i)
            if pos in (4, 12):
                _add(buf, 0.8 * snare, i)
            if pos % 4 == 2:
                _add(buf, _hat(rng, open_=True), i)
        elif style == "trap":
            if pos in (0, 7, 10) or (pos == 14 and s // 16 % 2):
                _add(buf, kick, i)
            if pos == 8:
                _add(buf, snare, i)
            _add(buf, 0.8 * _hat(rng), i)
            if pos in (13, 15) and s // 16 % 2:
                _add(buf, 0.6 * _hat(rng), i + int(sixteenth * SR / 2))
        elif style == "rock":
            if pos in (0, 8, 10):
                _add(buf, kick, i)
            if pos in (4, 12):
                _add(buf, snare, i)
            if pos % 2 == 0:
                _add(buf, _hat(rng), i)
        else:  # boombap
            if pos in (0, 7, 10):
                _add(buf, kick, i)
            if pos in (4, 12):
                _add(buf, snare, i)
            if pos % 2 == 0:
                _add(buf, (0.7 + 0.3 * rng.random()) * _hat(rng), i)
    return buf


def _render_bass(spec: DemoSpec, total: int) -> np.ndarray:
    buf = np.zeros(total)
    bar = 4 * 60.0 / spec.bpm
    eighth = bar / 8
    for b in range(spec.bars):
        root = _chord(spec.progression[b % len(spec.progression)], spec)[0] - 12
        pattern = (
            [0, None, 0, None, 7, None, 0, 12] if spec.drum_style != "none" else [0] + [None] * 7
        )
        for k, iv in enumerate(pattern):
            if iv is None:
                continue
            dur = eighth * (8 if spec.drum_style == "none" else 0.9)
            n = int(dur * SR)
            t = np.arange(n) / SR
            f = _midi_hz(root + iv)
            sig = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)
            sig = np.tanh(1.4 * sig) * _env(n, 0.005, 0.08, 0.7, 0.05)
            _add(buf, 0.5 * sig, int((b * bar + k * eighth) * SR))
    return buf


def _render_chords(spec: DemoSpec, total: int) -> np.ndarray:
    buf = np.zeros(total)
    bar = 4 * 60.0 / spec.bpm
    for b in range(spec.bars):
        notes = _chord(spec.progression[b % len(spec.progression)], spec)
        n = int(bar * SR)
        t = np.arange(n) / SR
        sig = np.zeros(n)
        for note in notes:
            f = _midi_hz(note + 12)
            for det in (-0.08, 0.08):
                ff = f * 2 ** (det / 12)
                # band-limited-ish saw via a few harmonics
                for h in range(1, 7):
                    sig += np.sin(2 * np.pi * ff * h * t) / h * (spec.brightness ** (h / 3))
        sig *= _env(n, 0.08, 0.3, 0.75, 0.25) * (1 + 0.05 * np.sin(2 * np.pi * 0.5 * t))
        _add(buf, 0.06 * sig, int(b * bar * SR))
    return _onepole_lp(buf, 1200 + 4000 * spec.brightness)


def _render_lead(spec: DemoSpec, total: int, rng: np.random.Generator) -> np.ndarray:
    buf = np.zeros(total)
    bar = 4 * 60.0 / spec.bpm
    eighth = bar / 8
    pent = [0, 3, 5, 7, 10] if spec.minor else [0, 2, 4, 7, 9]
    base = 72 + spec.key_root
    motif = [int(x) for x in rng.integers(0, len(pent) * 2, 8)]
    rhythm = [bool(x) for x in rng.random(8) > 0.35]
    for b in range(spec.bars):
        if b % 4 == 0 and b > 0:
            motif = [(m + int(rng.integers(-2, 3))) % (len(pent) * 2) for m in motif]
        if b % 2 == 1 and spec.bars > 4 and b == spec.bars - 1:
            continue
        for k in range(8):
            if not rhythm[k]:
                continue
            deg = motif[k]
            note = base + pent[deg % len(pent)] + 12 * (deg // len(pent)) - 12
            n = int(eighth * 0.95 * SR)
            t = np.arange(n) / SR
            f = _midi_hz(note)
            vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
            ph = 2 * np.pi * np.cumsum(f * vib) / SR
            sig = np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.1 * np.sin(3 * ph)
            sig *= _env(n, 0.01, 0.1, 0.6, 0.08)
            _add(buf, 0.18 * sig, int((b * bar + k * eighth) * SR))
    return buf


def _stereo(mono: np.ndarray, width: float = 0.0, pan: float = 0.0) -> np.ndarray:
    left = mono * np.sqrt((1 - pan) / 2) * np.sqrt(2)
    right = mono * np.sqrt((1 + pan) / 2) * np.sqrt(2)
    if width:
        d = int(0.012 * SR * width)
        right = np.concatenate([np.zeros(d), right[:-d]]) if d else right
    return np.stack([left, right], axis=1)


def render(spec: DemoSpec, out_dir: Path) -> dict:
    """Render stems + mix to ``out_dir``. Returns {"mix": path, "stems": {name: path}}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(spec.seed)
    bar = 4 * 60.0 / spec.bpm
    total = int((spec.bars * bar + 1.0) * SR)

    stems = {
        "drums": _stereo(_render_drums(spec, total, rng), 0.0),
        "bass": _stereo(_render_bass(spec, total), 0.0),
        "chords": _stereo(_render_chords(spec, total), 0.8),
        "lead": _stereo(_render_lead(spec, total, rng), 0.3, pan=0.15),
    }
    mix = sum(stems.values())
    peak = float(np.max(np.abs(mix))) or 1.0
    gain = 0.89 / peak

    stem_dir = out_dir / "stems_demo"
    stem_dir.mkdir(exist_ok=True)
    paths: dict[str, str] = {}
    for name, data in stems.items():
        p = stem_dir / f"{name}.wav"
        sf.write(p, (data * gain).astype(np.float32), SR, subtype="PCM_16")
        paths[name] = str(p)
    mix_path = out_dir / "mix.wav"
    sf.write(mix_path, (mix * gain).astype(np.float32), SR, subtype="PCM_16")
    return {"mix": str(mix_path), "stems": paths, "duration_s": total / SR}


def band_split(wav_path: str, out_dir: Path) -> dict[str, str]:
    """Fallback 'split' when Demucs isn't installed: 4 frequency bands.

    This is a crossover, not source separation - the UI labels it as such.
    """
    from scipy.signal import butter, sosfiltfilt

    data, sr = sf.read(wav_path, always_2d=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    bands = {
        "low (sub/bass)": ("lowpass", 160),
        "low-mid (body)": ("bandpass", (160, 1200)),
        "high-mid (presence)": ("bandpass", (1200, 6000)),
        "air (highs)": ("highpass", 6000),
    }
    result = {}
    for name, (kind, f) in bands.items():
        sos = butter(4, f, btype=kind, fs=sr, output="sos")
        y = sosfiltfilt(sos, data, axis=0)
        fname = re.sub(r"[^a-z]+", "_", name).strip("_") + ".wav"
        p = out_dir / fname
        sf.write(p, y.astype(np.float32), sr, subtype="PCM_16")
        result[name] = str(p)
    return result
