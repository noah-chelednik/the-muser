"""Desktop launcher for The Muser Studio (the entry point of the Windows and macOS installers).

Normal start:   opens the Studio in its own window (falls back to your browser) and quits the
                local server when the window closes.
--version       print the version and exit.
--smoke-test    headless self-check used by CI: imports every bundled engine, starts the server on a
                free port in demo mode, drives the API, and exits 0 only if everything works.
--no-window     run the server only (prints the URL).
--demo          force demo mode (no Ollama / models needed).

User data (tracks, exports, logs, downloaded models) lives in a per-user folder, never in the app
folder. Ollama is external: if it is missing the Studio runs in demo mode and says how to install it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

APP_NAME = "The Muser"
OLLAMA_URL = "https://ollama.com/download"


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "TheMuser"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "the-muser"


def resource_root() -> Path:
    """Folder that holds the bundled code and the built web UI."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def setup_environment(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MUSER_HOME", str(home))
    os.environ.setdefault("MUSER_STUDIO_DATA", str(Path(os.environ["MUSER_HOME"]) / "studio_data"))
    # Keep downloaded model files in the user folder too.
    os.environ.setdefault("HF_HOME", str(Path(os.environ["MUSER_HOME"]) / "models" / "huggingface"))
    if resource_root() not in map(Path, sys.path):
        sys.path.insert(0, str(resource_root()))
    _expose_ffmpeg(Path(os.environ["MUSER_HOME"]))


def _expose_ffmpeg(home: Path) -> None:
    """The installer bundles an ffmpeg build (imageio-ffmpeg). Put it on PATH as plain `ffmpeg`."""
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg

        src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return
    bindir = home / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    dst = bindir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    try:
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
            dst.chmod(0o755)
    except OSError:
        return
    os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")


def free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free local port")


class Server:
    def __init__(self, port: int):
        import uvicorn

        from studio.server.app import app

        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", log_config=None)
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self, timeout: float = 60.0) -> None:
        self._thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(self.url + "/api/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:
                time.sleep(0.25)
        raise RuntimeError("The Muser server did not start")

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


def _get(url: str, timeout: float = 20.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def smoke_test(with_models: bool = False) -> int:
    """Headless end-to-end check. Prints one JSON line per step; returns a process exit code."""
    tmp = Path(tempfile.mkdtemp(prefix="muser-smoke-"))
    os.environ["MUSER_HOME"] = str(tmp)
    os.environ["MUSER_STUDIO_DATA"] = str(tmp / "studio_data")
    os.environ["MUSER_STUDIO_DEMO"] = "1"
    setup_environment(tmp)
    results: list[tuple[str, bool, str]] = []

    def step(name: str, fn) -> None:
        try:
            detail = fn()
            results.append((name, True, str(detail or "")))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {e}"))
        ok, msg = results[-1][1], results[-1][2]
        print(json.dumps({"step": name, "ok": ok, "detail": msg[:300]}), flush=True)

    def imports():
        import importlib

        mods = [
            "numpy",
            "scipy",
            "soundfile",
            "librosa",
            "pedalboard",
            "pyloudnorm",
            "noisereduce",
            "matchering",
            "music21",
            "pretty_midi",
            "mido",
            "litellm",
            "fastapi",
            "uvicorn",
            "studio.server.app",
            "studio.server.engines.stem_fidelity",
            "studio.server.engines.separation",
            "src.orchestrator.tool_definitions",
        ]
        for m in mods:
            importlib.import_module(m)
        return f"{len(mods)} modules"

    def fidelity():
        import numpy as np

        from studio.server.engines import stem_fidelity as sf

        rng = np.random.default_rng(0)
        mix = rng.standard_normal((2, 4800)).astype("float32") * 0.1
        a, b = mix * 0.6, mix * 0.4
        db = sf.null_test_db(mix, {"a": a, "b": b})
        assert db < -60, db
        return f"null test {db:.1f} dB"

    def ffmpeg():
        import subprocess

        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()  # the copy bundled in the installer
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr[:200]
        assert shutil.which("ffmpeg"), "ffmpeg is not on PATH for the Studio"
        return out.stdout.splitlines()[0]

    def separation():
        """Real stem split with a downloaded model (needs internet; run with --with-models)."""
        import numpy as np
        import soundfile as sf

        from studio.server.engines import separation

        sr = 44100
        t = np.arange(sr * 8) / sr
        mix = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 1760 * t)
        mix += 0.05 * np.random.default_rng(1).standard_normal(t.size)
        src = tmp / "mix.wav"
        sf.write(src, np.stack([mix, mix * 0.9], axis=1).astype("float32"), sr, subtype="PCM_24")
        res = separation.separate(
            str(src),
            tmp / "stems",
            mode="2stem",
            engine="audio-separator",
            progress=lambda m: print(json.dumps({"progress": m[:120]}), flush=True),
        )
        names = sorted(res["stems"])
        assert len(names) >= 2, names
        return f"engine={res['engine']} model={res['model']} stems={names} {res['note'][-120:]}"

    server: Server | None = None

    def start():
        nonlocal server
        server = Server(free_port(0))
        server.start()
        return server.url

    def api():
        assert server
        st, body = _get(server.url + "/api/status")
        data = json.loads(body)
        assert st == 200 and data.get("mode") in ("demo", "hybrid", "full"), data.get("mode")
        return f"mode={data['mode']} tools={data.get('tool_count')}"

    def ui():
        assert server
        st, body = _get(server.url + "/")
        text = body.decode("utf-8", "replace")
        assert st == 200 and 'id="root"' in text, "web UI index.html not served"
        import re

        asset = re.search(r'(?:src|href)="(/assets/[^"]+\.js)"', text)
        assert asset, "no JS asset referenced"
        st2, _ = _get(server.url + asset.group(1))
        assert st2 == 200
        return asset.group(1)

    def generate():
        assert server
        req = urllib.request.Request(
            server.url + "/api/generate",
            data=json.dumps({"prompt": "lofi chill", "duration_s": 6, "force_demo": True}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            jid = json.loads(r.read())["job_id"]
        deadline = time.time() + 120
        while time.time() < deadline:
            _, body = _get(f"{server.url}/api/jobs/{jid}")
            j = json.loads(body)
            if j["status"] == "done":
                break
            if j["status"] in ("error", "failed"):
                raise RuntimeError(j.get("error") or j.get("message"))
            time.sleep(0.5)
        else:
            raise TimeoutError("demo generate did not finish")
        _, body = _get(server.url + "/api/tracks")
        tracks = json.loads(body)
        assert tracks, "no track saved"
        wav = tmp / "studio_data"
        assert any(wav.rglob("*.wav")), "no wav written to the user data folder"
        return f"{len(tracks)} track(s), audio written to user folder"

    step("version", lambda: __import__("studio.version", fromlist=["x"]).__version__)
    step("imports", imports)
    step("fidelity", fidelity)
    step("ffmpeg", ffmpeg)
    step("server", start)
    step("api", api)
    step("ui", ui)
    step("generate", generate)
    if with_models:
        step("separation", separation)
    if server:
        server.stop()
    shutil.rmtree(tmp, ignore_errors=True)
    failed = [n for n, ok, _ in results if not ok]
    print(json.dumps({"smoke_test": "FAIL" if failed else "PASS", "failed": failed}), flush=True)
    return 1 if failed else 0


def _redirect_output(home: Path) -> None:
    """Windowed apps have no console (sys.stdout is None). Log to a file instead."""
    logdir = home / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    f = open(logdir / "muser.log", "a", buffering=1, encoding="utf-8", errors="replace")  # noqa: SIM115
    sys.stdout = f
    sys.stderr = f


def _ollama_note() -> str | None:
    try:
        _get("http://localhost:11434/api/version", timeout=1.5)
        return None
    except Exception:
        return (
            "Ollama was not found, so chat runs in demo mode. For the AI assistant, install "
            f"Ollama from {OLLAMA_URL} and run: ollama pull qwen3:8b"
        )


def run_app(args: argparse.Namespace) -> int:
    home = user_data_dir()
    if getattr(sys, "frozen", False) and (sys.stdout is None or not sys.stdout.isatty()):
        home.mkdir(parents=True, exist_ok=True)
        _redirect_output(home)
    setup_environment(home)
    if args.demo:
        os.environ["MUSER_STUDIO_DEMO"] = "1"
    note = _ollama_note()
    if note:
        print("[INFO]", note, flush=True)
    server = Server(free_port(args.port))
    server.start()
    print(f"The Muser Studio running at {server.url}", flush=True)
    if args.no_window:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.stop()
            return 0
    try:
        import webview

        webview.create_window(
            "The Muser Studio", server.url, width=1360, height=860, min_size=(960, 640)
        )
        webview.start()
    except Exception as e:  # noqa: BLE001
        print(
            f"[INFO] No native window available ({type(e).__name__}); opening your browser.",
            flush=True,
        )
        import webbrowser

        webbrowser.open(server.url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    server.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="the-muser", description="The Muser Studio desktop app")
    p.add_argument("--version", action="store_true")
    p.add_argument("--smoke-test", action="store_true", help="headless self-check (used by CI)")
    p.add_argument(
        "--with-models",
        action="store_true",
        help="with --smoke-test: also download a stem model and split a test clip",
    )
    p.add_argument("--no-window", action="store_true", help="server only, no window")
    p.add_argument("--demo", action="store_true", help="force demo mode")
    p.add_argument("--port", type=int, default=int(os.environ.get("MUSER_STUDIO_PORT", "8765")))
    args = p.parse_args(argv)
    if args.version:
        from studio.version import __version__

        print(f"The Muser Studio {__version__}")
        return 0
    if args.smoke_test:
        return smoke_test(args.with_models)
    return run_app(args)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
