"""Small SVG icon system shared by every native platform.

The desktop client intentionally does not use emoji or font glyphs for UI
chrome: their shape changes between Windows, Linux, and macOS.  These icons
are rendered from one SVG path set by Qt instead.
"""
from __future__ import annotations

import weakref
from html import escape

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Default chrome-icon color follows the active theme's muted text color.
# Widgets that accept the default are recorded so a theme switch can retint
# them in place; explicit colors (accents, white-on-primary) are kept as-is.
_DEFAULT_COLOR = "#a3a094"
_REGISTRY: "weakref.WeakKeyDictionary[object, tuple[str, int, str | None]]" = (
    weakref.WeakKeyDictionary())


def set_default_icon_color(color: str) -> None:
    global _DEFAULT_COLOR
    _DEFAULT_COLOR = color


def retint_default_icons() -> None:
    """Re-render every registered default-colored icon in the new theme."""
    for widget, (name, size, explicit) in list(_REGISTRY.items()):
        if explicit is not None:
            continue
        try:
            widget.setIcon(svg_icon(name, size, _DEFAULT_COLOR))
        except RuntimeError:
            pass  # underlying C++ widget already deleted


PATHS = {
    "mark": '<path d="M12 2 19 12 12 22 5 12Z" fill="{color}" stroke="none"/>',
    "code": '<path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/>',
    "chat": '<path d="M20 15a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-2-3V7a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3Z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "chevron_down": '<path d="m7 9 5 5 5-5"/>',
    "chevron_left": '<path d="m15 18-6-6 6-6"/>',
    "paperclip": '<path d="m21.4 11.6-8.9 8.9a6 6 0 0 1-8.5-8.5l9.6-9.6a4 4 0 0 1 5.7 5.7l-9.6 9.6a2 2 0 0 1-2.8-2.8l8.9-8.9"/>',
    "arrow_up": '<path d="m5 12 7-7 7 7M12 5v14"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1" fill="{color}" stroke="none"/>',
    "folder": '<path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "panels": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
    "sparkle": '<path d="m12 3 1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6ZM5 16l.8 2.2L8 19l-2.2.8L5 22l-.8-2.2L2 19l2.2-.8Z"/>',
    "download": '<path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
    "moon": '<path d="M20.5 14.2A8 8 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "refresh": '<path d="M20 6v5h-5M4 18v-5h5"/><path d="M6.1 9a7 7 0 0 1 11.4-2.6L20 11M4 13l2.5 4.6A7 7 0 0 0 17.9 15"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/>',
    "edit": '<path d="m14 4 6 6L9 21H3v-6ZM12 6l6 6"/>',
    "pin": '<path d="m12 17-5 5M15 3l6 6-4 2-5 5-4-4 5-5Z"/>',
    "undo": '<path d="M9 7 4 12l5 5M4 12h10a6 6 0 0 1 6 6"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "more": '<circle cx="5" cy="12" r="1.2" fill="{color}" stroke="none"/><circle cx="12" cy="12" r="1.2" fill="{color}" stroke="none"/><circle cx="19" cy="12" r="1.2" fill="{color}" stroke="none"/>',
    "tool": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "skill": '<path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5ZM18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8Z"/>',
    "file": '<path d="M6 2h8l4 4v16H6Z"/><path d="M14 2v6h6"/>',
    "terminal": '<path d="m5 7 5 5-5 5M12 17h7"/>',
    "browser": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "research": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.4-4.4M8 11h6M11 8v6"/>',
    "arrow_left": '<path d="m15 18-6-6 6-6"/>',
    "arrow_right": '<path d="m9 18 6-6-6-6"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m21 15-5-5L5 20"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "minimize": '<path d="M6 12h12"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14"/>',
}


def svg_bytes(name: str, color: str | None = None) -> QByteArray:
    color = color or _DEFAULT_COLOR
    body = PATHS[name].format(color=escape(color, quote=True))
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{escape(color, quote=True)}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
    return QByteArray(source.encode("utf-8"))


def svg_pixmap(name: str, size: int = 18, color: str | None = None) -> QPixmap:
    renderer = QSvgRenderer(svg_bytes(name, color))
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size * ratio, size * ratio))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def svg_icon(name: str, size: int = 18, color: str | None = None) -> QIcon:
    icon = QIcon(svg_pixmap(name, size, color))
    icon.addPixmap(svg_pixmap(name, size, color), QIcon.Mode.Active)
    return icon


def set_svg_icon(widget, name: str, size: int = 18,
                 color: str | None = None) -> None:
    widget.setIcon(svg_icon(name, size, color))
    widget.setIconSize(QSize(size, size))
    try:
        _REGISTRY[widget] = (name, size, color)
    except TypeError:
        pass  # non-weakref-able widget: it simply keeps its current tint
