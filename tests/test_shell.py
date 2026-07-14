from __future__ import annotations

import time
import threading

from harness.tools.shell import MAX_OUTPUT, run_command


def test_shell_output_is_bounded_without_losing_exit_status():
    result = run_command('python -c "print(\'x\'*20000)"')
    assert "output truncated" in result
    assert "[exit code: 0]" in result
    assert len(result) < MAX_OUTPUT + 100


def test_shell_timeout_returns_promptly_and_kills_process_group():
    started = time.monotonic()
    result = run_command('python -c "import time; time.sleep(10)"', 1)
    elapsed = time.monotonic() - started
    assert "timed out after 1s" in result
    assert elapsed < 5


def test_shell_stop_event_returns_promptly_and_kills_process_group():
    stop = threading.Event()
    timer = threading.Timer(0.2, stop.set)
    started = time.monotonic()
    timer.start()
    try:
        result = run_command(
            'python -c "import time; time.sleep(10)"', 30,
            stop_event=stop,
        )
    finally:
        timer.cancel()
    assert "stopped by user" in result
    assert time.monotonic() - started < 5
