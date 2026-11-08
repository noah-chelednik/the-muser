#!/usr/bin/env bash
# Wrap dist/The Muser.app in a drag-to-Applications .dmg.   Usage: make_dmg.sh <version> <arch>
set -euo pipefail
VER="${1:?version}"; ARCH="${2:-arm64}"
cd "$(dirname "$0")/../.."
APP="dist/The Muser.app"
[ -d "$APP" ] || { echo "missing $APP"; exit 1; }
OUT="dist/installer/TheMuser-${VER}-macos-${ARCH}.dmg"
STAGE="$(mktemp -d)"
mkdir -p dist/installer
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/READ ME FIRST.txt" <<TXT
The Muser ${VER}

1. Drag "The Muser" onto "Applications".
2. This build is not signed by Apple. The first time, right-click (or Control-click) the app,
   choose Open, then click Open again.
   If macOS says the app is damaged, open Terminal and run:
     xattr -dr com.apple.quarantine "/Applications/The Muser.app"
3. Optional AI assistant: install Ollama from https://ollama.com/download.
   Without it the Studio runs in demo mode.

Your tracks, exports and downloaded models live in ~/Library/Application Support/The Muser.
TXT
rm -f "$OUT"
hdiutil create -volname "The Muser ${VER}" -srcfolder "$STAGE" -ov -format UDZO -fs HFS+ "$OUT"
rm -rf "$STAGE"
ls -lh "$OUT"
