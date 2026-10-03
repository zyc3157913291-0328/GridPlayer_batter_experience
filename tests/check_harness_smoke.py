import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("harness smoke")

c.check("data dir created", data_dir.is_dir(), str(data_dir))

from gridplayer.settings import Settings

Settings().set("player/window_maximized", True)
Settings().sync()
c.check(
    "settings write/read works in sandbox",
    Settings().get("player/window_maximized") is True,
)

c.finish()
