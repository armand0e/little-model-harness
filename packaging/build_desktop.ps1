# Builds the Windows desktop app: PyInstaller sidecar + Electron installer.
#
#   pwsh packaging/build_desktop.ps1 [-Version 1.2.0]
#
# Output: electron/dist/LittleHarness-Setup-<version>.exe
#         electron/dist/win-unpacked/  (portable, runnable in place)
param([string]$Version = "1.2.0")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 1. Pinned native computer-use backend (bundled into the sidecar).
if (-not (Test-Path "build\computer-use\open-computer-use.exe")) {
  python packaging/fetch_computer_use.py --output build/computer-use
  if ($LASTEXITCODE -ne 0) { throw "fetch_computer_use failed" }
}

# 2. PyInstaller sidecar (onedir -> dist/LittleHarness).
$env:LMH_VERSION = $Version
python -m PyInstaller packaging/littleharness.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

# 3. Electron shell + NSIS installer (bundles dist/LittleHarness as
#    resources/sidecar via extraResources).
Set-Location "$root\electron"
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
npx electron-builder --win
if ($LASTEXITCODE -ne 0) { throw "electron-builder failed" }

Write-Host "`nDone. Artifacts in electron\dist\" -ForegroundColor Green
