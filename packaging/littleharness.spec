# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Little Harness desktop app.

Build (from the project root):
    pip install pyinstaller
    pyinstaller packaging/littleharness.spec --noconfirm

Output: dist/LittleHarness/ (onedir — fast startup, antivirus-friendly).
Data (sessions, settings, memory, learned skills, browser profile) lives in
the per-user appdata dir, so the install folder can stay read-only.
"""
import os
import re
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP_VERSION = os.environ.get("LMH_VERSION", "0.0.0")
if not re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION):
    raise SystemExit(f"LMH_VERSION must use X.Y.Z format (got {APP_VERSION!r})")

datas = [
    (os.path.join(ROOT, "skills"), "skills"),
    (os.path.join(ROOT, "packaging", "littleharness.png"), "packaging"),
]
computer_use_dir = os.path.join(ROOT, "build", "computer-use")
if os.path.isdir(computer_use_dir):
    # Pinned native accessibility MCP + upstream MIT license/source manifest.
    datas.append((computer_use_dir, "computer-use"))
binaries = []
hiddenimports = ["multipart"]  # server-only compatibility mode

is_windows = sys.platform == "win32"
is_macos = sys.platform == "darwin"
ICON = (os.path.join(SPECPATH, "littleharness.ico") if is_windows
        else os.path.join(SPECPATH, "littleharness.icns") if is_macos
        else None)

# PyInstaller's Qt hook follows the statically imported PySide6 modules and
# their required plugins. Collecting all of PySide6 would also pull unused
# modules such as WebEngine into this deliberately non-webview application.
# The remaining libraries are used by skill helper scripts (run via
# `--runpy`), so bundle those explicitly.
collect_pkgs = ["docx", "openpyxl", "pptx", "pypdf", "fitz",
                "PIL", "pyautogui", "pygetwindow", "playwright", "mcp"]
if is_macos:
    # pyobjc frameworks the computer skill's permission preflight and
    # pyautogui need at runtime
    collect_pkgs += ["Quartz", "ApplicationServices", "AppKit", "Foundation",
                     "objc"]
for pkg in collect_pkgs:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        print(f"warning: could not collect {pkg} — is it installed?")

hiddenimports += collect_submodules("uvicorn")

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "tensorflow", "matplotlib", "numpy.f2py"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LittleHarness",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed: the native Qt window is the app
    disable_windowed_traceback=False,
    icon=ICON,
)
# Console-subsystem twin for synchronous CLI use: the `python` shim
# (--runpy) and the folder picker (--pick-folder) call this one so the
# shell reliably waits for it and captures stdout.
exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LittleHarnessCLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=ICON,
)
coll = COLLECT(
    exe,
    exe_cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LittleHarness",
)

if is_macos:
    app = BUNDLE(
        coll,
        name="Little Harness.app",
        icon=ICON,
        bundle_identifier="dev.littleharness.app",
        info_plist={
            "CFBundleName": "Little Harness",
            "CFBundleDisplayName": "Little Harness",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            # the app talks to an OpenAI-compatible model server over http
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
            # the computer skill drives apps via System Events (Automation
            # permission); this string appears in that consent prompt
            "NSAppleEventsUsageDescription":
                "Little Harness controls other apps (open, focus, type) "
                "when you ask it to automate your computer.",
        },
    )
