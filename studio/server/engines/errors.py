"""Plain-language errors so a beginner always knows what happened and what to do."""

from __future__ import annotations


class FriendlyError(Exception):
    """An error whose message is already written for a non-technical user."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.message} {self.hint}".strip()


_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("out of memory", "cuda oom", "outofmemoryerror"),
        "Your graphics card ran out of memory. Try a shorter song, a lighter model, or close other apps.",
    ),
    (
        ("ffmpeg",),
        "FFmpeg is missing. Run the setup script again (it installs FFmpeg) and restart the Studio.",
    ),
    (
        ("no module named", "modulenotfounderror", "not installed"),
        "That tool is not installed yet. Open Engines and press Install next to it.",
    ),
    (
        ("unknown track", "track not found"),
        "That song is no longer in your library. Pick another one and try again.",
    ),
    (
        ("has no stems", "split it first"),
        "Split the song into stems first (one click: Split stems).",
    ),
    (
        ("all stems are muted",),
        "Every part is muted, so there is nothing to render. Unmute at least one stem.",
    ),
    (
        ("connection", "timed out", "urlopen", "max retries"),
        "Could not download the model. Check your internet connection and try again.",
    ),
    (
        ("no such file", "filenotfound", "does not exist"),
        "An audio file the Studio needed is missing. Try the step again, or re-import the song.",
    ),
    (
        ("libsndfile", "format not recognised", "error opening"),
        "That audio file could not be read. Try a WAV, MP3 or FLAC file.",
    ),
]


def friendly_message(exc: BaseException) -> str:
    """Turn any exception into one calm, actionable sentence."""
    if isinstance(exc, FriendlyError):
        return str(exc)
    raw = f"{type(exc).__name__}: {exc}".lower()
    for needles, msg in _RULES:
        if any(n in raw for n in needles):
            return msg
    return "Something went wrong on that step. Nothing was lost: your previous version is still in the library. Try again, or open Advanced for details."
