"""Server upload guard: allowlist, magic bytes, size cap, decode check, random storage names."""

import io
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from server import upload_guard as ug  # noqa: E402


def wav_bytes(seconds: float = 0.1, rate: int = 8000) -> bytes:
    n = int(seconds * rate)
    data = b"\x00\x00" * n
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return hdr + b"data" + struct.pack("<I", len(data)) + data


def test_sanitize_title():
    assert ug.sanitize_title("../../etc/my <b>snare</b>.wav") .find("/") == -1
    assert "<" not in ug.sanitize_title("my <b>.wav")


def test_rejects_bad_extension(tmp_path):
    with pytest.raises(ug.UploadRejected):
        ug.save_upload(io.BytesIO(wav_bytes()), "beat.exe", "application/octet-stream", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_rejects_non_audio_bytes(tmp_path):
    with pytest.raises(ug.UploadRejected):
        ug.save_upload(io.BytesIO(b"hello, not audio " * 100), "fake.wav", "audio/wav", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_rejects_extension_mismatch(tmp_path):
    with pytest.raises(ug.UploadRejected):
        ug.save_upload(io.BytesIO(wav_bytes()), "liar.mp3", "audio/mpeg", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_rejects_oversize_streamed(tmp_path, monkeypatch):
    monkeypatch.setattr(ug, "MAX_UPLOAD_BYTES", 64 * 1024)
    with pytest.raises(ug.UploadRejected):
        ug.save_upload(io.BytesIO(wav_bytes(seconds=10)), "big.wav", "audio/wav", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_accepts_wav_with_random_name(tmp_path):
    pytest.importorskip("soundfile")
    stored, title = ug.save_upload(io.BytesIO(wav_bytes()), "../my snare.wav", "audio/wav", tmp_path)
    assert stored.parent.resolve() == tmp_path.resolve()
    assert stored.name.startswith("up_") and stored.suffix == ".wav"
    assert "snare" in title and "/" not in title
    assert (stored.stat().st_mode & 0o777) == 0o600
