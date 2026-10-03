"""Shared helpers for the MOD test scripts. No third-party test framework."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SAMPLES = ROOT / "tests" / "samples"

# Keep a module-level reference: a QApplication with no Python reference gets
# garbage collected, and the next QWidget() then aborts with
# "Must construct a QApplication before a QWidget".
_APP = None


def sample(name: str) -> Path:
    """A media file that ships with the repository.

    Checks used to reach into the portable GridPlayer install that sat next to
    the checkout. That made them depend on a machine-specific path, and they
    broke outright the moment it was removed. These two clips are generated
    (testsrc, 320x240, 2s, ~8 KB each) so the repository stands on its own.
    """
    return SAMPLES / name


def bootstrap() -> Path:
    """Prepare a sandboxed run: temp data dir, app on sys.path, QApplication."""
    global _APP

    data_dir = Path(tempfile.mkdtemp(prefix="gpmod-test-"))
    os.environ["GRIDPLAYER_DATA_DIR"] = str(data_dir)

    os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(ROOT / "libVLC" / "libvlc.dll"))
    os.environ.setdefault("PYTHON_VLC_MODULE_PATH", str(ROOT / "libVLC" / "plugins"))

    sys.path.insert(0, str(ROOT))

    from PyQt5.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication(sys.argv)

    return data_dir


class Checker:
    def __init__(self, title: str):
        self._title = title
        self._results = []

    def check(self, name, cond, detail=""):
        self._results.append(bool(cond))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}   {detail}")

    def finish(self):
        passed = sum(self._results)
        total = len(self._results)
        print(f"\n==== {self._title}: {passed}/{total} checks passed ====")
        sys.exit(0 if passed == total else 1)
