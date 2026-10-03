"""Real end to end probe: does the app end itself when its last video goes?

Starts the actual application with one video, closes that video through the
app's own API - no clicking, no desktop interaction - and checks that the
process ends on its own.

Runs against a throwaway data directory on purpose: closing the window writes
window geometry and volume into settings, and this must not overwrite the real
install's.

Not a check_*.py, because it opens a real window and ends its own process.
Markers go to a file rather than stdout: the app exits via os._exit(), which
would drop anything still buffered.

Exit codes: 0 the app ended itself, 97 it stayed open until the event loop
returned, 98 no video was ever loaded, 99 it was still running at the deadline.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

os.environ["PYTHON_VLC_LIB_PATH"] = str(ROOT / "libVLC" / "libvlc.dll")
os.environ["PYTHON_VLC_MODULE_PATH"] = str(ROOT / "libVLC" / "plugins")
os.environ["GRIDPLAYER_DATA_DIR"] = tempfile.mkdtemp(prefix="gpmod-quit-probe-")

sys.path.insert(0, str(ROOT))

LOG = ROOT / "evidence" / "quit-probe.txt"

VIDEOS = [
    Path(r"E:\pic\整活\八级果冻大狂风1.mp4"),
    Path(r"E:\pic\整活\八级果冻大旋风1.mp4"),
]

CLOSE_AFTER_MS = 10_000
GIVE_UP_AFTER_MS = 35_000

# "single": one video, close it, the app must end itself.
# "keep":   two videos, close one, the app must still be there afterwards.
MODE = sys.argv[1] if len(sys.argv) > 1 else "single"


def note(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")

    from multiprocessing import freeze_support

    freeze_support()

    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.main.init_log import init_log

    init_app_env()
    init_log()

    from PyQt5.QtCore import QTimer

    from gridplayer.main.init_app import init_app
    from gridplayer.main.init_icons import init_icon
    from gridplayer.params import env
    from gridplayer.utils.libvlc import init_vlc

    wanted = VIDEOS[:1] if MODE == "single" else VIDEOS[:2]

    note(f"mode: {MODE}")
    note(f"data dir: {os.environ['GRIDPLAYER_DATA_DIR']}")
    for v in wanted:
        note(f"video: {v}  exists={v.exists()}")

    app = init_app()

    vlc_version, vlc_python_version = init_vlc()
    env.VLC_VERSION = vlc_version
    env.VLC_PYTHON_VERSION = vlc_python_version

    from gridplayer.player import Player

    player = Player()
    player.show()

    if env.IS_WINDOWS:
        init_icon(app)

    app.installEventFilter(player)

    player.process_arguments([str(v) for v in wanted])

    def close_one():
        blocks = list(player._context.video_blocks)

        note(f"grid holds {len(blocks)} video(s)")

        if not blocks:
            note("no video was ever loaded")
            os._exit(98)

        blocks[0].close()

        note("closed one; waiting to see what the app does")

    def give_up():
        note("gave up: the app was still running at the deadline")
        os._exit(99)

    QTimer.singleShot(CLOSE_AFTER_MS, close_one)
    QTimer.singleShot(GIVE_UP_AFTER_MS, give_up)

    if MODE == "keep":

        def check_still_alive():
            blocks = list(player._context.video_blocks)

            note(f"5s later: {len(blocks)} video(s) left, app still running")

            if blocks:
                note("OK: closing one of two did not end the app")
                os._exit(0)

            note("BAD: the app emptied its grid and should have closed")
            os._exit(96)

        QTimer.singleShot(CLOSE_AFTER_MS + 5_000, check_still_alive)

    ret = app.exec_()

    note(f"exec_ returned {ret} - the app did not close itself")
    sys.exit(97)


if __name__ == "__main__":
    main()
