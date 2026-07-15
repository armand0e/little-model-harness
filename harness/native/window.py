"""Main native Qt window for Little Harness."""
from __future__ import annotations

import threading
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSizeGrip,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .dialogs import AboutNativeDialog, SettingsDialog
from .icons import set_svg_icon, svg_pixmap
from .service import HarnessService, ServiceError
from .theme import apply_theme, current_theme
from .widgets import (
    ArtifactPreview,
    ComposerEdit,
    IconButton,
    JobWatcher,
    MarkdownView,
    SelectButton,
    SessionList,
    TranscriptView,
    WelcomePanel,
    create_browser_panel,
    create_terminal,
)


class TitleBar(QFrame):
    def __init__(self, window: QMainWindow) -> None:
        super().__init__()
        self.host_window = window
        self.setObjectName("titleBar")
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)
        mark = QLabel()
        mark.setPixmap(svg_pixmap("mark", 11, "#d97757"))
        name = QLabel("Little Harness")
        name.setObjectName("appName")
        self.context = QLabel("Native local AI workspace")
        self.context.setObjectName("windowContext")
        layout.addWidget(mark)
        layout.addWidget(name)
        layout.addWidget(self.context)
        layout.addStretch(1)
        for icon, tooltip, slot, close in (
            ("minimize", "Minimize", window.showMinimized, False),
            ("maximize", "Maximize", self.toggle_maximize, False),
            ("close", "Close", window.close, True),
        ):
            button = IconButton(icon, tooltip, size=11)
            button.setFixedSize(46, 36)
            button.setObjectName("windowClose" if close else "windowControl")
            button.clicked.connect(slot)
            layout.addWidget(button)

    def toggle_maximize(self) -> None:
        (self.host_window.showNormal() if self.host_window.isMaximized()
         else self.host_window.showMaximized())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.host_window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    models_ready = Signal(list)
    models_failed = Signal(str)
    background_error = Signal(str)

    def __init__(self, service: HarnessService) -> None:
        super().__init__()
        self.service = service
        self.mode = str(QSettings("LittleHarness", "LittleHarness").value(
            "mode", "agent"))
        if self.mode not in {"agent", "chat", "research"}:
            self.mode = "agent"
        self.current_id: str | None = None
        self.session_cache: list[dict] = []
        self.watchers: dict[str, JobWatcher] = {}
        self.live_events: dict[str, list[dict]] = {}
        self.attachments: list[str] = []
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.Window)
        self.setMinimumSize(980, 650)
        self.resize(1380, 880)
        self.setObjectName("root")
        self._build()
        self.models_ready.connect(self._populate_models)
        self.models_failed.connect(self._models_unavailable)
        self.background_error.connect(self._show_error)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_sessions)
        self.refresh_timer.start(1200)
        self.set_mode(self.mode)
        self._load_models_async()

    # ---------- structure ----------
    def _build(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)
        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.sidebar = self._build_sidebar()
        self.center = self._build_center()
        self.right_panel = self._build_right_panel()
        self.body_splitter.addWidget(self.sidebar)
        self.body_splitter.addWidget(self.center)
        self.body_splitter.addWidget(self.right_panel)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setStretchFactor(2, 0)
        self.body_splitter.setSizes([270, 800, 310])
        # The splitter handle advertises resizing, so honor it: the sidebar
        # is draggable between 220 and 400 pixels rather than fixed.
        self.sidebar.setMaximumWidth(400)
        self.right_panel.setMinimumWidth(300)
        self.right_panel.setMaximumWidth(600)
        self.right_panel.hide()
        root.addWidget(self.body_splitter, 1)
        self.setCentralWidget(central)
        # Float the resize grip over the corner instead of giving it its own
        # layout row, which left a dead strip under the sidebar and composer.
        self.size_grip = QSizeGrip(central)
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.raise_()
        QTimer.singleShot(0, self._layout_responsive)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_responsive()
        if hasattr(self, "size_grip"):
            host = self.centralWidget()
            self.size_grip.move(host.width() - 16, host.height() - 16)
            self.size_grip.raise_()

    def _layout_responsive(self) -> None:
        if not hasattr(self, "composer_column"):
            return
        available = max(360, self.center.width() - 48)
        self.composer_column.setFixedWidth(min(760, available))

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 12, 8, 10)
        brand_row = QHBoxLayout()
        brand_mark = QLabel()
        brand_mark.setPixmap(svg_pixmap("mark", 12, "#d97757"))
        brand = QLabel("Little Harness")
        brand.setObjectName("brand")
        collapse = IconButton("chevron_left", "Hide sidebar", size=15)
        collapse.clicked.connect(lambda: self.toggle_sidebar(False))
        brand_row.addWidget(brand_mark)
        brand_row.addWidget(brand, 1)
        brand_row.addWidget(collapse)
        layout.addLayout(brand_row)
        self.code_nav = QPushButton("Code tasks")
        self.chat_nav = QPushButton("Chat")
        self.research_nav = QPushButton("Deep research")
        set_svg_icon(self.code_nav, "code", 14)
        set_svg_icon(self.chat_nav, "chat", 14)
        set_svg_icon(self.research_nav, "research", 14)
        for button in (self.code_nav, self.chat_nav, self.research_nav):
            button.setObjectName("navButton")
            button.setCheckable(True)
            layout.addWidget(button)
        self.code_nav.clicked.connect(lambda: self.set_mode("agent"))
        self.chat_nav.clicked.connect(lambda: self.set_mode("chat"))
        self.research_nav.clicked.connect(lambda: self.set_mode("research"))
        self.new_button = QPushButton("New code task")
        set_svg_icon(self.new_button, "plus", 15, "#ffffff")
        self.new_button.setObjectName("primary")
        self.new_button.clicked.connect(self.new_session)
        layout.addWidget(self.new_button)
        self.history_label = QLabel("CODE HISTORY")
        self.history_label.setObjectName("sectionLabel")
        layout.addWidget(self.history_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search code history…")
        self.search.textChanged.connect(self.render_session_list)
        layout.addWidget(self.search)
        self.session_list = SessionList()
        self.session_list.itemSelectionChanged.connect(self._session_selected)
        self.session_list.customContextMenuRequested.connect(self._session_menu)
        layout.addWidget(self.session_list, 1)
        context_row = QHBoxLayout()
        self.context_label = QLabel("context")
        self.context_label.setObjectName("contextLabel")
        self.context_bar = QProgressBar()
        self.context_bar.setRange(0, 100)
        self.context_bar.setValue(0)
        self.context_bar.setTextVisible(False)
        self.context_bar.setFixedHeight(5)
        self.context_percent = QLabel("0%")
        self.context_percent.setObjectName("contextLabel")
        context_row.addWidget(self.context_label)
        context_row.addWidget(self.context_bar, 1)
        context_row.addWidget(self.context_percent)
        layout.addLayout(context_row)
        footer = QHBoxLayout()
        theme = QPushButton("Theme")
        settings = QPushButton("Settings")
        theme.setObjectName("footerButton")
        settings.setObjectName("footerButton")
        set_svg_icon(theme, "moon", 14)
        set_svg_icon(settings, "settings", 14)
        theme.clicked.connect(self.toggle_theme)
        settings.clicked.connect(self.open_settings)
        footer.addWidget(theme)
        footer.addWidget(settings)
        layout.addLayout(footer)
        return sidebar

    def _build_center(self) -> QWidget:
        center = QFrame()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top = QFrame()
        top.setObjectName("topBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(10, 9, 12, 9)
        top_layout.setSpacing(8)
        self.sidebar_toggle = IconButton("menu", "Show sidebar", size=16)
        self.sidebar_toggle.clicked.connect(lambda: self.toggle_sidebar(True))
        self.sidebar_toggle.hide()
        self.chat_title = QLabel("New task")
        self.chat_title.setObjectName("chatTitle")
        self.model_select = SelectButton(minimum_width=90)
        # Styled as quiet inline text inside the composer, like the Claude
        # client's model picker.
        self.model_select.setObjectName("composerModelSelect")
        self.model_select.changed.connect(self._model_changed)
        self.export_button = IconButton("download", "Export conversation", size=16)
        self.export_button.clicked.connect(self.export_conversation)
        self.artifact_button = IconButton("panels", "Toggle artifact preview", size=16)
        self.artifact_button.clicked.connect(lambda: self.toggle_right_panel(0))
        self.files_button = IconButton("folder", "Workspace files", size=16)
        self.files_button.clicked.connect(lambda: self.toggle_right_panel(1))
        self.terminal_button = IconButton("terminal", "Terminal", size=16)
        self.terminal_button.clicked.connect(lambda: self.toggle_right_panel(4))
        self.browser_button = IconButton("browser", "Managed browser", size=16)
        self.browser_button.clicked.connect(lambda: self.toggle_right_panel(5))
        self.about_button = IconButton("sparkle", "About Little Harness", size=16)
        self.about_button.clicked.connect(lambda: AboutNativeDialog(self).exec())
        top_layout.addWidget(self.sidebar_toggle)
        top_layout.addWidget(self.chat_title, 1)
        top_layout.addWidget(self.export_button)
        top_layout.addWidget(self.artifact_button)
        top_layout.addWidget(self.files_button)
        top_layout.addWidget(self.terminal_button)
        top_layout.addWidget(self.browser_button)
        top_layout.addWidget(self.about_button)
        layout.addWidget(top)
        self.transcript = TranscriptView()
        self.transcript.revert_requested.connect(
            lambda index: self._redo_from(index, regenerate=False))
        self.transcript.edit_requested.connect(
            lambda index: self._redo_from(index, regenerate=False))
        self.transcript.regenerate_requested.connect(
            lambda index: self._redo_from(index, regenerate=True))
        layout.addWidget(self.transcript, 1)
        self.welcome_host = WelcomePanel()
        self.welcome_host.prompt_selected.connect(self._use_suggestion)
        self.welcome_host.hide()
        layout.addWidget(self.welcome_host, 1)
        layout.addWidget(self._build_composer())
        self._composer_in_welcome = False
        return center

    def _build_composer(self) -> QWidget:
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(24, 5, 24, 18)
        wrap_layout.setSpacing(5)
        self.composer_column = QWidget()
        self.composer_column.setMaximumWidth(760)
        self.composer_column.setMinimumWidth(360)
        self.composer_column.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        column = QVBoxLayout(self.composer_column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self.followup_list = QListWidget()
        self.followup_list.setMaximumHeight(95)
        self.followup_list.setVisible(False)
        column.addWidget(self.followup_list)
        self.attachment_row = QHBoxLayout()
        column.addLayout(self.attachment_row)
        self.workspace_button = QPushButton("Workspace")
        self.workspace_button.setObjectName("workspaceChip")
        set_svg_icon(self.workspace_button, "folder", 13)
        self.workspace_button.clicked.connect(self.choose_workspace)
        workspace_row = QHBoxLayout()
        workspace_row.addWidget(self.workspace_button)
        workspace_row.addStretch(1)
        column.addLayout(workspace_row)
        frame = QFrame()
        frame.setObjectName("composerFrame")
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 55))
        frame.setGraphicsEffect(shadow)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        self.composer = ComposerEdit()
        self.composer.setPlaceholderText("Message Little Harness…")
        self.composer.setFixedHeight(48)
        self.composer.textChanged.connect(self._resize_composer)
        self.composer.submitted.connect(self.send)
        self.composer.stop_requested.connect(self.stop_generation)
        self.composer.files_dropped.connect(self._add_attachments)
        layout.addWidget(self.composer)
        row = QHBoxLayout()
        self.attach_button = IconButton("plus", "Attach files", size=16)
        self.attach_button.setObjectName("attachButton")
        self.attach_button.clicked.connect(self.choose_attachments)
        self.send_action = SelectButton(minimum_width=80)
        self.send_action.set_options([("Queue", "queue"), ("Steer", "steer")])
        self.send_action.setVisible(False)
        self.stop_button = IconButton("stop", "Stop generation", size=14)
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self.stop_generation)
        self.stop_button.setVisible(False)
        self.send_button = IconButton("arrow_up", "Send message", size=16)
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.send)
        self.composer_hint = QLabel("Enter to send · Shift+Enter for a new line")
        self.composer_hint.setObjectName("composerHint")
        row.addWidget(self.attach_button)
        row.addWidget(self.composer_hint)
        row.addStretch(1)
        row.addWidget(self.send_action)
        # The model pill lives with the composer, like the web client.
        row.addWidget(self.model_select)
        row.addWidget(self.stop_button)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        column.addWidget(frame)
        centered = QHBoxLayout()
        centered.addStretch(1)
        centered.addWidget(self.composer_column)
        centered.addStretch(1)
        self._composer_bottom_slot = centered
        self._composer_bottom_wrap = wrap
        wrap_layout.addLayout(centered)
        return wrap

    def _set_composer_home(self, welcome: bool) -> None:
        """Empty conversations center the composer under the greeting, like
        the Claude desktop client; the first message docks it to the bottom."""
        if welcome != self._composer_in_welcome:
            self._composer_in_welcome = welcome
            if welcome:
                self.welcome_host.composer_slot.addWidget(self.composer_column)
            else:
                self._composer_bottom_slot.insertWidget(1, self.composer_column)
        if welcome:
            self.welcome_host.refresh(self.mode)
        self.welcome_host.setVisible(welcome)
        self.transcript.setVisible(not welcome)
        self._composer_bottom_wrap.setVisible(not welcome)
        self.composer_column.show()
        self._layout_responsive()
        self.composer.setFocus()
        placeholders = {"research": "What should I research in depth?"}
        self.composer.setPlaceholderText(
            placeholders.get(self.mode, "How can I help you today?")
            if welcome else "Reply to Little Harness…")

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("rightPanel")
        panel.setMinimumWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self.right_select = SelectButton(minimum_width=150)
        self.right_select.set_options([
            ("Preview", "0"), ("Files", "1"), ("Skills", "2"),
            ("Memory", "3"), ("Terminal", "4"), ("Browser", "5"),
        ])
        self.right_select.changed.connect(
            lambda value: self._set_right_index(int(value)))
        header.addWidget(self.right_select)
        header.addStretch(1)
        layout.addLayout(header)
        self.right_tabs = QStackedWidget()
        self.artifact_preview = ArtifactPreview()
        self.files_tab = QWidget()
        files_layout = QVBoxLayout(self.files_tab)
        tools = QHBoxLayout()
        refresh = QPushButton("Refresh")
        folder = QPushButton("New folder")
        refresh.clicked.connect(self.refresh_files)
        folder.clicked.connect(self.new_folder)
        tools.addWidget(refresh)
        tools.addWidget(folder)
        tools.addStretch(1)
        files_layout.addLayout(tools)
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.itemDoubleClicked.connect(self.open_file)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._file_menu)
        files_layout.addWidget(self.file_tree)
        self.skills_tab = QWidget()
        skills_layout = QVBoxLayout(self.skills_tab)
        skills_layout.setContentsMargins(4, 4, 4, 4)
        skills_layout.setSpacing(7)
        skills_heading = QLabel("Skills")
        skills_heading.setObjectName("panelHeading")
        self.skills_count = QLabel("")
        self.skills_count.setObjectName("panelSubtle")
        skills_header = QHBoxLayout()
        skills_header.addWidget(skills_heading)
        skills_header.addWidget(self.skills_count, 1)
        skills_layout.addLayout(skills_header)
        self.skills_search = QLineEdit()
        self.skills_search.setPlaceholderText("Filter skills…")
        self.skills_search.textChanged.connect(self._render_skill_cards)
        skills_layout.addWidget(self.skills_search)
        self.skills_list = QListWidget()
        self.skills_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.skills_list.setSpacing(4)
        self.skills_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        skills_layout.addWidget(self.skills_list, 1)
        self._skills_cache: list[dict] = []
        self.memory_tab = QWidget()
        memory_layout = QVBoxLayout(self.memory_tab)
        memory_layout.setContentsMargins(4, 4, 4, 4)
        memory_layout.setSpacing(7)
        memory_heading = QLabel("Memory")
        memory_heading.setObjectName("panelHeading")
        memory_subtle = QLabel("Facts the assistant keeps across sessions")
        memory_subtle.setObjectName("panelSubtle")
        memory_layout.addWidget(memory_heading)
        memory_layout.addWidget(memory_subtle)
        memory_scroll = QScrollArea()
        memory_scroll.setWidgetResizable(True)
        memory_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.memory_view = MarkdownView("")
        memory_host = QWidget()
        memory_host_layout = QVBoxLayout(memory_host)
        memory_host_layout.setContentsMargins(6, 6, 6, 12)
        memory_host_layout.addWidget(self.memory_view)
        memory_host_layout.addStretch(1)
        memory_scroll.setWidget(memory_host)
        memory_layout.addWidget(memory_scroll, 1)
        self.terminal = create_terminal()
        self.browser_panel = create_browser_panel()
        self.right_tabs.addWidget(self.artifact_preview)
        self.right_tabs.addWidget(self.files_tab)
        self.right_tabs.addWidget(self.skills_tab)
        self.right_tabs.addWidget(self.memory_tab)
        self.right_tabs.addWidget(self.terminal)
        self.right_tabs.addWidget(self.browser_panel)
        self.right_tabs.currentChanged.connect(self.refresh_right_panel)
        self.right_tabs.currentChanged.connect(
            lambda index: self.right_select.set_value(str(index)))
        layout.addWidget(self.right_tabs)
        return panel

    def _set_right_index(self, index: int) -> None:
        if 0 <= index < self.right_tabs.count():
            self.right_tabs.setCurrentIndex(index)
            self.right_select.set_value(str(index))

    # ---------- sessions and modes ----------
    def set_mode(self, mode: str) -> None:
        if mode not in {"agent", "chat", "research"}:
            return
        self.mode = mode
        QSettings("LittleHarness", "LittleHarness").setValue("mode", mode)
        self.code_nav.setChecked(mode == "agent")
        self.chat_nav.setChecked(mode == "chat")
        self.research_nav.setChecked(mode == "research")
        labels = {
            "agent": ("New code task", "Search code tasks…", "New task"),
            "chat": ("New chat", "Search chats…", "New chat"),
            "research": ("New research", "Search research…", "New research"),
        }[mode]
        self.new_button.setText(labels[0])
        self.history_label.setText("RECENTS")
        self.search.setPlaceholderText(labels[1])
        if mode != "agent":
            self.right_panel.hide()
        # Research is a reading experience: no workspace/file chrome.
        self.workspace_button.setVisible(mode == "agent")
        self.attach_button.setVisible(mode == "agent")
        self.artifact_button.setVisible(mode == "agent")
        self.files_button.setVisible(mode == "agent")
        self.terminal_button.setVisible(mode == "agent")
        self.browser_button.setVisible(mode == "agent")
        self.current_id = None
        self.transcript.mode = mode
        self.transcript.render_display([], Path.cwd())
        self.chat_title.setText(labels[2])
        self._set_composer_home(True)
        self.refresh_sessions(open_latest=True)

    def refresh_sessions(self, open_latest: bool = False) -> None:
        try:
            self.session_cache = self.service.sessions(self.mode)
        except ServiceError as exc:
            self._show_error(str(exc))
            return
        self.render_session_list()
        for session in self.session_cache:
            if session.get("job_id"):
                job = self.service.job(session["id"])
                if job is not None:
                    self.watch_job(job)
        if open_latest and self.current_id is None and self.session_cache:
            self.open_session(self.session_cache[0]["id"])
        self._sync_running_ui()

    def render_session_list(self) -> None:
        query = self.search.text().strip().casefold()
        if query:
            try:
                sessions = self.service.search_sessions(query, self.mode)
            except (ServiceError, AttributeError):
                sessions = [item for item in self.session_cache
                            if query in item.get("title", "").casefold()]
        else:
            sessions = self.session_cache
        self.session_list.blockSignals(True)
        self.session_list.set_sessions(sessions, self.current_id)
        self.session_list.blockSignals(False)

    def _session_selected(self) -> None:
        item = self.session_list.currentItem()
        if item:
            self.open_session(str(item.data(Qt.ItemDataRole.UserRole)))

    def new_session(self) -> None:
        try:
            session = self.service.create_session(self.mode)
        except ServiceError as exc:
            self._show_error(str(exc))
            return
        self.current_id = session["id"]
        self.refresh_sessions()
        if self.current_id is not None:
            self.open_session(self.current_id)
        self.composer.setFocus()

    def open_session(self, sid: str) -> None:
        try:
            session = self.service.session(sid)
        except ServiceError as exc:
            self._show_error(str(exc))
            return
        if session.get("mode", "agent") != self.mode:
            self.mode = session.get("mode", "agent")
            self.set_mode(self.mode)
        self.current_id = sid
        self.chat_title.setText(session["title"])
        self.title_bar.context.setText(session["title"])
        workspace = Path(session["workspace"])
        self.terminal.set_workspace(workspace)
        self.browser_panel.set_workspace(workspace)
        self.workspace_button.setText(str(workspace.name or workspace))
        self.transcript.render_display(session.get("display", []), workspace)
        for event in self.live_events.get(sid, []):
            self.transcript.apply_event(event)
        self._set_composer_home(not session.get("display")
                                and not self.live_events.get(sid)
                                and not session.get("running")
                                and not session.get("queued"))
        context = session.get("context", {})
        ceiling = context.get("compact_threshold") or context.get("window") or 1
        used = context.get("estimated_tokens") or context.get("last_prompt_tokens") or 0
        percent = min(100, round(100 * used / ceiling))
        self.context_bar.setValue(percent)
        self.context_percent.setText(f"{percent}%")
        tools = context.get("tools_available") or []
        breakdown = [
            f"Prompt: {int(used):,} / {int(ceiling):,} tokens before compaction",
            f"Profile: {context.get('tool_profile', 'auto')}",
            f"System: {int(context.get('system_tokens', 0)):,}",
            f"Tool schemas: {int(context.get('tool_schema_tokens', 0)):,}",
            f"Conversation: {int(context.get('conversation_tokens', 0)):,}",
        ]
        if tools:
            breakdown.append("Available tools: " + ", ".join(map(str, tools)))
        tooltip = "\n".join(breakdown)
        self.context_bar.setToolTip(tooltip)
        self.context_percent.setToolTip(tooltip)
        self._render_followups(session.get("pending_messages", []))
        self.render_session_list()
        self.refresh_right_panel()
        self._sync_running_ui()

    def _session_menu(self, point) -> None:
        item = self.session_list.itemAt(point)
        if item is None:
            return
        sid = str(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        meta = next((entry for entry in self.session_cache
                     if entry["id"] == sid), {})
        pin = menu.addAction("Unpin" if meta.get("pinned") else "Pin")
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        chosen = menu.exec(self.session_list.mapToGlobal(point))
        if chosen == pin:
            try:
                self.service.pin_session(sid, not bool(meta.get("pinned")))
                self.refresh_sessions()
            except ServiceError as exc:
                self._show_error(str(exc))
        elif chosen == rename:
            title, ok = QInputDialog.getText(self, "Rename conversation",
                                             "Conversation title:", text=item.text())
            if ok and title.strip():
                try:
                    self.service.rename_session(sid, title.strip())
                    self.refresh_sessions()
                    if sid == self.current_id:
                        self.chat_title.setText(title.strip())
                except ServiceError as exc:
                    self._show_error(str(exc))
        elif chosen == delete:
            answer = QMessageBox.question(
                self, "Delete conversation?",
                "This conversation and its saved history will be permanently removed.")
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    self.service.stop(sid)
                    QTimer.singleShot(250, lambda: self._delete_session(sid))
                except ServiceError as exc:
                    self._show_error(str(exc))

    def _delete_session(self, sid: str) -> None:
        try:
            self.service.delete_session(sid)
        except ServiceError as exc:
            self._show_error(str(exc))
            return
        if sid == self.current_id:
            self.current_id = None
            self.transcript.render_display([], Path.cwd())
            self._set_composer_home(True)
        self.refresh_sessions(open_latest=True)

    # ---------- generation ----------
    def send(self) -> None:
        text = self.composer.toPlainText().strip()
        if not text and not self.attachments:
            return
        if self.current_id is None:
            try:
                session = self.service.create_session(self.mode)
                self.current_id = session["id"]
            except ServiceError as exc:
                self._show_error(str(exc))
                return
        current = next((item for item in self.session_cache
                        if item["id"] == self.current_id), None)
        busy = bool(current and (current.get("running") or current.get("queued")))
        try:
            if busy:
                if self.attachments:
                    raise ServiceError("Attachments cannot be queued or steered yet")
                self.service.followup(
                    self.current_id, text, self.send_action.value())
            else:
                job = self.service.send(self.current_id, text, self.attachments)
                self.live_events[self.current_id] = []
                self.watch_job(job)
        except ServiceError as exc:
            self._show_error(str(exc))
            return
        self.composer.clear()
        for path in self.attachments:
            self._discard_pasted_temp(path)
        self.attachments.clear()
        self._render_attachment_chips()
        self._set_composer_home(False)
        self.refresh_sessions()

    def _use_suggestion(self, prompt: str) -> None:
        self.composer.setPlainText(prompt)
        self.composer.setFocus()

    def _redo_from(self, display_index: int, *, regenerate: bool) -> None:
        if not self.current_id:
            return
        current = next((item for item in self.session_cache
                        if item["id"] == self.current_id), {})
        if current.get("running") or current.get("queued"):
            self._show_error("Stop the active generation before reverting a message.")
            return
        verb = "Regenerate" if regenerate else "Revert"
        if QMessageBox.question(
                self, f"{verb} from this message?",
                "Later messages will be removed and checkpointed file changes "
                "will be restored.") != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.service.revert(self.current_id, display_index)
            workspace = self.service.workspace(self.current_id)
            paths = [str(workspace / item["name"])
                     for item in result.get("attachments", [])
                     if (workspace / item.get("name", "")).is_file()]
            if regenerate:
                job = self.service.send(self.current_id, result["text"], paths)
                self.live_events[self.current_id] = []
                self.watch_job(job)
            else:
                self.composer.setPlainText(result["text"])
                self.attachments = paths
                self._render_attachment_chips()
                self.composer.setFocus()
            self.open_session(self.current_id)
            self.refresh_sessions()
        except ServiceError as exc:
            self._show_error(str(exc))

    def _resize_composer(self) -> None:
        document_height = int(self.composer.document().size().height())
        self.composer.setFixedHeight(max(48, min(150, document_height + 16)))

    def _animate_panel(self, panel, show: bool, width: int,
                       minimum: int, maximum: int) -> None:
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        previous = getattr(panel, "_lmh_width_anim", None)
        if previous is not None:
            previous.stop()
        panel.setMinimumWidth(0)
        start = panel.width() if panel.isVisible() else 0
        if show:
            panel.setMaximumWidth(max(1, start))
            panel.show()
        animation = QPropertyAnimation(panel, b"maximumWidth", self)
        animation.setDuration(170)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(start)
        animation.setEndValue(width if show else 0)

        def finish() -> None:
            if not show:
                panel.hide()
            panel.setMinimumWidth(minimum)
            panel.setMaximumWidth(maximum)

        animation.finished.connect(finish)
        panel._lmh_width_anim = animation
        animation.start()

    def toggle_sidebar(self, visible: bool) -> None:
        self._animate_panel(self.sidebar, visible,
                            width=max(240, self.sidebar.width() or 270),
                            minimum=220, maximum=400)
        self.sidebar_toggle.setVisible(not visible)

    def toggle_right_panel(self, tab: int = 0) -> None:
        if self.mode == "chat":
            return
        if self.right_panel.isVisible() and self.right_tabs.currentIndex() == tab:
            self._animate_panel(self.right_panel, False,
                                width=0, minimum=300, maximum=600)
            return
        already_visible = self.right_panel.isVisible()
        self._set_right_index(tab)
        if not already_visible:
            self._animate_panel(self.right_panel, True,
                                width=340, minimum=300, maximum=600)
        self.refresh_right_panel()
        if tab == 4:
            self.terminal.input.setFocus()

    def export_conversation(self) -> None:
        if not self.current_id:
            return
        try:
            session = self.service.session(self.current_id)
        except ServiceError as exc:
            self._show_error(str(exc))
            return
        suggested = "".join(
            char if char.isalnum() or char in "-_ " else ""
            for char in session.get("title", "conversation")) or "conversation"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export conversation", f"{suggested}.md", "Markdown (*.md)")
        if not path:
            return
        lines = [f"# {session.get('title', 'Conversation')}", ""]
        for item in session.get("display", []):
            kind = item.get("t")
            if kind == "user":
                lines.extend(("## You", "", str(item.get("text", "")), ""))
            elif kind == "steer":
                lines.extend(("_Steer:_ " + str(item.get("text", "")), ""))
            elif kind == "text":
                lines.extend(("## Little Harness", "", str(item.get("text", "")), ""))
            elif kind == "tool":
                lines.extend((f"### Tool: {item.get('name', '')}", "", "```text",
                              str(item.get("result", "")), "```", ""))
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
        except OSError as exc:
            self._show_error(f"Could not export conversation: {exc}")

    def watch_job(self, job) -> None:
        if job.id in self.watchers:
            return
        watcher = JobWatcher(job)
        self.watchers[job.id] = watcher
        watcher.event_received.connect(
            lambda event, sid=job.session.id: self._on_job_event(sid, event))
        watcher.stream_finished.connect(
            lambda state, jid=job.id, sid=job.session.id:
            self._on_job_finished(jid, sid, state))
        watcher.start()

    def _on_job_event(self, sid: str, event: dict) -> None:
        self.live_events.setdefault(sid, []).append(event)
        if sid == self.current_id:
            self.transcript.apply_event(event)
            if event.get("type") == "session" and isinstance(event.get("data"), dict):
                self.chat_title.setText(event["data"].get("title", self.chat_title.text()))
            if (event.get("type") == "tool_call"
                    and isinstance(event.get("data"), dict)
                    and event["data"].get("name") == "browser"
                    and hasattr(self.browser_panel, "set_locked")
                    and not self.right_panel.isVisible()):
                # The live browser is about to do something — show it.
                self.toggle_right_panel(5)
        if event.get("type") in {"job", "queue", "session"}:
            self.refresh_sessions()

    def _on_job_finished(self, job_id: str, sid: str, _state: str) -> None:
        watcher = self.watchers.pop(job_id, None)
        if watcher:
            watcher.deleteLater()
        self.live_events.pop(sid, None)
        self.refresh_sessions()
        if sid == self.current_id:
            self.open_session(sid)
            self._notify("Task finished", self.chat_title.text())
        QTimer.singleShot(150, lambda: self._watch_next_job(sid))

    def _watch_next_job(self, sid: str) -> None:
        job = self.service.job(sid)
        if job is not None:
            self.live_events[sid] = []
            self.watch_job(job)

    def stop_generation(self) -> None:
        if not self.current_id:
            return
        try:
            result = self.service.stop(self.current_id)
            if result.get("requested"):
                self.transcript.show_activity("Stopping generation…")
                self.stop_button.setEnabled(False)
        except ServiceError as exc:
            self._show_error(str(exc))

    def _sync_running_ui(self) -> None:
        current = next((item for item in self.session_cache
                        if item["id"] == self.current_id), None)
        busy = bool(current and (current.get("running") or current.get("queued")))
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(True)
        self.send_action.setVisible(busy)
        self.composer_hint.setText(
            "Queue or steer the active turn" if busy
            else "Enter to send · Shift+Enter for a new line")
        if hasattr(self.browser_panel, "set_locked"):
            self.browser_panel.set_locked(busy)

    # ---------- attachments and followups ----------
    def choose_attachments(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach files")
        self._add_attachments(paths)

    def _add_attachments(self, paths: list[str]) -> None:
        oversized = []
        for path in paths:
            source = Path(path)
            try:
                if not source.is_file():
                    continue
                if source.stat().st_size > 50 * 1024 * 1024:
                    oversized.append(source.name)
                    continue
            except OSError:
                continue
            normalized = str(source.resolve())
            if normalized not in self.attachments:
                self.attachments.append(normalized)
        self._render_attachment_chips()
        if oversized:
            self._show_error("Attachments over 50 MB were skipped: "
                             + ", ".join(oversized))

    def _render_attachment_chips(self) -> None:
        while self.attachment_row.count():
            item = self.attachment_row.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        for path in self.attachments:
            button = QPushButton(f"{Path(path).name}  ×")
            if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    button.setIcon(QIcon(pixmap))
            button.clicked.connect(lambda _checked=False, p=path: self._remove_attachment(p))
            self.attachment_row.addWidget(button)
        self.attachment_row.addStretch(1)

    def _remove_attachment(self, path: str) -> None:
        if path in self.attachments:
            self.attachments.remove(path)
            self._discard_pasted_temp(path)
            self._render_attachment_chips()

    @staticmethod
    def _discard_pasted_temp(path: str) -> None:
        candidate = Path(path)
        if (candidate.parent == Path(tempfile.gettempdir())
                and candidate.name.startswith("little-harness-paste-")):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass

    def _render_followups(self, messages: list[dict]) -> None:
        self.followup_list.clear()
        for item in messages:
            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(0, 38))
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 2, 5, 2)
            label = QLabel(str(item.get("text", "")))
            label.setToolTip(str(item.get("text", "")))
            state = QLabel("Queued")
            state.setObjectName("sectionLabel")
            steer = IconButton("arrow_right", "Steer current turn", size=13)
            remove = IconButton("trash", "Remove queued message", size=13)
            message_id = str(item.get("id", ""))
            steer.clicked.connect(
                lambda _checked=False, mid=message_id: self._promote_followup(mid))
            remove.clicked.connect(
                lambda _checked=False, mid=message_id: self._delete_followup(mid))
            layout.addWidget(label, 1)
            layout.addWidget(state)
            layout.addWidget(steer)
            layout.addWidget(remove)
            self.followup_list.addItem(list_item)
            self.followup_list.setItemWidget(list_item, row)
        # Fit the list to its rows; a fixed 95px box around one queued
        # message reads as an empty panel.
        self.followup_list.setFixedHeight(min(95, len(messages) * 40 + 6))
        self.followup_list.setVisible(bool(messages))

    def _delete_followup(self, message_id: str) -> None:
        if not self.current_id:
            return
        try:
            self._render_followups(
                self.service.delete_followup(self.current_id, message_id))
            self.refresh_sessions()
        except ServiceError as exc:
            self._show_error(str(exc))

    def _promote_followup(self, message_id: str) -> None:
        if not self.current_id:
            return
        try:
            self._render_followups(
                self.service.promote_followup(self.current_id, message_id))
            self.refresh_sessions()
        except ServiceError as exc:
            self._show_error(str(exc))

    # ---------- workspace/files ----------
    def choose_workspace(self) -> None:
        if not self.current_id:
            self.new_session()
        if not self.current_id:
            return
        start = str(self.service.workspace(self.current_id))
        path = QFileDialog.getExistingDirectory(self, "Choose workspace", start)
        if path:
            try:
                self.service.set_workspace(self.current_id, path)
                if self.current_id is not None:
                    self.open_session(self.current_id)
            except ServiceError as exc:
                self._show_error(str(exc))

    def refresh_right_panel(self) -> None:
        if self.mode == "chat":
            return
        index = self.right_tabs.currentIndex()
        if index == 1:
            self.refresh_files()
        elif index == 2:
            try:
                self._skills_cache = list(self.service.skills())
            except ServiceError as exc:
                self._show_error(str(exc))
                return
            self._render_skill_cards()
        elif index == 3:
            try:
                content = self.service.memory()["content"].strip()
            except ServiceError as exc:
                self._show_error(str(exc))
                return
            self.memory_view.set_markdown(
                content or "*Nothing saved yet. Ask the assistant to "
                "remember something and it will appear here.*")

    def _render_skill_cards(self) -> None:
        query = self.skills_search.text().strip().casefold() \
            if hasattr(self, "skills_search") else ""
        self.skills_list.clear()
        shown = 0
        for skill in self._skills_cache:
            name = str(skill.get("name", ""))
            description = str(skill.get("description", ""))
            if query and query not in name.casefold() \
                    and query not in description.casefold():
                continue
            shown += 1
            card = QFrame()
            card.setObjectName("skillCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(10, 8, 10, 9)
            layout.setSpacing(2)
            title_row = QHBoxLayout()
            icon = QLabel()
            icon.setPixmap(svg_pixmap("skill", 13, "#d97757"))
            title = QLabel(name)
            title.setObjectName("skillName")
            title_row.addWidget(icon)
            title_row.addWidget(title, 1)
            layout.addLayout(title_row)
            hint = QLabel(description)
            hint.setObjectName("skillHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            self.skills_list.addItem(item)
            self.skills_list.setItemWidget(item, card)
        self.skills_count.setText(
            f"{shown} of {len(self._skills_cache)}" if query
            else f"{len(self._skills_cache)} installed")

    def refresh_files(self) -> None:
        if not self.current_id:
            return
        try:
            tree = self.service.file_tree(self.current_id)
        except ServiceError as exc:
            self._show_error(str(exc))
            return
        self.file_tree.clear()
        self.file_tree.setToolTip(tree.get("root", ""))

        def add(parent, nodes: list[dict]) -> None:
            for node in nodes:
                item = QTreeWidgetItem(parent, [node["name"]])
                item.setData(0, Qt.ItemDataRole.UserRole, node)
                if node.get("dir"):
                    add(item, node.get("children", []))
        add(self.file_tree, tree.get("tree", []))

    def open_file(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("dir") or not self.current_id:
            item.setExpanded(not item.isExpanded())
            return
        path = self.service.workspace(self.current_id) / data["path"]
        self.artifact_preview.preview(path)
        self._set_right_index(0)
        self.right_panel.show()

    def _file_menu(self, point) -> None:
        item = self.file_tree.itemAt(point)
        if item is None or not self.current_id:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        menu = QMenu(self)
        open_action = menu.addAction("Open")
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self.file_tree.viewport().mapToGlobal(point))
        if chosen == open_action:
            self.open_file(item)
        elif chosen == rename_action:
            name, ok = QInputDialog.getText(
                self, "Rename", "New name:", text=data.get("name", ""))
            if ok and name.strip():
                try:
                    self.service.rename_path(self.current_id, data["path"], name.strip())
                    self.refresh_files()
                except ServiceError as exc:
                    self._show_error(str(exc))
        elif chosen == delete_action:
            if QMessageBox.question(self, "Delete?", data.get("path", "")) \
                    == QMessageBox.StandardButton.Yes:
                try:
                    self.service.delete_path(self.current_id, data["path"])
                    self.refresh_files()
                except ServiceError as exc:
                    self._show_error(str(exc))

    def new_folder(self) -> None:
        if not self.current_id:
            return
        name, ok = QInputDialog.getText(self, "New folder", "Folder name:")
        if ok and name.strip():
            try:
                self.service.make_folder(self.current_id, name.strip())
                self.refresh_files()
            except ServiceError as exc:
                self._show_error(str(exc))

    # ---------- settings/models/theme ----------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.service, self)
        dialog.exec()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            # Text size / appearance settings apply immediately.
            apply_theme(app, current_theme())
        self._load_models_async()
        self.refresh_sessions()

    def _load_models_async(self) -> None:
        def load() -> None:
            try:
                self.models_ready.emit(self.service.models())
            except ServiceError as exc:
                # An offline model server must not greet the user with a
                # modal error box; the pill falls back to the configured ID.
                self.models_failed.emit(str(exc))
        threading.Thread(target=load, name="lmh-native-model-list", daemon=True).start()

    def _models_unavailable(self, error: str) -> None:
        selected = ""
        try:
            selected = str(self.service.settings().get("model", ""))
        except ServiceError:
            pass
        self.model_select.set_options(
            [(selected or "model", selected)], selected)
        self.model_select.setToolTip(
            "The model endpoint did not answer a model listing; using the "
            f"configured ID. {error}")

    def _populate_models(self, models: list[dict]) -> None:
        selected = self.service.settings().get("model", "")
        options = []
        for model in models:
            context = model.get("n_ctx")
            label = model["id"] + (f" · {int(context):,}" if context else "")
            options.append((label, model["id"]))
        if selected and not any(value == selected for _label, value in options):
            options.insert(0, (selected, selected))
        self.model_select.set_options(options, selected)

    def _model_changed(self, model: str) -> None:
        if not model:
            return
        try:
            self.service.save_settings({"model": str(model)})
        except ServiceError as exc:
            self._show_error(str(exc))

    def toggle_theme(self) -> None:
        name = "light" if current_theme() == "dark" else "dark"
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, name)

    # ---------- misc ----------
    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Little Harness", message)

    def _notify(self, title: str, message: str) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = QSystemTrayIcon(self.windowIcon(), self)
            tray.show()
            tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
            QTimer.singleShot(3500, tray.deleteLater)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.refresh_timer.stop()
        self.terminal.shutdown()
        for watcher in self.watchers.values():
            watcher.requestInterruption()
        self.service.close()
        event.accept()
