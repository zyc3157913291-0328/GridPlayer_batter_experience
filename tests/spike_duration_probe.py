"""SPIKE - not a regression test.

Can we read a file's duration from a second libvlc instance inside the app
process, without disturbing playback?

Round 1 taught us that parse_with_options() is asynchronous: it returned in 0 ms
and get_duration() gave -1. This round brackets it with a status poll that has
its own wall-clock deadline, which is what a background prober needs anyway
(parse() would be synchronous but "could block indefinitely").
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import ROOT, SAMPLES, bootstrap, sample

bootstrap()

from gridplayer.vlc_player import vlc

PARSE_TIMEOUT_MS = 5000

FILES = [
    sample("probe.mp4"),
    sample("probe.mov"),
    ROOT / "libVLC" / "libvlc.dll",  # not media: must not hang
    ROOT / "README.md",  # not media either
]

POLL_INTERVAL = 0.02
FINAL_STATES = (
    vlc.MediaParsedStatus.done,
    vlc.MediaParsedStatus.failed,
    vlc.MediaParsedStatus.timeout,
)


def probe(instance, path, timeout_ms=PARSE_TIMEOUT_MS):
    media = instance.media_new_path(str(path))

    start = time.monotonic()
    media.parse_with_options(vlc.MediaParseFlag.local, timeout_ms)

    deadline = start + timeout_ms / 1000 + 1.0
    status = None

    while time.monotonic() < deadline:
        status = media.get_parsed_status()
        if status in FINAL_STATES:
            break
        time.sleep(POLL_INTERVAL)

    duration = media.get_duration()
    media.release()

    return duration, status, (time.monotonic() - start) * 1000


print("creating a dedicated libvlc instance (no video, no audio)...")
instance = vlc.Instance("--no-video", "--no-audio", "--quiet")
print(f"  instance = {instance}")

if instance is None:
    print("SPIKE RESULT: FAIL - could not create a second libvlc instance")
    sys.exit(2)

print()
print(f"{'file':14s} {'duration':>10s} {'status':>10s} {'elapsed':>10s}")
print("-" * 50)

good = 0
for path in SAMPLES:
    if not path.is_file():
        print(f"{path.name:14s} {'MISSING':>10s}")
        continue

    try:
        duration, status, elapsed_ms = probe(instance, path)
        label = getattr(status, "name", None) or str(status)
        print(f"{path.name:14s} {duration:>10} {label:>10} {elapsed_ms:>9.0f}ms")
        if duration and duration > 0:
            good += 1
    except Exception as e:  # noqa: BLE001
        print(f"{path.name:14s} RAISED {e!r}")

instance.release()
print()
print(f"SPIKE RESULT: {good} media file(s) returned a positive duration")

if good >= 2:
    print("=> in-process probing is VIABLE; P3 keeps duration sorting as planned")
else:
    print("=> in-process probing did NOT work; report to the user before continuing")
