"""MOD: folder scanning and sorting for the playlist panel."""

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from gridplayer.models.media_entry import MediaEntry
from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT

SORT_KEYS = ("name", "size", "mtime", "history", "duration")

_DIGITS = re.compile(r"(\d+)")


def natural_key(name: str):
    """Split into digit / non-digit runs so 'clip 2' sorts before 'clip 10'."""
    parts = _DIGITS.split(name.casefold())

    return tuple(
        (1, int(part)) if part.isdigit() else (0, part) for part in parts if part != ""
    )


def scan_folder(video_path: Path) -> list[MediaEntry]:
    """Every supported media file next to `video_path`. Never raises."""
    folder = Path(video_path).parent

    try:
        items = list(folder.iterdir())
    except OSError:
        return []

    entries = []

    for item in items:
        try:
            if not item.is_file() or item.suffix[1:].lower() not in SUPPORTED_MEDIA_EXT:
                continue

            stat = item.stat()
        except OSError:
            continue

        entries.append(MediaEntry(item, item.name, stat.st_size, stat.st_mtime))

    return entries


def _has_value(entry: MediaEntry, key: str, history: Mapping[str, int]) -> bool:
    if key == "history":
        return entry.key in history
    if key == "duration":
        return entry.duration_ms is not None

    return True


def _primary(entry: MediaEntry, key: str, history: Mapping[str, int]):
    if key == "size":
        return entry.size
    if key == "mtime":
        return entry.mtime
    if key == "history":
        return history[entry.key]
    if key == "duration":
        return entry.duration_ms

    return natural_key(entry.name)


def sort_entries(
    entries: Sequence[MediaEntry],
    key: str,
    desc: bool,
    history: Mapping[str, int],
) -> list[MediaEntry]:
    """Sort with a stable name-order tie-break.

    Entries whose value for `key` is unknown (never played / duration not probed
    yet) always end up last, regardless of direction - that is the behaviour the
    user asked for, so it is deliberately NOT flipped by `desc`.
    """
    known = [e for e in entries if _has_value(e, key, history)]
    unknown = [e for e in entries if not _has_value(e, key, history)]

    known.sort(key=lambda e: natural_key(e.name))  # stable base order

    if key == "name":
        known.sort(key=lambda e: natural_key(e.name), reverse=desc)
    else:
        known.sort(key=lambda e: _primary(e, key, history), reverse=desc)

    unknown.sort(key=lambda e: natural_key(e.name))

    return known + unknown
