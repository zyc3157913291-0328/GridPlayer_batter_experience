"""MOD: on-disk cache of media durations, keyed by path and validated by size/mtime."""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from gridplayer.utils.app_dir import get_app_data_dir

if TYPE_CHECKING:
    from gridplayer.models.media_entry import MediaEntry

CACHE_FILE_NAME = "duration_cache.json"


class DurationCache:
    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)
        self._entries: dict[str, dict] = {}

    @property
    def path(self) -> Path:
        return get_app_data_dir() / CACHE_FILE_NAME

    def get(self, entry: "MediaEntry") -> int | None:
        record = self._entries.get(entry.key)
        if not record:
            return None

        if record.get("size") != entry.size or record.get("mtime") != entry.mtime:
            return None

        duration = record.get("duration_ms")

        return int(duration) if isinstance(duration, (int, float)) else None

    def put(self, entry: "MediaEntry", duration_ms: int | None):
        # An unknown duration is never stored; a probe that failed must not
        # throw away a duration we already know.
        if duration_ms is None:
            return

        self._entries[entry.key] = {
            "size": entry.size,
            "mtime": entry.mtime,
            "duration_ms": int(duration_ms),
        }

    def load(self):
        if not self.path.is_file():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self._log.warning(f"Duration cache unreadable, starting empty: {e}")
            return

        if isinstance(data, dict):
            self._entries = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def save(self):
        try:
            self.path.write_text(
                json.dumps(self._entries, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            self._log.warning(f"Could not write duration cache: {e}")
