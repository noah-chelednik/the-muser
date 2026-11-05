"""Studio engine layer: registry, selector, presets, loudness, mastering and the lightweight engines.

CPU only, no network, no model downloads. Optional engines are skipped when they are not installed.
"""

from __future__ import annotations

import importlib.util
import json

import numpy as np
import pytest

from studio.server.engines import dsp, fx, hardware, loudness, mastering, registry, selector
from studio.server.engines.errors import FriendlyError

SR = 44100
CPU = hardware.Hardware(os="Windows", cpu_count=8, ram_gb=16.0)
GPU12 = hardware.Hardware(
    os="Windows", cpu_count=16, ram_gb=32.0, gpu="RTX 4070", vram_gb=12.0, cuda=True, source="env"
)


def _music(seconds: float = 6.0, seed: int = 0) -> np.ndarray:
    """A small stereo test signal with drums-like transients, a bass line and a pad."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * seconds)) / SR
    bass = 0.25 * np.sin(2 * np.pi * 55 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t))
    pad = 0.08 * (
        np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 277 * t) + np.sin(2 * np.pi * 330 * t)
    )
    env = np.exp(-((t % 0.5) * 30))
    kick = 0.6 * env * np.sin(2 * np.pi * 60 * t * (1 + env))
    hat = 0.05 * rng.standard_normal(len(t)) * np.exp(-(((t + 0.25) % 0.5) * 120))
    x = bass + pad + kick + hat
    return np.stack([x, 0.97 * x], axis=1).astype(np.float32) * 0.5


def _healthy(_spec):
    return {"installed": True, "healthy": True, "detail": "test"}


def _only_builtin(spec):
    ok = spec.tier == "builtin"
    return {"installed": ok, "healthy": ok, "detail": "test"}


# --------------------------------------------------------------------------- registry


def test_registry_specs_are_complete():
    keys = [e.key for e in registry.ENGINES]
    assert len(keys) == len(set(keys)), "duplicate engine keys"
    assert len(keys) >= 20
    for e in registry.ENGINES:
        assert e.tasks and all(t in registry.TASKS for t in e.tasks), e.key
        assert e.commercial in ("yes", "conditional", "no"), e.key
        assert e.tier in ("builtin", "core", "optional", "heavy"), e.key
        assert e.verified in ("working", "adapter"), e.key
        assert e.windows in ("native", "partial", "wsl", "separate-app"), e.key
        assert e.code_license and e.weights_license and e.summary, e.key
        if e.tier != "builtin":
            assert e.homepage.startswith("http"), e.key
        if e.commercial != "yes":
            assert e.commercial_note, f"{e.key} needs a note explaining the licence limits"
        pub = e.public()
        assert pub["untested_here"] == (e.verified != "working")
        json.dumps(pub)


def test_every_task_has_a_builtin_or_core_fallback():
    for task in ("generate", "separate", "denoise", "match", "midi", "fx", "master", "loudness"):
        assert any(task in e.tasks and e.tier == "builtin" for e in registry.ENGINES), task


def test_heavy_models_are_marked_untested():
    heavy = [e for e in registry.ENGINES if e.tier == "heavy"]
    assert heavy
    assert all(e.verified == "adapter" for e in heavy)


def test_builtin_engines_report_healthy():
    for e in registry.ENGINES:
        if e.tier == "builtin":
            assert registry.health(e)["healthy"], e.key


def test_missing_module_reports_not_installed():
    spec = registry.EngineSpec(
        key="x-test",
        name="X",
        tasks=["fx"],
        summary="s",
        homepage="https://example.com",
        code_license="MIT",
        weights_license="none",
        commercial="yes",
        commercial_note="",
        tier="optional",
        install=registry.Install(kind="pip", pip=["nope"]),
        quality={"fx": 1},
        modules=["definitely_not_a_module_xyz"],
    )
    h = registry.health(spec)
    assert not h["installed"] and not h["healthy"] and "missing" in h["detail"]


def test_unknown_engine_key():
    with pytest.raises(KeyError):
        registry.get("nope")


# --------------------------------------------------------------------------- selector


def test_selector_excludes_non_commercial_by_default():
    for task in registry.TASKS:
        try:
            c = selector.select(task, GPU12, health_fn=_healthy)
        except FriendlyError:
            continue
        assert registry.get(c.engine).commercial != "no", (task, c.engine)


def test_selector_can_include_non_commercial_when_asked():
    keys = [
        c["key"]
        for c in selector.candidates("generate", GPU12, commercial_only=False, health_fn=_healthy)
        if c["allowed"]
    ]
    assert "musicgen" in keys


def test_selector_strict_commercial_drops_conditional():
    c = selector.select("separate", CPU, allow_conditional=False, health_fn=_healthy)
    assert registry.get(c.engine).commercial == "yes"


def test_selector_falls_back_to_builtin_on_cpu():
    for task in ("generate", "separate", "denoise", "match", "midi", "fx", "master", "loudness"):
        c = selector.select(task, CPU, health_fn=_only_builtin)
        assert registry.get(c.engine).tier == "builtin", (task, c.engine)
        assert c.reasons


def test_selector_never_picks_gpu_only_model_without_gpu():
    c = selector.select("generate", CPU, health_fn=_healthy)
    spec = registry.get(c.engine)
    assert spec.min_vram_gb == 0 or spec.cpu_ok


def test_selector_prefers_gpu_model_when_it_fits():
    c = selector.select("generate", GPU12, health_fn=_healthy)
    assert registry.get(c.engine).tier == "heavy"
    assert any("untested" in r.lower() for r in c.reasons)


def test_selector_prefer_and_errors():
    c = selector.select("fx", CPU, prefer="builtin-dsp", health_fn=_healthy)
    assert c.engine == "builtin-dsp"
    with pytest.raises(FriendlyError):
        selector.select("fx", CPU, prefer="demo-synth", health_fn=_healthy)
    with pytest.raises(FriendlyError):
        selector.select("not-a-task", CPU)
    with pytest.raises(FriendlyError):
        selector.select("generate", CPU, prefer="acestep", health_fn=_only_builtin)


def test_fits_reasons():
    acestep = registry.get("acestep")
    assert selector.fits(acestep, GPU12)[0]
    ok, why = selector.fits(registry.get("yue"), GPU12)
    assert not ok and "GB" in why


def test_recommendations_order():
    rec = selector.recommendations(GPU12)
    assert rec and all(r["min_vram_gb"] >= 0 for r in rec)
    can = [r["can_run"] for r in rec]
    assert can == sorted(can, reverse=True), "runnable models come first"
    assert not any(r["can_run"] for r in selector.recommendations(CPU) if r["min_vram_gb"] > 0)


def test_hardware_tiers():
    assert CPU.tier() == "cpu" and not CPU.has_gpu
    assert GPU12.tier() == "gpu"
    assert hardware.Hardware(os="x", cpu_count=1, ram_gb=1, vram_gb=24).tier() == "studio-gpu"
    d = hardware.detect()
    assert d.cpu_count >= 1


# --------------------------------------------------------------------------- presets


def test_factory_preset_library():
    from studio.server import presets

    counts = presets.counts()
    assert sum(counts.values()) >= 100
    for cat in ("genre", "mix", "master", "vocal", "fx"):
        assert counts.get(cat, 0) >= 10, cat
    known = presets.all_presets()
    for pid, p in known.items():
        clean = presets.validate(p, known)
        assert clean["name"] and clean["category"] == p["category"], pid
        assert "—" not in json.dumps(p, ensure_ascii=False), f"em dash in preset {pid}"


def test_genre_presets_reference_existing_presets():
    from studio.server import presets

    known = presets.all_presets()
    genres = [p for p in known.values() if p["category"] == "genre"]
    assert len(genres) >= 20
    for g in genres:
        assert g["generate"]["prompt"]
        for k in ("energy", "vocals", "bass", "brightness", "space"):
            assert 0 <= g["macros"][k] <= 100
        for ref in list(g.get("stems", {}).values()) + [g.get("master")]:
            if isinstance(ref, str):
                assert ref in known, (g["id"], ref)


def test_preset_validation_rejects_bad_input():
    from studio.server import presets

    with pytest.raises(FriendlyError):
        presets.validate({"name": "x", "category": "nope"})
    with pytest.raises(FriendlyError):
        presets.validate({"name": "", "category": "mix", "chain": []})
    with pytest.raises(FriendlyError):
        presets.validate({"name": "x", "category": "mix", "chain": [{"type": "flux-capacitor"}]})
    with pytest.raises(FriendlyError):
        presets.validate({"name": "x", "category": "master", "master": {"target": "mars"}})
    clamped = presets.validate(
        {
            "name": "x",
            "category": "mix",
            "chain": [{"type": "compressor", "params": {"ratio": 999}}],
        }
    )
    assert (
        clamped["chain"][0]["params"]["ratio"] == fx.PLUGINS["compressor"]["params"]["ratio"]["max"]
    )


def test_preset_search_and_user_roundtrip(tmp_path, monkeypatch):
    from studio.server import presets

    monkeypatch.setattr(presets, "USER_DIR", tmp_path / "user")
    monkeypatch.setattr(presets, "FAV_FILE", tmp_path / "fav.json")
    assert presets.listing(q="vocal")
    assert all(p["category"] == "master" for p in presets.listing(category="master"))
    saved = presets.save_user(
        {"name": "My Glue", "category": "mix", "chain": [{"type": "compressor"}]}
    )
    pid = saved["id"]
    assert presets.get(pid)["name"] == "My Glue"
    assert presets.toggle_favorite(pid) is True
    assert any(p["id"] == pid for p in presets.listing(favorites_only=True))
    bundle = presets.export_bundle([pid])
    assert presets.delete_user(pid)
    imported = presets.import_bundle(bundle)
    assert imported


def test_macro_definitions():
    from studio.server import presets

    m = presets.macros()
    assert {s["key"] if isinstance(s, dict) else s for s in m["sliders"]} >= {
        "energy",
        "vocals",
        "bass",
        "brightness",
        "space",
    }


# --------------------------------------------------------------------------- loudness and mastering


def test_builtin_lufs_matches_pyloudnorm():
    pytest.importorskip("pyloudnorm")
    import pyloudnorm as pyln

    x = _music()
    ref = pyln.Meter(SR).integrated_loudness(x)
    assert abs(loudness.integrated_lufs_builtin(x, SR) - ref) < 0.3


def test_lufs_of_reference_sine():
    # a full-scale 997 Hz sine reads about -3.0 LUFS on a single channel
    t = np.arange(SR * 3) / SR
    x = np.sin(2 * np.pi * 997 * t).astype(np.float32)[:, None]
    assert abs(loudness.integrated_lufs_builtin(x, SR) - (-3.01)) < 0.2


def test_true_peak_detects_intersample_peaks():
    t = np.arange(SR) / SR
    x = (0.99 * np.sin(2 * np.pi * (SR / 4) * t + np.pi / 4)).astype(np.float32)[:, None]
    assert loudness.true_peak_db(x, SR) > 20 * np.log10(np.max(np.abs(x))) + 0.5


@pytest.mark.parametrize("target", ["spotify", "youtube", "soundcloud", "club"])
def test_finish_hits_platform_targets(target):
    x = _music(8.0)
    y, rep = mastering.finish(x, SR, target)
    t = mastering.TARGETS[target]
    assert rep["within_tolerance"], rep
    assert abs(rep["lufs"] - t.lufs) <= mastering.TOLERANCE_LU
    assert rep["true_peak_db"] <= t.true_peak_db + 0.05
    assert np.isfinite(y).all() and np.max(np.abs(y)) <= 1.0
    assert abs(loudness.integrated_lufs(y, SR) - rep["lufs"]) < 0.05


def test_finish_custom_target_and_silence():
    y, rep = mastering.finish(_music(), SR, "spotify", lufs=-12.0, true_peak=-2.0)
    assert abs(rep["lufs"] + 12.0) <= mastering.TOLERANCE_LU and rep["true_peak_db"] <= -1.95
    with pytest.raises(FriendlyError):
        mastering.finish(np.zeros((SR, 2), np.float32), SR, "spotify")


def test_targets_have_easy_platforms():
    for k in ("spotify", "youtube", "soundcloud", "club"):
        assert k in mastering.TARGETS


# --------------------------------------------------------------------------- lightweight engines


def test_fx_chain_builtin_and_bypass():
    x = _music(2.0)
    chain = [{"type": t} for t in fx.PLUGINS]
    y, eng = fx.render_chain(x, SR, chain, engine="builtin")
    assert y.shape == x.shape and np.isfinite(y).all()
    y2, _ = fx.render_chain(
        x, SR, [{"type": "gain", "params": {"gain_db": 6}, "bypass": True}], engine="builtin"
    )
    assert np.allclose(y2, x, atol=1e-6)


@pytest.mark.skipif(
    importlib.util.find_spec("pedalboard") is None, reason="pedalboard not installed"
)
def test_fx_chain_pedalboard():
    x = _music(2.0)
    y, eng = fx.render_chain(
        x, SR, [{"type": "compressor"}, {"type": "reverb"}, {"type": "limiter"}], engine="auto"
    )
    assert "pedalboard" in eng and y.shape[1] == 2 and np.isfinite(y).all()


def test_builtin_denoise_reduces_noise():
    from studio.server.engines import cleanup

    rng = np.random.default_rng(1)
    t = np.arange(SR * 3) / SR
    clean = 0.3 * np.sin(2 * np.pi * 440 * t) * (t % 1 < 0.5)
    noisy = (clean + 0.03 * rng.standard_normal(len(t))).astype(np.float32)[:, None]
    y, eng = cleanup.clean(noisy, SR, engine="builtin-dsp", strength=1.0)
    quiet = (t % 1) > 0.6
    assert np.std(y[quiet, 0]) < 0.6 * np.std(noisy[quiet, 0])


@pytest.mark.skipif(
    importlib.util.find_spec("noisereduce") is None, reason="noisereduce not installed"
)
def test_noisereduce_engine():
    from studio.server.engines import cleanup

    rng = np.random.default_rng(2)
    noisy = (0.03 * rng.standard_normal(SR * 2)).astype(np.float32)[:, None]
    y, eng = cleanup.clean(noisy, SR, engine="noisereduce", strength=1.0)
    assert eng == "noisereduce" and np.std(y) < np.std(noisy)


def test_builtin_reference_match_moves_tone_and_loudness():
    from studio.server.engines import reference

    x = _music(4.0)
    ref = fx.render_chain(
        _music(4.0, seed=3) * 1.8,
        SR,
        [{"type": "highshelf", "params": {"gain_db": 9}}],
        engine="builtin",
    )[0]
    y = reference.builtin(x, ref, SR)
    assert abs(loudness.integrated_lufs(y, SR) - loudness.integrated_lufs(ref, SR)) < 1.5


def test_pyin_midi(tmp_path):
    from studio.server.engines import audio_io, transcribe

    t = np.arange(SR * 2) / SR
    tone = np.where(t < 1, np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)) * 0.4
    wav = audio_io.write(tmp_path / "tone.wav", tone.astype(np.float32)[:, None], SR)
    res = transcribe.to_midi(wav, str(tmp_path / "out.mid"), engine="pyin-midi")
    assert (tmp_path / "out.mid").exists()
    assert res.get("notes", 1) >= 1


def test_audio_write_guards(tmp_path):
    from studio.server.engines import audio_io

    with pytest.raises(FriendlyError):
        audio_io.write(tmp_path / "silent.wav", np.zeros((SR, 2), np.float32), SR)
    loud = (np.ones((SR, 2)) * 3.0).astype(np.float32)
    p = audio_io.write(tmp_path / "loud.wav", loud, SR)
    y, _ = audio_io.read(p)
    assert np.max(np.abs(y)) <= 1.0


def test_dsp_true_peak_limiter():
    x = _music() * 4.0
    y = dsp.true_peak_limit(x, SR, ceiling_db=-1.0)
    assert loudness.true_peak_db(y, SR) <= -0.95


# ---------------------------------------------------------------- setup CLI


def test_cli_hardware_and_status(capsys):
    from studio.server.engines import cli

    assert cli.main(["hardware"]) == 0
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "tier" in out and "demo-synth" in out


def test_cli_extras_map_to_registry():
    from studio.server.engines import cli, registry

    keys = {s.key for s in registry.ENGINES}
    for names in cli.EXTRAS.values():
        assert set(names) <= keys
    assert set(cli.core_keys()) == {s.key for s in registry.ENGINES if s.tier == "core"}


# ----------------------------------------------------------------- 8 GB card (RTX 2080 Super)


def _rtx2080s():
    from studio.server.engines.hardware import Hardware

    return Hardware(
        os="Windows",
        cpu_count=16,
        ram_gb=32,
        gpu="NVIDIA GeForce RTX 2080 SUPER",
        vram_gb=8.0,
        cuda=True,
        source="test",
        compute_cap="7.5",
    )


def test_8gb_card_verdicts():
    from studio.server.engines import registry, selector

    hw = _rtx2080s()
    assert not hw.bf16 and not hw.flash_attn
    v = {s.key: selector.verdict(s, hw) for s in registry.ENGINES}
    for key in ("acestep", "stable-audio-open", "applio", "seed-vc", "resemble-enhance"):
        assert v[key]["recommended"], (key, v[key])
    assert v["acestep"]["status"] == "fits-reduced"
    assert "0.6B" in v["acestep"]["profile"]["how"]
    for key in ("diffrhythm", "audiosr"):
        assert v[key]["status"] == "tight" and not v[key]["recommended"]
    for key in ("yue", "songgeneration"):
        assert v[key]["status"] == "too-big"
        assert v[key]["label"] == "Not recommended for your card"
    assert "FlashAttention" in v["yue"]["caveat"]


def test_every_heavy_engine_lists_real_vram():
    from studio.server.engines import registry

    for s in registry.ENGINES:
        if s.tier == "heavy":
            assert s.vram_profiles, s.key
            assert s.vram_full_gb >= s.min_vram_gb > 0


def test_auto_selector_never_defaults_to_tight_or_too_big():
    from studio.server.engines import registry, selector
    from studio.server.engines.errors import FriendlyError

    hw = _rtx2080s()

    def all_installed(spec):
        return {"installed": True, "healthy": True, "detail": ""}

    c = selector.select("generate", hw, commercial_only=False, health_fn=all_installed)
    assert c.engine not in ("yue", "songgeneration", "diffrhythm")
    assert selector.verdict(registry.get(c.engine), hw)["recommended"]
    with pytest.raises(FriendlyError, match="not recommended for your card"):
        selector.select("generate", hw, prefer="yue", health_fn=all_installed)
    # Tight engines still work when picked by hand.
    forced = selector.select("generate", hw, prefer="diffrhythm", health_fn=all_installed)
    assert any("Tight fit" in r for r in forced.reasons)


def test_recommendations_order_for_8gb():
    from studio.server.engines import selector

    rec = selector.recommendations(_rtx2080s())
    statuses = [r["status"] for r in rec]
    first_bad = next(i for i, s in enumerate(statuses) if s in ("tight", "too-big"))
    assert all(s in ("fits", "fits-reduced", "cpu") for s in statuses[:first_bad])
    assert all(s in ("tight", "too-big") for s in statuses[first_bad:])


def test_acestep_upstream_profile(monkeypatch):
    from src.utils.vram_profile import acestep_profile

    for k in ("MUSER_ACESTEP_DIT_MODEL", "MUSER_ACESTEP_LM_MODEL", "MUSER_ACESTEP_QUANT"):
        monkeypatch.delenv(k, raising=False)
    p = acestep_profile(7.8)
    assert p.dit_model == "acestep-v15-turbo" and p.lm_model == "acestep-5Hz-lm-0.6B"
    assert p.offload_to_cpu and p.quantization == "int8_weight_only" and p.budget_gb < 8
    big = acestep_profile(24)
    assert big.dit_model == "acestep-v15-sft" and big.quantization is None
    monkeypatch.setenv("MUSER_ACESTEP_QUANT", "none")
    assert acestep_profile(7.8).quantization is None


def test_every_genre_has_tuned_acestep_8gb_settings():
    from studio.server import presets

    genres = [p for p in presets.all_presets().values() if p["category"] == "genre"]
    assert len(genres) == 24
    seen = set()
    for g in genres:
        ace = g["generate"].get("acestep")
        assert ace, g["id"]
        assert ace["profile"] == "8gb"
        assert len(ace["tags"].split()) >= 20, g["id"]
        assert ace["infer_step"] == 8  # the 8 GB profile loads the turbo DiT
        assert 10 <= ace["duration_s"] <= 60  # short on purpose: offloaded DiT is slow
        assert ace["lyrics"] == "[instrumental]"
        assert "—" not in ace["tags"]
        seen.add(ace["tags"])
    assert len(seen) == 24  # no two genres share a prompt
