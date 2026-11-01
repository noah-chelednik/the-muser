#!/usr/bin/env python
"""Dev-only: score a stem split against reference stems (SDR, SI-SDR, null test).

NOT part of the Studio and never imported by it. Use it to compare splitter models or settings on
your own test songs:

    python scripts/bench_sdr.py REF_DIR EST_DIR [--mix MIX.wav]

``REF_DIR`` and ``EST_DIR`` hold WAVs with matching names (vocals.wav, drums.wav, ...). Stems are
matched by file stem, truncated to the shorter length, and scored per stem and on average.

The metrics are plain numpy, so there is nothing to install. ``--museval`` adds the classic
BSS-Eval SDR when ``museval`` is installed (a heavier, slower, standard number).

Idea of an SDR benchmark harness inspired by nussl (MIT): https://github.com/nussl/nussl and its
modernized fork https://github.com/Stavion-Colquitt/nussl. No nussl code is used or shipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

EPS = 1e-12


def sdr(ref: np.ndarray, est: np.ndarray) -> float:
    """Signal-to-distortion ratio in dB: 10 log10(|ref|^2 / |ref - est|^2). Higher is better."""
    num = float(np.sum(ref.astype(np.float64) ** 2)) + EPS
    den = float(np.sum((ref.astype(np.float64) - est.astype(np.float64)) ** 2)) + EPS
    return 10.0 * np.log10(num / den)


def si_sdr(ref: np.ndarray, est: np.ndarray) -> float:
    """Scale-invariant SDR in dB: ignores a pure gain difference between estimate and reference."""
    r = ref.astype(np.float64).ravel()
    e = est.astype(np.float64).ravel()
    alpha = float(np.dot(e, r)) / (float(np.dot(r, r)) + EPS)
    target = alpha * r
    noise = e - target
    return 10.0 * np.log10((float(np.sum(target**2)) + EPS) / (float(np.sum(noise**2)) + EPS))


def null_db(mix: np.ndarray, stems: list[np.ndarray]) -> float:
    """dB (re mix RMS) of mix minus the sum of the stems. More negative = they add up better."""
    n = min([mix.shape[0], *[s.shape[0] for s in stems]])
    resid = mix[:n].astype(np.float64) - sum(s[:n].astype(np.float64) for s in stems)
    rms_mix = float(np.sqrt(np.mean(mix[:n].astype(np.float64) ** 2))) + EPS
    return float(20.0 * np.log10((float(np.sqrt(np.mean(resid**2))) + EPS) / rms_mix))


def _read(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    x, sr = sf.read(str(path), always_2d=True, dtype="float32")
    return x, sr


def score_dirs(ref_dir: Path, est_dir: Path, mix: Path | None = None, use_museval: bool = False):
    refs = {p.stem.lower(): p for p in ref_dir.glob("*.wav")}
    ests = {p.stem.lower(): p for p in est_dir.glob("*.wav")}
    names = sorted(set(refs) & set(ests))
    if not names:
        raise SystemExit(f"No matching stem names between {ref_dir} and {est_dir}")
    rows, est_arrays = {}, []
    for n in names:
        r, rs = _read(refs[n])
        e, es = _read(ests[n])
        if rs != es:
            raise SystemExit(f"{n}: sample rates differ ({rs} vs {es}). Resample first.")
        k = min(len(r), len(e))
        c = min(r.shape[1], e.shape[1])
        r, e = r[:k, :c], e[:k, :c]
        est_arrays.append(e)
        row = {"sdr": round(sdr(r, e), 2), "si_sdr": round(si_sdr(r, e), 2)}
        if use_museval:
            row["museval_sdr"] = _museval(r, e, rs)
        rows[n] = row
    out = {"stems": rows, "mean_sdr": round(float(np.mean([v["sdr"] for v in rows.values()])), 2)}
    if mix is not None:
        m, _ = _read(mix)
        c = min(m.shape[1], *[a.shape[1] for a in est_arrays])
        out["null_db"] = round(null_db(m[:, :c], [a[:, :c] for a in est_arrays]), 2)
    return out


def _museval(ref: np.ndarray, est: np.ndarray, sr: int) -> float | None:
    try:
        import museval  # type: ignore
    except ImportError:
        return None
    sdr_v, *_ = museval.evaluate(ref[None], est[None], win=sr, hop=sr)
    return round(float(np.nanmedian(sdr_v)), 2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ref_dir", type=Path)
    ap.add_argument("est_dir", type=Path)
    ap.add_argument("--mix", type=Path, help="the original mix, to also report the null test")
    ap.add_argument("--museval", action="store_true", help="also report BS-Eval SDR if installed")
    a = ap.parse_args(argv)
    print(json.dumps(score_dirs(a.ref_dir, a.est_dir, a.mix, a.museval), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
