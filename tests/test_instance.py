from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_second_process_cannot_acquire_same_data_directory(tmp_path: Path):
    env = {**os.environ, "LMH_DATA_DIR": str(tmp_path)}
    holder_code = (
        "import time; from harness.instance import acquire_instance_lock; "
        "assert acquire_instance_lock(); print('locked', flush=True); time.sleep(10)"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code], cwd=Path(__file__).parents[1],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        contender = subprocess.run(
            [sys.executable, "-c",
             "from harness.instance import acquire_instance_lock; "
             "raise SystemExit(0 if not acquire_instance_lock() else 1)"],
            cwd=Path(__file__).parents[1], env=env,
            capture_output=True, text=True, timeout=5,
        )
        assert contender.returncode == 0, contender.stderr
    finally:
        holder.terminate()
        holder.wait(timeout=5)
