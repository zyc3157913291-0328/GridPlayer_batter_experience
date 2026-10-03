# MOD: new file - per-file playback history store for the playlist panel.
"""MOD: per-file 'last played' timestamps for the playlist panel's history sort."""

import json
import logging
import time
from pathlib import Path

from gridplayer.utils.app_dir import get_app_data_dir

HISTORY_FILE_NAME = "play_history.json"
HISTORY_MAX_ENTRIES = 5000


class PlayHistory:
    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)
        self._entries: dict[str, int] = {}

    @property
    def path(self) -> Path:
        return get_app_data_dir() / HISTORY_FILE_NAME

    def as_mapping(self) -> dict[str, int]:
        return dict(self._entries)

    def get(self, key: str) -> int | None:
        return self._entries.get(key)

    def record(self, key: str, when_ms: int | None = None) -> None:
        self._entries[key] = (
            int(time.time() * 1000) if when_ms is None else int(when_ms)
        )

    def prune(self) -> None:
        if len(self._entries) <= HISTORY_MAX_ENTRIES:
            return

        newest = sorted(self._entries.items(), key=lambda kv: kv[1], reverse=True)
        self._entries = dict(newest[:HISTORY_MAX_ENTRIES])

    def load(self) -> None:
        if not self.path.is_file():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self._log.warning(f"Play history unreadable, starting empty: {e}")
            return

        if isinstance(data, dict):
            self._entries = {
                str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))
            }

        # An oversized file can only appear if the cap was lowered between
        # versions, but loading 5000+ entries into memory is worth avoiding.
        self.prune()

    def save(self) -> None:
        self.prune()

        try:
            self.path.write_text(
                json.dumps(self._entries, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            self._log.warning(f"Could not write play history: {e}")
