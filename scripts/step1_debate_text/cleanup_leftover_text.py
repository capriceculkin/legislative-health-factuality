#!/usr/bin/env python3
"""
cleanup_leftover_text.py

The text folders keep files from earlier runs: a rebuild writes the files of the bill-days it has now, but
never deletes the file of a bill-day an earlier run had and this one does not (on Oct 3 GitHub had 1,580
Ontario files for 1,537 bill-days, and 953 Quebec files for 943 sections). Those old files sit next to the
real ones and can be opened from GitHub as if they were current.

A file is moved out only when BOTH hold:
  1. the current index does not list it (Ontario hansard_segments_v3.json, Quebec segments_index.json,
     US segments_index.json), and
  2. it was written before this run started (--since <time>; without it: a minute before the index), so an
     earlier run wrote it. A file this run wrote is never moved
Moved files go to data/_leftover_text_<time>/ (same folder layout), so nothing is deleted. Files that fail
only one of the two tests stay where they are and are listed.

Run from the project folder AFTER the rebuilds:  python3 scripts/step1_debate_text/cleanup_leftover_text.py [--since <unix time>]
Add --dry-run to list without moving.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
DRY = "--dry-run" in sys.argv
SINCE = float(sys.argv[sys.argv.index("--since") + 1]) if "--since" in sys.argv else None
STAMP = time.strftime("%Y%m%d-%H%M%S")
DEST = ROOT / "data" / f"_leftover_text_{STAMP}"


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def listed_ontario():
    idx = ROOT / "data/canada/ontario/v3/hansard_segments_v3.json"
    seg = load(idx)
    if not isinstance(seg, dict):
        return None, idx
    return {(ROOT / "data/canada/ontario/v3/bill_texts" / k / f"{d}.txt").resolve() for k, days in seg.items()
            for d in days}, idx


def listed_quebec():
    idx = ROOT / "data/canada/quebec_assembly/v3/segments_index.json"
    seg = load(idx)
    if not isinstance(seg, list):
        return None, idx
    return {(ROOT / "data/canada/quebec_assembly" / e["file"]).resolve() for e in seg if e.get("file")}, idx


def listed_us():
    idx = ROOT / "data/us/v3/segments_index.json"
    seg = load(idx)
    if not isinstance(seg, list):
        return None, idx
    return {(ROOT / "data/us" / e["file"]).resolve() for e in seg if e.get("file")}, idx


FOLDERS = [("Ontario", ROOT / "data/canada/ontario/v3/bill_texts", listed_ontario),
           ("Quebec", ROOT / "data/canada/quebec_assembly/v3/bill_segments_v3", listed_quebec),
           ("US", ROOT / "data/us/v3/cr_segments_v3", listed_us)]

total = 0
for name, folder, fn in FOLDERS:
    listed, idx = fn()
    if listed is None or not folder.is_dir():
        print(f"{name}: index or folder missing ({idx}); nothing done here")
        continue
    t_cut = SINCE if SINCE is not None else idx.stat().st_mtime - 60
    files = [p for p in folder.rglob("*.txt") if p.is_file()]
    here = {p.resolve() for p in files}
    not_listed = [p for p in files if p.resolve() not in listed]
    old = [p for p in not_listed if p.stat().st_mtime < t_cut]
    new_unlisted = [p for p in not_listed if p not in old]
    missing = sorted(listed - here)
    print(f"{name}: {len(files)} files; listed in the index {len(listed)}; listed but no file {len(missing)}; "
          f"not listed {len(not_listed)} (older than the index: {len(old)}, written by this run: {len(new_unlisted)})")
    for p in missing[:5]:
        print(f"   listed but no file: {p.relative_to(ROOT)}")
    for p in new_unlisted[:10]:
        print(f"   NOT MOVED (not listed, but written by this run): {p.relative_to(ROOT)}")
    for p in old[:8]:
        print(f"   {'would move' if DRY else 'moving'}: {p.relative_to(ROOT)}")
    if len(old) > 8:
        print(f"   ... and {len(old) - 8} more")
    if missing and len(missing) > 0.1 * max(len(listed), 1) or len(old) > max(60, 0.2 * len(files)):
        print(f"   NOT MOVING anything in {name}: too many files would move or are missing, which points to a "
              "path mismatch rather than leftovers. Send this output to Claude.")
        continue
    if not DRY:
        for p in old:
            d = DEST / p.relative_to(ROOT)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(d))
        for d in sorted({p.parent for p in old}, key=lambda x: -len(x.parts)):
            if d != folder and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        after = sum(1 for p in folder.rglob("*.txt") if p.is_file())
        print(f"   {name} files now: {after}; index entries: {len(listed)}"
              + ("  (same)" if after == len(listed) else "  (DIFFERENT, see the lines above)"))
    total += len(old)
print(f"{'would move' if DRY else 'moved'} {total} old file(s)" + ("" if DRY or not total else f" to {DEST.relative_to(ROOT)}"))
