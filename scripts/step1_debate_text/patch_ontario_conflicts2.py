#!/usr/bin/env python3
"""
patch_ontario_conflicts2.py   (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)

The Oct 3 run split the paragraphs under a bill heading two bills of one session share, from each line that
moves a bill. One day lost text that way: on 1996-06-25 (36-1) one motion moved second reading of nine bills at
once ("moved second reading of the following bills:" then "Bill 61, An Act to simplify government processes ...",
... "Bill 69, ..."), and the debate that followed is one debate for all nine. The split read the list as nine
separate lines and gave the debate to none of them, so Bill 67 lost 135 paragraphs.
A day whose paragraphs under the shared heading contain such a joint motion now keeps the handling it had before
Oct 3 (the bill's own official day keeps the whole debate). Every other day under a shared heading is unchanged.

Run from the project folder:  python3 scripts/step1_debate_text/patch_ontario_conflicts2.py
Needs patch_ontario_conflicts.py first. If the file does not contain the expected code, nothing is changed.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "ontario_rebuild.py"
s = P.read_text(encoding="utf-8")
if "PATCHED_CONFLICTS2_2026_10_04" in s:
    print("ontario_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)
if "PATCHED_CONFLICTS_2026_10_03" not in s:
    sys.exit("ontario_rebuild.py does not have the Oct 3 shared-heading patch; nothing changed. Send this output to Claude.")

EDITS = [
    ("""def cmd_assign():
""",
     """# PATCHED_CONFLICTS2_2026_10_04: one motion that moves several bills ("moved second reading of the following
# bills: Bill 61, ..., Bill 69") is one debate for every bill it names
_JOINT_MOTION = re.compile(r"\\bmoved?\\s+(?:(?:first|second|third)\\s+)?reading\\s+of\\s+(?:the\\s+following\\s+bills|bills\\s+\\d)",
                           re.I)
_LIST_ITEM = re.compile(r"^\\s*Bill\\s+(\\d+)\\s*,\\s*An\\s+Act\\b", re.I)


def joint_motion(group):
    if any(_JOINT_MOTION.search(row_text(r)) for r in group):
        return True
    return len({m.group(1) for r in group for m in [_LIST_ITEM.match(row_text(r))] if m}) >= 2


def cmd_assign():
"""),
    ("""                         and any(a["strong"] or official for r in group
                                 for a in find_anchors_en(row_text(r), r.get("speaker"), topic, r.get("typeOfBusiness"))))
""",
     """                         and any(a["strong"] or official for r in group
                                 for a in find_anchors_en(row_text(r), r.get("speaker"), topic, r.get("typeOfBusiness")))
                         and not joint_motion(group))
"""),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"ontario_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. "
             "Send this output to Claude.")
for a, b in EDITS:
    s = s.replace(a, b)
compile(s, str(P), "exec")
backup = P.with_name("ontario_rebuild_before_conflicts2_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")
sys.path.insert(0, str(P.parent))
import importlib  # noqa: E402
ob = importlib.import_module("ontario_rebuild")
t = lambda x: {"paragraph": x}   # noqa: E731
assert ob.joint_motion([t("Mr Tsubouchi, on behalf of Mr Harnick, moved second reading of the following bills:")])
assert ob.joint_motion([t("Bill 61, An Act to simplify government processes"), t("Bill 67, An Act to simplify")])
assert not ob.joint_motion([t("Hon. Mr. Elston moved second reading of Bill 78, An Act to amend the Mental Health Act.")])
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}). Checks passed.")
