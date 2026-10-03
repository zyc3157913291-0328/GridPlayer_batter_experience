import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("duration cache")

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.duration_cache import CACHE_FILE_NAME, DurationCache

video = data_dir / "v.mp4"
video.write_bytes(b"x" * 100)
entry = MediaEntry(video, "v.mp4", 100, 111.0)

cache = DurationCache()
c.check("miss on empty cache", cache.get(entry) is None)

cache.put(entry, 3000)
c.check("hit after put", cache.get(entry) == 3000)

cache.save()
path = data_dir / CACHE_FILE_NAME
c.check("cache file written", path.is_file())

raw = json.loads(path.read_text(encoding="utf-8"))
c.check("keyed by casefolded path", raw[entry.key]["duration_ms"] == 3000, f"{raw}")

c2 = DurationCache()
c2.load()
c.check("reloads from disk", c2.get(entry) == 3000)

# --- the path is matched case-insensitively (same key after casefold) ---
upper = MediaEntry(Path(str(video).upper()), "V.MP4", 100, 111.0)
c.check("path match is case-insensitive", c2.get(upper) == 3000, f"{upper.key}")

# --- invalidation on size change ---
changed_size = MediaEntry(video, "v.mp4", 999, 111.0)
c.check("size change invalidates", c2.get(changed_size) is None)

# --- invalidation on mtime change ---
changed_mtime = MediaEntry(video, "v.mp4", 100, 222.0)
c.check("mtime change invalidates", c2.get(changed_mtime) is None)

# --- unknown durations are not cached ---
# NOTE: the plan used `entry` here, but that key already holds a valid 3000 ms
# record in c2, so the plan's own put() (early return on None) would leave it
# readable and the check could never pass. The intent - a None result is never
# stored as a duration - is checked with a never-probed key, plus an explicit
# check that a failed probe does not erase a duration we already know.
never_probed = MediaEntry(data_dir / "unknown.mp4", "unknown.mp4", 100, 111.0)
c2.put(never_probed, None)
c.check("None not cached as a hit", c2.get(never_probed) is None)
c2.put(entry, None)
c.check("None put keeps an existing hit", c2.get(entry) == 3000)

# --- valid JSON that is not an object degrades to empty ---
path.write_text("[]", encoding="utf-8")
c3 = DurationCache()
c3.load()
c.check("non-dict json degrades to empty", c3.get(entry) is None)

# --- corrupt file degrades to empty ---
path.write_text("nonsense", encoding="utf-8")
c4 = DurationCache()
c4.load()
c.check("corrupt cache degrades to empty", c4.get(entry) is None)

c.finish()
