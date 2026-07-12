# Build the Windows app (dist\LittleHarness\) and, if Inno Setup is
# installed, the installer (dist\LittleHarness-Setup.exe).
# Run from the project root:  powershell -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$PackageVersion = $env:LMH_VERSION
if (-not $PackageVersion -and $env:GITHUB_REF_TYPE -eq "tag") {
    $PackageVersion = $env:GITHUB_REF_NAME -replace '^v', ''
}
if (-not $PackageVersion) { $PackageVersion = "0.0.0" }
if ($PackageVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "LMH_VERSION must use X.Y.Z format (got '$PackageVersion')"
}
$env:LMH_VERSION = $PackageVersion
Write-Host "Building Little Harness $PackageVersion for Windows x64"

# Build from a clean venv so no stray global site-packages leak into the app
if (-not (Test-Path ".venv-build")) {
    python -m venv .venv-build
}
.venv-build\Scripts\python -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed ($LASTEXITCODE)" }
# Always reconcile the build environment. Reusing an existing venv must not
# silently package stale dependencies after requirements change.
.venv-build\Scripts\python -m pip install --quiet --upgrade-strategy only-if-needed `
    -r requirements.txt pyinstaller playwright
if ($LASTEXITCODE -ne 0) { throw "build dependency install failed ($LASTEXITCODE)" }
.venv-build\Scripts\python packaging\fetch_computer_use.py `
    --output build\computer-use
if ($LASTEXITCODE -ne 0) { throw "computer-use preparation failed ($LASTEXITCODE)" }
.venv-build\Scripts\python -m PyInstaller packaging\littleharness.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

Write-Host ""
Write-Host "Built dist\LittleHarness\LittleHarness.exe"

$isccOnPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty Source -First 1
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          $isccOnPath) |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    # ISCC is a GUI-subsystem executable, so PowerShell's call operator can
    # return before compression finishes.  An explicit waited process keeps
    # CI from uploading a partially written installer.
    $compiler = Start-Process -FilePath $iscc `
        -ArgumentList @("/DAppVersion=$PackageVersion", "packaging\installer.iss") `
        -Wait -PassThru -NoNewWindow
    if ($compiler.ExitCode -ne 0) {
        throw "Inno Setup failed with exit code $($compiler.ExitCode)"
    }
    Write-Host "Built dist\LittleHarness-Setup.exe"
} else {
    if ($env:CI) {
        throw "Inno Setup is required for CI installer builds but ISCC.exe was not found"
    }
    Write-Host "Inno Setup not found - skipped the installer. Install with:"
    Write-Host "  winget install JRSoftware.InnoSetup"
}
