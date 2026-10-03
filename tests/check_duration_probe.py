"""Real libvlc duration probing against the sample clips.

This is the test the plan left out (Task 4 Step 1 only covers the cache, "探测本身
依赖真实 VLC，留给 Task 9 的 GUI 验证"). It probes the real files with the bundled
libVLC and drives DurationProber's QThread for real, so a broken probe path fails
here instead of only showing up in the GUI.

Needs: libVLC/ under the repo root (bootstrap() points PYTHON_VLC_LIB_PATH at it)
and the sample clips in tests/samples/.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap, sample

data_dir = bootstrap()
c = Checker("duration probe")

from PyQt5.QtWidgets import QApplication

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.duration_cache import CACHE_FILE_NAME
from gridplayer.utils.duration_probe import (
    PROBE_TIMEOUT_MS,
    DurationProber,
    probe_duration,
)
from gridplayer.vlc_player import vlc

MP4 = sample("probe.mp4")
MOV = sample("probe.mov")

c.check(
    "sample clips present",
    MP4.is_file() and MOV.is_file(),
    f"{MP4.parent} ({MP4.is_file()=}, {MOV.is_file()=})",
)

if not (MP4.is_file() and MOV.is_file()):
    c.finish()

# a non-media file next to the samples' data dir, plus a path that is not there
not_media = data_dir / "not_media.txt"
not_media.write_text("this is not a video\n", encoding="utf-8")

start = time.monotonic()
instance = vlc.Instance("--no-video", "--no-audio", "--quiet")
instance_ms = (time.monotonic() - start) * 1000

c.check(
    "probing libvlc instance created", instance is not None, f"{instance_ms:.0f} ms"
)

# --- the pure probe function: no Qt thread, no event loop needed ---
mp4_ms = probe_duration(instance, MP4)
c.check(
    "probe.mp4 -> ~3000 ms",
    isinstance(mp4_ms, int) and 2500 <= mp4_ms <= 3500,
    f"got {mp4_ms!r}",
)

mov_ms = probe_duration(instance, MOV)
c.check(
    "probe.mov -> ~3000 ms",
    isinstance(mov_ms, int) and 2500 <= mov_ms <= 3500,
    f"got {mov_ms!r}",
)

# --- non-media must degrade to None, not hang or raise ---
edge_timeout = 2000

start = time.monotonic()
not_media_ms = probe_duration(instance, not_media, edge_timeout)
not_media_s = time.monotonic() - start
c.check(
    "non-media text file -> None",
    not_media_ms is None,
    f"got {not_media_ms!r} in {not_media_s * 1000:.0f} ms",
)

missing_ms = probe_duration(instance, data_dir / "no_such_file.mp4", edge_timeout)
c.check("missing path -> None", missing_ms is None, f"got {missing_ms!r}")

dir_ms = probe_duration(instance, data_dir, edge_timeout)
c.check("directory -> None", dir_ms is None, f"got {dir_ms!r}")

c.check("no instance -> None", probe_duration(None, MP4) is None)

path_ms = probe_duration(instance, MP4, PROBE_TIMEOUT_MS)
c.check(
    "re-probing the same file gives the same answer",
    path_ms == mp4_ms,
    f"{path_ms} vs {mp4_ms}",
)

instance.release()

# --- the real worker path: DurationProber over a live QThread ---
clips = [MP4, MOV, not_media]
entries = [MediaEntry(p, p.name, p.stat().st_size, p.stat().st_mtime) for p in clips]

prober = DurationProber()
seen = {}


def on_ready(entry_key, duration_ms):
    seen[entry_key] = duration_ms


prober.duration_ready.connect(on_ready)

start = time.monotonic()
prober.request(entries)

deadline = time.monotonic() + 30
while len(seen) < len(entries) and time.monotonic() < deadline:
    QApplication.processEvents()
    time.sleep(0.01)

batch_s = time.monotonic() - start

c.check(
    "worker reported every entry",
    len(seen) == len(entries),
    f"{len(seen)}/{len(entries)} after {batch_s * 1000:.0f} ms",
)

worker_mp4 = seen.get(entries[0].key)
c.check(
    "worker: probe.mp4 ~3000 ms",
    isinstance(worker_mp4, int) and 2500 <= worker_mp4 <= 3500,
    f"got {worker_mp4!r}",
)

worker_mov = seen.get(entries[1].key)
c.check(
    "worker: probe.mov ~3000 ms",
    isinstance(worker_mov, int) and 2500 <= worker_mov <= 3500,
    f"got {worker_mov!r}",
)

c.check(
    "worker: non-media -> None",
    entries[2].key in seen and seen[entries[2].key] is None,
    f"got {seen.get(entries[2].key)!r}",
)

c.check(
    "probed durations are cache hits",
    prober.cached(entries[0]) == worker_mp4 and prober.cached(entries[1]) == worker_mov,
    f"{prober.cached(entries[0])!r}, {prober.cached(entries[1])!r}",
)

prober.stop()

cache_path = data_dir / CACHE_FILE_NAME
c.check("cache written on stop", cache_path.is_file(), f"{cache_path}")

raw = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
c.check(
    "cache holds the probed clip",
    raw.get(entries[0].key, {}).get("duration_ms") == worker_mp4,
    f"{raw.get(entries[0].key)}",
)
c.check(
    "unknown durations stay out of the cache",
    entries[2].key not in raw,
    f"{sorted(raw)}",
)

# --- a fresh prober reads those durations back from disk, no probing ---
prober2 = DurationProber()
c.check(
    "fresh prober serves the mp4 from disk cache",
    prober2.cached(entries[0]) == worker_mp4,
    f"{prober2.cached(entries[0])!r}",
)
c.check(
    "fresh prober has no duration for the non-media file",
    prober2.cached(entries[2]) is None,
)
prober2.stop()

print(
    f"\nmeasured: probe.mp4={mp4_ms} ms  probe.mov={mov_ms} ms  "
    f"non-media={not_media_ms!r}  instance={instance_ms:.0f} ms  "
    f"worker batch={batch_s * 1000:.0f} ms"
)

c.finish()
