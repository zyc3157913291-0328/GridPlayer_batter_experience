"""MOD: background duration probing so the playlist panel never blocks."""

import logging
import queue
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from gridplayer.utils.duration_cache import DurationCache

if TYPE_CHECKING:
    from gridplayer.models.media_entry import MediaEntry

PROBE_TIMEOUT_MS = 5000

# How often the parse status is polled while libvlc works in the background.
POLL_INTERVAL_S = 0.02

# Filled in lazily by _vlc_module() once the vlc module is importable.
_PARSE_FINAL_STATES: tuple = ()


def _vlc_module():
    """Import the bundled libvlc bindings lazily and cache the final states.

    Kept out of the module import path so that importing this module never
    pulls in libvlc (and never fails where libvlc is unavailable).
    """
    global _PARSE_FINAL_STATES

    from gridplayer.vlc_player import vlc

    if not _PARSE_FINAL_STATES:
        _PARSE_FINAL_STATES = (
            vlc.MediaParsedStatus.done,
            vlc.MediaParsedStatus.failed,
            vlc.MediaParsedStatus.timeout,
        )

    return vlc


def probe_duration(instance, path, timeout_ms: int = PROBE_TIMEOUT_MS) -> int | None:
    """Return the duration of `path` in milliseconds, or None if unknown.

    Synchronous and bounded: parse_with_options() is ASYNCHRONOUS in libvlc (it
    returns immediately and get_duration() then gives -1), so the parse status
    is polled until it reaches a final state, with our own wall-clock deadline
    as the backstop. The deprecated blocking parse() is deliberately not used -
    it "could block indefinitely" on a bad file.

    0 and -1 both mean "unknown" (a non-media file yields 0).
    """
    if instance is None:
        return None

    vlc = _vlc_module()

    media = instance.media_new_path(str(path))
    if media is None:
        return None

    try:
        start = time.monotonic()
        media.parse_with_options(vlc.MediaParseFlag.local, timeout_ms)

        deadline = start + timeout_ms / 1000 + 1.0
        while time.monotonic() < deadline:
            if media.get_parsed_status() in _PARSE_FINAL_STATES:
                break
            time.sleep(POLL_INTERVAL_S)

        raw = media.get_duration()
    finally:
        media.release()

    return int(raw) if raw and raw > 0 else None


class _ProbeWorker(QThread):
    probed = pyqtSignal(str, object)  # entry key, duration_ms (or None)
    batch_done = pyqtSignal()

    def __init__(self, cache: DurationCache):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)
        self._cache = cache
        self._queue: queue.Queue = queue.Queue()
        self._stop = False
        self._instance = None

    def request(self, entries: Sequence["MediaEntry"]):
        for entry in entries:
            self._queue.put(entry)

    def stop(self):
        self._stop = True
        self._queue.put(None)

    def run(self):
        vlc = _vlc_module()

        try:
            self._instance = vlc.Instance("--no-video", "--no-audio", "--quiet")
        except Exception as e:
            self._log.error(f"Cannot create a probing libvlc instance: {e}")
            return

        while not self._stop:
            entry = self._queue.get()
            if entry is None:
                break

            duration = None

            try:
                duration = probe_duration(self._instance, entry.path)
            except Exception as e:
                self._log.debug(f"Probe failed for {entry.name}: {e}")

            self._cache.put(entry, duration)
            self.probed.emit(entry.key, duration)

            # batch_done is only a "persist the cache now" opportunity, never a
            # correctness-critical signal, so it does not need an exact pending
            # count. Queue.empty() is internally locked, whereas a counter would
            # be mutated from both threads. A request landing in the window just
            # after this check simply means the cache is written again on the
            # next drain, or by DurationProber.stop().
            if self._queue.empty():
                self.batch_done.emit()

        if self._instance is not None:
            self._instance.release()


class DurationProber(QObject):
    """Thin wrapper: dedupes requests and forwards results on the UI thread."""

    duration_ready = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cache = DurationCache()
        self._cache.load()

        self._worker = _ProbeWorker(self._cache)
        self._worker.probed.connect(self.duration_ready)
        self._worker.batch_done.connect(self._cache.save)

    def cached(self, entry: "MediaEntry") -> int | None:
        return self._cache.get(entry)

    def request(self, entries: Sequence["MediaEntry"]):
        missing = [e for e in entries if self._cache.get(e) is None]

        if not missing:
            return

        # MOD: queue the whole batch BEFORE the thread starts. Starting first
        # let the worker drain and finish entries while request() was still
        # counting them, so batch_done could fire early (or twice).
        self._worker.request(missing)

        if not self._worker.isRunning():
            self._worker.start()

    def stop(self):
        if self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)

        self._cache.save()
