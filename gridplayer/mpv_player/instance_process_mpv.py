# MOD: new file - the mpv child process, and the players it hosts.
"""The process that owns mpv players.

This mirrors InstanceProcessVLCHW, with one simplification: libVLC is a shared
instance that has to be created once per process, while every mpv player owns
its own libmpv instance. Instance setup and teardown therefore have nothing to
do, and there is no per-player shared data to hand out.
"""

from gridplayer.mpv_player.player_process_mpv import PlayerProcessMPV
from gridplayer.multiprocess.instance_process import InstanceProcess


class InstanceProcessMPV(InstanceProcess):
    def __init__(self, vlc_log_level=None, **kwargs):
        # ProcessManagerVLC injects vlc_log_level for its own log wiring; mpv has
        # no equivalent, so it is accepted and ignored
        super().__init__(**kwargs)

    # process
    def init_instance(self):
        """Nothing shared to set up: each player owns its own libmpv."""

    # process
    def cleanup_instance(self):
        """Nothing shared to tear down."""

    # process
    def init_player_shared_data(self, player_id):
        """mpv players share no data with the main process."""

    # process
    def release_player_shared_data(self, player_id):
        """Nothing was handed out, so there is nothing to reclaim."""

    # process
    def new_player(self, player_id, init_data, pipe):
        player = PlayerProcessMPV(
            player_id=player_id,
            release_callback=self.release_player,
            init_data=init_data,
            crash_func=self.crash,
            pipe=pipe,
        )

        self._players[player_id] = player
