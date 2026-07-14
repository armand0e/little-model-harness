"""Qt application bootstrap."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import __version__
from .service import HarnessService
from .theme import apply_theme, current_theme
from .window import MainWindow


def _icon_path() -> Path:
    root = (Path(getattr(sys, "_MEIPASS")) if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[2])
    return root / "packaging" / "littleharness.png"


def run_native() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QCoreApplication.setOrganizationName("LittleHarness")
    QCoreApplication.setApplicationName("LittleHarness")
    QCoreApplication.setApplicationVersion(__version__)
    app = QApplication.instance() or QApplication(sys.argv)
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(True)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    icon_path = _icon_path()
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_theme(app, current_theme())
    service = HarnessService()
    service.start()
    window = MainWindow(service)
    window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()


def smoke_native() -> int:
    """Construct and exercise the packaged native shell without interaction."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QCoreApplication.setOrganizationName("LittleHarness")
    QCoreApplication.setApplicationName("LittleHarness")
    app = QApplication.instance() or QApplication(sys.argv)
    assert isinstance(app, QApplication)
    apply_theme(app, "dark")
    service = HarnessService()
    service.start()
    window = MainWindow(service)
    window.show()
    if window.centralWidget() is None or window.transcript is None:
        service.close()
        return 2
    QTimer.singleShot(350, window.close)
    QTimer.singleShot(2000, app.quit)
    return app.exec()
