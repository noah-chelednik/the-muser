# Windows desktop build and installer

The Muser ships a real desktop app (`TheMuser.exe`) built with PyInstaller and a full Inno Setup installer (`muser.iss`). The installer creates Start Menu and optional desktop shortcuts, an uninstaller, and keeps user data in `%LOCALAPPDATA%\TheMuser` so uninstalling does not delete tracks or the sample library.

`nodaw-studio.iss` is an older starter script that copied the web `dist` folder plus a `.bat` launcher. Prefer `muser.iss`.

## What you need

- Windows 10/11 x64
- Node.js 20+
- Python 3.10+
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (`ISCC.exe` on your PATH)

## Build

From the repo root:

```powershell
.\packaging\windows\build-installer.ps1
```

That builds `studio/web`, bundles the Python server and UI with `packaging/muser.spec`, then compiles `packaging/windows/muser.iss`.

Output:

- App folder: `dist/TheMuser/TheMuser.exe`
- Installer: `dist/installer/TheMuser-Setup-1.1.0-win64.exe`

You can also compile the installer yourself after a PyInstaller run:

```powershell
iscc /DAppVersion=1.1.0 packaging\windows\muser.iss
```

Optional CI: add `.github/workflows/desktop-installers.yml` on a machine whose GitHub token has the `workflow` scope, then dispatch it or push a `v*` tag:

```yaml
name: Windows installer
on:
  workflow_dispatch:
  push:
    tags: ["v*"]
jobs:
  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: npm, cache-dependency-path: studio/web/package-lock.json }
      - name: Build web UI
        working-directory: studio/web
        run: |
          npm ci
          npm run build
      - name: Bundle desktop app
        run: |
          python -m pip install --disable-pip-version-check pyinstaller
          python -m PyInstaller packaging/muser.spec --noconfirm
      - name: Install Inno Setup
        run: choco install innosetup --no-progress -y
      - name: Compile installer
        run: iscc /DAppVersion=1.1.0 packaging\windows\muser.iss
      - uses: actions/upload-artifact@v4
        with: { name: TheMuser-Setup, path: dist/installer/*.exe }
```


## MIDI and the sample library

- MIDI learn works in the desktop window the same as in the browser (Web MIDI).
- Scan folders from the Sample Library pane. Indexed files are served only through `/api/library/file` (path must already be in the library database).
- Pad kits still persist in IndexedDB inside the desktop webview, with an Autosave kit written whenever you load a sample onto a pad.
