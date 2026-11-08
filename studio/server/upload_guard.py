"""Server-side guard for user audio uploads (local Studio backend).

Mirrors the browser checks in studio/web/src/audio/upload.ts:

- extension allowlist and a MIME allowlist
- streamed size cap (40 MB) so an oversized body is never fully written
- magic bytes sniffed from the head of the file and matched to the extension family
- a real decode check (soundfile, or ffprobe when installed) before the file is accepted
- stored under a random name inside UPLOADS_DIR; the client filename is never used as a path,
  only as a sanitized display title
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import BinaryIO

MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_SECONDS = 12 * 60

EXT_FAMILY = {
    ".wav": "wav", ".wave": "wav", ".mp3": "mp3", ".flac": "flac", ".ogg": "ogg", ".oga": "ogg", ".opus": "ogg",
    ".aif": "aiff", ".aiff": "aiff", ".aifc": "aiff", ".m4a": "m4a", ".webm": "webm", ".weba": "webm",
}
MIME_OK = {
    "audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave", "audio/mpeg", "audio/mp3", "audio/x-mp3",
    "audio/flac", "audio/x-flac", "audio/ogg", "audio/opus", "application/ogg", "audio/aiff", "audio/x-aiff",
    "audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac", "audio/webm", "video/webm", "application/octet-stream", "",
}
FAMILY_SUFFIX = {"wav": ".wav", "mp3": ".mp3", "flac": ".flac", "ogg": ".ogg", "aiff": ".aiff", "m4a": ".m4a", "webm": ".webm"}


class UploadRejected(ValueError):
    """Raised with a user-readable message when an upload fails a check."""


def sanitize_title(raw: str | None) -> str:
    name = Path((raw or "").replace("\\", "/")).name
    name = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name)
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[\x00-\x1f\x7f<>\"'`&;{}$|\\/]", "", name)
    name = re.sub(r"[^\w .()#+-]", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return name[:60] or "Upload"


def ext_family(filename: str | None) -> str | None:
    return EXT_FAMILY.get(Path(filename or "").suffix.lower())


def sniff(head: bytes) -> str | None:
    if len(head) < 12:
        return None
    if head[:4] in (b"RIFF", b"RF64") and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[4:8] == b"ftyp":
        return "m4a" if head[8:12] in (b"M4A ", b"M4B ", b"mp42", b"mp41", b"isom", b"iso2", b"dash", b"MSNV", b"f4a ") or head[8:11] == b"3gp" else None
    if head[:3] == b"ID3":
        size = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) | ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
        o = 10 + size
        return "flac" if head[o:o + 4] == b"fLaC" else "mp3"
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0 and (head[1] & 0x06) and (head[2] & 0xF0) != 0xF0:
        return "mp3"
    if head[0] == 0xFF and (head[1] & 0xF6) == 0xF0:
        return "m4a"
    return None


def check_meta(filename: str | None, content_type: str | None) -> str:
    fam = ext_family(filename)
    if not fam:
        raise UploadRejected("Only WAV, MP3, FLAC, OGG, AIFF, M4A or WebM audio files can be uploaded.")
    if (content_type or "").lower().split(";")[0].strip() not in MIME_OK:
        raise UploadRejected(f"This file says it is {content_type}, not audio.")
    return fam


def _decodes(path: Path) -> float:
    """Duration in seconds if the file really decodes as audio. Raises UploadRejected otherwise."""
    try:
        import soundfile as sf  # type: ignore

        try:
            info = sf.info(str(path))
            if info.frames <= 0 or info.samplerate <= 0:
                raise UploadRejected("The file decoded to no audio.")
            return info.frames / info.samplerate
        except UploadRejected:
            raise
        except Exception:
            pass  # mp3, m4a and webm need ffmpeg below
    except ImportError:
        pass
    probe = shutil.which("ffprobe")
    if probe:
        r = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type:format=duration", "-of", "default=nw=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0 or "codec_type=audio" not in r.stdout:
            raise UploadRejected("The file could not be decoded as audio.")
        m = re.search(r"duration=([0-9.]+)", r.stdout)
        return float(m.group(1)) if m else 0.0
    raise UploadRejected("The file could not be decoded as audio.")


def save_upload(stream: BinaryIO, filename: str | None, content_type: str | None, dest_dir: Path) -> tuple[Path, str]:
    """Validate and store an upload. Returns (stored path with a random name, sanitized title)."""
    fam = check_meta(filename, content_type)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored = dest_dir / f"up_{secrets.token_hex(12)}{FAMILY_SUFFIX[fam]}"
    root = dest_dir.resolve()
    if stored.resolve().parent != root:
        raise UploadRejected("Bad upload path.")
    total = 0
    head = b""
    try:
        with open(stored, "xb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise UploadRejected(f"That file is over the {MAX_UPLOAD_BYTES // 1048576} MB limit.")
                if len(head) < 4096:
                    head += chunk[: 4096 - len(head)]
                out.write(chunk)
        if total < 44:
            raise UploadRejected("That file is empty or too small to be audio.")
        got = sniff(head)
        if not got:
            raise UploadRejected("The file contents are not a recognised audio format.")
        if got != fam:
            raise UploadRejected(f"The file is named {Path(filename or '').suffix} but its contents are {got.upper()}.")
        secs = _decodes(stored)
        if secs > MAX_SECONDS:
            raise UploadRejected(f"That is {round(secs / 60)} minutes long. The limit is {MAX_SECONDS // 60} minutes.")
        os.chmod(stored, 0o600)
    except BaseException:
        stored.unlink(missing_ok=True)
        raise
    return stored, sanitize_title(filename)
