import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("media folder")

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.media_folder import natural_key, scan_folder, sort_entries

# --- build a folder with a known shape ---
folder = data_dir / "videos"
folder.mkdir()
for name, size in (
    ("clip 2.mp4", 200),
    ("clip 10.mp4", 100),
    ("b.mkv", 300),
    ("a.MOV", 400),
    ("notes.txt", 10),
    ("sub", 0),
):
    p = folder / name
    if name == "sub":
        p.mkdir()
    else:
        p.write_bytes(b"x" * size)

# stagger mtimes so mtime ordering is deterministic
base = time.time() - 1000
for i, name in enumerate(("clip 2.mp4", "clip 10.mp4", "b.mkv", "a.MOV")):
    os.utime(folder / name, (base + i * 100, base + i * 100))

entries = scan_folder(folder / "clip 2.mp4")

c.check(
    "only media files, no dirs", len(entries) == 4, f"{sorted(e.name for e in entries)}"
)
c.check("non-media excluded", all(e.name != "notes.txt" for e in entries))
c.check("directory excluded", all(e.name != "sub" for e in entries))
c.check("sizes captured", {e.name: e.size for e in entries}["b.mkv"] == 300)
c.check("duration starts unknown", all(e.duration_ms is None for e in entries))

# --- natural order ---
c.check(
    "natural_key puts 2 before 10",
    natural_key("clip 2.mp4") < natural_key("clip 10.mp4"),
)

# --- name sort, ascending / descending ---
names_asc = [e.name for e in sort_entries(entries, "name", False, {})]
c.check(
    "name asc is natural",
    names_asc == ["a.MOV", "b.mkv", "clip 2.mp4", "clip 10.mp4"],
    f"{names_asc}",
)
names_desc = [e.name for e in sort_entries(entries, "name", True, {})]
c.check("name desc reverses", names_desc == list(reversed(names_asc)), f"{names_desc}")

# --- size sort ---
sizes_desc = [e.size for e in sort_entries(entries, "size", True, {})]
c.check("size desc", sizes_desc == [400, 300, 200, 100], f"{sizes_desc}")

# --- mtime sort ---
mt_desc = [e.name for e in sort_entries(entries, "mtime", True, {})]
c.check("mtime desc = newest first", mt_desc[0] == "a.MOV", f"{mt_desc}")
mt_asc = [e.name for e in sort_entries(entries, "mtime", False, {})]
c.check(
    "mtime asc = oldest first (full order)",
    mt_asc == list(reversed(mt_desc)),
    f"{mt_asc}",
)

# --- history: unknown always last, both directions ---
history = {entries[0].key: 500, entries[1].key: 900}
hist_desc = sort_entries(entries, "history", True, history)
c.check("history desc: newest played first", hist_desc[0].key == entries[1].key)
# full order: played by timestamp, then unplayed in natural name order
# (entries[0] is a.MOV -> 500, entries[1] is b.mkv -> 900)
c.check(
    "history desc: played by timestamp, unplayed after in name order",
    [e.name for e in hist_desc] == ["b.mkv", "a.MOV", "clip 2.mp4", "clip 10.mp4"],
    f"{[e.name for e in hist_desc]}",
)
c.check(
    "history desc: unplayed last",
    hist_desc[-1].key not in history,
    f"{[e.name for e in hist_desc]}",
)
hist_asc = sort_entries(entries, "history", False, history)
c.check(
    "history asc: played by timestamp, unplayed after in name order",
    [e.name for e in hist_asc] == ["a.MOV", "b.mkv", "clip 2.mp4", "clip 10.mp4"],
    f"{[e.name for e in hist_asc]}",
)
c.check(
    "history asc: unplayed STILL last",
    all(e.key in history for e in hist_asc[:2])
    and all(e.key not in history for e in hist_asc[2:]),
    f"{[e.name for e in hist_asc]}",
)

# --- duration: unknown always last, both directions ---
d = [
    MediaEntry(folder / "x1.mp4", "x1.mp4", 1, 0.0, 9000),
    MediaEntry(folder / "x2.mp4", "x2.mp4", 1, 0.0, None),
    MediaEntry(folder / "x3.mp4", "x3.mp4", 1, 0.0, 1000),
]
dur_desc = [e.name for e in sort_entries(d, "duration", True, {})]
c.check("duration desc", dur_desc == ["x1.mp4", "x3.mp4", "x2.mp4"], f"{dur_desc}")
dur_asc = [e.name for e in sort_entries(d, "duration", False, {})]
c.check(
    "duration asc: unknown last",
    dur_asc == ["x3.mp4", "x1.mp4", "x2.mp4"],
    f"{dur_asc}",
)

# --- ties keep name order (stable) ---
tied = [
    MediaEntry(folder / "z.mp4", "z.mp4", 5, 0.0),
    MediaEntry(folder / "a.mp4", "a.mp4", 5, 0.0),
]
c.check(
    "ties fall back to name order",
    [e.name for e in sort_entries(tied, "size", True, {})] == ["a.mp4", "z.mp4"],
)

# --- scanning a file whose folder is gone does not raise ---
c.check("missing folder -> empty list", scan_folder(folder / "nope" / "x.mp4") == [])

c.finish()
