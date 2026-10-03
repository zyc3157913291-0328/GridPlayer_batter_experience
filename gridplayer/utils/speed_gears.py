# MOD: new file - playback speed gears, shared by the overlay control and the
# long-press gesture. Pure functions, no Qt, so the arithmetic is testable on
# its own.
"""Playback speed gears and the long-press gesture maths.

The original player changes speed in 0.1 steps from the keyboard (C / X / Z,
MIN_RATE 0.2 to MAX_RATE 12). That stays as it is; these are the discrete gears
the overlay control and the hold-and-drag gesture use.
"""

import math

GEARS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)

# Written as an escape rather than the literal character: it is easy to mistake
# for the letter x in source, and ruff flags it for exactly that reason
# (RUF001). The label really is a multiplication sign.
MULTIPLICATION_SIGN = "\u00d7"

DEFAULT_GEAR = 2.0

# The gesture spans this fraction of the video area's width, laid evenly over
# the gaps between gears. The press lands on DEFAULT_GEAR, which is two gears
# right of 1.25 - the middle of the table - so travelling left reaches five
# gears (down to 0.5) while travelling right only reaches two (up to 3.0). The
# asymmetry is deliberate: there is more room below 2x than above it.
GESTURE_AREA_FRACTION = 1 / 5

# A plain click pauses on release, so this only has to be long enough not to
# catch a deliberately slow click.
LONG_PRESS_MS = 500


def default_index() -> int:
    return GEARS.index(DEFAULT_GEAR)


def step_px(area_width: float) -> float:
    """Width of one gear step, in the same units as area_width."""
    return (area_width * GESTURE_AREA_FRACTION) / (len(GEARS) - 1)


def gear_index_for_offset(dx, area_width, base_index=None) -> int:
    """Which gear an offset of dx from the press point lands on.

    Rounding is round-half-up rather than Python's round(), which is
    round-half-to-even: with the builtin, a step boundary at exactly 1.5 and one
    at 2.5 would both land on 2, so some gears would be a whole step wide and
    others half a step. Each gear gets exactly one step here, and the press
    point itself is exactly DEFAULT_GEAR.
    """
    if base_index is None:
        base_index = default_index()

    step = step_px(area_width)
    if step <= 0:
        return base_index

    offset = math.floor(dx / step + 0.5)

    return max(0, min(len(GEARS) - 1, base_index + offset))


def gear_after_drag(dx, area_width, gear_index):
    """The gear after dragging dx from the reference point, and steps taken.

    The reference point moves with the mouse rather than staying at the press
    point: whole steps are taken off dx, and the caller moves its reference by
    steps * step_px. That is what makes the boundary follow the drag - backing
    off from the top gear takes a full step before a gear drops - and it means
    reaching the edge of the screen no longer caps how far the drag can go.

    Steps are reported even when the gear is already at an end, so a clamped
    drag still carries the reference along with the mouse.
    """
    step = step_px(area_width)
    if step <= 0:
        return gear_index, 0

    steps = math.floor(dx / step + 0.5)

    if steps == 0:
        return gear_index, 0

    new_index = max(0, min(len(GEARS) - 1, gear_index + steps))

    return new_index, steps


def rate_for_index(index: int) -> float:
    return GEARS[max(0, min(len(GEARS) - 1, index))]


def index_for_rate(rate: float):
    """The gear a rate corresponds to, or None when it is not a gear.

    The keyboard's 0.1 steps leave values like 1.1 behind, and the menu has to
    show that none of the gears is selected rather than silently claiming one.
    """
    for index, gear in enumerate(GEARS):
        if abs(gear - rate) < 1e-9:
            return index

    return None


def format_rate(rate: float) -> str:
    """Text for the control and the gesture indicator, e.g. the 1x label.

    Two decimals is enough for both the gears and the 0.1 steps the keyboard
    still produces, and trailing zeros come off integers so 1x does not read as
    1.00x.
    """
    value = round(rate, 2)

    if value == int(value):
        return f"{MULTIPLICATION_SIGN}{int(value)}"

    return f"{MULTIPLICATION_SIGN}{value:g}"
