"""The application's own icon set: two-tone line icons drawn as SVG.

Every icon lives on a 24 x 24 grid with round 1.7 px strokes. `C` is replaced by the
main colour and `A` by the accent colour, so the whole set follows the theme and the
disabled state is just another pair of colours.
"""

from functools import cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

MAIN = "#334155"
ACCENT = "#2563eb"
DISABLED = "#cbd5e1"
SIZES = (20, 40, 60)
"""Pixel sizes rendered for normal, 2x and 3x screens."""

# A Lorentzian line from a baseline at y = 19; reused by the NMR-specific icons.
_PEAK = "c5 0 6.5-1 7.5-6 .6-3 1-8 1.5-8s.9 5 1.5 8c1 5 2.5 6 7.5 6"
_SMALL_PEAK = "c3.5 0 4.5-1 5.2-5 .5-3 .8-6 1.3-6s.8 3 1.3 6c.7 4 1.7 5 5.2 5"
_FOLDER = "M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
_SHEET = "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"
_DISK = "M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"
_INTEGRAL = "c-2.5-1.5-4 0-4 3v10c0 3-1.5 4.5-4 3"
_FRAME = '<rect x="3" y="4" width="18" height="16" rx="2"/>'

ICONS = {
    # file
    "new": f'<path d="{_SHEET}"/><path d="M14 3v5h5"/><path stroke="A" d="M12 12v6M9 15h6"/>',
    "open": f'<path d="{_FOLDER}"/><path stroke="A" d="M3 11.5h18"/>',
    "import": f'<path d="{_FOLDER}"/><path stroke="A" d="M12 11v6M9.5 14.5 12 17l2.5-2.5"/>',
    "save": f'<path d="{_DISK}"/><path d="M7 3v5h8V3"/><path stroke="A" d="M7 21v-7h10v7"/>',
    "save-as": (
        f'<path d="{_DISK}"/><path d="M7 3v5h8V3"/>'
        '<path stroke="A" d="M9 18.5l.8-3 5.4-5.4 2.2 2.2-5.4 5.4z"/>'
    ),
    "export": (
        '<path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>'
        '<path stroke="A" d="M12 15V4M8 8l4-4 4 4"/>'
    ),
    "quit": (
        '<path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4"/>'
        '<path stroke="A" d="M15 8l4 4-4 4M19 12H9"/>'
    ),
    # edit
    "undo": '<path stroke="A" d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "redo": '<path stroke="A" d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>',
    "copy": (
        '<rect stroke="A" x="8" y="8" width="12" height="12" rx="2"/>'
        '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'
    ),
    "remove": (
        '<path d="M4 7h16M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>'
        '<path stroke="A" d="M10 11v6M14 11v6"/>'
    ),
    # tools and view
    "select": '<path d="M5 3l5.5 16 2.3-6.7L19.5 10z"/>',
    "zoom": (
        '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.5-4.5"/>'
        '<path stroke="A" d="M11 8v6M8 11h6"/>'
    ),
    "zoom-out": (
        '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.5-4.5"/><path stroke="A" d="M8 11h6"/>'
    ),
    "pan": (
        '<path d="M12 3v18M3 12h18"/>'
        '<path stroke="A" d="M9.5 5.5 12 3l2.5 2.5M9.5 18.5 12 21l2.5-2.5'
        'M5.5 9.5 3 12l2.5 2.5M18.5 9.5 21 12l-2.5 2.5"/>'
    ),
    "crosshair": (
        '<circle cx="12" cy="12" r="6.5"/><path stroke="A" d="M12 2v6M12 16v6M2 12h6M16 12h6"/>'
    ),
    "full": (
        '<path d="M4 5v14M20 5v14"/>'
        '<path stroke="A" d="M8 12h8M10.5 9.5 8 12l2.5 2.5M13.5 9.5 16 12l-2.5 2.5"/>'
    ),
    "fit-height": (
        '<path d="M5 4h14M5 20h14"/>'
        '<path stroke="A" d="M12 8v8M9.5 10.5 12 8l2.5 2.5M9.5 13.5 12 16l2.5-2.5"/>'
    ),
    "intensity-up": (
        f'<path d="M2 19{_SMALL_PEAK}"/><path stroke="A" d="M19.5 18V7M16.5 10l3-3 3 3"/>'
    ),
    "intensity-down": (
        f'<path d="M2 19{_SMALL_PEAK}"/><path stroke="A" d="M19.5 6v11M16.5 14l3 3 3-3"/>'
    ),
    "previous": '<path stroke="A" d="M6 15l6-6 6 6"/>',
    "next": '<path stroke="A" d="M6 9l6 6 6-6"/>',
    "panel-left": f'{_FRAME}<path stroke="A" d="M9 4v16"/>',
    "panel-right": f'{_FRAME}<path stroke="A" d="M15 4v16"/>',
    "panel-table": f'{_FRAME}<path stroke="A" d="M3 10h18M3 15h18M10 10v10"/>',
    # processing and analysis
    "fid": (
        '<path stroke="A" d="M2 12c.8-9 1.7-9 2.5 0s1.700 7 2.500 0 1.600-5.500 2.400 0 '
        "1.500 4.200 2.200 0 1.300-3.200 2-0 1.200 2.400 1.800 0 1 -1.700 1.600 0 "
        '.900 1.100 1.400 0"/><path d="M19 12h3"/>'
    ),
    "auto-phase": f'<path d="M2 19{_SMALL_PEAK}"/><path stroke="A" d="M19 3v6M16 6h6"/>',
    "phase": (
        f'<path d="M2 19{_SMALL_PEAK}"/>'
        '<path stroke="A" d="M19.5 5v12M17 7.5l2.5-2.5 2.5 2.5M17 14.5l2.5 2.5 2.5-2.5"/>'
    ),
    "reference": (
        f'<path d="M3 19{_PEAK}"/><path stroke="A" stroke-dasharray="1.5 3" d="M12 2v20"/>'
    ),
    "baseline": (
        '<path d="M3 7c3 5 4.500 6.500 6.500 6.500l1.300-7 1.300 7c3 0 5.400-1.500 8.900-5.500"/>'
        '<path stroke="A" d="M3 19h18"/>'
    ),
    "integrate": f'<path d="M4 20h3M17 4h3"/><path stroke="A" d="M15 4{_INTEGRAL}"/>',
    "clear-integrals": (
        f'<path d="M12 4{_INTEGRAL}"/><path stroke="A" d="M15 14l5 5M20 14l-5 5"/>'
    ),
    "multiplet": (
        '<path d="M3 20h18"/>'
        '<path stroke="A" d="M7 20v-6M12 20V6M17 20v-6"/>'
        '<path d="M7 10V8h10v2M12 8V4"/>'
    ),
    "clear-multiplets": (
        '<path d="M3 20h9M5 20v-5M9 20V8"/><path stroke="A" d="M15 14l5 5M20 14l-5 5"/>'
    ),
    "report": (
        '<rect x="5" y="4" width="14" height="17" rx="2"/>'
        '<path d="M9 4V3h6v1"/>'
        '<path stroke="A" d="M8.5 10h7M8.5 13.5h7M8.5 17h4"/>'
    ),
    # help
    "shortcuts": (
        '<rect x="2" y="6" width="20" height="12" rx="2"/>'
        '<path stroke="A" d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7.500 14h9"/>'
    ),
    "about": '<circle cx="12" cy="12" r="9"/><path stroke="A" d="M12 11v6M12 7.500h.01"/>',
    # widget parts used by the style sheet
    "chevron-down": '<path d="M7 10l5 5 5-5"/>',
    "check": '<path stroke="#ffffff" stroke-width="3" d="M5 12.500l4.500 4.500L19 7.500"/>',
}


def _svg(name: str, main: str, accent: str) -> QByteArray:
    body = ICONS[name].replace('stroke="A"', f'stroke="{accent}"')
    return QByteArray(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{main}" stroke-width="1.7" stroke-linecap="round" '
            f'stroke-linejoin="round">{body}</svg>'
        ).encode()
    )


def pixmap(name: str, size: int, main: str = MAIN, accent: str = ACCENT) -> QPixmap:
    """Render an icon to a square pixmap of `size` device pixels."""
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(_svg(name, main, accent)).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return result


@cache
def icon(name: str) -> QIcon:
    """The themed icon `name`, with crisp versions for high-resolution screens."""
    result = QIcon()
    for scale, size in enumerate(SIZES, start=1):
        for mode, colours in (
            (QIcon.Mode.Normal, (MAIN, ACCENT)),
            (QIcon.Mode.Disabled, (DISABLED, DISABLED)),
        ):
            rendered = pixmap(name, size, *colours)
            rendered.setDevicePixelRatio(scale)
            result.addPixmap(rendered, mode)
    return result
