#!/usr/bin/env python3
"""
patch_quebec_verify7.py   (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)

The running table's column check2_listed_in_cheminement said "Y" for every section, because until now
every section came from a debate listed in the bill's cheminement. The 1985-1994 sections come from the
Journal scan (quebec_pre1994.py), so for them the column now says so. Nothing else changes.
Run from the project folder:  python3 scripts/step1_debate_text/patch_quebec_verify7.py
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py"
s = P.read_text(encoding="utf-8")
if "PATCHED_VERIFY7_2026_10_03" in s:
    print("quebec_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)
EDITS = [
    ('''            "check2_listed_in_cheminement": "Y",''',
     '''            # PATCHED_VERIFY7_2026_10_03: 1985-1994 sections come from the Journal scan, not a cheminement
            "check2_listed_in_cheminement": ("Y" if e.get("source") != "bibliotheque_pre1994"
                                             else "N: found by the 1985-1994 Journal scan"),'''),
    ('''    print(f"CHECK 2 every segment comes from a debate listed in the bill's cheminement: {len(rows)} of {len(rows)} "
          "by construction; coverage above is the real test of this check")''',
     '''    n_scan = sum(1 for r in rows if r["check2_listed_in_cheminement"] != "Y")
    print(f"CHECK 2 every segment comes from a debate listed in the bill's cheminement: {len(rows) - n_scan} of {len(rows)} "
          f"by construction; the other {n_scan} are 1985-1994 days found by the Journal scan (quebec_pre1994.py)")'''),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"quebec_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. "
             "(The running table will still say Y in that column for the 1985-1994 sections.)")
for a, b in EDITS:
    s = s.replace(a, b)
compile(s, str(P), "exec")
backup = P.with_name("quebec_rebuild_before_verify7_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}).")
