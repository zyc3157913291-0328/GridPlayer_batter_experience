# MOD: new file - background thumbnail fetching for the playlist panel.
"""MOD: fetch shell thumbnails off the GUI thread."""

import logging
import queue
from collections.abc import Sequence

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.shell_thumbnail import (
    DEFAULT_SIZE,
    com_initialize,
    com_uninitialize,
    thumbnail_image,
)


class _ThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(str, object)  # entry key, QImage or None

    def __init__(self, size: int = DEFAULT_SIZE):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)
        self._queue: queue.Queue = queue.Queue()
        self._size = size
        self._stop = False
        self._seen: set[str] = set()

    def request(self, entries: Sequence[MediaEntry]):
        for entry in entries:
            if entry.key in self._seen:
                continue

            self._seen.add(entry.key)
            self._queue.put(entry)

    def forget(self, keys):
        """Allow re-fetching, e.g. after the file changed on disk."""
        for key in keys:
            self._seen.discard(key)

    def stop(self):
        self._stop = True
        self._queue.put(None)

    def run(self):
        com_initialize()

        try:
            while not self._stop:
                entry = self._queue.get()
                if entry is None:
                    break

                image = None
                try:
                    image = thumbnail_image(entry.path, self._size)
                except Exception as e:
                    self._log.debug(f"Thumbnail failed for {entry.name}: {e}")

                self.thumbnail_ready.emit(entry.key, image)
        finally:
            com_uninitialize()


class ThumbnailProvider(QObject):
    """Thin wrapper: dedupes requests and forwards results on the GUI thread."""

    thumbnail_ready = pyqtSignal(str, object)

    def __init__(self, size: int = DEFAULT_SIZE, parent=None):
        super().__init__(parent)

        self._worker = _ThumbnailWorker(size)
        self._worker.thumbnail_ready.connect(self.thumbnail_ready)

    def request(self, entries: Sequence[MediaEntry]):
        if not entries:
            return

        if not self._worker.isRunning():
            self._worker.start()

        self._worker.request(entries)

    def stop(self):
        if self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
