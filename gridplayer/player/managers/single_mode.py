from pathlib import Path

from PyQt5.QtCore import QEvent, Qt, pyqtSignal

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.widgets.video_overlay_tabs import STYLES as TAB_STYLES


class SingleModeManager(ManagerBase):
    mode_changed = pyqtSignal()
    # MOD: single-mode tab strip payload - (list of (block_id, label), id of the
    # block that currently fills the screen, or None when there is no strip)
    tabs_changed = pyqtSignal(object, object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_single_mode = False

        self._pre_sm_states = {}

    @property
    def event_map(self):
        return {
            QEvent.MouseButtonDblClick: self.mouseDoubleClickEvent,
        }

    @property
    def commands(self):
        return {
            "next_single_video": self.next_single_video,
            "previous_single_video": self.previous_single_video,
            "toggle_single_video": self.toggle_single_video,
            "is_single_mode": lambda: self._ctx.is_single_mode,
            "is_more_than_one_video": lambda: len(self._ctx.video_blocks) > 1,
        }

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        # MOD: double-click now drives fullscreen as well as the in-grid zoom.
        # The four cases are deliberately distinguished by video count, because
        # with a single video there is no "zoom" state to toggle into.
        is_fullscreen = self.parent().isFullScreen()

        if len(self._ctx.video_blocks) <= 1:
            # one video: windowed <-> fullscreen (cmd_fullscreen keeps whatever
            # maximized state the window had before going fullscreen)
            self._ctx.commands.fullscreen()
        elif not is_fullscreen:
            # several videos, windowed: go fullscreen
            self._ctx.commands.fullscreen()
        else:
            # several videos, fullscreen: zoom this one into the grid, or step
            # back to the grid if it is already zoomed
            self.toggle_single_video()

    def set_video_count(self, video_count):
        """Exit single mode when number of videos change"""

        was_single_mode = self._ctx.is_single_mode

        self.single_mode_off()

        # MOD: video_count_changed is wired to grid.reload_video_grid *before*
        # it reaches this manager (that is the order Player.connections is built
        # in), so the grid has just been rebuilt while the other blocks were
        # still hidden by single mode. At that moment visible_count is 1, the
        # grid collapses to 1x1 and every remaining video is crammed into a
        # single row instead of the proper layout.
        #
        # Now that single_mode_off() has shown them all again, rebuild the grid
        # so it matches. Only when single mode was actually on: reloading the
        # grid while it is on would be worse, not better - the one visible block
        # would then only get its share of a single collapsed row.
        if was_single_mode:
            self._ctx.commands.reload_video_grid()

    def toggle_single_video(self):
        if len(self._ctx.video_blocks) <= 1:
            return

        if self._ctx.is_single_mode:
            self.single_mode_off()
        else:
            self.single_mode_on()

    def next_single_video(self):
        self._switch_single_video(is_before=False)

    def previous_single_video(self):
        self._switch_single_video(is_before=True)

    # MOD: bring one particular video to the screen, driven by the overlay tab
    # strip (clicking a tab). Shares the switch bookkeeping with next/previous.
    def switch_to_single_video(self, block_id):
        if not self._ctx.is_single_mode:
            return

        target = self._ctx.video_blocks.by_id(block_id)
        current_sv = self._current_single_video()

        if target is None or current_sv is None or target is current_sv:
            return

        self._activate_single_video(current_sv, target)

    def single_mode_on(self):
        self._ctx.is_single_mode = True

        is_pause_background_videos = Settings().get("player/pause_background_videos")

        for vb in self._ctx.video_blocks:
            if vb == self._ctx.active_block:
                continue

            if is_pause_background_videos:
                self._pre_sm_states[vb.id] = vb.video_params.is_paused
                vb.set_pause(True)

            vb.hide()

        self.mode_changed.emit()

        self._update_tabs()

    def single_mode_off(self):
        self._ctx.is_single_mode = False

        for vb in self._ctx.video_blocks:
            if vb == self._ctx.active_block:
                continue

            pre_sm_state = self._pre_sm_states.pop(vb.id, None)
            if pre_sm_state is not None:
                vb.set_pause(pre_sm_state)

            vb.show()

        self.mode_changed.emit()

        self._update_tabs()

    def _switch_single_video(self, is_before):
        if not self._ctx.is_single_mode:
            return

        current_sv = self._current_single_video()

        if current_sv is None:
            return

        next_sv = self._find_next_single_video(current_sv, is_before)

        self._activate_single_video(current_sv, next_sv)

    def _activate_single_video(self, current_sv, next_sv):
        is_pause_background_videos = Settings().get("player/pause_background_videos")

        # MOD: if the controls were on screen when the switch was triggered -
        # clicking a tab requires exactly that - keep them on screen on the
        # video coming up, otherwise the strip would vanish from under the
        # pointer and there would be no way to click a second tab.
        was_overlay_visible = current_sv.overlay.isVisible()

        if is_pause_background_videos:
            self._pre_sm_states[current_sv.id] = current_sv.video_params.is_paused
            current_sv.set_pause(True)
        current_sv.hide()

        pre_sm_state = self._pre_sm_states.pop(next_sv.id, None)
        if pre_sm_state is not None:
            next_sv.set_pause(pre_sm_state)

        next_sv.show()

        if was_overlay_visible:
            next_sv.show_overlay()

        self._update_tabs()

    def _find_next_single_video(self, current_sv, is_before):
        if is_before:
            next_sv_idx = self._ctx.video_blocks.index(current_sv) - 1
        else:
            next_sv_idx = self._ctx.video_blocks.index(current_sv) + 1

        if next_sv_idx > len(self._ctx.video_blocks) - 1:
            next_sv_idx = 0

        return self._ctx.video_blocks[next_sv_idx]

    # MOD: tab strip ----------------------------------------------------------

    def set_tab_style(self, style):
        """Switch the tab strip between the plain and the merged look.

        The strip reads the style back out of settings on every rebuild, so
        storing it and pushing the tabs again is all that is needed - the cached
        payload check inside the tab bar also looks at the style, which is what
        makes an otherwise unchanged push rebuild it.
        """

        if style not in TAB_STYLES:
            return

        Settings().set("misc/tab_style", style)
        Settings().sync()

        self._update_tabs()

    def _current_single_video(self):
        """The block that is currently filling the screen, if any."""

        return next((v for v in self._ctx.video_blocks if v.isVisible()), None)

    def _update_tabs(self):
        tabs, current_id = self._tabs_payload()

        self.tabs_changed.emit(tabs, current_id)

    def _tabs_payload(self):
        current_sv = self._current_single_video() if self._ctx.is_single_mode else None

        if current_sv is None:
            return [], None

        tabs = [(vb.id, _tab_label(vb)) for vb in self._ctx.video_blocks]

        return tabs, current_sv.id


def _tab_label(block):
    """Filename with extension for local files, title for everything else."""

    uri = getattr(block.video_params, "uri", None)

    if isinstance(uri, Path):
        return uri.name

    return block.title or str(uri or "")
