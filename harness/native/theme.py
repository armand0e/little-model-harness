"""Palette and stylesheet for the native Qt client."""
from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


LIGHT = {
    "bg": "#f4f3ee", "panel": "#fbfaf7", "raised": "#ffffff",
    "text": "#1f1e1b", "muted": "#75726a", "faint": "#a5a297",
    "border": "#e4e2da", "soft": "#edebe4", "accent": "#c96442",
    "accent_hover": "#b55638", "accent_soft": "#f4e3dc",
    "user": "#e8e6df", "code": "#f0efe9", "error": "#b3452f",
}
DARK = {
    "bg": "#262624", "panel": "#2e2e2b", "raised": "#383835",
    "text": "#e8e6e1", "muted": "#a3a094", "faint": "#6f6d64",
    "border": "#43423e", "soft": "#3a3936", "accent": "#d97757",
    "accent_hover": "#e08a6d", "accent_soft": "#453630",
    "user": "#3b3a36", "code": "#21211f", "error": "#e57862",
}


# Colors of the currently applied theme, for widgets that paint document
# content (markdown code blocks, tables) rather than using QSS.
CURRENT: dict[str, str] = dict(DARK)


def current_theme() -> str:
    return str(QSettings("LittleHarness", "LittleHarness").value(
        "theme", "dark"))


def apply_theme(app: QApplication, name: str) -> None:
    colors = dict(DARK if name == "dark" else LIGHT)
    available = set(QFontDatabase.families())
    candidates = (["Segoe UI Variable Text", "Segoe UI"] if sys.platform == "win32"
                  else ["SF Pro Text", ".AppleSystemUIFont"] if sys.platform == "darwin"
                  else ["Inter", "Noto Sans", "DejaVu Sans"])
    family = next((item for item in candidates if item in available), app.font().family())
    serif = next((item for item in ("Source Serif 4", "Georgia", "Noto Serif",
                                    "DejaVu Serif") if item in available), family)
    colors["ui_font"] = family
    colors["serif_font"] = serif
    CURRENT.clear()
    CURRENT.update(colors)
    app.setFont(QFont(family, 10))
    QSettings("LittleHarness", "LittleHarness").setValue("theme", name)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["raised"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["soft"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["panel"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    # Ported from the web client: links and placeholders must follow the
    # theme, not Qt's blue/gray defaults (unreadable on the dark palette).
    palette.setColor(QPalette.ColorRole.Link, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(colors["accent_hover"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["faint"]))
    palette.setColor(QPalette.ColorRole.Mid, QColor(colors["muted"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["raised"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    from .icons import retint_default_icons, set_default_icon_color
    set_default_icon_color(colors["muted"])
    app.setPalette(palette)
    app.setStyleSheet(STYLE.format(**colors))
    # Re-polish live widgets: swapping the app stylesheet at runtime leaves
    # some already-styled frames (e.g. the custom title bar) on the previous
    # theme until they are explicitly unpolished.
    for widget in app.allWidgets():
        app.style().unpolish(widget)
        app.style().polish(widget)
        widget.update()
    retint_default_icons()


STYLE = """
* {{ font-family: "{ui_font}"; font-size: 13px; color: {text}; }}
QWidget#root, QMainWindow {{ background: {bg}; }}
QFrame#titleBar {{ background: {panel}; border-bottom: 1px solid {border}; }}
QLabel#appName {{ font-size: 12px; font-weight: 650; }}
QLabel#windowContext {{ color: {faint}; font-size: 11px; }}
QLabel#brand {{ font-family: "{serif_font}"; font-size: 17px; font-weight: 600; }}
QLabel#sectionLabel {{ color: {faint}; font-size: 10px; font-weight: 700; }}
QLabel#dialogTitle {{ font-family: "{serif_font}"; font-size: 22px; font-weight: 650; }}
QLabel#chatTitle {{ font-size: 14px; font-weight: 600; }}
QLabel#contextLabel {{ color: {muted}; font-size: 11px; }}
QProgressBar {{ background: {soft}; border: none; border-radius: 2px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 2px; }}
QFrame#sidebar {{ background: {panel}; border-right: 1px solid {border}; }}
QFrame#topBar {{ background: {bg}; border-bottom: 1px solid {border}; }}
QFrame#composerFrame {{ background: {raised}; border: 1px solid {border}; border-radius: 22px; }}
QFrame#composerFrame QPlainTextEdit {{ background: transparent; border: none; padding: 3px; }}
QFrame#rightPanel {{ background: {panel}; border-left: 1px solid {border}; }}
QPushButton, QToolButton {{ border: none; border-radius: 7px; padding: 6px 9px; background: transparent; }}
QPushButton:hover, QToolButton:hover {{ background: {soft}; }}
QPushButton#primary {{ background: {accent}; color: white; font-weight: 700; padding: 9px 13px; }}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#navButton {{ text-align: left; color: {muted}; padding: 7px 10px; }}
QPushButton#navButton:checked {{ background: {user}; color: {text}; font-weight: 700; }}
QPushButton#footerButton {{ border: 1px solid {border}; color: {muted}; padding: 7px; }}
QPushButton#workspaceChip {{ border: 1px solid {border}; border-radius: 13px; background: {panel}; color: {muted}; padding: 4px 11px; font-size: 12px; }}
QPushButton#attachButton {{ border: 1px solid {border}; border-radius: 9px; padding: 6px; }}
QPushButton#stopButton {{ background: {accent}; border-radius: 10px; padding: 8px; }}
QPushButton#iconButton {{ padding: 6px; }}
QPushButton#windowClose:hover {{ background: #c42b1c; color: white; border-radius: 0; }}
QPushButton#windowControl {{ border-radius: 0; padding: 0; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
  background: {raised}; border: 1px solid {border}; border-radius: 8px; padding: 7px 9px;
  selection-background-color: {accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {accent}; }}
QPlainTextEdit {{ selection-background-color: {accent}; }}
QFrame#selectButton {{ background: {panel}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#selectButton:hover {{ border-color: {faint}; }}
QLabel#selectLabel {{ color: {muted}; font-size: 12px; }}
QMenu {{ background: {raised}; border: 1px solid {border}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 28px 7px 10px; border-radius: 7px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {text}; }}
QMenu::indicator {{ width: 0; height: 0; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QListWidget#sessionList {{ background: transparent; border: none; outline: none; }}
QListWidget#sessionList::item {{ border-radius: 8px; padding: 8px 9px; color: {muted}; }}
QListWidget#sessionList::item:hover {{ background: {soft}; color: {text}; }}
QListWidget#sessionList::item:selected {{ background: {user}; color: {text}; }}
QFrame#userBubble {{ background: {user}; border-radius: 14px; max-width: 650px; }}
QFrame#steerBubble {{ background: {accent_soft}; border: 1px solid {accent}; border-radius: 11px; max-width: 650px; }}
QFrame#reasoningCard {{ border-left: 2px solid {border}; background: transparent; }}
QTextBrowser#markdownView {{ background: transparent; border: none; }}
QScrollArea#transcript, QWidget#transcriptViewport, QWidget#transcriptCanvas {{ background: {bg}; }}
QFrame#welcome {{ background: {bg}; }}
QLabel#welcomeTitle {{ font-family: "{serif_font}"; font-size: 30px; font-weight: 500; color: {text}; }}
QLabel#welcomeSubtitle {{ color: {muted}; margin-bottom: 20px; }}
QFrame#suggestion {{ background: {panel}; border: 1px solid {border}; border-radius: 12px; min-height: 66px; }}
QFrame#suggestion:hover {{ border-color: {accent}; background: {raised}; }}
QLabel#suggestionTitle {{ font-size: 13px; font-weight: 650; }}
QLabel#suggestionDetail {{ color: {muted}; font-size: 12px; }}
QFrame#toolCard {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
QFrame#toolCard QPlainTextEdit {{ background: {code}; border: 1px solid {border}; border-radius: 8px; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }}
QTextBrowser#diffView {{ background: {code}; border: 1px solid {border}; border-radius: 8px; padding: 4px; }}
QToolButton#toolToggle {{ text-align: left; font-family: "Cascadia Code", monospace; }}
QLabel#notice {{ color: {muted}; background: {soft}; border-radius: 7px; padding: 6px 9px; }}
QLabel#errorNotice {{ color: {error}; background: {soft}; border-radius: 7px; padding: 7px 9px; }}
QLabel#activity {{ color: {muted}; font-style: italic; }}
QFrame#welcomeHost {{ background: {bg}; }}
QPushButton#promptPill {{ border: 1px solid {border}; border-radius: 16px; background: {panel}; color: {muted}; padding: 7px 14px; font-size: 12px; }}
QPushButton#promptPill:hover {{ border-color: {accent}; color: {text}; background: {raised}; }}
QFrame#composerModelSelect {{ background: transparent; border: none; }}
QFrame#composerModelSelect:hover {{ background: {soft}; border-radius: 9px; }}
QPushButton#attachmentTile {{ border: 1px solid {border}; background: {panel}; text-align: left; }}
QLabel#settingsHealth {{ background: {code}; color: {muted}; border-radius: 9px; padding: 10px; }}
QLabel#settingsError {{ background: {accent_soft}; color: {error}; border-radius: 9px; padding: 10px; }}
QTreeWidget {{ background: transparent; border: none; }}
QLabel#terminalLocation {{ color: {faint}; font-size: 10px; }}
QPlainTextEdit#terminalOutput, QPlainTextEdit#browserState {{ background: {code}; border: 1px solid {border}; border-radius: 8px; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }}
QLineEdit#terminalInput {{ background: {code}; font-family: "Cascadia Mono", "Consolas", monospace; }}
QLabel#browserImage {{ background: {code}; border: 1px solid {border}; border-radius: 9px; color: {faint}; }}
QScrollArea {{ background: {bg}; border: none; }}
QScrollBar:vertical {{ width: 9px; background: transparent; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 9px; background: transparent; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QLabel#composerHint {{ color: {faint}; font-size: 11px; }}
QToolTip {{ background: {raised}; color: {text}; border: 1px solid {border}; padding: 4px 7px; }}
"""
