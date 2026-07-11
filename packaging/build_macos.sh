#!/usr/bin/env bash
# Build "dist/Little Harness.app" and dist/LittleHarness.dmg.
# Must run ON macOS (PyInstaller cannot cross-compile):
#   bash packaging/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# the harness needs Python >= 3.11; Apple's stock /usr/bin/python3 is older,
# so prefer a Homebrew/python.org install if present
PY=""
for cand in python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1 \
       && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        PY="$cand"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "error: need Python 3.11+ (try: brew install python@3.12)" >&2
    exit 1
fi
echo "using $($PY --version) at $(command -v $PY)"

"$PY" -m venv .venv-build-mac
# shellcheck disable=SC1091
. .venv-build-mac/bin/activate
pip install --quiet --upgrade pip
# pywebview pulls pyobjc (Cocoa/WebKit window) automatically on macOS;
# ApplicationServices/Quartz power the computer skill's permission checks
pip install --quiet -r requirements.txt pyinstaller playwright \
    pyobjc-framework-Quartz pyobjc-framework-ApplicationServices

python -m PyInstaller packaging/littleharness.spec --noconfirm

# ad-hoc sign so the app runs on Apple Silicon (unsigned binaries are
# killed outright on arm64); users still right-click > Open the first time
codesign --force --deep --sign - "dist/Little Harness.app" || true

# drag-to-Applications DMG
STAGE=build/dmg-stage
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "dist/Little Harness.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Little Harness" -srcfolder "$STAGE" -ov \
    -format UDZO "dist/LittleHarness.dmg"

echo
echo "Built dist/LittleHarness.dmg"
echo "First launch on a Mac: right-click the app > Open (it is unsigned)."
echo "Data lives in ~/Library/Application Support/LittleHarness."
