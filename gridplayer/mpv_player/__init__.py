# MOD: new file - mpv playback driver package.
"""mpv playback driver for GridPlayer.

Why this package exists
-----------------------

libVLC re-clocks its audio output every time the playback rate changes, which
drops the sound for a moment. Measured on this machine: disabling the time
stretcher, swapping the audio module, switching the resampler and ramping the
rate all left the dropout in place, while mpv changes speed with no gap and no
pitch shift at all. The engine is therefore the thing that has to change; this
package adds one, alongside the existing VLC drivers rather than replacing them.

The driver is selected with the usual ``player/video_driver`` setting.

Vendored dependency
-------------------

``mpv.py`` in this directory is python-mpv, vendored verbatim the same way
``gridplayer/vlc_player/vlc.py`` is vendored python-vlc. It is not modified, so
it can be replaced wholesale when a newer release is wanted.

    upstream : https://github.com/jaseg/python-mpv
    version  : 1.0.8
    commit   : 93c4de9bb7a0  (2025-04-25)
    sha256   : c05b55fcca8659486e801b32b70008d47219ffa83181a35db26876e18f89ce4f
    licence  : GPL-2.0-or-later, or LGPL-2.1-or-later (dual, see the file header)

The upstream file is GPL-2.0 **or later**, which is what makes it compatible
with this repository's GPL-3.0.

Runtime requirement
-------------------

python-mpv locates libmpv through ``PATH`` (it looks for ``libmpv-2.dll``,
``mpv-2.dll`` or ``mpv-1.dll``). This package therefore has to put the
directory holding that DLL on ``PATH`` **before** ``mpv.py`` is imported.
"""
