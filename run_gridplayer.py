"""Entry point for running this modified GridPlayer from a source checkout.

This is a thin launcher: the application code lives in `gridplayer/` next to this
file and differs from upstream 0.5.5 only inside clearly marked `MOD:` blocks.

Why a launcher instead of editing the frozen build: GridPlayer's own modules are
compiled into a PYZ embedded in GridPlayer.exe, and PyInstaller's frozen finder
takes precedence over anything dropped on disk, so the frozen build cannot be
patched from the outside.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Reuse the libVLC shipped with the original portable build, so no separate
# VLC installation is needed. gridplayer.vlc_player.vlc (vendored python-vlc)
# reads both of these variables in its find_lib().
os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(ROOT / "libVLC" / "libvlc.dll"))
os.environ.setdefault("PYTHON_VLC_MODULE_PATH", str(ROOT / "libVLC" / "plugins"))

# Keep settings.ini / gridplayer.log next to the app instead of in %APPDATA%.
os.environ.setdefault("GRIDPLAYER_DATA_DIR", str(ROOT / "data"))

sys.path.insert(0, str(ROOT))

from gridplayer.__main__ import main  # noqa: E402

if __name__ == "__main__":
    # Guard matters: GridPlayer spawns worker processes, and multiprocessing on
    # Windows re-imports this module in each child as __mp_main__.
    main()
