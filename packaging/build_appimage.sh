#!/usr/bin/env bash
# Build dist/LittleHarness-x86_64.AppImage. Run on Linux (or WSL) from the
# project root:  bash packaging/build_appimage.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PACKAGE_VERSION="${LMH_VERSION:-}"
if [[ -z "$PACKAGE_VERSION" && "${GITHUB_REF_TYPE:-}" == "tag" ]]; then
    PACKAGE_VERSION="${GITHUB_REF_NAME#v}"
fi
PACKAGE_VERSION="${PACKAGE_VERSION:-0.0.0}"
if [[ ! "$PACKAGE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "error: LMH_VERSION must use X.Y.Z format (got '$PACKAGE_VERSION')" >&2
    exit 1
fi
export LMH_VERSION="$PACKAGE_VERSION"
echo "Building Little Harness $PACKAGE_VERSION for Linux x86_64"

python3 -m venv .venv-build-linux
# shellcheck disable=SC1091
. .venv-build-linux/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt pyinstaller playwright

python packaging/fetch_computer_use.py --output build/computer-use
python -m PyInstaller packaging/littleharness.spec --noconfirm
find dist/LittleHarness -type f -name open-computer-use -exec chmod +x {} +

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
Categories=Utility;
Comment=Agent harness for small local LLMs
Terminal=false
X-AppImage-Version=LMH_PACKAGE_VERSION
DESKTOP
sed -i "s/LMH_PACKAGE_VERSION/$PACKAGE_VERSION/" \
    "$APPDIR/littleharness.desktop"

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
ARCH=x86_64 VERSION="$PACKAGE_VERSION" \
    "$TOOL" --appimage-extract-and-run "$APPDIR" \
    dist/LittleHarness-x86_64.AppImage

echo
echo "Built dist/LittleHarness-x86_64.AppImage"
echo "Data lives in \${XDG_DATA_HOME:-~/.local/share}/LittleHarness."
