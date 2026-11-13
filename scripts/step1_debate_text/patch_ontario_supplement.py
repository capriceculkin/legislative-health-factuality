#!/usr/bin/env python3
"""
patch_ontario_supplement.py   (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)

The Ontario fetch searched each bill's own headings only up to 45 days after its last procedural line, so some
debates before 1995 were never fetched (the 1986 Committee of the Whole on Bills 7, 54 and 55, the 1989 one on
Bill 194, Bill 84's third reading in 1991, first readings). Claude fetched them with two read-only probes and kept
only days under the bill's own heading, in its session, that move the bill or name it at least as often as any
other bill, and that are not already in the data under any bill. Those rows are in
data/canada/ontario/v3/raw_supplement/<bill>/<date>.json. This makes `ontario_rebuild.py assign` add them, after
everything else, with the method "supplement_checked", so a later rebuild keeps them.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "ontario_rebuild.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
P = ROOT / "scripts" / "step1_debate_text" / "ontario_rebuild.py"
s = P.read_text(encoding="utf-8")
MARK = "PATCHED_SUPPLEMENT_2026_10_06"
if MARK in s:
    print("ontario_rebuild.py already has the supplement step; nothing to do.")
    sys.exit(0)
OLD = "    save_json(segments, SEGMENTS)\n    for key, days in segments.items():\n"
NEW = '''    # PATCHED_SUPPLEMENT_2026_10_06: days the 45-day fetch window missed, fetched and checked by hand
    # (see scripts/step1_debate_text/patch_ontario_supplement.py); added after everything else, never twice
    sup_dir = os.path.join(OUT, "raw_supplement")
    if os.path.isdir(sup_dir):
        for key in sorted(os.listdir(sup_dir)):
            if key not in master or not master[key].get("health"):
                continue
            for fn in sorted(os.listdir(os.path.join(sup_dir, key))):
                if not fn.endswith(".json"):
                    continue
                day = fn[:-5]
                have = {re.sub(r"\\W", "", p["text"].lower()) for p in segments.get(key, {}).get(day, [])}
                seen = set()
                for r in load_json(os.path.join(sup_dir, key, fn), []) or []:
                    if row_date(r) == day and row_id(r) not in seen and re.sub(r"\\W", "", row_text(r).lower()) not in have:
                        seen.add(row_id(r))
                        add(key, day, r, "supplement_checked")
    save_json(segments, SEGMENTS)
    for key, days in segments.items():
'''
if s.count(OLD) != 1:
    sys.exit("ontario_rebuild.py cmd_assign is not in the expected form; nothing changed. Send this output to Claude.")
backup = P.with_name("ontario_rebuild_before_supplement_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
s = s.replace(OLD, NEW)
s = s.replace("if k in ('anchor_split', 'topic_hash_exact', 'topic_hash_fuzzy', 'official_day_heading')",
              "if k in ('anchor_split', 'topic_hash_exact', 'topic_hash_fuzzy', 'official_day_heading', 'supplement_checked')")
compile(s, str(P), "exec")
P.write_text(s, encoding="utf-8")
print(f"Patched {P.relative_to(ROOT)} (backup {backup.name}): assign now adds data/canada/ontario/v3/raw_supplement.")
