"""Self-checks for this fork's own rules.

The original file was lost to an accidental deletion and was never tracked by
git, so it could not be recovered from the object database. This is a fresh
design rather than a restoration.

It guards the conventions this fork works under, and the facts that are
expensive to rediscover:

  * portable - nothing may depend on where this checkout happens to live
  * few deps - the engines are runtimes placed beside the checkout, never
    committed, and no playback library is added to requirements
  * modular  - additions are marked, and vendored third-party files are left
    byte-for-byte alone

Body kept as plain ASCII on purpose: PowerShell 5.1 reads files as GBK unless
told otherwise, and a round trip through it once destroyed this file.
"""

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tests._harness import ROOT, Checker, bootstrap

bootstrap()
c = Checker("self-check")

SRC = ROOT / "gridplayer"

py_files = [
    p
    for p in SRC.rglob("*.py")
    if p.name not in ("mpv.py", "vlc.py", "resources_bin.py")
]
# Only the runtime is scanned. The checks under tests/ may hold absolute paths:
# they exercise path handling, and a fixture like C:\\some\\where is generic rather
# than this machine's.
#
# What makes a checkout machine-specific is an absolute path, so that is what is
# looked for - not a list of this machine's paths, which would defeat the point
# by putting them in the repository.
ABSOLUTE_PATH = re.compile(r"\b[A-Za-z]:[\\/]")

# Windows strings the code is meant to contain: registry keys, pipe names, and
# documentation examples. They look like paths but are not filesystem paths.
ALLOWED_SHAPES = (
    "HKCU:",
    "Software\\\\VideoLAN",
    "\\\\.\\pipe",
    "libname=",
    "BasePython",
    "C:\\\\Python",
)

offenders = []
for path in py_files:
    text = path.read_text(encoding="utf-8", errors="ignore")

    for lineno, line in enumerate(text.splitlines(), 1):
        if not ABSOLUTE_PATH.search(line):
            continue

        if any(shape in line for shape in ALLOWED_SHAPES):
            continue

        offenders.append(f"{path.name}:{lineno}")

c.check(
    "no source file hardcodes a path from this machine",
    not offenders,
    f"{offenders}" if offenders else "moved checkouts keep working",
)

gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
c.check(
    "the runtimes are ignored, not committed",
    all(entry in gitignore for entry in ("libVLC/", "mpv/")),
    "a checkout carries source, the engines are placed beside it",
)
c.check(
    "and so is anything holding local state",
    all(entry in gitignore for entry in ("data/", "pyenv/")),
)

requirements = "\n".join(
    line
    for line in (ROOT / "requirements.txt")
    .read_text(encoding="utf-8")
    .lower()
    .splitlines()
    if not line.strip().startswith("#")
)
c.check(
    "no playback library was added to requirements",
    all(name not in requirements for name in ("mpv", "sounddevice", "pyaudio")),
    "the engines are runtimes, not pip packages",
)

MPV_PY = SRC / "mpv_player" / "mpv.py"
RECORDED = "c05b55fcca8659486e801b32b70008d47219ffa83181a35db26876e18f89ce4f"
actual = hashlib.sha256(MPV_PY.read_bytes()).hexdigest()
c.check(
    "the vendored mpv binding is untouched",
    actual == RECORDED,
    actual[:12] + "...",
)

pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
c.check(
    "both vendored bindings are excluded from lint",
    "vlc_player/vlc.py" in pyproject and "mpv_player/mpv.py" in pyproject,
    "third-party code is not held to this project's style rules",
)

MOD_FILES = (
    SRC / "mpv_player" / "player_mpv.py",
    SRC / "mpv_player" / "player_process_mpv.py",
    SRC / "mpv_player" / "instance_process_mpv.py",
    SRC / "mpv_player" / "video_driver_mpv.py",
    SRC / "utils" / "mpv_finder.py",
    SRC / "widgets" / "video_frame_mpv.py",
)

unmarked = [
    p.name for p in MOD_FILES if "# MOD:" not in p.read_text(encoding="utf-8")[:400]
]
c.check(
    "every added file says it is an addition",
    not unmarked,
    f"{unmarked}" if unmarked else f"{len(MOD_FILES)} files marked",
)

from gridplayer.models.video import MAX_RATE, MIN_RATE  # noqa: E402

c.check(
    "the upstream rate limits are still the upstream rate limits",
    (MIN_RATE, MAX_RATE) == (0.2, 12),
    f"{MIN_RATE} .. {MAX_RATE}",
)

from gridplayer.utils import speed_gears  # noqa: E402

c.check(
    "the gear list stays sorted and contains normal speed",
    list(speed_gears.GEARS) == sorted(speed_gears.GEARS) and 1.0 in speed_gears.GEARS,
    f"{speed_gears.GEARS}",
)
c.check(
    "the multiplication sign is escaped rather than written literally",
    speed_gears.MULTIPLICATION_SIGN == "\u00d7"
    and "\u00d7" not in (SRC / "utils" / "speed_gears.py").read_text(encoding="utf-8"),
    "RUF001 flags the literal character",
)
c.check(
    "the gear popup lists the largest gear first",
    speed_gears.rate_for_index(len(speed_gears.GEARS) - 1) == max(speed_gears.GEARS),
)

from gridplayer.params.static import VideoDriver  # noqa: E402
from gridplayer.player.managers.video_driver import VideoDriverManager  # noqa: E402

c.check(
    "the VLC drivers are all still registered",
    all(
        driver in VideoDriverManager._video_drivers
        for driver in (
            VideoDriver.VLC_HW,
            VideoDriver.VLC_HW_SP,
            VideoDriver.VLC_SW,
            VideoDriver.DUMMY,
        )
    ),
    "adding mpv must not disturb them",
)

manager_src = (SRC / "player" / "managers" / "video_driver.py").read_text(
    encoding="utf-8"
)
mpv_registrations = manager_src.count("VideoDriver.MPV")
c.check(
    "mpv is registered everywhere a driver has to be",
    mpv_registrations >= 3,
    f"{mpv_registrations} registration(s): widget, process class, process model",
)

c.check(
    "no check file is named like a pytest test",
    not list((ROOT / "tests").glob("test_*.py")),
    "they are standalone scripts, run by _runtests.py",
)
c.check(
    "and the runner that drives them is present",
    (ROOT / "_runtests.py").is_file(),
)
c.check(
    "the self-check itself runs standalone",
    (ROOT / "_selftest.py").is_file(),
)

c.finish()
