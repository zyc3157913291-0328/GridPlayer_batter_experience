from enum import Enum, auto
from typing import NamedTuple

from gridplayer.params import env

PLAYER_ID_LENGTH = 8

PLAYER_INITIAL_SIZE = (640, 360)
PLAYER_MIN_VIDEO_SIZE = (100, 90)

OVERLAY_ACTIVITY_EVENT = 2000

FONT_SIZE_MAIN = 12 if env.IS_MACOS else 9
FONT_SIZE_BIG_INFO = 22 if env.IS_MACOS else 16

VIDEO_END_LOOP_MARGIN_MS = 500


class AutoName(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()


class GridMode(AutoName):
    AUTO_ROWS = auto()
    AUTO_COLS = auto()


class VideoAspect(AutoName):
    FIT = auto()
    STRETCH = auto()
    NONE = auto()


class VideoCrop(NamedTuple):
    Left: int
    Top: int
    Right: int
    Bottom: int


class VideoTransform(AutoName):
    ROTATE_90 = auto()
    ROTATE_180 = auto()
    ROTATE_270 = auto()
    HFLIP = auto()
    VFLIP = auto()
    TRANSPOSE = auto()
    ANTITRANSPOSE = auto()
    NONE = auto()


class VideoRepeat(AutoName):
    SINGLE_FILE = auto()
    DIR = auto()
    DIR_SHUFFLE = auto()
    # MOD: play to the end, then stay paused - no loop, no next file
    PAUSE_AT_END = auto()


# MOD: click order for the overlay repeat button. List loop is first because it
# is the default mode (video_defaults/repeat = dir on this install).
VIDEO_REPEAT_CYCLE = (
    VideoRepeat.DIR,
    VideoRepeat.SINGLE_FILE,
    VideoRepeat.DIR_SHUFFLE,
    VideoRepeat.PAUSE_AT_END,
)


def next_video_repeat(mode) -> VideoRepeat:
    """MOD: the mode after `mode` in the overlay repeat button's click order."""
    try:
        idx = VIDEO_REPEAT_CYCLE.index(mode)
    except ValueError:
        return VIDEO_REPEAT_CYCLE[0]

    return VIDEO_REPEAT_CYCLE[(idx + 1) % len(VIDEO_REPEAT_CYCLE)]


class VideoDriver(AutoName):
    VLC_SW = auto()
    VLC_HW = auto()
    VLC_HW_SP = auto()
    DUMMY = auto()
    MPV = auto()  # MOD


class SeekSyncMode(AutoName):
    DISABLED = auto()
    PERCENT = auto()
    TIMECODE = auto()


class URLResolver(AutoName):
    STREAMLINK = auto()
    YT_DLP = auto()
    DIRECT = auto()


class AudioChannelMode(AutoName):
    UNSET = auto()
    STEREO = auto()
    RSTEREO = auto()
    LEFT = auto()
    RIGHT = auto()
    DOLBYS = auto()
    HEADPHONES = auto()
    MONO = auto()


class WindowState(NamedTuple):
    is_maximized: bool
    is_fullscreen: bool
    geometry: str
