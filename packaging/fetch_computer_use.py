"""Fetch the pinned MIT-licensed native Open Computer Use runtime.

The upstream npm artifact contains native binaries for all supported OS/arch
pairs. Build scripts call this before PyInstaller and bundle only the current
target plus its license. The SHA-256 pin makes an upstream package replacement
fail closed instead of silently entering the desktop-control trust boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "0.2.3"
URL = ("https://registry.npmjs.org/@qwen-code/open-computer-use/-/"
       f"open-computer-use-{VERSION}.tgz")
SHA256 = "96d44abf9a3d0c2585a8a164b00b9aa8dbcc85822fe8584bebf591815d36e574"
MAX_DOWNLOAD = 30 * 1024 * 1024
WINDOWS_SOURCE_COMMIT = "f238d1bc85b53bd785d2618d4fbb5d2402207c7a"
WINDOWS_MAIN_SHA256 = "6a1cb3cca2b51f54f846ba25f5fb11b6a45af7a7b1a02a4e7e249c3f11d2f33b"
WINDOWS_RUNTIME_SHA256 = "b47ac4345ac56deb34af7fe9a6158a6e5bfeafe3eb833d3fa7eb665e19b39d4f"


def _target_member() -> tuple[str, str]:
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    system = platform.system()
    if system == "Windows":
        return (f"package/dist/windows/{arch}/open-computer-use.exe",
                "open-computer-use.exe")
    if system == "Linux":
        return (f"package/dist/linux/{arch}/open-computer-use",
                "open-computer-use")
    if system == "Darwin":
        # The npm package's app executable is universal (x64 + arm64).
        return ("package/dist/Open Computer Use.app/Contents/MacOS/"
                "OpenComputerUse", "open-computer-use")
    raise SystemExit(f"unsupported computer-use build target: {system} {machine}")


def _download(cache: Path) -> bytes:
    if cache.is_file():
        data = cache.read_bytes()
        if hashlib.sha256(data).hexdigest() == SHA256:
            return data
    request = urllib.request.Request(URL, headers={
        "User-Agent": "LittleHarness-build/1.0",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise SystemExit("computer-use package exceeded download size limit")
    actual = hashlib.sha256(data).hexdigest()
    if actual != SHA256:
        raise SystemExit(
            f"computer-use package hash mismatch: expected {SHA256}, got {actual}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def _download_source(name: str, expected_sha256: str) -> bytes:
    url = ("https://raw.githubusercontent.com/QwenLM/open-computer-use/"
           f"{WINDOWS_SOURCE_COMMIT}/apps/OpenComputerUseWindows/{name}")
    request = urllib.request.Request(url, headers={
        "User-Agent": "LittleHarness-build/1.0",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(2 * 1024 * 1024)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise SystemExit(
            f"computer-use {name} hash mismatch: expected "
            f"{expected_sha256}, got {actual}")
    return data


def _load_windows_sources() -> tuple[bytes, bytes]:
    expected = {
        "main.go": WINDOWS_MAIN_SHA256,
        "runtime.ps1": WINDOWS_RUNTIME_SHA256,
    }
    source_override = os.environ.get("LMH_COMPUTER_USE_SOURCE_DIR", "").strip()
    if source_override:
        root = Path(source_override)
        values = tuple((root / name).read_bytes() for name in expected)
    else:
        try:
            values = tuple(_download_source(name, digest)
                           for name, digest in expected.items())
        except Exception:
            git = shutil.which("git")
            if not git:
                raise
            with tempfile.TemporaryDirectory(prefix="lmh-ocu-source-") as temp:
                repo = Path(temp) / "repo"
                env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
                subprocess.run([
                    git, "-c", "core.autocrlf=false", "clone", "--depth", "1",
                    "--filter=blob:none",
                    "--no-checkout", "https://github.com/QwenLM/open-computer-use.git",
                    str(repo),
                ], env=env, check=True)
                subprocess.run([
                    git, "-c", "core.autocrlf=false", "-C", str(repo),
                    "checkout", WINDOWS_SOURCE_COMMIT,
                    "--", "apps/OpenComputerUseWindows/main.go",
                    "apps/OpenComputerUseWindows/runtime.ps1",
                ], env=env, check=True)
                root = repo / "apps" / "OpenComputerUseWindows"
                values = tuple((root / name).read_bytes() for name in expected)
    for (name, digest), data in zip(expected.items(), values):
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise SystemExit(
                f"computer-use {name} hash mismatch: expected {digest}, got {actual}")
    return values  # type: ignore[return-value]


def _build_patched_windows(target: Path) -> None:
    """Build the pinned Windows runtime with a JSON correctness patch.

    Windows PowerShell 5.1's ConvertTo-Json leaves some UI Automation control
    characters (Chrome commonly exposes BEL) unescaped. The upstream Go
    process then rejects its own snapshot as invalid JSON. Keep the upstream
    source pinned and hashed, and escape raw JSON control characters before
    stdout. This is deliberately a source build rather than an opaque binary
    mutation so the shipped trust boundary remains auditable.
    """
    target = target.resolve()
    go = shutil.which("go")
    if not go:
        raise SystemExit(
            "Go 1.22+ is required to build the patched Windows computer-use runtime")
    main_bytes, runtime_bytes = _load_windows_sources()
    main = main_bytes.decode("utf-8")
    runtime = runtime_bytes.decode("utf-8")
    old_version = 'var version = "0.1.51"'
    if old_version not in main:
        raise SystemExit("pinned computer-use main.go version marker changed")
    main = main.replace(old_version, f'var version = "{VERSION}-lmh.1"', 1)
    old_output = "$response | ConvertTo-Json -Depth 50 -Compress"
    new_output = r'''$json = $response | ConvertTo-Json -Depth 50 -Compress
$json = [regex]::Replace($json, '[\x00-\x1f]', {
    param($match)
    return ('\u{0:x4}' -f [int][char]$match.Value)
})
$bytes = [Text.Encoding]::UTF8.GetBytes($json)
$stdout = [Console]::OpenStandardOutput()
$stdout.Write($bytes, 0, $bytes.Length)'''
    if old_output not in runtime:
        raise SystemExit("pinned computer-use runtime output marker changed")
    runtime = runtime.replace(old_output, new_output, 1)
    with tempfile.TemporaryDirectory(prefix="lmh-computer-use-") as temp:
        source = Path(temp)
        (source / "main.go").write_text(main, encoding="utf-8")
        (source / "runtime.ps1").write_text(runtime, encoding="utf-8")
        (source / "go.mod").write_text(
            "module littleharness.local/opencomputerusewindows\n\ngo 1.22\n",
            encoding="utf-8")
        subprocess.run(
            [go, "build", "-trimpath", "-ldflags=-s -w", "-o", str(target), "."],
            cwd=source, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path("build/computer-use"))
    parser.add_argument("--cache", type=Path,
                        default=Path("build/vendor-cache") /
                        f"open-computer-use-{VERSION}.tgz")
    args = parser.parse_args()
    member_name, executable_name = _target_member()
    data = _download(args.cache)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        executable = archive.extractfile(member_name)
        license_file = archive.extractfile("package/LICENSE")
        if executable is None or license_file is None:
            raise SystemExit("computer-use package is missing expected files")
        executable_bytes = executable.read()
        license_bytes = license_file.read()
    args.output.mkdir(parents=True, exist_ok=True)
    # A developer may build multiple platforms from one checkout (for example
    # Windows after WSL). Never let a runtime left by the previous target leak
    # into PyInstaller's directory-level data collection.
    for runtime_name in ("open-computer-use", "open-computer-use.exe"):
        stale_runtime = args.output / runtime_name
        if stale_runtime.exists() or stale_runtime.is_symlink():
            stale_runtime.unlink()
    target = args.output / executable_name
    if platform.system() == "Windows":
        _build_patched_windows(target)
    else:
        target.write_bytes(executable_bytes)
    if os.name != "nt":
        target.chmod(0o755)
    (args.output / "LICENSE.open-computer-use.txt").write_bytes(license_bytes)
    (args.output / "source.json").write_text(json.dumps({
        "name": "@qwen-code/open-computer-use",
        "version": VERSION,
        "url": URL,
        "sha256": SHA256,
        "upstream": "https://github.com/QwenLM/open-computer-use",
        "license": "MIT",
        "windows_source_commit": WINDOWS_SOURCE_COMMIT,
        "windows_patch": ("escape raw PowerShell JSON control characters "
                          "and force UTF-8 stdout"),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
