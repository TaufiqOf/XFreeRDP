#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/appimage"
APPDIR="$BUILD_DIR/XFreeRDP-GUI.AppDir"
ARCH="$(uname -m)"
APPIMAGE_OUT="$BUILD_DIR/XFreeRDP-GUI-${ARCH}.AppImage"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON="$ROOT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

if ! command -v appimagetool >/dev/null 2>&1; then
    echo "ERROR: appimagetool not found in PATH."
    echo "Download it from: https://github.com/AppImage/AppImageKit/releases"
    exit 1
fi

echo "[1/4] Building standalone binary with PyInstaller..."
"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --windowed \
    --name xfreerdp-gui \
    "$ROOT_DIR/main.py"

echo "[2/4] Preparing AppDir..."
rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications"

cp "$ROOT_DIR/dist/xfreerdp-gui" "$APPDIR/usr/bin/xfreerdp-gui"
cp "$ROOT_DIR/packaging/appimage/AppRun" "$APPDIR/AppRun"
cp "$ROOT_DIR/packaging/appimage/xfreerdp-gui.desktop" "$APPDIR/xfreerdp-gui.desktop"
cp "$ROOT_DIR/icon.svg" "$APPDIR/xfreerdp-gui.svg"

chmod +x "$APPDIR/AppRun"
chmod +x "$APPDIR/usr/bin/xfreerdp-gui"
ln -sf "xfreerdp-gui.svg" "$APPDIR/.DirIcon"

echo "[3/4] Creating AppImage..."
appimagetool "$APPDIR" "$APPIMAGE_OUT"

echo "[4/4] Done"
echo "AppImage created: $APPIMAGE_OUT"