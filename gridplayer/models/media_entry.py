"""MOD: one media file found in a folder, as shown in the playlist panel."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaEntry:
    path: Path
    name: str
    size: int
    mtime: float
    duration_ms: int | None = None

    @property
    def key(self) -> str:
        """Stable case-insensitive identity used by the history/duration stores."""
        return str(self.path).casefold()

    def with_duration(self, duration_ms: int | None) -> "MediaEntry":
        return MediaEntry(self.path, self.name, self.size, self.mtime, duration_ms)
