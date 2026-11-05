"""Studio API v2 in demo mode: Easy flow, Finish, one-click tools, Advanced render, presets, engines, session.

CPU only. Runs the built-in engines (plus any lightweight engines that happen to be installed).
"""

from __future__ import annotations

import io
import json
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["MUSER_STUDIO_DEMO"] = "1"
    os.environ.setdefault("MUSER_STUDIO_DATA", str(tmp_path_factory.mktemp("studio_data_v2")))
    from fastapi.testclient import TestClient

    from studio.server.app import app

    return TestClient(app)


def _wait(client, job_id, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.2)
    raise TimeoutError(job_id)


def _run(client, method, url, **kw):
    r = getattr(client, method)(url, **kw)
    assert r.status_code == 200, r.text
    j = _wait(client, r.json()["job_id"])
    assert j["status"] == "done", j
    return j["result"]


@pytest.fixture(scope="module")
def made(client):
    return _run(
        client,
        "post",
        "/api/easy/make",
        json={
            "vibe": "rainy night, warm and dusty",
            "genre_id": "genre/lo-fi-chill",
            "duration_s": 12,
        },
    )


def test_vibes_and_targets(client):
    d = client.get("/api/vibes").json()
    assert len(d["vibes"]) >= 12
    assert {"spotify", "youtube", "soundcloud", "club"} <= set(d["finish"])
    assert len(d["sliders"]) == 5
    t = client.get("/api/mastering/targets").json()["targets"]
    assert t["spotify"]["lufs"] == -14


def test_engines_and_hardware(client):
    d = client.get("/api/engines").json()
    assert len(d["engines"]) >= 20
    for e in d["engines"]:
        assert {"health", "fits", "fit_reason", "untested_here", "commercial"} <= set(e)
    sel = d["selected"]
    for task in ("generate", "separate", "denoise", "match", "midi", "fx", "master", "loudness"):
        assert sel[task]["engine"], task
    keys = {e["key"]: e for e in d["engines"]}
    for task, pick in sel.items():
        if pick["engine"]:
            assert keys[pick["engine"]]["commercial"] != "no", task
    h = client.get("/api/hardware").json()
    assert h["tier"] and isinstance(h["recommendations"], list)
    assert client.get("/api/engines/demo-synth/health").json()["healthy"]
    assert client.get("/api/engines/nope/health").status_code == 404


def test_install_dry_run(client):
    res = _run(client, "post", "/api/engines/noisereduce/install?dry_run=true")
    assert res["engine"] == "noisereduce"
    assert any("pip" in line for line in res["log"])


def test_easy_make_and_render(client, made):
    assert made["track"]["id"] and made["root_id"]
    assert set(made["macros"]) == {"energy", "vocals", "bass", "brightness", "space"}
    res = _run(
        client,
        "post",
        "/api/easy/render",
        json={"track_id": made["root_id"], "genre_id": made["genre_id"], "energy": 90, "space": 10},
    )
    assert res["track"]["id"] != made["root_id"]
    assert res["track"]["url"]


def test_easy_make_needs_a_vibe(client):
    assert client.post("/api/easy/make", json={"vibe": ""}).status_code == 400


@pytest.mark.parametrize("target,lufs,tp", [("spotify", -14, -1), ("club", -8, -0.5)])
def test_finish(client, made, target, lufs, tp):
    res = _run(
        client, "post", "/api/finish", json={"track_id": made["track"]["id"], "target": target}
    )
    rep = res["report"]
    assert rep["target"]["key"] == target
    assert abs(rep["lufs"] - lufs) <= 0.5 and rep["true_peak_db"] <= tp + 0.05
    assert rep["within_tolerance"]
    a = client.get(f"/api/tracks/{res['track']['id']}/analysis").json()["analysis"]
    assert abs(a["lufs"] - rep["lufs"]) < 0.2


def test_finish_unknown_target(client, made):
    assert (
        client.post(
            "/api/finish", json={"track_id": made["track"]["id"], "target": "mars"}
        ).status_code
        == 400
    )


@pytest.mark.parametrize("tool", ["denoise", "midi", "split"])
def test_one_click_tools(client, made, tool):
    res = _run(client, "post", f"/api/tools/{tool}", json={"track_id": made["track"]["id"]})
    if tool == "midi":
        assert res["midi_url"]
    else:
        assert res["track"]["id"] != made["track"]["id"] or tool == "split"


def test_unknown_tool(client, made):
    assert (
        client.post("/api/tools/teleport", json={"track_id": made["track"]["id"]}).status_code
        == 404
    )


def test_advanced_render_and_mute(client, made):
    tr = client.get("/api/tracks").json()
    t = next(x for x in tr if x["id"] == made["root_id"])
    assert t["stems"]
    stems = [
        {"stem_id": s["id"], "chain": [{"type": "compressor"}], "gain_db": -2, "pan": 0.1}
        for s in t["stems"]
    ]
    res = _run(
        client,
        "post",
        "/api/advanced/render",
        json={"track_id": t["id"], "stems": stems, "master_chain": [{"type": "limiter"}]},
    )
    assert res["track"]["id"] != t["id"]
    all_muted = [dict(s, mute=True) for s in stems]
    r = client.post("/api/advanced/render", json={"track_id": t["id"], "stems": all_muted})
    j = _wait(client, r.json()["job_id"])
    assert j["status"] == "error" and "muted" in j["error"]


def test_presets_api(client):
    d = client.get("/api/presets").json()
    assert len(d["presets"]) >= 100 and sum(d["counts"].values()) >= 100
    assert client.get("/api/presets?q=vocal").json()["presets"]
    pid = d["presets"][0]["id"]
    assert client.get(f"/api/presets/{pid}/item").json()["id"] == pid
    saved = client.post(
        "/api/presets",
        json={"preset": {"name": "Test Chain", "category": "fx", "chain": [{"type": "delay"}]}},
    ).json()["preset"]
    assert client.post(f"/api/presets/{saved['id']}/favorite").json()["favorite"] is True
    bundle = client.get(f"/api/presets/export?ids={saved['id']}").json()
    assert client.delete(f"/api/presets/{saved['id']}/item").json()["deleted"]
    up = client.post(
        "/api/presets/import",
        files={"file": ("p.json", io.BytesIO(json.dumps(bundle).encode()), "application/json")},
    )
    assert up.status_code == 200 and up.json()["imported"]
    bad = client.post(
        "/api/presets",
        json={"preset": {"name": "x", "category": "mix", "chain": [{"type": "warp-drive"}]}},
    )
    assert bad.status_code == 400


def test_preset_preview(client):
    res = _run(
        client, "post", "/api/presets/preview", json={"preset_id": "mix/airy-bus", "seconds": 3}
    )
    assert res["url"] and res["dry_url"]


def test_session_roundtrip(client):
    assert client.put("/api/session", json={"easy": {"versions": [1, 2]}}).json()["saved"]
    s = client.get("/api/session").json()
    assert s["easy"]["versions"] == [1, 2] and s["saved"]


def test_spa_still_served_after_v2_routes(client):
    assert client.get("/api/fx/plugins").json()["plugins"]["compressor"]
    assert client.get("/api/separation/models").json()["default"]["4stem"]
