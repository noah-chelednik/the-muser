"""Stem fidelity: source-rate 24-bit stems, null test, residual subtraction, dev SDR benchmark.

CPU only, synthetic audio, no model downloads (the splitter itself is faked).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from studio.server.engines import audio_io, separation, stem_fidelity
from studio.server.engines.errors import FriendlyError

SR = 48000


def _tone(f, seconds=2.0, sr=SR, amp=0.3, phase=0.0):
    t = np.arange(int(sr * seconds)) / sr
    return amp * np.sin(2 * np.pi * f * t + phase)


def _stereo(x):
    return np.stack([x, 0.9 * x], axis=1).astype(np.float32)


def _song(sr=SR, hot=1.0):
    voc = _stereo(_tone(440, sr=sr, amp=0.35 * hot))
    bass = _stereo(_tone(80, sr=sr, amp=0.4 * hot))
    drums = _stereo(_tone(3000, sr=sr, amp=0.1 * hot))
    return voc, bass, drums


def _write(path, x, sr, subtype="PCM_16"):
    sf.write(str(path), x, sr, subtype=subtype)
    return str(path)


# --------------------------------------------------------------------------- null test maths


def test_null_test_identical_is_floor_and_gain_error_is_measured():
    voc, bass, drums = _song()
    mix = voc + bass + drums
    assert stem_fidelity.null_test_db(mix, {"a": voc, "b": bass, "c": drums}) <= -150
    # one stem 10% too quiet -> error is 10% of that stem's energy share, a bit worse than -40 dB
    db = stem_fidelity.null_test_db(mix, {"a": voc, "b": bass, "c": drums * 0.0})
    assert -30 < db < -10  # drums are ~10% amplitude of the mix: missing stem ~ -20 dB
    with pytest.raises(ValueError):
        stem_fidelity.null_test_db(mix, {})


def test_make_residual_closes_the_gap():
    voc, bass, drums = _song()
    mix = voc + bass + drums
    stems = {"vocals": voc, "bass": bass, "other": drums * 0.5}  # model lost half the drums
    assert stem_fidelity.null_test_db(mix, stems) > -40
    fixed = stem_fidelity.make_residual(mix, stems, "other")
    assert stem_fidelity.null_test_db(mix, fixed) < -120
    np.testing.assert_allclose(fixed["other"], drums, atol=1e-5)
    with pytest.raises(ValueError):
        stem_fidelity.make_residual(mix, stems, "guitar")


def test_pick_residual_target():
    assert stem_fidelity.pick_residual_target(["vocals", "instrumental"]) == "instrumental"
    assert stem_fidelity.pick_residual_target(["vocals", "drums", "bass", "other"]) == "other"
    assert stem_fidelity.pick_residual_target(["vocals", "drums"]) is None


def test_match_channels_folds_to_mono_by_mean():
    st = np.stack([np.ones(4), -np.ones(4)], axis=1).astype(np.float32)
    assert float(np.abs(stem_fidelity._match_channels(st, 1)).max()) == 0.0
    assert stem_fidelity._match_channels(np.ones((4, 1), np.float32), 2).shape == (4, 2)


# --------------------------------------------------------------------------- reconcile


def _split_files(tmp_path, sr_stem=44100, lose_drums=0.0, hot=1.0, subtype="PCM_16"):
    """A 48 kHz source plus stems a splitter would hand back at 44.1 kHz / 16 bit."""
    voc, bass, drums = _song(hot=hot)
    mix = voc + bass + drums
    src = _write(tmp_path / "song.wav", mix, SR)
    others = {}
    for name, x in {"vocals": voc, "bass": bass, "other": drums * (1 - lose_drums)}.items():
        x44 = stem_fidelity.resample(x, SR, sr_stem)
        others[name] = _write(tmp_path / f"{name}.wav", x44, sr_stem, subtype)
    return src, others


def test_reconcile_restores_source_rate_and_24_bit(tmp_path):
    src, stems = _split_files(tmp_path)
    r = stem_fidelity.reconcile(src, stems)
    assert "error" not in r
    assert r["sample_rate"] == SR and r["subtype"] == "PCM_24"
    for p in r["stems"].values():
        info = sf.info(p)
        assert info.samplerate == SR and info.subtype == "PCM_24"
        assert info.frames == sf.info(src).frames
    assert r["null_db_after"] < -45  # one clean resample round trip, 16-bit input stems


def test_reconcile_rebuilds_other_when_stems_lose_energy(tmp_path):
    src, stems = _split_files(tmp_path, lose_drums=0.6)
    r = stem_fidelity.reconcile(src, stems)
    assert r["null_db_before"] > -30
    assert r["residual"] == "other"
    assert r["null_db_after"] < r["null_db_before"] - 25


def test_reconcile_auto_leaves_an_already_exact_set_alone(tmp_path):
    voc, bass, drums = _song()
    mix = voc + bass + drums
    src = _write(tmp_path / "song.wav", mix, SR, "PCM_24")
    stems = {
        "vocals": _write(tmp_path / "v.wav", voc, SR, "PCM_24"),
        "other": _write(tmp_path / "o.wav", bass + drums, SR, "PCM_24"),
    }
    r = stem_fidelity.reconcile(src, stems)
    assert r["residual"] is None and r["null_db_after"] <= stem_fidelity.EXACT_DB


def test_reconcile_residual_off_and_forced(tmp_path):
    src, stems = _split_files(tmp_path, lose_drums=0.6)
    off = stem_fidelity.reconcile(src, stems, residual="off")
    assert off["residual"] is None and off["null_db_after"] > -30
    forced = stem_fidelity.reconcile(src, stems, residual="bass")
    assert forced["residual"] == "bass"


def test_reconcile_hot_master_does_not_get_worse(tmp_path):
    """Stems that clip at full scale must never make the null test worse than it was."""
    src, stems = _split_files(tmp_path, lose_drums=0.5, hot=2.2)
    r = stem_fidelity.reconcile(src, stems)
    assert r["null_db_after"] <= r["null_db_before"] + 0.5


def test_reconcile_missing_source_raises_friendly(tmp_path):
    with pytest.raises(FriendlyError):
        stem_fidelity.reconcile(tmp_path / "nope.wav", {"vocals": str(tmp_path / "v.wav")})


def test_reconcile_bad_stem_keeps_originals(tmp_path):
    src, stems = _split_files(tmp_path)
    Path(stems["bass"]).write_bytes(b"not audio")
    before = {k: Path(v).read_bytes() for k, v in stems.items()}
    r = stem_fidelity.reconcile(src, stems)
    assert "error" in r and r["stems"] == stems
    assert {k: Path(v).read_bytes() for k, v in stems.items()} == before
    assert "skipped" in stem_fidelity.describe(r)


def test_mono_source_with_stereo_stems(tmp_path):
    x = _tone(440)
    src = _write(tmp_path / "m.wav", x[:, None].astype(np.float32), SR)
    st = {
        "vocals": _write(tmp_path / "v.wav", _stereo(x * 0.5), SR),
        "instrumental": _write(tmp_path / "i.wav", _stereo(x * 0.5), SR),
    }
    r = stem_fidelity.reconcile(src, st)
    assert "error" not in r
    # the stereo stems fold back to mono: a 0.9 right channel averages to 0.95x
    assert sf.info(r["stems"]["vocals"]).channels == 1
    assert r["null_db_after"] < -20


def test_describe_wording():
    d = stem_fidelity.describe({"null_db_after": -90.0, "sample_rate": 48000, "residual": "other"})
    assert "24-bit" in d and "48 kHz" in d and "'other'" in d and "exactly" not in d
    loose = stem_fidelity.describe({"null_db_after": -25.0, "sample_rate": 44100, "residual": None})
    assert "within -25 dB" in loose


# --------------------------------------------------------------------------- audio_io.write


def test_write_limit_false_clips_instead_of_limiting(tmp_path):
    x = np.array([[1.5, -1.5], [0.5, -0.5], [0.0, 0.0]], dtype=np.float32)
    p = audio_io.write(tmp_path / "a.wav", x, 48000, allow_silent=True, limit=False)
    y, _ = sf.read(p, always_2d=True)
    assert abs(y[1, 0] - 0.5) < 1e-6  # untouched, a limiter would have scaled everything
    assert y.max() <= 1.0
    assert sf.info(p).subtype == "PCM_24"


# --------------------------------------------------------------------------- separate()


def _fake_separate(src_path):
    def _impl(path, out_dir, mode, engine, model, progress):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        voc, bass, drums = _song()
        stems = {}
        for name, x in {"vocals": voc, "instrumental": (bass + drums) * 0.8}.items():
            x44 = stem_fidelity.resample(x, SR, 44100)
            p = out_dir / f"{name}.wav"
            sf.write(str(p), x44, 44100, subtype="PCM_16")
            stems[name] = str(p)
        return {"stems": stems, "engine": "audio-separator", "model": "m", "note": "Separated."}

    return _impl


def test_separate_runs_fidelity_pass(tmp_path, monkeypatch):
    voc, bass, drums = _song()
    src = _write(tmp_path / "song.wav", voc + bass + drums, SR)
    monkeypatch.setattr(separation, "_separate", _fake_separate(src))
    res = separation.separate(src, tmp_path / "out", mode="2stem", engine="audio-separator")
    assert res["fidelity"]["sample_rate"] == SR
    assert res["fidelity"]["residual"] == "instrumental"
    assert "24-bit" in res["note"] and res["note"].startswith("Separated.")
    assert sf.info(res["stems"]["vocals"]).samplerate == SR


def test_separate_fidelity_off_and_band_split_untouched(tmp_path, monkeypatch):
    voc, bass, drums = _song()
    src = _write(tmp_path / "song.wav", voc + bass + drums, SR)
    monkeypatch.setattr(separation, "_separate", _fake_separate(src))
    res = separation.separate(src, tmp_path / "o1", engine="audio-separator", fidelity=False)
    assert "fidelity" not in res and sf.info(res["stems"]["vocals"]).samplerate == 44100

    def band(path, out_dir, mode, engine, model, progress):
        return {"stems": {"low": "x"}, "engine": "band-split", "model": None, "note": "Bands."}

    monkeypatch.setattr(separation, "_separate", band)
    assert separation.separate(src, tmp_path / "o2")["stems"] == {"low": "x"}


def test_separator_passes_normalization_threshold_one(tmp_path, monkeypatch):
    seen = {}

    class Sep:
        def __init__(self, **kw):
            seen.update(kw)

    mod = types.ModuleType("audio_separator.separator")
    mod.Separator = Sep
    monkeypatch.setitem(sys.modules, "audio_separator", types.ModuleType("audio_separator"))
    monkeypatch.setitem(sys.modules, "audio_separator.separator", mod)
    monkeypatch.setattr(separation, "SEP_MODEL_DIR", tmp_path / "m")
    separation._separator(tmp_path)
    assert seen["normalization_threshold"] == 1.0


def test_separator_falls_back_for_older_audio_separator(tmp_path, monkeypatch):
    seen = {}

    class Old:
        def __init__(self, output_dir, model_file_dir, log_level):
            seen.update(output_dir=output_dir)

    mod = types.ModuleType("audio_separator.separator")
    mod.Separator = Old
    monkeypatch.setitem(sys.modules, "audio_separator", types.ModuleType("audio_separator"))
    monkeypatch.setitem(sys.modules, "audio_separator.separator", mod)
    monkeypatch.setattr(separation, "SEP_MODEL_DIR", tmp_path / "m")
    assert isinstance(separation._separator(tmp_path), Old)


def test_curated_models_flag_unverified_weight_licences():
    files = [m["file"] for m in separation.MODELS]
    assert len(files) == len(set(files))
    community = [m for m in separation.MODELS if m.get("weights_license") == "unstated"]
    assert {m["file"].split("_")[0] for m in community} >= {"mel", "denoise"}
    for m in community:
        assert "licence unstated" in m["label"] and "default_for" not in m
    # the GPL-3.0 anvuew de-reverb weights must not be offered
    assert not any("anvuew" in f for f in files)
    assert separation.default_model("2stem") == "UVR-MDX-NET-Inst_HQ_3.onnx"


# --------------------------------------------------------------------------- dev benchmark


def _bench():
    spec = importlib.util.spec_from_file_location(
        "bench_sdr", Path(__file__).resolve().parents[1] / "scripts" / "bench_sdr.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bench_sdr_metrics_and_dirs(tmp_path):
    b = _bench()
    ref = _tone(440)
    assert b.sdr(ref, ref) > 100
    assert b.si_sdr(ref, 0.5 * ref) > 100  # pure gain is ignored
    assert b.sdr(ref, 0.5 * ref) < 7  # but not by plain SDR (~6 dB)
    rng = np.random.default_rng(0)
    noisy = ref + 0.02 * rng.standard_normal(len(ref))
    assert 15 < b.sdr(ref, noisy) < 25

    voc, bass, _drums = _song()
    (tmp_path / "ref").mkdir()
    (tmp_path / "est").mkdir()
    for n, x in {"vocals": voc, "bass": bass}.items():
        sf.write(str(tmp_path / "ref" / f"{n}.wav"), x, SR)
        sf.write(str(tmp_path / "est" / f"{n}.wav"), x * 0.9, SR)
    sf.write(str(tmp_path / "mix.wav"), voc + bass, SR)
    out = b.score_dirs(tmp_path / "ref", tmp_path / "est", tmp_path / "mix.wav")
    assert set(out["stems"]) == {"vocals", "bass"}
    assert out["null_db"] == pytest.approx(-20.0, abs=0.2)  # every stem is 10% low
    assert out["mean_sdr"] == pytest.approx(20.0, abs=0.2)


def test_bench_is_not_imported_by_the_app():
    root = Path(__file__).resolve().parents[1]
    for p in (root / "studio" / "server").rglob("*.py"):
        assert "bench_sdr" not in p.read_text(encoding="utf-8"), p
