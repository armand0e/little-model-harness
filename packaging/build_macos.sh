#!/usr/bin/env bash
# Build "dist/Little Harness.app" and dist/LittleHarness.dmg.
# Must run ON macOS (PyInstaller cannot cross-compile):
#   bash packaging/build_macos.sh
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
echo "Building Little Harness $PACKAGE_VERSION for $(uname -m) macOS"

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

python packaging/fetch_computer_use.py --output build/computer-use
python -m PyInstaller packaging/littleharness.spec --noconfirm
find "dist/Little Harness.app" -type f -name open-computer-use -exec chmod +x {} +

# ad-hoc sign so the app runs on Apple Silicon (unsigned binaries are
# killed outright on arm64); users still right-click > Open the first time
codesign --force --deep --sign - "dist/Little Harness.app"

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
echo "First launch on a Mac: right-click the app > Open (it is not notarized)."
echo "Data lives in ~/Library/Application Support/LittleHarness."
