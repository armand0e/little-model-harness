"""Native dialogs for settings and destructive confirmations."""
from __future__ import annotations

import json
import threading

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .service import HarnessService, ServiceError
from .widgets import WheelGuard


class SettingsDialog(QDialog):
    save_finished = Signal(object, str)

    def __init__(self, service: HarnessService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(590, 620)
        self.setObjectName("settingsDialog")
        outer = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setObjectName("dialogTitle")
        outer.addWidget(title)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.1)
        self.temperature.setDecimals(2)
        self.base_url = QLineEdit()
        self.model = QLineEdit()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.context_window = QSpinBox()
        self.context_window.setRange(2048, 1_048_576)
        self.context_window.setSingleStep(1024)
        self.max_output = QSpinBox()
        self.max_output.setRange(256, 131_072)
        self.max_output.setSingleStep(256)
        self.mcp = QPlainTextEdit()
        self.mcp.setMinimumHeight(150)
        for label, widget in (
            ("Temperature", self.temperature),
            ("Base URL", self.base_url),
            ("Model ID", self.model),
            ("API key (leave blank to keep current)", self.api_key),
            ("Context window", self.context_window),
            ("Maximum output tokens", self.max_output),
            ("Additional MCP servers (JSON)", self.mcp),
        ):
            form.addRow(label, widget)
        self.wheel_guard = WheelGuard(self)
        for spin in (self.temperature, self.context_window, self.max_output):
            spin.installEventFilter(self.wheel_guard)
        outer.addLayout(form)
        self.health = QLabel()
        self.health.setWordWrap(True)
        self.health.setObjectName("settingsHealth")
        outer.addWidget(self.health)
        actions = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
            | QDialogButtonBox.StandardButton.Save)
        self.save_button = actions.button(QDialogButtonBox.StandardButton.Save)
        self.close_button = actions.button(QDialogButtonBox.StandardButton.Close)
        self.save_button.setText("Save changes")
        actions.rejected.connect(self.reject)
        self.save_button.clicked.connect(self.save)
        outer.addWidget(actions)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(600)
        self.poll_timer.timeout.connect(self.poll_health)
        self.poll_attempts = 0
        self._saving = False
        self.save_finished.connect(self._save_complete)
        self.populate()

    def reject(self) -> None:
        if self._saving:
            return
        super().reject()

    def populate(self) -> None:
        settings = self.service.settings()
        self.temperature.setValue(float(settings["temperature"]))
        self.base_url.setText(str(settings["base_url"]))
        self.model.setText(str(settings["model"]))
        self.context_window.setValue(int(settings["context_window"]))
        self.max_output.setValue(int(settings["max_output_tokens"]))
        self.mcp.setPlainText(json.dumps(settings.get("mcp_servers", {}), indent=2))
        effective = settings.get("effective_context_window")
        mcp_count = sum(1 for item in settings.get("mcp_status", [])
                        if item.get("state") == "ready")
        computer = settings.get("computer_control", {})
        self.health.setText(
            f"Effective context: {effective:,} tokens\n"
            f"MCP: {mcp_count} connected\n"
            f"Computer control: {computer.get('state', 'unknown')}")

    def save(self) -> None:
        try:
            mcp = json.loads(self.mcp.toPlainText() or "{}")
            if not isinstance(mcp, dict):
                raise ValueError("MCP configuration must be a JSON object")
            values = {
                "temperature": self.temperature.value(),
                "base_url": self.base_url.text().strip(),
                "model": self.model.text().strip(),
                "context_window": self.context_window.value(),
                "max_output_tokens": self.max_output.value(),
                "mcp_servers": mcp,
            }
            if self.api_key.text():
                values["api_key"] = self.api_key.text()
        except (ServiceError, ValueError, json.JSONDecodeError) as exc:
            self._show_save_error(str(exc))
            return
        self._saving = True
        self.save_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.save_button.setText("Saving…")
        self.health.setObjectName("settingsHealth")
        self.health.setText("Saving settings to disk…")
        self._repolish_health()

        def work() -> None:
            try:
                result = self.service.save_settings(values)
                self.save_finished.emit(result, "")
            except Exception as exc:
                self.save_finished.emit(
                    {}, f"{type(exc).__name__}: {exc}")

        threading.Thread(target=work, name="lmh-settings-save", daemon=True).start()

    def _save_complete(self, settings: object, error: str) -> None:
        if error:
            self._show_save_error(error)
            return
        self._saving = False
        self.save_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.save_button.setText("Save changes")
        self.health.setObjectName("settingsHealth")
        self.health.setText(
            "Settings saved. Checking the model endpoint and MCP connections…")
        self._repolish_health()
        self.poll_attempts = 0
        self.poll_timer.start()

    def poll_health(self) -> None:
        self.poll_attempts += 1
        try:
            settings = self.service.settings()
        except ServiceError as exc:
            self.poll_timer.stop()
            self._show_save_error(f"Saved, but health could not be read: {exc}")
            return
        background = settings.get("background", {})
        model = background.get("model", {})
        mcp = background.get("mcp", {})
        active = model.get("state") in {"checking", "connecting"} \
            or mcp.get("state") in {"checking", "connecting"}
        problems = [str(item.get("error")) for item in (model, mcp)
                    if item.get("state") == "error" and item.get("error")]
        effective = settings.get("effective_context_window", 0)
        lines = ["Settings saved.",
                 f"Model: {model.get('state', 'idle')}",
                 f"MCP: {mcp.get('state', 'idle')}",
                 f"Effective context: {int(effective):,} tokens"]
        lines.extend(problems)
        self.health.setText("\n".join(lines))
        self.health.setObjectName("settingsError" if problems else "settingsHealth")
        self._repolish_health()
        if not active or self.poll_attempts >= 20:
            self.poll_timer.stop()

    def _show_save_error(self, message: str) -> None:
        self._saving = False
        self.health.setObjectName("settingsError")
        self.health.setText(f"Could not save settings: {message}")
        self._repolish_health()
        self.save_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.save_button.setText("Save changes")

    def _repolish_health(self) -> None:
        self.health.style().unpolish(self.health)
        self.health.style().polish(self.health)


class AboutNativeDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Little Harness")
        layout = QVBoxLayout(self)
        title = QLabel("Little Harness")
        title.setObjectName("dialogTitle")
        description = QLabel(
            "Native Qt desktop client for local OpenAI-compatible models.\n"
            "The desktop UI communicates with the Python agent in-process; "
            "it does not run a localhost web application.")
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
