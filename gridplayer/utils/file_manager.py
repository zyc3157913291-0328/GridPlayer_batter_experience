# MOD: new file - show a file in the system's file manager.
"""MOD: hand a path to the system file manager."""

import subprocess
import sys
from pathlib import Path


def reveal_command(path: Path) -> list[str]:
    """The command that opens the file manager showing `path`.

    Windows' explorer needs the selection flag welded to the path into a single
    argument ("/select," immediately followed by the path); passing that through
    a shell would eat the comma, so every caller spawns it directly.
    """
    path = Path(path)

    if sys.platform == "win32":
        return ["explorer", f"/select,{path}"]
    if sys.platform == "darwin":
        return ["open", "-R", str(path)]

    return ["xdg-open", str(path if path.is_dir() else path.parent)]


def reveal_path(path: Path) -> None:
    """Open the file manager on `path`, selecting it where the platform can."""
    try:
        subprocess.Popen(reveal_command(path))
    except OSError:
        # a headless or stripped-down system may have no file manager at all;
        # failing to show one must not take the window down
        pass
