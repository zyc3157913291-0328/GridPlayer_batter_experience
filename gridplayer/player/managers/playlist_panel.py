# MOD: new file - owns the playlist side panel and the per-block folder listings.
"""MOD: owns the playlist side panel and the per-block folder listings."""

import sys
from pathlib import Path

from PyQt5.QtCore import QProcess, pyqtSignal, pyqtSlot

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.duration_probe import DurationProber
from gridplayer.utils.media_folder import scan_folder
from gridplayer.utils.play_history import PlayHistory
from gridplayer.utils.single_instance import NEW_WINDOW_FLAG
from gridplayer.utils.thumbnail_probe import ThumbnailProvider
from gridplayer.widgets.playlist_panel import PlaylistPanel, show_in_splitter


class PlaylistPanelManager(ManagerBase):
    panel_visibility_changed = pyqtSignal(bool)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._history = PlayHistory()
        self._history.load()

        self._prober = DurationProber(parent=self)
        self._thumbs = ThumbnailProvider(parent=self)

        self._panel = PlaylistPanel(self.parent())
        self._panel.hide()
        self._last_width = 0
        self._last_remembered = None
        self._panel.entry_activated.connect(self._play_entry)
        self._panel.entry_play_next.connect(self._play_next)
        self._panel.entry_new_window.connect(self._open_new_window)
        self._panel.entry_add_to_grid.connect(self._add_to_grid)
        self._panel.sort_changed.connect(self._on_sort_changed)
        self._panel.set_history(self._history.as_mapping())
        self._panel.set_sort(
            Settings().get("player/playlist_sort_key"),
            Settings().get("player/playlist_sort_desc"),
        )

        # grid creates these; this manager must be registered after "grid" in
        # Player.managers or Context.__getattr__ raises KeyError here.
        # addWidget (not insertWidget(0)) puts the panel on the RIGHT of the
        # video area; show_in_splitter() reads the index back to size it.
        self._ctx.layout_splitter.addWidget(self._panel)

        self._prober.duration_ready.connect(self._on_duration_ready)
        self._thumbs.thumbnail_ready.connect(self._panel.set_thumbnail)

        # read lazily on close, so window_state can persist them
        self._ctx.playlist_sort_key = lambda: self._panel.sort_key
        self._ctx.playlist_sort_desc = lambda: bool(self._panel.sort_desc)

    @property
    def commands(self):
        return {
            "toggle_playlist_panel": self.cmd_toggle,
            "is_playlist_panel_visible": lambda: self._panel.isVisible(),
        }

    # --- visibility ---

    def cmd_toggle(self):
        self.set_panel_visible(self._panel.isHidden())

    def set_panel_visible(self, is_visible: bool):
        if is_visible:
            show_in_splitter(self._ctx.layout_splitter, self._panel, self._last_width)
            self._last_width = self._panel.width()
        else:
            self._last_width = self._panel.width()
            self._panel.setVisible(False)

        self.panel_visibility_changed.emit(bool(is_visible))

        if is_visible:
            self.refresh()

    # --- list building ---

    def on_active_block_changed(self, block):
        if block is None:
            return

        self.refresh()

    def _target_block(self):
        """Which block the panel is acting on.

        Not ctx.active_block directly: ActiveBlockManager drives that from the
        pointer (update_active_under_mouse / update_active_reset), so it is None
        whenever the cursor sits off the video area - over the title bar or the
        panel's own sort header, for instance. Reading it raw silently dropped
        playlist clicks in exactly that situation. Fall back to the remembered
        block the same way window_state.py does, and to the only block there is
        when the pointer has never entered the grid at all.
        """
        block = self._ctx.active_block
        if block is not None:
            self._ctx.last_active_block = block
            return block

        try:
            last = self._ctx.last_active_block
        except KeyError:
            last = None

        if last is not None:
            return last

        blocks = self._ctx.video_blocks

        return blocks[0] if len(blocks) == 1 else None

    def refresh(self):
        """Rebuild the list for whatever the active block is playing."""
        if self._panel.isHidden():
            return

        block = self._target_block()
        if block is None:
            # Nothing to show. Only clear when there really is nothing at all;
            # otherwise leave the current listing alone rather than wiping it.
            if not self._ctx.video_blocks:
                self._panel.set_entries([], None)
            return

        uri = block.video_params.uri
        if not isinstance(uri, Path):
            return

        # Only write history when the file actually changed. refresh() runs on
        # every active-block change, and the pointer crossing a grid would
        # otherwise hit the disk each time.
        if uri != self._last_remembered:
            self._last_remembered = uri
            self._remember(uri)

        entries = scan_folder(uri)

        for i, entry in enumerate(entries):
            cached = self._prober.cached(entry)
            if cached is not None:
                entries[i] = entry.with_duration(cached)

        self._panel.set_history(self._history.as_mapping())
        self._panel.set_entries(entries, uri)
        self._prober.request(entries)
        self._thumbs.request(entries)

    # --- reactions ---

    @pyqtSlot(str, object)
    def _on_duration_ready(self, entry_key, duration_ms):
        self._panel.update_duration(entry_key, duration_ms)

    def _play_entry(self, path):
        block = self._target_block()
        if block is None:
            return

        self._remember(Path(path))
        self._panel.set_history(self._history.as_mapping())

        block.switch_video(Path(path))
        self._panel.set_current(Path(path))

    def _play_next(self, path):
        """Queue this file to follow the current one, without interrupting it."""
        block = self._target_block()
        if block is None:
            return

        block.set_next_override(Path(path))

    def _open_new_window(self, path):
        """Start a genuinely separate window.

        --new-window stops the new process from handing its arguments to this
        one, which is what one_instance would otherwise do.
        """
        entry_script = Path(sys.argv[0]).resolve()

        QProcess.startDetached(
            sys.executable,
            [str(entry_script), str(Path(path)), NEW_WINDOW_FLAG],
            str(entry_script.parent),
        )

    def _add_to_grid(self, path):
        """Append the file to the grid as a new block.

        Goes through AddVideosManager's command rather than touching the
        VideoBlocks collection: add_videos lives on the manager, and the
        context's video_blocks is the plain collection.
        """
        self._ctx.commands.add_files([Path(path).resolve()])

    def _remember(self, uri: Path):
        self._history.record(str(uri).casefold())
        self._history.save()

    def _on_sort_changed(self, key, desc):
        Settings().set("player/playlist_sort_key", key)
        Settings().set("player/playlist_sort_desc", bool(desc))
        Settings().sync()

    def save_sort_settings(self):
        """Called on close so the next window starts with the same sorting."""
        Settings().set("player/playlist_sort_key", self._panel.sort_key)
        Settings().set("player/playlist_sort_desc", bool(self._panel.sort_desc))
        Settings().sync()

    def cleanup(self):
        self._prober.stop()
        self._thumbs.stop()
