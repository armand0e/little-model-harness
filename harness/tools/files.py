"""File tools. All results are plain strings sized for a small context."""
from __future__ import annotations

import fnmatch
import itertools
import os
import tempfile
from pathlib import Path

MAX_LIST = 100
MAX_MATCHES = 50
MAX_READ_CHARS = 100_000
MAX_LINE_CHARS = 4000


def _resolve(path: str, base: Path | None = None) -> Path:
    """Absolute paths pass through; relative ones land in base (the chat's
    workspace) instead of wherever the server process happens to run."""
    p = Path(os.path.expandvars(os.path.expanduser(path)))
    if base is not None and not p.is_absolute():
        p = base / p
    return p.resolve()


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    """Replace a file without leaving it truncated after interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            try:
                os.chmod(tmp_name, path.stat().st_mode)
            except OSError:
                pass
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _bounded_text_lines(f):
    """Yield physical lines without ever loading an unbounded line."""
    while True:
        segment = f.readline(MAX_LINE_CHARS + 1)
        if not segment:
            return
        truncated = (len(segment) > MAX_LINE_CHARS
                     and not segment.endswith(("\n", "\r")))
        shown = segment[:MAX_LINE_CHARS]
        if truncated:
            while segment and not segment.endswith(("\n", "\r")):
                segment = f.readline(MAX_LINE_CHARS + 1)
        yield shown.rstrip("\r\n") + (" …[line truncated]" if truncated else "")


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
    start = max(1, start_line)
    limit = min(max(1, max_lines), 2000)
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            lines = _bounded_text_lines(f)
            chunk: list[str] = []
            chars = 0
            stopped_for_chars = False
            for line in itertools.islice(lines, start - 1, start - 1 + limit + 1):
                if chunk and chars + len(line) > MAX_READ_CHARS:
                    stopped_for_chars = True
                    break
                chunk.append(line)
                chars += len(line)
    except (OSError, UnicodeError) as e:
        return f"Error reading {p}: {e}"
    has_more = len(chunk) > limit or stopped_for_chars
    chunk = chunk[:limit]
    out = "\n".join(
        f"{i}| {line}"
        for i, line in enumerate(chunk, start)
    )
    if has_more:
        out += f"\n... (more lines; continue with start_line={start + len(chunk)})"
    return out or "(empty file)"


def write_file(path: str, content: str, base: Path | None = None) -> str:
    p = _resolve(path, base)
    _atomic_write_text(p, content)
    return f"Wrote {len(content)} chars to {p}"


def edit_file(path: str, old_text: str, new_text: str,
              base: Path | None = None) -> str:
    p = _resolve(path, base)
    if not p.exists():
        return f"Error: file not found: {p}"
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ("Error: file is not valid UTF-8 text; refusing to edit it "
                "because rewriting it would corrupt its bytes.")
    except OSError as e:
        return f"Error reading {p}: {e}"
    n = text.count(old_text)
    if n == 0:
        return "Error: old_text not found in file. Read the file and copy the text exactly."
    if n > 1:
        return f"Error: old_text appears {n} times. Include more surrounding lines to make it unique."
    _atomic_write_text(p, text.replace(old_text, new_text, 1))
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


_SKIP_DIRS = {".git", ".lmh", "node_modules", "__pycache__", ".venv", "venv", ".idea"}


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
            patterns = (glob, glob[3:]) if glob.startswith("**/") else (glob,)
            if glob and not any(fnmatch.fnmatch(rel, pat) or
                                fnmatch.fnmatch(fname, pat) for pat in patterns):
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
