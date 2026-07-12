from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_runpy_mode_forces_unicode_safe_console_output(tmp_path: Path):
    script = tmp_path / "unicode_helper.py"
    script.write_text("print('plain → unicode ✓')\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "run_app.py", "--runpy", str(script)],
        cwd=Path(__file__).parents[1], capture_output=True, text=True,
        encoding="utf-8", errors="strict", timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "plain → unicode ✓" in result.stdout
