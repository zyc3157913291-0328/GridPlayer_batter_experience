import base64

from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal, pyqtSlot

from gridplayer.params import env
from gridplayer.params.static import WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.misc import force_terminate


class WindowStateManager(ManagerBase):
    pause_on_minimize = pyqtSignal()
    closing = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_maximized_pre_fullscreen = False
        self._ctx.window_state = self.window_state

        self.pre_minimize_unpaused = []

    def init(self):
        # MOD: put the window back where it was closed
        self._restore_saved_window_state()

        # Linux has window manager for this, the flag doesn't work there anyway
        if not env.IS_LINUX and Settings().get("player/stay_on_top"):
            self.parent().setWindowFlag(Qt.WindowStaysOnTopHint)

    def _saved_window_state(self) -> WindowState | None:
        """MOD: the window state stored by the last window that closed."""
        geometry = Settings().get("player/window_geometry")
        if not geometry:
            return None

        # A hand-edited or truncated settings.ini must not stop the app from
        # starting: restoreGeometry() decodes base64 internally and raises on a
        # malformed blob, so validate it here and fall back to the default.
        try:
            base64.b64decode(geometry)
        except (ValueError, TypeError) as e:
            self._log.warning(f"Stored window geometry is unusable, ignoring it: {e}")
            return None

        return WindowState(
            is_maximized=Settings().get("player/window_maximized"),
            is_fullscreen=Settings().get("player/window_fullscreen"),
            geometry=geometry,
        )

    def _restore_saved_window_state(self) -> bool:
        """MOD: apply the stored window state.

        No off-screen guard is needed here: Qt's own restoreGeometry() already
        relocates a window whose saved screen is gone (measured - a blob saved
        at (-9000, -9000) comes back inside the primary screen's available
        area). Verified by tests/check_window_state_restore.py rather than
        assumed, so this stays a thin wrapper on purpose.
        """
        window_state = self._saved_window_state()
        if window_state is None:
            return False

        self._log.debug(f"Restoring window state; size before={self.parent().size()}")
        self.restore_window_state(window_state)
        self._log.debug(f"Restored window state; size after={self.parent().size()}")
        return True

    @property
    def event_map(self):
        return {
            QEvent.WindowStateChange: self.changeEvent,
            QEvent.Close: self.closeEvent,
        }

    @property
    def commands(self):
        return {
            "minimize": self.parent().showMinimized,
            "close": self.parent().close,
            "fullscreen": self.cmd_fullscreen,
            "is_fullscreen": self.parent().isFullScreen,
        }

    def changeEvent(self, event):
        if not Settings().get("player/pause_minimized"):
            return

        # Minimize
        if self.parent().isMinimized():
            self.pre_minimize_unpaused = self._ctx.video_blocks.unpaused
            self.pause_on_minimize.emit()
        # Restore
        elif event.oldState() & Qt.WindowMinimized:
            for v in self.pre_minimize_unpaused:
                v.set_pause(False)
            self.pre_minimize_unpaused = []

    def closeEvent(self, event):
        # MOD: both of these must be read *before* close_playlist(). That call
        # emits playlist_closed, which is wired to video_blocks.close_all()
        # (blocks gone -> no volume to read) and to window_state.restore_to_minimum()
        # (window shrunk to its minimum size -> wrong geometry to store).
        remembered_volume = self._current_volume()
        remembered_window_state = self.window_state()

        if not self._ctx.commands.close_playlist():
            event.ignore()
            return True

        self._save_last_volume(remembered_volume)
        self._save_window_state(remembered_window_state)
        self._save_playlist_sort()

        self.closing.emit()

        self.parent().hide()

        force_terminate()

    def _current_volume(self):
        """MOD: volume of the active video, i.e. the one the user last used.

        Falls back to the last block that was active, then to the last block.
        Returns None when there is nothing to remember.
        """
        video_blocks = self._ctx.video_blocks
        if not video_blocks:
            return None

        block = self._ctx.active_block or self._ctx.last_active_block
        if block is None:
            block = video_blocks[-1]

        return round(float(block.video_params.volume), 2)

    def _save_last_volume(self, volume):
        """MOD: persist the volume for the next session.

        Deliberately written only on close and read only when a video is
        created, so several windows open at the same time never overwrite
        each other's volume - only a window opened *after* this one closed
        picks the value up.
        """
        if volume is None:
            return

        settings = Settings()
        settings.set("player/volume", volume)
        settings.sync()

        self._log.debug(f"Saved volume for next session: {volume}")

    def _save_playlist_sort(self):
        """MOD: carry the playlist panel's sorting over to the next session.

        Read through the context rather than importing the panel manager, and
        tolerate its absence: a window that failed before that manager was
        created still has to be closable.
        """
        try:
            key = self._ctx.playlist_sort_key
            desc = self._ctx.playlist_sort_desc
        except KeyError:
            self._log.debug("No playlist panel to carry sorting over from")
            return

        settings = Settings()
        settings.set("player/playlist_sort_key", key)
        settings.set("player/playlist_sort_desc", bool(desc))
        settings.sync()

    def _save_window_state(self, current):
        """MOD: persist the window state captured by closeEvent.

        Takes the value rather than reading it here: restore_to_minimum() has
        already shrunk the window by the time this runs (see closeEvent).
        """
        settings = Settings()

        settings.set("player/window_geometry", current.geometry)
        settings.set("player/window_maximized", current.is_maximized)
        settings.set("player/window_fullscreen", current.is_fullscreen)
        settings.sync()

        self._log.debug(
            f"Saved window state: maximized={current.is_maximized},"
            f" fullscreen={current.is_fullscreen}"
        )

    def cmd_fullscreen(self):
        if self.parent().isFullScreen():
            if self._ctx.is_maximized_pre_fullscreen:
                self.parent().showMaximized()
            else:
                self.parent().showNormal()

            self._ctx.is_maximized_pre_fullscreen = False
        else:
            self._ctx.is_maximized_pre_fullscreen = (
                self.parent().windowState() == Qt.WindowMaximized
            )

            self.parent().showFullScreen()

    def set_minimum_size(self, size):
        self.parent().setMinimumSize(size)

    def restore_to_minimum(self):
        if not self.parent().isMaximized() and not self.parent().isFullScreen():
            self.parent().resize(self.parent().minimumSize())

    def activate_window(self):
        self.parent().raise_()
        self.parent().activateWindow()

    # MOD: no videos left ----------------------------------------------------

    def close_when_empty(self):
        """Close the window when the last video goes away.

        Upstream leaves the window sitting there with the "Drag and drop media
        files or URLs here" placeholder, which is no use to anyone who just
        closed their last video.

        Deferred by one event loop turn rather than acted on straight away, for
        two reasons:

        * the count reaches zero from inside that video's own close handling
          (a tab's x, the overlay exit button), and tearing the window down with
          that still on the stack is asking for trouble;
        * emptying the grid is not the same as the user being done - loading a
          playlist over the top of another one takes the grid through zero and
          refills it again in the same turn. Waiting a turn means a refill wins
          and the window stays.
        """

        QTimer.singleShot(0, self._close_if_still_empty)

    def _close_if_still_empty(self):
        if self._ctx.video_blocks:
            return

        self._ctx.commands.close()

    def window_state(self):
        is_maximized = (
            self.parent().isMaximized() or self._ctx.is_maximized_pre_fullscreen
        )

        return WindowState(
            is_maximized=is_maximized,
            is_fullscreen=self.parent().isFullScreen(),
            geometry=base64.b64encode(bytes(self.parent().saveGeometry())).decode(),
        )

    @pyqtSlot(WindowState)
    def restore_window_state(self, window_state):
        geometry = base64.b64decode(window_state.geometry.encode())

        self.parent().restoreGeometry(geometry)

        if window_state.is_fullscreen:
            # MOD: upstream gated this on is_maximized, which is only true when
            # the window was maximized *before* going fullscreen. Fullscreen
            # entered from a normal window was therefore silently not restored.
            # Keep remembering the pre-fullscreen maximized state instead of
            # gating the restore on it.
            self._ctx.is_maximized_pre_fullscreen = window_state.is_maximized
            self.parent().showFullScreen()

        elif window_state.is_maximized:
            self.parent().showMaximized()

        else:
            # MOD: restoreGeometry() restores the window *state* recorded in the
            # blob as well as its geometry, and that state can disagree with the
            # flags stored next to it. Seen in practice: the blob said
            # fullscreen while the flags said windowed, and the window came back
            # fullscreen because neither branch above ran. The flags are the
            # authoritative record (they are read off the live window at close),
            # so enforce them.
            self.parent().showNormal()
