"""Tests for the Studio API layer (studio/server) in demo mode.

Runs without GPU, models, or an LLM. Skipped if FastAPI isn't installed
(install with: pip install -e ".[studio]").
"""

from __future__ import annotations

import json
import shutil
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["MUSER_STUDIO_DEMO"] = "1"
    os.environ["MUSER_STUDIO_DATA"] = str(tmp_path_factory.mktemp("studio_data"))
    from fastapi.testclient import TestClient

    from studio.server.app import app

    return TestClient(app)


def _wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.2)
    raise TimeoutError(job_id)


def test_status_reports_demo_mode(client):
    r = client.get("/api/status?refresh=true")
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "demo"
    assert d["tool_count"] >= 40
    for key in ("ollama", "ffmpeg", "gpu", "demucs", "acestep"):
        assert key in d["items"]
        assert d["items"][key]["detail"]


def test_demo_parse_prompt():
    from studio.server.demo_synth import parse_prompt

    s = parse_prompt("lo-fi beat in F minor", duration_s=20)
    assert s.bpm == 80 and s.key_name == "F minor"
    assert parse_prompt("house track 126 bpm in D major").key_name == "D major"


def test_chat_stream_demo_creates_track(client):
    with client.stream("POST", "/api/chat", json={"message": "dark trap beat 8 seconds"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    events = [blk.split("\n") for blk in body.strip().split("\n\n") if blk.startswith("event:")]
    names = [e[0].split(": ", 1)[1] for e in events]
    assert "token" in names and "track" in names and names[-1] == "done"
    track = next(json.loads(e[1][6:]) for e in events if e[0] == "event: track")["track"]
    assert track["source"] == "demo-synth"


def test_generate_split_mix_export(client):
    j = _wait(
        client,
        client.post("/api/generate", json={"prompt": "lofi in A minor", "duration_s": 8}).json()[
            "job_id"
        ],
    )
    assert j["status"] == "done", j
    tid = j["result"]["track"]["id"]
    assert client.get(j["result"]["track"]["url"]).status_code == 200

    j = _wait(
        client, client.post(f"/api/tracks/{tid}/split", json={"mode": "4stem"}).json()["job_id"]
    )
    assert j["status"] == "done", j
    stems = j["result"]["track"]["stems"]
    assert [s["name"] for s in stems] == ["drums", "bass", "chords", "lead"]
    assert j["result"]["method"] == "demo-synth"

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    params = [
        {"stem_id": stems[0]["id"], "gain_db": -3, "eq_low_db": 4, "comp": 0.5},
        {"stem_id": stems[1]["id"], "pan": -0.3, "reverb": 0.3},
        {"stem_id": stems[2]["id"], "mute": True},
        {"stem_id": stems[3]["id"], "eq_high_db": 3},
    ]
    j = _wait(
        client, client.post("/api/mix", json={"track_id": tid, "stems": params}).json()["job_id"]
    )
    assert j["status"] == "done", j
    mix = j["result"]["track"]
    assert mix["source"] == "mixdown" and mix["duration_s"] > 4

    j = _wait(
        client,
        client.post("/api/export", json={"track_id": mix["id"], "formats": ["wav", "mp3"]}).json()[
            "job_id"
        ],
    )
    assert j["status"] == "done", j
    assert {"wav", "mp3"} <= set(j["result"]["files"])


def test_band_split_fallback_for_upload(client, tmp_path):
    import numpy as np
    import soundfile as sf

    p = tmp_path / "tone.wav"
    t = np.arange(44100) / 44100
    sf.write(p, 0.3 * np.sin(2 * np.pi * 220 * t), 44100)
    with open(p, "rb") as f:
        up = client.post("/api/upload", files={"file": ("tone.wav", f, "audio/wav")}).json()
    tid = up["track"]["id"]
    j = _wait(
        client, client.post(f"/api/tracks/{tid}/split", json={"mode": "4stem"}).json()["job_id"]
    )
    assert j["status"] == "done", j
    # demo mode forces the band-split fallback even if Demucs is installed
    assert j["result"]["method"] == "band-split"
    assert len(j["result"]["track"]["stems"]) == 4


def test_files_endpoint_blocks_traversal(client):
    from studio.server.store import DATA_DIR, resolve_file

    assert resolve_file(DATA_DIR.name, "../../../../etc/passwd") is None
    r = client.get(f"/files/{DATA_DIR.name}/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd")
    assert "root:" not in r.text
