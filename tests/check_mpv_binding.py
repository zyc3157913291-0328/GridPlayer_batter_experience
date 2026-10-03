"""MOD: the vendored python-mpv binding, and that libmpv really works here.

Two things are worth protecting:

  * the vendored file is third-party code kept verbatim, so its recorded hash is
    asserted - an accidental edit (a linter, a format-on-save) would otherwise
    go unnoticed until a confusing bug appeared
  * libmpv loads and the handful of properties this driver depends on actually
    read and write - the spike showed mpv changes speed without a gap, and this
    is the cheapest way to keep that reachable

The runtime is optional: a checkout without libmpv skips the live half instead
of failing, so the suite stays green on a machine that has not placed it yet.
"""

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import ROOT, Checker, bootstrap, sample

bootstrap()
c = Checker("mpv binding")

MPV_PY = ROOT / "gridplayer" / "mpv_player" / "mpv.py"

# recorded in gridplayer/mpv_player/__init__.py, next to the provenance note
VENDORED_SHA256 = "c05b55fcca8659486e801b32b70008d47219ffa83181a35db26876e18f89ce4f"

# libmpv is not in the repository (the same policy as libVLC): it is found
# beside the repository, or through MPV_DIR. No machine-specific path belongs
# here - a checkout has to work after being moved to another computer.
MPV_DIRS = (
    Path(os.environ["MPV_DIR"]) if os.environ.get("MPV_DIR") else None,
    ROOT / "mpv",
)


def find_mpv_dir():
    for candidate in MPV_DIRS:
        if candidate and (candidate / "libmpv-2.dll").is_file():
            return candidate

    return None


# --- the vendored file ---

c.check("the vendored binding is present", MPV_PY.is_file(), f"{MPV_PY.name}")

digest = hashlib.sha256(MPV_PY.read_bytes()).hexdigest() if MPV_PY.is_file() else ""
c.check(
    "and is byte-for-byte the released file",
    digest == VENDORED_SHA256,
    f"{digest[:16]}… vs {VENDORED_SHA256[:16]}…",
)

init_src = (ROOT / "gridplayer" / "mpv_player" / "__init__.py").read_text(
    encoding="utf-8"
)
c.check(
    "its provenance is recorded next to it",
    all(
        token in init_src
        for token in ("jaseg/python-mpv", "1.0.8", VENDORED_SHA256[:16])
    ),
    "upstream, version and hash, for the licence trail",
)
c.check(
    "the licence trail says or-later, which is what makes GPL-3.0 work",
    "or later" in init_src and "GPL-2.0" in init_src,
)
c.check(
    "ruff is told to leave it alone",
    "mpv_player/mpv.py" in (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    "third-party code has to be excluded, the same way vlc_player/vlc.py is",
)

# --- the runtime ---

mpv_dir = find_mpv_dir()

if mpv_dir is None:
    print("\n  libmpv-2.dll not found - skipping the live checks")
    print("  (put it in <repo>/mpv/, or point MPV_DIR at the directory holding it)")
    c.finish()
    sys.exit(0)

print(f"\n  libmpv from: {mpv_dir}")

# python-mpv resolves the DLL through PATH, so it has to go in before the import
os.environ["PATH"] = str(mpv_dir) + os.pathsep + os.environ["PATH"]

from gridplayer.mpv_player import mpv  # noqa: E402

c.check("the binding imports", mpv is not None)
c.check("and reports a version", bool(mpv.__version__), f"{mpv.__version__}")

player = mpv.MPV(vo="null", ao="null", idle="yes")

c.check("libmpv instantiates", player is not None)
c.check("and identifies itself", bool(player.mpv_version), f"{player.mpv_version}")

# --- the properties this driver is built on ---

c.check("speed reads", player.speed == 1.0, f"{player.speed}")

player.speed = 2.0
c.check(
    "speed writes - the whole reason this driver exists",
    player.speed == 2.0,
    f"{player.speed}",
)

player.speed = 1.0

player.play(str(sample("probe.mp4")))
player.wait_until_playing(timeout=20)

c.check("it plays a file", bool(player.path), f"{player.path}")
c.check(
    "and reports the right duration",
    player.duration is not None and 2.5 <= player.duration <= 3.5,
    f"{player.duration}",
)

player.pause = True
c.check("pause writes", player.pause is True, f"{player.pause}")

position = player.time_pos
c.check(
    "position reads",
    position is not None and position >= 0,
    f"{player.time_pos}",
)

player.terminate()

c.check("and it shuts down cleanly", True)

c.finish()
