# Build the Windows app (dist\LittleHarness\) and, if Inno Setup is
# installed, the installer (dist\LittleHarness-Setup.exe).
# Run from the project root:  powershell -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Build from a clean venv so no stray global site-packages leak into the app
if (-not (Test-Path ".venv-build")) {
    python -m venv .venv-build
    .venv-build\Scripts\python -m pip install --quiet --upgrade pip
    .venv-build\Scripts\python -m pip install --quiet -r requirements.txt pyinstaller playwright
}
.venv-build\Scripts\python -m PyInstaller packaging\littleharness.spec --noconfirm

Write-Host ""
Write-Host "Built dist\LittleHarness\LittleHarness.exe"

$iscc = @("$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc packaging\installer.iss
    Write-Host "Built dist\LittleHarness-Setup.exe"
} else {
    Write-Host "Inno Setup not found - skipped the installer. Install with:"
    Write-Host "  winget install JRSoftware.InnoSetup"
}
