"""Cross-platform single-instance lock for processes that persist sessions."""
from __future__ import annotations

import atexit
import importlib
import os
from typing import Any, BinaryIO

from .config import DATA_DIR

_HANDLE: BinaryIO | None = None


def acquire_instance_lock() -> bool:
    global _HANDLE
    if _HANDLE is not None:
        return True
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "instance.lock"
    handle = path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            # ``fcntl`` does not exist in the Windows typeshed, even though
            # this branch is only reachable on POSIX.  Import it dynamically
            # so one source tree can be type-checked on either platform.
            fcntl: Any = importlib.import_module("fcntl")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        handle.close()
        return False
    _HANDLE = handle
    atexit.register(release_instance_lock)
    return True


def release_instance_lock() -> None:
    global _HANDLE
    handle, _HANDLE = _HANDLE, None
    if handle is None:
        return
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl: Any = importlib.import_module("fcntl")
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        handle.close()
