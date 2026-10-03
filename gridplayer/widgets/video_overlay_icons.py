import math

from PyQt5.QtCore import QPointF, QRect, Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen


def draw_volume_on(rect, painter, color_fg, color_bg):
    draw_volume_off(rect, painter, color_fg, color_bg)

    painter.fillRect(
        rect.x() + 5 + 6 + 3, rect.y() + 6, 4, rect.height() - 12, color_fg
    )


def draw_volume_off(rect, painter, color_fg, color_bg):
    painter.setRenderHint(QPainter.Antialiasing, True)

    path = QPainterPath()

    path.moveTo(rect.x() + 5, round(rect.height() / 2) - 3)

    path.lineTo(rect.x() + 5 + 3, round(rect.height() / 2) - 3)
    path.lineTo(rect.x() + 5 + 6, 4)
    path.lineTo(rect.x() + 5 + 6, rect.height() - 4)
    path.lineTo(rect.x() + 5 + 3, round(rect.height() / 2) + 3)
    path.lineTo(rect.x() + 5, round(rect.height() / 2) + 3)

    path.lineTo(rect.x() + 5, round(rect.height() / 2) - 3)

    painter.setPen(Qt.NoPen)
    painter.fillPath(path, QBrush(color_fg))


def draw_play(rect, painter, color_fg, color_bg):
    painter.setRenderHint(QPainter.Antialiasing, True)

    path = QPainterPath()

    path.moveTo(rect.x() + 5, rect.y() + 4)
    path.lineTo(rect.width() - 5, round(rect.height() / 2))
    path.lineTo(rect.x() + 5, rect.height() - 4)
    path.lineTo(rect.x() + 5, rect.y() + 4)

    painter.setPen(Qt.NoPen)
    painter.fillPath(path, QBrush(color_fg))


def draw_pause(rect, painter, color_fg, color_bg):
    painter.fillRect(rect.x() + 5, rect.y() + 4, 5, rect.height() - 8, color_fg)
    painter.fillRect(rect.width() - 5 - 5, rect.y() + 4, 5, rect.height() - 8, color_fg)


def draw_cross(rect, painter, color_fg, color_bg):
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(color_fg, 4))

    line_len = round(math.sqrt((rect.width() - 10) ** 2 + (rect.width() - 10) ** 2))

    painter.drawLine(
        rect.x() + 5,
        rect.y() + 5,
        rect.x() + line_len,
        rect.y() + line_len,
    )
    painter.drawLine(
        rect.x() + line_len,
        rect.y() + 5,
        rect.x() + 5,
        rect.y() + line_len,
    )


def draw_spin_circle(
    rect: QRect, painter: QPainter, color_fg: QColor, color_bg: QColor, spin: int
):
    painter.setRenderHint(QPainter.Antialiasing, True)

    rect_spin = rect.adjusted(5, 5, -5, -5)

    painter.setPen(QPen(color_fg, 4))
    painter.drawArc(rect_spin, 0, 16 * 360)

    painter.setPen(QPen(color_bg, 2))
    painter.drawArc(rect_spin, -spin * 16, 16 * 90)


# --- MOD: repeat-mode icons + the playlist panel's hamburger -----------------

CW_START_DEG = 90.0  # start the clockwise sweep at the top of the circle
ARROW_HEAD = 4.0


def _arc_point(box, angle_deg):
    """Point on the ellipse inscribed in `box`, Qt's angle convention."""
    rad = math.radians(angle_deg)

    return QPointF(
        box.center().x() + (box.width() / 2) * math.cos(rad),
        box.center().y() - (box.height() / 2) * math.sin(rad),
    )


def _fill_head(painter, tip, dx, dy, color_fg, size=ARROW_HEAD):
    """Filled triangle at `tip`, pointing along the unit vector (dx, dy)."""
    perp_x, perp_y = -dy, dx

    head = QPainterPath()
    head.moveTo(tip.x() + dx * size, tip.y() + dy * size)
    head.lineTo(tip.x() + perp_x * size * 0.8, tip.y() + perp_y * size * 0.8)
    head.lineTo(tip.x() - perp_x * size * 0.8, tip.y() - perp_y * size * 0.8)
    head.closeSubpath()

    painter.setPen(Qt.NoPen)
    painter.fillPath(head, QBrush(color_fg))


def _draw_cw_arrow(rect, painter, color_fg, gap_deg=80):
    """Clockwise circular arrow - the base of the list / single / pause icons.

    Qt's drawArc() treats a *positive* span as counter-clockwise on screen, so
    the clockwise sweep this icon needs is expressed as a negative span.
    """
    painter.setRenderHint(QPainter.Antialiasing, True)

    box = rect.adjusted(5, 5, -5, -5)
    sweep = 360.0 - gap_deg

    painter.setPen(QPen(color_fg, 2, Qt.SolidLine, Qt.RoundCap))
    painter.drawArc(box, int(CW_START_DEG * 16), int(-sweep * 16))

    end_deg = CW_START_DEG - sweep  # where the sweep stops, next to the gap
    tip = _arc_point(box, end_deg)

    rad = math.radians(end_deg)
    # travelling clockwise means decreasing angle, i.e. minus the CCW tangent
    _fill_head(painter, tip, math.sin(rad), math.cos(rad), color_fg)


def _badge_rect(rect, side=11):
    box = rect.adjusted(5, 5, -5, -5)

    return QRect(
        round(box.center().x() - side / 2),
        round(box.center().y() - side / 2),
        side,
        side,
    )


def _clear_badge(rect, painter, color_bg):
    """Punch a background-coloured hole so the arrow does not cross the glyph."""
    patch = _badge_rect(rect)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color_bg))
    painter.drawEllipse(patch)
    painter.setBrush(Qt.NoBrush)

    return patch


def draw_repeat_list(rect, painter, color_fg, color_bg):
    """List loop: a clockwise arrow."""
    _draw_cw_arrow(rect, painter, color_fg)


def draw_repeat_single(rect, painter, color_fg, color_bg):
    """Single-file loop: a clockwise arrow with a 1 inside it."""
    _draw_cw_arrow(rect, painter, color_fg)

    patch = _clear_badge(rect, painter, color_bg)

    font = painter.font()
    font.setPixelSize(9)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(color_fg, 1))
    painter.drawText(patch, Qt.AlignCenter, "1")


def draw_repeat_pause(rect, painter, color_fg, color_bg):
    """Play once then stop: a clockwise arrow with a pause glyph inside it."""
    _draw_cw_arrow(rect, painter, color_fg)

    patch = _clear_badge(rect, painter, color_bg)

    bar_w, bar_h = 3, 7
    top = patch.center().y() - bar_h // 2

    painter.setPen(Qt.NoPen)
    painter.fillRect(patch.center().x() - bar_w - 1, top, bar_w, bar_h, color_fg)
    painter.fillRect(patch.center().x() + 1, top, bar_w, bar_h, color_fg)


def draw_repeat_shuffle(rect, painter, color_fg, color_bg):
    """Shuffle: two arrows crossing from left to right."""
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(color_fg, 2, Qt.SolidLine, Qt.RoundCap))

    box = rect.adjusted(5, 5, -5, -5)
    left, right = box.left(), box.right()
    top, bottom = box.top() + 2, box.bottom() - 2

    painter.drawLine(left, top, right - 3, bottom - 2)
    painter.drawLine(left, bottom, right - 3, top + 2)

    _fill_head(painter, QPointF(right, bottom), 0.89, 0.45, color_fg, 3.5)
    _fill_head(painter, QPointF(right, top), 0.89, -0.45, color_fg, 3.5)


def draw_menu(rect, painter, color_fg, color_bg):
    """Three horizontal bars - the playlist panel toggle."""
    painter.setRenderHint(QPainter.Antialiasing, False)

    bar_h = 2
    left = rect.x() + 5
    width = rect.width() - 10
    first_top = rect.y() + round(rect.height() / 2) - 6

    for i in range(3):
        painter.fillRect(left, first_top + i * 5, width, bar_h, color_fg)
