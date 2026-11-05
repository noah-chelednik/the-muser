"""Audio to MIDI: Basic Pitch (ONNX, polyphonic) or librosa pYIN (monophonic)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .errors import FriendlyError


def _onnx_model_path() -> str:
    import basic_pitch  # type: ignore

    p = Path(basic_pitch.__file__).parent / "saved_models" / "icassp_2022" / "nmp.onnx"
    if not p.exists():
        raise FriendlyError(
            "Basic Pitch's model file is missing.", "Reinstall Basic Pitch from System."
        )
    return str(p)


def basic_pitch(
    path: str, out_mid: str, onset: float = 0.5, frame: float = 0.3, min_note_ms: float = 80
) -> dict[str, Any]:
    from basic_pitch.inference import predict  # type: ignore

    _, midi, notes = predict(
        path,
        _onnx_model_path(),
        onset_threshold=onset,
        frame_threshold=frame,
        minimum_note_length=min_note_ms,
    )
    midi.write(out_mid)
    return {"notes": len(notes), "engine": "basic-pitch", "midi": out_mid}


def pyin(path: str, out_mid: str) -> dict[str, Any]:
    import librosa
    import pretty_midi

    y, sr = librosa.load(path, sr=22050, mono=True)
    hop = 256
    f0, voiced, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr, hop_length=hop
    )
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    t = librosa.times_like(f0, sr=sr, hop_length=hop)
    cur, start = None, 0.0
    for i, (hz, v) in enumerate(zip(f0, voiced)):
        note = int(round(librosa.hz_to_midi(hz))) if v and hz and not np.isnan(hz) else None
        if note != cur:
            if cur is not None and t[i] - start >= 0.06:
                inst.notes.append(
                    pretty_midi.Note(velocity=90, pitch=cur, start=float(start), end=float(t[i]))
                )
            cur, start = note, float(t[i])
    if cur is not None:
        inst.notes.append(
            pretty_midi.Note(velocity=90, pitch=cur, start=float(start), end=float(t[-1]))
        )
    pm.instruments.append(inst)
    pm.write(out_mid)
    return {"notes": len(inst.notes), "engine": "pyin-midi", "midi": out_mid}


def to_midi(path: str, out_mid: str, engine: str = "auto", **kw) -> dict[str, Any]:
    from . import selector

    if engine == "auto":
        engine = selector.select("midi").engine
    if engine == "basic-pitch":
        return basic_pitch(path, out_mid, **kw)
    if engine == "pyin-midi":
        return pyin(path, out_mid)
    raise FriendlyError(f"'{engine}' can't make MIDI.")
