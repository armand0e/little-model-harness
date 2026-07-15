from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
import pytest  # noqa: E402

import harness.app as desktop_app  # noqa: E402
import harness.instance as instance  # noqa: E402
import harness.native as native  # noqa: E402
from harness.native.window import MainWindow  # noqa: E402
from harness.native.dialogs import SettingsDialog  # noqa: E402
from harness.native.widgets import AttachmentTile, TranscriptView  # noqa: E402


class FakeService:
    def sessions(self, mode=None): return []
    def models(self): return [{"id": "local-model"}]
    def settings(self): return {"model": "local-model"}
    def file_tree(self, sid): return {"root": "", "tree": []}
    def skills(self): return []
    def memory(self): return {"content": ""}
    def close(self): pass


@pytest.fixture(autouse=True)
def isolate_native_settings(tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    yield


def test_native_window_constructs_without_a_webview() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(FakeService())  # type: ignore[arg-type]
    window.refresh_timer.stop()
    app.processEvents()
    try:
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.title_bar.isVisibleTo(window)
        assert window.transcript is not None
        # empty conversations greet with the centered welcome composer
        assert window.composer.placeholderText() in {
            "How can I help you today?", "What should I research in depth?"}
        assert window.welcome_host.isVisibleTo(window)
        assert window.code_nav.isCheckable()
        assert window.chat_nav.isCheckable()
        assert window.research_nav.isCheckable()
        assert not hasattr(window, "mode_toggle")
        assert window.terminal is not None
        assert window.browser_panel is not None
        assert window.artifact_preview is not None
    finally:
        window.close()
        app.processEvents()


def test_default_desktop_entrypoint_does_not_start_uvicorn(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(sys, "argv", ["run_app.py"])
    monkeypatch.setattr(instance, "acquire_instance_lock", lambda: True)
    monkeypatch.setattr(native, "run_native", lambda: called.append("native") or 0)
    monkeypatch.setattr(
        desktop_app, "_start_server",
        lambda port: (_ for _ in ()).throw(AssertionError("server started")))
    desktop_app.main()
    assert called == ["native"]


def test_native_smoke_exit_code_is_propagated(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_app.py", "--native-smoke"])
    monkeypatch.setattr(instance, "acquire_instance_lock", lambda: True)
    monkeypatch.setattr("harness.native.app.smoke_native", lambda: 3)
    with pytest.raises(SystemExit) as caught:
        desktop_app.main()
    assert caught.value.code == 3


def test_settings_save_stays_open_and_reports_completion() -> None:
    saved = []

    class SettingsService:
        def settings(self):
            return {
                "temperature": 0.4,
                "base_url": "http://localhost:1234/v1",
                "model": "local-model",
                "context_window": 32768,
                "max_output_tokens": 4096,
                "mcp_servers": {},
                "effective_context_window": 32768,
                "mcp_status": [],
                "computer_control": {"state": "ready"},
                "background": {
                    "model": {"state": "ready", "error": None},
                    "mcp": {"state": "ready", "error": None},
                },
            }

        def save_settings(self, values):
            saved.append(values)
            return self.settings()

    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(SettingsService())  # type: ignore[arg-type]
    dialog.show()
    dialog.save()
    deadline = time.monotonic() + 2
    while (not saved or not dialog.save_button.isEnabled()) \
            and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    try:
        assert saved
        assert dialog.isVisible()
        assert dialog.result() == 0
        assert dialog.health.text().startswith("Settings saved")
    finally:
        dialog.close()
        app.processEvents()


def test_stop_button_calls_the_in_process_cancellation_path() -> None:
    class StopService(FakeService):
        def __init__(self):
            self.stopped = []

        def stop(self, sid):
            self.stopped.append(sid)
            return {"requested": True, "state": "running"}

    app = QApplication.instance() or QApplication([])
    service = StopService()
    window = MainWindow(service)  # type: ignore[arg-type]
    window.refresh_timer.stop()
    window.current_id = "session-1"
    window.stop_generation()
    try:
        assert service.stopped == ["session-1"]
        assert not window.stop_button.isEnabled()
    finally:
        window.close()
        app.processEvents()


def test_sidebar_modes_load_separate_histories(tmp_path) -> None:
    class ModeService(FakeService):
        records = {
            "agent": [{"id": "code-1", "title": "Fix repository", "mode": "agent"}],
            "chat": [{"id": "chat-1", "title": "Weekend ideas", "mode": "chat"}],
        }

        def sessions(self, mode=None):
            return list(self.records.get(mode, []))

        def search_sessions(self, query, mode=None):
            return [item for item in self.sessions(mode)
                    if query.casefold() in item["title"].casefold()]

        def session(self, sid):
            item = next(item for values in self.records.values()
                        for item in values if item["id"] == sid)
            return {
                **item, "workspace": str(tmp_path), "display": [],
                "context": {}, "pending_messages": [],
            }

        def job(self, sid):
            return None

        def workspace(self, sid):
            return tmp_path

    app = QApplication.instance() or QApplication([])
    window = MainWindow(ModeService())  # type: ignore[arg-type]
    window.refresh_timer.stop()
    try:
        window.set_mode("agent")
        assert [item["id"] for item in window.session_cache] == ["code-1"]
        assert window.session_list.item(0).text().startswith("Fix repository")
        window.set_mode("chat")
        assert [item["id"] for item in window.session_cache] == ["chat-1"]
        assert window.session_list.item(0).text().startswith("Weekend ideas")
        assert not window.workspace_button.isVisibleTo(window)
    finally:
        window.close()
        app.processEvents()


def test_image_attachment_tile_uses_workspace_file(tmp_path) -> None:
    from PySide6.QtGui import QImage
    image = QImage(32, 24, QImage.Format.Format_RGB32)
    image.fill(0x336699)
    path = tmp_path / "preview.png"
    assert image.save(str(path))
    tile = AttachmentTile({"name": path.name, "kind": "image"}, tmp_path)
    assert tile.is_image
    assert tile.path == path
    assert not tile.icon().isNull()


def test_transcript_settles_at_the_real_scroll_bottom(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    transcript = TranscriptView()
    transcript.resize(420, 220)
    transcript.show()
    transcript.render_display([
        {"t": "user" if index % 2 == 0 else "text",
         "text": f"Message {index}\n" + ("long content " * 20)}
        for index in range(20)
    ], tmp_path)
    # The eased scroll animation may still be in flight; pump until the view
    # settles (bounded), then require it to sit exactly at the bottom.
    bar = transcript.verticalScrollBar()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
        if (time.monotonic() - deadline > -1.7 and bar.maximum() > 0
                and bar.value() == bar.maximum()):
            break
    try:
        assert bar.maximum() > 0
        assert bar.value() == bar.maximum()
    finally:
        transcript.close()
        app.processEvents()


def test_pty_key_sequences_cover_shell_essentials() -> None:
    QApplication.instance() or QApplication([])
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    from harness.native.widgets import _pty_sequence

    def make(key, modifiers=Qt.KeyboardModifier.NoModifier, text=""):
        return QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)

    assert _pty_sequence(make(Qt.Key.Key_Tab)) == "\t"
    assert _pty_sequence(make(Qt.Key.Key_Return)) == "\r"
    assert _pty_sequence(make(Qt.Key.Key_Backspace)) == "\x7f"
    assert _pty_sequence(make(Qt.Key.Key_Up)) == "\x1b[A"
    assert _pty_sequence(
        make(Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)) == "\x03"
    # the copy/paste chords stay with the widget, not the shell
    assert _pty_sequence(make(
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.ShiftModifier)) is None
    assert _pty_sequence(make(Qt.Key.Key_A, text="a")) == "a"
    assert _pty_sequence(make(Qt.Key.Key_F35)) is None
