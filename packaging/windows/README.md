# Windows Desktop Build & Installer

NoDAW Studio PRO can be packaged as a native Windows desktop application with a full installer.

## Options

### 1. Electron wrapper (recommended for the existing web UI)

The Studio is already a Vite + React frontend served by the FastAPI backend.

```bash
# In a new folder or monorepo
npm create electron-app@latest nodaw-desktop --template=vite-typescript
# Point the Electron main process at the built studio/web/dist and launch the Python server
# as a child process (or bundle the Python runtime with PyInstaller).
```

Use `electron-builder` or `electron-forge` to produce an NSIS or Inno Setup installer.

### 2. PyInstaller + Inno Setup (single executable + installer)

Bundle the Python server and a minimal Chromium or use the system browser, then wrap with Inno Setup.

See `nodaw-studio.iss` for a starter Inno Setup script.

## Building the installer

1. Build the web UI: `cd studio/web && npm run build`
2. Create a PyInstaller spec that includes the server, .venv dependencies, and the dist folder.
3. Run Inno Setup Compiler on `nodaw-studio.iss`.

The resulting `NoDAWStudio-Setup.exe` installs the app, creates Start Menu and Desktop shortcuts, and registers the file association for `.nodaw` projects.

## MIDI & Sample Library

- MIDI learn works in the desktop build the same as the browser (Web MIDI API).
- The drive scanner lives in the Python backend and is available via `/api/library/scan` and `/api/library/search`.
- Samples assigned to pads persist in IndexedDB (browser) or can be extended to a local database for the desktop build.
