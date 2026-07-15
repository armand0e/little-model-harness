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
    (os.path.join(ROOT, "web"), "web"),
    (os.path.join(ROOT, "skills"), "skills"),
]
computer_use_dir = os.path.join(ROOT, "build", "computer-use")
if os.path.isdir(computer_use_dir):
    # Pinned native accessibility MCP + upstream MIT license/source manifest.
    datas.append((computer_use_dir, "computer-use"))
binaries = []
hiddenimports = ["multipart",   # python-multipart (fastapi uploads)
                 "websockets"]  # uvicorn ws protocol (terminal endpoint)

is_windows = sys.platform == "win32"
is_macos = sys.platform == "darwin"
ICON = (os.path.join(SPECPATH, "littleharness.ico") if is_windows
        else os.path.join(SPECPATH, "littleharness.icns") if is_macos
        else None)

# webview = the native app window (WebView2 on Windows, Qt/GTK on Linux,
# Cocoa on macOS). The rest are libraries used only by skill helper
# scripts (run via `--runpy`), so static analysis of run_app.py never
# sees them — bundle them explicitly.
collect_pkgs = ["webview", "docx", "openpyxl", "pptx", "pypdf", "fitz",
                "PIL", "pyautogui", "pygetwindow", "playwright", "mcp"]
if is_windows:
    # ConPTY backend for the interactive terminal; its winpty DLLs are
    # loaded dynamically and invisible to static analysis.
    collect_pkgs.append("winpty")
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
    excludes=[
        "torch", "tensorflow", "matplotlib", "numpy.f2py", "logfire",
        # Heavy packages that leak in from crowded site-packages via
        # optional-import chains and hooks; the harness never uses them.
        "patchright", "xformers", "bitsandbytes", "triton", "cv2",
        "googleapiclient", "pyarrow", "spacy", "ctranslate2", "av",
        "scipy", "PySide6", "qtpy", "shiboken6", "transformers",
        "diffusers", "accelerate", "gradio", "gradio_client", "altair",
        "yt_dlp", "open_webui", "pandas", "sklearn", "onnxruntime",
        "numba", "llvmlite", "sentence_transformers", "faster_whisper",
        "librosa", "soundfile", "torchvision", "torchaudio", "cupy",
        "nvidia", "opensearchpy", "IPython",
        "langchain", "langchain_core", "langchain_community",
        "langchain_text_splitters", "datasets", "outlines", "selenium",
        "faiss", "nltk", "pycountry", "chromadb", "unstructured",
        # pywebview backends for other platforms/toolkits
        "webview.platforms.qt", "webview.platforms.gtk",
        "webview.platforms.android", "webview.platforms.cocoa",
    ],
    noarchive=False,
)
# patchright (a playwright fork) registers PyInstaller hooks under
# playwright's own hook names, so its 90MB driver stows away whenever
# playwright is bundled. We only ship the real playwright.
a.datas = [entry for entry in a.datas
           if not entry[0].startswith("patchright")]
a.binaries = [entry for entry in a.binaries
              if not entry[0].startswith("patchright")]
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
    console=False,          # windowed: the native webview window is the app
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
            # the app talks to the local model server over http
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
            # the computer skill drives apps via System Events (Automation
            # permission); this string appears in that consent prompt
            "NSAppleEventsUsageDescription":
                "Little Harness controls other apps (open, focus, type) "
                "when you ask it to automate your computer.",
        },
    )
