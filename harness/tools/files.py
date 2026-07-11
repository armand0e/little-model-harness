"""File tools. All results are plain strings sized for a small context."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

MAX_LIST = 100
MAX_MATCHES = 50


def _resolve(path: str, base: Path | None = None) -> Path:
    """Absolute paths pass through; relative ones land in base (the chat's
    workspace) instead of wherever the server process happens to run."""
    p = Path(os.path.expandvars(os.path.expanduser(path)))
    if base is not None and not p.is_absolute():
        p = base / p
    return p.resolve()


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def read_file(path: str, start_line: int = 1, max_lines: int = 200,
              base: Path | None = None) -> str:
    p = _resolve(path, base)
    if not p.exists():
        return f"Error: file not found: {p}"
    ext = p.suffix.lower()
    if ext in IMAGE_EXTS:
        # handled by the agent: loads and attaches the actual image
        return f"__IMAGE_FILE__:{p}"
    if ext == ".pdf":
        # start_line = first page, max_lines = page count (agent renders)
        return f"__PDF_FILE__:{p}:{max(1, start_line)}:{min(max_lines, 4) if max_lines < 200 else 2}"
    if ext in (".docx", ".xlsx", ".pptx"):
        return (f"This is a {p.suffix} file, not plain text. Load the matching "
                f"skill (documents/spreadsheets/presentations) and use its "
                f"read script instead.")
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"Error reading {p}: {e}"
    total = len(lines)
    start = max(1, start_line)
    chunk = lines[start - 1:start - 1 + max_lines]
    out = "\n".join(f"{i}| {l}" for i, l in enumerate(chunk, start))
    if start - 1 + len(chunk) < total:
        out += f"\n... ({total} lines total; continue with start_line={start + len(chunk)})"
    return out or "(empty file)"


def write_file(path: str, content: str, base: Path | None = None) -> str:
    p = _resolve(path, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {p}"


def edit_file(path: str, old_text: str, new_text: str,
              base: Path | None = None) -> str:
    p = _resolve(path, base)
    if not p.exists():
        return f"Error: file not found: {p}"
    text = p.read_text(encoding="utf-8", errors="replace")
    n = text.count(old_text)
    if n == 0:
        return "Error: old_text not found in file. Read the file and copy the text exactly."
    if n > 1:
        return f"Error: old_text appears {n} times. Include more surrounding lines to make it unique."
    p.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Edited {p}"


def list_dir(path: str = ".", base: Path | None = None) -> str:
    p = _resolve(path, base)
    if not p.is_dir():
        return f"Error: not a directory: {p}"
    entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    lines = []
    for e in entries[:MAX_LIST]:
        if e.is_dir():
            lines.append(f"{e.name}/")
        else:
            lines.append(f"{e.name}  ({e.stat().st_size:,} bytes)")
    if len(entries) > MAX_LIST:
        lines.append(f"... and {len(entries) - MAX_LIST} more")
    return f"{p}\n" + "\n".join(lines) if lines else f"{p}\n(empty)"


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea"}


def search(glob: str = "", text: str = "", path: str = ".",
           base: Path | None = None) -> str:
    if not glob and not text:
        return "Error: provide glob and/or text."
    root = _resolve(path, base)
    if not root.is_dir():
        return f"Error: not a directory: {root}"
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            fp = Path(dirpath) / fname
            rel = fp.relative_to(root).as_posix()
            if glob and not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(fname, glob)):
                continue
            if text:
                try:
                    if fp.stat().st_size > 2_000_000:
                        continue
                    content = fp.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for i, line in enumerate(content.splitlines(), 1):
                    if text in line:
                        results.append(f"{rel}:{i}: {line.strip()[:150]}")
                        if len(results) >= MAX_MATCHES:
                            break
            else:
                results.append(rel)
            if len(results) >= MAX_MATCHES:
                break
        if len(results) >= MAX_MATCHES:
            break
    if not results:
        return "No matches."
    header = f"Matches in {root}:"
    tail = f"\n... (stopped at {MAX_MATCHES} matches)" if len(results) >= MAX_MATCHES else ""
    return header + "\n" + "\n".join(results) + tail
