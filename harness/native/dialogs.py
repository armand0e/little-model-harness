"""Native dialogs for settings and destructive confirmations."""
from __future__ import annotations

import json
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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
    models_listed = Signal(list)

    def __init__(self, service: HarnessService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(590, 700)
        self.setObjectName("settingsDialog")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 14)
        outer.setSpacing(10)
        title = QLabel("Settings")
        title.setObjectName("dialogTitle")
        outer.addWidget(title)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.1)
        self.temperature.setDecimals(2)
        self.base_url = QLineEdit()
        self.model = QComboBox()
        self.model.setEditable(True)
        model_editor = self.model.lineEdit()
        if model_editor is not None:
            model_editor.setPlaceholderText(
                "auto — first model reported by the endpoint")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.context_window = QSpinBox()
        self.context_window.setRange(2048, 1_048_576)
        self.context_window.setSingleStep(1024)
        self.max_output = QSpinBox()
        self.max_output.setRange(256, 131_072)
        self.max_output.setSingleStep(256)
        self.font_px = QSpinBox()
        self.font_px.setRange(11, 17)
        self.font_px.setSuffix(" px")
        self.rules = QPlainTextEdit()
        self.rules.setPlaceholderText(
            "Instructions the assistant follows in every conversation — "
            "tone, language, formatting, house rules…")
        self.rules.setMinimumHeight(90)
        self.mcp = QPlainTextEdit()
        self.mcp.setMinimumHeight(110)
        # Modern card layout: each section is a rounded card; each row has a
        # bold name, a muted caption, and its control — no bare form grid.
        from PySide6.QtWidgets import QFrame, QScrollArea

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(12)

        def card(section_title: str) -> QVBoxLayout:
            frame = QFrame()
            frame.setObjectName("settingsCard")
            card_layout = QVBoxLayout(frame)
            card_layout.setContentsMargins(16, 12, 16, 14)
            card_layout.setSpacing(10)
            heading = QLabel(section_title)
            heading.setObjectName("settingsCardTitle")
            card_layout.addWidget(heading)
            content_layout.addWidget(frame)
            return card_layout

        def row(card_layout: QVBoxLayout, name: str, caption: str,
                widget: QWidget, *, wide: bool = False) -> None:
            from PySide6.QtWidgets import QBoxLayout
            block = QVBoxLayout()
            block.setSpacing(3)
            head: QBoxLayout = QVBoxLayout() if wide else QHBoxLayout()
            head.setSpacing(1 if wide else 12)
            text_column = QVBoxLayout()
            text_column.setSpacing(1)
            name_label = QLabel(name)
            name_label.setObjectName("settingName")
            caption_label = QLabel(caption)
            caption_label.setObjectName("settingCaption")
            caption_label.setWordWrap(True)
            text_column.addWidget(name_label)
            text_column.addWidget(caption_label)
            if wide:
                head.addLayout(text_column)
                block.addLayout(head)
                block.addWidget(widget)
            else:
                head.addLayout(text_column, 1)
                widget.setMinimumWidth(230)
                head.addWidget(widget, 0,
                               Qt.AlignmentFlag.AlignVCenter)
                block.addLayout(head)
            card_layout.addLayout(block)

        model_card = card("Model")
        row(model_card, "Endpoint", "OpenAI-compatible base URL "
            "(LM Studio, llama.cpp, Ollama…)", self.base_url, wide=True)
        row(model_card, "Model", "Leave empty to use the first model the "
            "endpoint reports", self.model)
        row(model_card, "API key", "Only if your endpoint requires one; "
            "blank keeps the current key", self.api_key)

        generation_card = card("Generation")
        row(generation_card, "Temperature",
            "Lower is more focused; higher is more creative", self.temperature)
        row(generation_card, "Context window",
            "Clamped to what the model server actually supports",
            self.context_window)
        row(generation_card, "Max output tokens",
            "Upper bound for a single response", self.max_output)

        appearance_card = card("Appearance & behavior")
        row(appearance_card, "Text size", "Applies across the whole app",
            self.font_px)
        row(appearance_card, "Global rules", "Instructions the assistant "
            "follows in every conversation", self.rules, wide=True)

        integrations_card = card("Integrations")
        row(integrations_card, "MCP servers", "JSON map of external tool "
            "servers; applied after saving", self.mcp, wide=True)

        self.health = QLabel()
        self.health.setWordWrap(True)
        self.health.setObjectName("settingsHealth")
        content_layout.addWidget(self.health)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self.wheel_guard = WheelGuard(self)
        for spin in (self.temperature, self.context_window, self.max_output,
                     self.font_px, self.model):
            spin.installEventFilter(self.wheel_guard)
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
        self._closed = False
        self.save_finished.connect(self._save_complete)
        self.models_listed.connect(self._fill_model_choices)
        self.populate()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closed = True
        super().closeEvent(event)

    def reject(self) -> None:
        if self._saving:
            return
        super().reject()

    def populate(self) -> None:
        settings = self.service.settings()
        self.temperature.setValue(float(settings["temperature"]))
        self.base_url.setText(str(settings["base_url"]))
        self.model.setCurrentText(str(settings["model"]))
        self.font_px.setValue(int(settings.get("ui_font_px") or 13))
        self.rules.setPlainText(str(settings.get("global_rules") or ""))
        self.context_window.setValue(int(settings["context_window"]))
        self.max_output.setValue(int(settings["max_output_tokens"]))
        self.mcp.setPlainText(json.dumps(settings.get("mcp_servers", {}), indent=2))
        self._load_model_choices()
        effective = settings.get("effective_context_window")
        mcp_count = sum(1 for item in settings.get("mcp_status", [])
                        if item.get("state") == "ready")
        computer = settings.get("computer_control", {})
        self.health.setText(
            f"Effective context: {effective:,} tokens\n"
            f"MCP: {mcp_count} connected\n"
            f"Computer control: {computer.get('state', 'unknown')}")

    def _load_model_choices(self) -> None:
        def work() -> None:
            try:
                models = [str(m["id"]) for m in self.service.models()]
            except Exception:
                return
            # The dialog is short-lived: emitting into a destroyed QObject
            # from this worker crashes the process, not just the thread.
            try:
                import shiboken6
                if self._closed or not shiboken6.isValid(self):
                    return
                self.models_listed.emit(models)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="lmh-settings-models",
                         daemon=True).start()

    def _fill_model_choices(self, models: list) -> None:
        current = self.model.currentText()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems([str(m) for m in models])
        self.model.setCurrentText(current)
        self.model.blockSignals(False)

    def save(self) -> None:
        try:
            mcp = json.loads(self.mcp.toPlainText() or "{}")
            if not isinstance(mcp, dict):
                raise ValueError("MCP configuration must be a JSON object")
            values = {
                "temperature": self.temperature.value(),
                "base_url": self.base_url.text().strip(),
                "model": self.model.currentText().strip(),
                "context_window": self.context_window.value(),
                "max_output_tokens": self.max_output.value(),
                "ui_font_px": self.font_px.value(),
                "global_rules": self.rules.toPlainText(),
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
