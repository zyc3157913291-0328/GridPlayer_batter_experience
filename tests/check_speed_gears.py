"""MOD: the playback speed gears and the hold-and-drag gesture arithmetic.

Everything here is pure, so the properties that matter - the press point is
exactly 2x, travelling left reaches further than travelling right, a rate that
is not a gear is reported as such instead of being rounded onto one - are
asserted as numbers rather than judged by dragging on screen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("speed gears")

from gridplayer.utils.speed_gears import (
    DEFAULT_GEAR,
    GEARS,
    LONG_PRESS_MS,
    default_index,
    format_rate,
    gear_after_drag,
    gear_index_for_offset,
    index_for_rate,
    rate_for_index,
    step_px,
)

AREA = 1400  # an arbitrary video-area width


# --- the table ---

c.check(
    "the gears are the requested ones, ascending",
    GEARS == (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0),
    f"{GEARS}",
)
c.check("eight gears", len(GEARS) == 8, f"{len(GEARS)}")
c.check("the default gear is 2x", DEFAULT_GEAR == 2.0)
c.check("1x is among the gears", 1.0 in GEARS)
c.check(
    "2x sits two gears right of 1.25",
    default_index() - GEARS.index(1.25) == 2,
    f"{default_index()} vs {GEARS.index(1.25)}",
)

# --- the mapping ---

c.check(
    "the whole span is 1/5 of the area over 7 steps",
    abs(step_px(AREA) - (AREA / 5) / 7) < 1e-9,
    f"{step_px(AREA)}",
)

c.check("pressing with no movement is 2x", gear_index_for_offset(0, AREA) == 5)
c.check(
    "the press point really is 2x",
    rate_for_index(gear_index_for_offset(0, AREA)) == 2.0,
)

# --- the asymmetry the gesture is specified around ---
#
# A gear is entered half a step before its centre, so the outermost gears are
# reached at 4.5 and 1.5 steps from the press point rather than 5 and 2.


def offset_reaching(gear, direction):
    """Smallest offset in that direction landing on gear, or None."""
    limit = AREA if direction > 0 else -AREA

    for dx in range(0, limit + direction, direction):
        if rate_for_index(gear_index_for_offset(dx, AREA)) == gear:
            return dx

    return None


to_min = offset_reaching(GEARS[0], -1)
to_max = offset_reaching(GEARS[-1], +1)

c.check(
    "the minimum is only reachable leftward and the maximum only rightward",
    to_min is not None and to_max is not None,
    f"{to_min}, {to_max}",
)
c.check(
    "leftward travel to the minimum is longer than rightward travel to the maximum",
    abs(to_min) > to_max,
    f"left {abs(to_min)}px vs right {to_max}px",
)
c.check(
    "the minimum is 4.5 steps away and the maximum 1.5",
    abs(abs(to_min) - 4.5 * step_px(AREA)) <= 1
    and abs(to_max - 1.5 * step_px(AREA)) <= 1,
    f"{abs(to_min)} ~= 4.5*{step_px(AREA):.2f}, {to_max} ~= 1.5*{step_px(AREA):.2f}",
)
c.check(
    "and the whole reachable span fits inside 1/5 of the area",
    abs(to_min) + to_max <= AREA / 5,
    f"{abs(to_min) + to_max} <= {AREA / 5}",
)

# round-half-to-even would make some gears a full step wide and others half,
# which is invisible in a screenshot and obvious under the finger.
# The base gear's own leftward offset is the press point itself, so it is left
# out - only the gears strictly below it have a real boundary to measure to.
narrower = [offset_reaching(g, -1) for g in GEARS[: default_index()]]
widths = [a - b for a, b in zip(narrower, narrower[1:])]

c.check(
    "every gear is exactly one step wide",
    all(abs(width) == round(step_px(AREA)) for width in widths),
    f"{widths} vs step {step_px(AREA):.2f}",
)

# --- each gear is reachable, and the ends clamp ---

c.check(
    "every gear is reachable from the press point",
    sorted(
        {
            rate_for_index(gear_index_for_offset(dx, AREA))
            for dx in range(-AREA // 3, AREA // 3)
        }
    )
    == sorted(GEARS),
)
c.check(
    "past the left end it stays at the minimum",
    rate_for_index(gear_index_for_offset(-AREA, AREA)) == 0.5,
)
c.check(
    "past the right end it stays at the maximum",
    rate_for_index(gear_index_for_offset(AREA, AREA)) == 3.0,
)
c.check("a zero-width area cannot divide by zero", gear_index_for_offset(50, 0) == 5)

# --- 1x is three steps left of the press point, 1.25 is two ---

c.check(
    "1.25 is two steps left of the press point",
    rate_for_index(gear_index_for_offset(-2 * step_px(AREA), AREA)) == 1.25,
)
c.check(
    "1x is three steps left of the press point",
    rate_for_index(gear_index_for_offset(-3 * step_px(AREA), AREA)) == 1.0,
)

# --- formatting: gears and the keyboard's fine steps ---

for rate, expected in (
    (1.0, "×1"),
    (2.0, "×2"),
    (3.0, "×3"),
    (0.5, "×0.5"),
    (0.75, "×0.75"),
    (1.25, "×1.25"),
    (2.5, "×2.5"),
    (1.1, "×1.1"),
    (0.7, "×0.7"),
    (12.0, "×12"),
):
    c.check(
        f"formats {rate} as {expected}",
        format_rate(rate) == expected,
        f"{format_rate(rate)}",
    )

c.check(
    "uses a real multiplication sign, not the letter x",
    format_rate(1.0).startswith("×") and "\u00d7" in format_rate(1.0),
    f"{format_rate(1.0)!r}",
)
c.check(
    "float drift does not leak into the label",
    format_rate(0.1 + 0.1 + 0.1) == "×0.3",
    f"{format_rate(0.1 + 0.1 + 0.1)}",
)
c.check(
    "the widest label is the measuring stick",
    max(len(format_rate(g)) for g in GEARS) == len("×0.75"),
)

# --- telling a gear from a keyboard step ---

c.check("1.25 is recognised as a gear", index_for_rate(1.25) == 3)
c.check("1.1 is reported as not a gear", index_for_rate(1.1) is None)
c.check("2.0 is recognised as a gear", index_for_rate(2.0) == 5)

c.check("the long press is 500 ms", LONG_PRESS_MS == 500)

# --- the ratchet: the reference travels with the mouse ---
#
# Replayed from the worked example that pinned the rule down: press at the
# default gear, drag far enough right to clamp at the top, then come back. The
# boundary has to follow the drag, so leaving the top gear takes a full step.


def replay(path, area=AREA):
    """Feed absolute positions through the ratchet, the way the gesture does."""
    gear = default_index()
    reference = path[0]
    seen = [gear]

    for position in path[1:]:
        gear, steps = gear_after_drag(position - reference, area, gear)
        reference += steps * step_px(area)
        seen.append(gear)

    return seen


step = step_px(AREA)
base = default_index()  # 5, the default gear

# The press point at 5, then 8 -> 7 -> 6 -> 2 -> 3 -> 4, in whole steps. The
# three-gear example this came from reads as: top, one below, the default, then
# far below, one up, one more up.
plain = replay([p * step for p in (5, 8, 7, 6, 2, 3, 4)])

c.check(
    "the worked example replays to the gears it should",
    plain == [base, len(GEARS) - 1, base + 1, base, base - 4, base - 3, base - 2],
    f"gears {plain}",
)
c.check(
    "clamped at the top, one step back drops exactly one gear",
    plain[1] - plain[2] == 1,
    f"{plain[1]} -> {plain[2]}",
)
c.check(
    "two steps back from the top is the default gear again",
    plain[3] == base,
    f"{plain[3]}",
)
c.check(
    "dragging well past the bottom and returning climbs one gear per step",
    plain[5] - plain[4] == 1 and plain[6] - plain[5] == 1,
    f"{plain[4]} -> {plain[5]} -> {plain[6]}",
)

# The reference is never more than half a step behind the mouse, clamped or not:
# that is what keeps the boundary following the drag instead of sitting at the
# press point, and what lets the drag carry on past the edge of the screen.
c.check(
    "a clamped drag still carries the reference along",
    replay([0, 40 * step])[-1] == len(GEARS) - 1,
    "otherwise the gear would snap back the moment the mouse moved",
)
c.check(
    "so coming back from the top costs a full step, every time",
    replay([0, 20 * step, 20 * step - step])[-1] == len(GEARS) - 2,
    "20 steps out, then one step back",
)
c.check(
    "and less than half a step back changes nothing",
    replay([0, 20 * step, 20 * step - step // 2 + 1])[-1] == len(GEARS) - 1,
    "the boundary sits at half a step",
)
c.check(
    "the same holds at the bottom end",
    replay([0, -20 * step, -20 * step + step])[-1] == 1
    and replay([0, -20 * step, -20 * step + step // 2 - 1])[-1] == 0,
    "clamped low, then back up",
)
c.check(
    "a drag with no whole step in it changes nothing",
    replay([0, step // 2 - 1]) == [base, base],
    f"{replay([0, step // 2 - 1])}",
)
c.check("a zero width cannot divide by zero", gear_after_drag(50, 0, 4) == (4, 0))

c.finish()
