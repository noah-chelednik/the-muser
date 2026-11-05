"""One-click installer for registry engines.

Only installs what the registry declares (no arbitrary packages). Uses ``uv``
when it is available (fast), otherwise ``python -m pip`` inside the running
venv. Heavy repo engines are cloned into ``models/<key>`` with their own venv so
their pinned dependencies never break the Studio.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from . import registry
from .errors import FriendlyError

Log = Callable[[str], None]


def _pip_base() -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]


def plan(key: str) -> list[list[str]]:
    """Commands that would run for this engine (also used for dry runs and tests)."""
    spec = registry.get(key)
    ins = spec.install
    cmds: list[list[str]] = []
    if ins.kind == "builtin":
        return cmds
    if ins.kind == "pip":
        base = _pip_base()
        if ins.pip:
            cmd = base + list(ins.pip)
            if ins.index_url:
                cmd += ["--extra-index-url", ins.index_url]
            cmds.append(cmd)
        if ins.no_deps:
            cmds.append(base + ["--no-deps"] + list(ins.no_deps))
        return cmds
    if ins.kind in ("repo", "app"):
        target = Path(registry.MODELS_DIR) / key
        if not shutil.which("git"):
            raise FriendlyError(
                "Git is needed to install this model.", "Install Git for Windows, then try again."
            )
        cmds.append(["git", "clone", "--depth", "1", ins.repo, str(target)])
        if ins.kind == "repo":
            venv = target / ".venv"
            py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            cmds.append([sys.executable, "-m", "venv", str(venv)])
            cmds.append([str(py), "-m", "pip", "install", "-r", str(target / ins.requirements)])
        return cmds
    raise FriendlyError(f"Don't know how to install {spec.name}.")


def _prefetch_audio_separator(log: Log) -> None:
    from .separation import DEFAULT_MODEL, prefetch

    log(f"Downloading separation model {DEFAULT_MODEL} ...")
    prefetch(DEFAULT_MODEL)


def _prefetch_deepfilternet(log: Log) -> None:
    log("Downloading DeepFilterNet3 weights ...")
    from df.enhance import init_df  # type: ignore

    init_df(log_level="ERROR")


PREFETCH: dict[str, Callable[[Log], None]] = {
    "audio_separator": _prefetch_audio_separator,
    "deepfilternet": _prefetch_deepfilternet,
}


def install(key: str, log: Log = print, dry_run: bool = False) -> dict:
    spec = registry.get(key)
    if spec.install.kind == "builtin":
        return {"engine": key, "installed": True, "log": ["Built in, nothing to install."]}
    lines: list[str] = []

    def emit(s: str) -> None:
        lines.append(s)
        log(s)

    cmds = plan(key)
    if spec.install.kind in ("repo", "app") and (Path(registry.MODELS_DIR) / key).exists():
        cmds = [c for c in cmds if c[:2] != ["git", "clone"]]
        emit(f"{Path(registry.MODELS_DIR) / key} already exists, skipping download.")
    for cmd in cmds:
        emit("$ " + " ".join(cmd))
        if dry_run:
            continue
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                emit(line[-300:])
        if proc.wait() != 0:
            raise FriendlyError(
                f"Installing {spec.name} failed.",
                "See the install log in System. Your Studio still works without it.",
            )
    importlib_invalidate()
    if spec.install.prefetch and not dry_run:
        try:
            PREFETCH[spec.install.prefetch](emit)
        except Exception as e:
            emit(f"Model download will happen on first use instead ({type(e).__name__}: {e}).")
    for step in spec.install.steps:
        emit("Note: " + step)
    h = registry.health(spec) if not dry_run else {"installed": False, "detail": "dry run"}
    emit(h["detail"])
    return {
        "engine": key,
        "installed": bool(h["installed"]),
        "dry_run": dry_run,
        "log": lines[-200:],
    }


def importlib_invalidate() -> None:
    import importlib

    importlib.invalidate_caches()
