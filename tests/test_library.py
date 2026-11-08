"""Unit tests for the sample / soundfont library scanner and file gate."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from studio.server import library


def _tiny_wav(path: Path, frames: int = 441, sr: int = 44100) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(b"\x00\x00" * frames)


@pytest.fixture()
def libdb(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "DB_PATH", tmp_path / "sample_library.db")
    return tmp_path


def test_scan_indexes_samples_and_soundfonts(libdb: Path):
    kit = libdb / "kit"
    kit.mkdir()
    _tiny_wav(kit / "kick.wav")
    (kit / "piano.sf2").write_bytes(b"RIFF\x00\x00\x00\x00sfbk")
    result = library.scan_paths([str(kit)])
    assert result["scanned"] == 2
    samples = library.search("kick", kind="sample")
    assert len(samples) == 1
    assert samples[0]["name"] == "kick"
    assert samples[0]["duration"] == pytest.approx(0.01, rel=1e-2)
    assert samples[0]["sample_rate"] == 44100
    fonts = library.search("", kind="soundfont")
    assert len(fonts) == 1
    assert fonts[0]["name"] == "piano"
    stats = library.get_stats()
    assert stats["samples"] == 1
    assert stats["soundfonts"] == 1


def test_resolve_indexed_allows_scanned_file(libdb: Path):
    kit = libdb / "kit"
    kit.mkdir()
    wav = kit / "snare.wav"
    _tiny_wav(wav)
    library.scan_paths([str(kit)])
    resolved = library.resolve_indexed(str(wav))
    assert resolved == wav.resolve()


def test_resolve_indexed_rejects_unindexed_and_traversal(libdb: Path):
    kit = libdb / "kit"
    kit.mkdir()
    _tiny_wav(kit / "hat.wav")
    secret = libdb / "secret.txt"
    secret.write_text("nope")
    library.scan_paths([str(kit)])
    with pytest.raises(PermissionError):
        library.resolve_indexed(str(secret))
    sneaky = kit / ".." / "secret.txt"
    with pytest.raises(PermissionError):
        library.resolve_indexed(str(sneaky))


def test_library_file_route_allows_indexed_and_blocks_others(libdb: Path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from studio.server.routes_library import router

    kit = libdb / "kit"
    kit.mkdir()
    wav = kit / "ride.wav"
    _tiny_wav(wav)
    secret = libdb / "secret.txt"
    secret.write_text("nope")
    library.scan_paths([str(kit)])

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    ok = client.get("/api/library/file", params={"path": str(wav)})
    assert ok.status_code == 200
    assert ok.content[:4] == b"RIFF"

    denied = client.get("/api/library/file", params={"path": str(secret)})
    assert denied.status_code == 403

    missing = client.get("/api/library/file", params={"path": str(libdb / "nope.wav")})
    assert missing.status_code == 404
