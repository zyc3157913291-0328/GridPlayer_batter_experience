# MOD: new file - locates the libmpv runtime, the way libvlc_fixer locates libVLC.
"""Find libmpv and make it importable.

python-mpv resolves the library through ``PATH``, so the directory holding it
has to go in before the binding is imported. Nothing here knows about any
particular machine: the runtime lives in ``mpv/`` beside the repository, exactly
as ``libVLC/`` does, and ``MPV_DIR`` overrides it for a checkout that keeps it
somewhere else.
"""

import os
from pathlib import Path

# python-mpv tries these in order; libmpv-2.dll is the one current builds ship
DLL_NAMES = ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll")

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIRNAME = "mpv"


def mpv_dir():
    """The directory holding libmpv, or None when it is not installed."""
    override = os.environ.get("MPV_DIR")

    candidates = [Path(override)] if override else []
    candidates.append(REPO_ROOT / RUNTIME_DIRNAME)

    for candidate in candidates:
        if any((candidate / name).is_file() for name in DLL_NAMES):
            return candidate

    return None


def prepare_import():
    """Put the runtime on PATH so the binding can find it. Returns its dir."""
    found = mpv_dir()

    if found is None:
        return None

    os.environ["PATH"] = str(found) + os.pathsep + os.environ.get("PATH", "")

    return found


def missing_runtime_message() -> str:
    return (
        "libmpv was not found. Put libmpv-2.dll in "
        f"'{REPO_ROOT / RUNTIME_DIRNAME}' (or point MPV_DIR at the directory "
        "holding it) and restart. See the README for where to get an official "
        "build."
    )
