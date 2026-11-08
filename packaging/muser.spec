# PyInstaller spec for The Muser Studio (Windows + macOS desktop builds).
# Build from the repo root:  pyinstaller packaging/muser.spec --noconfirm
# Needs the web UI built first: (cd studio/web && npm ci && npm run build)
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.getcwd())
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

datas, binaries, hiddenimports = [], [], []

# Our own packages are imported by name at runtime (tool registry, engine registry), so take them all.
hiddenimports += collect_submodules("studio") + collect_submodules("src")
datas += [
    (os.path.join(ROOT, "studio", "presets"), os.path.join("studio", "presets")),
    (os.path.join(ROOT, "studio", "web", "dist"), os.path.join("studio", "web", "dist")),
    (os.path.join(ROOT, "NOTICE"), "."),
    (os.path.join(ROOT, "LICENSE"), "."),
    (os.path.join(ROOT, "THIRD_PARTY_LICENSES.md"), "."),
]

# Packages that ship data files / native libs / lazy imports.
for pkg in (
    "pedalboard",
    "pyloudnorm",
    "noisereduce",
    "matchering",
    "librosa",
    "soundfile",
    "pretty_midi",
    "litellm",
    "imageio_ffmpeg",
    "symusic",
    "lazy_loader",
    "uvicorn",
    "tiktoken",
    "tiktoken_ext",
    "certifi",
    "mido",
    "resampy",
    "soxr",
    "audioread",
    "pooch",
):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

# music21 ships a ~300 MB corpus we never read; keep its code and small data only.
datas += [
    (src, dst)
    for src, dst in collect_data_files("music21")
    if f"{os.sep}corpus{os.sep}" not in src and "/corpus/" not in src
]
hiddenimports += collect_submodules("music21")

hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "multipart",
    "python_multipart",
    "h11",
    "anyio._backends._asyncio",
]
if IS_MAC:
    hiddenimports += ["webview.platforms.cocoa"]
if IS_WIN:
    hiddenimports += ["webview.platforms.edgechromium", "webview.platforms.winforms"]

# Real stem splitting (audio-separator + CPU torch + ONNX Runtime). Model weights are NOT bundled: the
# splitter downloads them on first use into the per-user folder. Set MUSER_BUNDLE_SEPARATE=0 for a
# small "core only" build (demo splitter only).
BUNDLE_SEPARATE = os.environ.get("MUSER_BUNDLE_SEPARATE", "1") == "1"
excludes = [
    "tkinter",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "gradio",
    "tensorflow",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
]
if BUNDLE_SEPARATE:
    for pkg in (
        "audio_separator",
        "onnxruntime",
        "onnx",
        "onnx2torch",
        "julius",
        "einops",
        "rotary_embedding_torch",
        "ml_collections",
        "diffq",
        "beartype",
        "samplerate",
        "pydub",
        "requests",
        "tqdm",
        "yaml",
        "six",
        "torch",
        "torchaudio",
        "torchvision",
    ):
        try:
            d, b, h = collect_all(pkg)
        except Exception:
            continue
        datas += d
        binaries += b
        hiddenimports += h
else:
    excludes += ["torch", "torchaudio"]

# Trim files the app never needs (C++ headers, torch's own test-suite, build helpers).
_DROP = (
    f"{os.sep}torch{os.sep}include{os.sep}",
    f"{os.sep}torch{os.sep}test{os.sep}",
    f"{os.sep}torch{os.sep}bin{os.sep}",
    f"{os.sep}torchgen{os.sep}",
)
datas = [d for d in datas if not any(x in os.path.join(os.sep, d[0]) for x in _DROP)]
binaries = [b for b in binaries if not any(x in os.path.join(os.sep, b[0]) for x in _DROP)]

a = Analysis(
    [os.path.join(ROOT, "packaging", "muser_desktop.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = None
for cand in ("packaging/icon.icns" if IS_MAC else "packaging/icon.ico",):
    if os.path.exists(os.path.join(ROOT, cand)):
        icon = os.path.join(ROOT, cand)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TheMuser",
    console=False if (IS_MAC or IS_WIN) else True,
    icon=icon,
    upx=False,
)
exes = [exe]
if IS_WIN:
    # A console twin so --version / --smoke-test print to a terminal (the windowed exe has no stdout).
    exes.append(
        EXE(
            pyz,
            a.scripts,
            [],
            exclude_binaries=True,
            name="TheMuser-cli",
            console=True,
            icon=icon,
            upx=False,
        )
    )
coll = COLLECT(*exes, a.binaries, a.datas, name="TheMuser", upx=False)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="The Muser.app",
        icon=icon,
        bundle_identifier="com.myaiplug.themuser",
        info_plist={
            "CFBundleName": "The Muser",
            "CFBundleDisplayName": "The Muser",
            "CFBundleShortVersionString": os.environ.get("MUSER_VERSION", "1.1.0"),
            "CFBundleVersion": os.environ.get("MUSER_VERSION", "1.1.0"),
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSMicrophoneUsageDescription": "The Muser can record audio for stem splitting and voice tools.",
        },
    )
