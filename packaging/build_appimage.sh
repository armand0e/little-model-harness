#!/usr/bin/env bash
# Build dist/LittleHarness-x86_64.AppImage. Run on Linux (or WSL) from the
# project root:  bash packaging/build_appimage.sh
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv-build-linux
# shellcheck disable=SC1091
. .venv-build-linux/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt pyinstaller "pywebview[qt]"

python -m PyInstaller packaging/littleharness.spec --noconfirm

APPDIR=build/LittleHarness.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/app"
cp -a dist/LittleHarness/. "$APPDIR/usr/app/"
cp packaging/littleharness.png "$APPDIR/littleharness.png"

cat > "$APPDIR/littleharness.desktop" <<'DESKTOP'
[Desktop Entry]
Name=Little Harness
Exec=LittleHarness
Icon=littleharness
Type=Application
Categories=Utility;Office;
Comment=Agent harness for small local LLMs
Terminal=false
DESKTOP

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/app/LittleHarness" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

mkdir -p build dist
TOOL=build/appimagetool.AppImage
if [ ! -f "$TOOL" ]; then
    curl -fsSL -o "$TOOL" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
# --appimage-extract-and-run works without FUSE (containers, WSL)
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" \
    dist/LittleHarness-x86_64.AppImage

echo
echo "Built dist/LittleHarness-x86_64.AppImage"
echo "Data lives in \${XDG_DATA_HOME:-~/.local/share}/LittleHarness."
