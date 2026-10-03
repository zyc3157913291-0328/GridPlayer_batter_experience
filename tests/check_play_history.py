import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("play history")

from gridplayer.utils.play_history import (
    HISTORY_FILE_NAME,
    HISTORY_MAX_ENTRIES,
    PlayHistory,
)

h = PlayHistory()
c.check("starts empty", h.as_mapping() == {})

h.record("a.mp4", when_ms=1000)
h.record("b.mp4", when_ms=2000)
c.check("records kept", h.get("a.mp4") == 1000 and h.get("b.mp4") == 2000)
c.check("unknown key -> None", h.get("zzz.mp4") is None)

h.record("a.mp4", when_ms=3000)
c.check("re-record overwrites", h.get("a.mp4") == 3000)

h.save()
path = data_dir / HISTORY_FILE_NAME
c.check("file written", path.is_file(), str(path))

raw = json.loads(path.read_text(encoding="utf-8"))
c.check("file is a flat path->ts map", raw.get("a.mp4") == 3000, f"{raw}")

h2 = PlayHistory()
h2.load()
c.check("reloads from disk", h2.get("a.mp4") == 3000 and h2.get("b.mp4") == 2000)

# --- pruning keeps the newest N ---
h3 = PlayHistory()
for i in range(HISTORY_MAX_ENTRIES + 50):
    h3.record(f"f{i}.mp4", when_ms=i)
h3.prune()
kept = h3.as_mapping()
c.check("pruned to the cap", len(kept) == HISTORY_MAX_ENTRIES, f"{len(kept)}")
c.check("oldest dropped", "f0.mp4" not in kept)
c.check("newest kept", f"f{HISTORY_MAX_ENTRIES + 49}.mp4" in kept)

# --- corrupt file must not crash ---
path.write_text("{ this is not json", encoding="utf-8")
h4 = PlayHistory()
h4.load()
c.check("corrupt file degrades to empty", h4.as_mapping() == {})

# --- case-insensitive keys ---
h5 = PlayHistory()
h5.record(r"E:\Movies\Film.MP4".casefold(), when_ms=7)
c.check(
    "keys are casefolded by the caller's convention",
    h5.get(r"E:\Movies\Film.MP4".casefold()) == 7,
)

# --- loading an oversized file prunes it to the cap ---
oversized = {f"old{i}.mp4": i for i in range(HISTORY_MAX_ENTRIES + 25)}
path.write_text(json.dumps(oversized), encoding="utf-8")
h6 = PlayHistory()
h6.load()
c.check(
    "load prunes an oversized file",
    len(h6.as_mapping()) == HISTORY_MAX_ENTRIES,
    f"{len(h6.as_mapping())}",
)

c.finish()
