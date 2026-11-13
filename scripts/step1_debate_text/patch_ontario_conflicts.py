#!/usr/bin/env python3
"""
patch_ontario_conflicts.py   (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)

A bill heading that two bills of one session both use is left out of the topic hash (no bill has 2/3 of
its moving lines). Its paragraphs then went to nobody, or, through a near-match with another heading, all to
one of the two bills (Bill 190's debate under Bill 78), or, on an official day, whole to the bill of that day.
Real cases among health bills:
  33-3  MENTAL HEALTH AMENDMENT ACT                     Bill 78 and Bill 190 (both "An Act to amend the Mental Health Act")
  34-1  OCCUPATIONAL HEALTH AND SAFETY AMENDMENT ACT    Bills 71, 177 and 180
  34-1  HEALTH PROTECTION AND PROMOTION AMENDMENT ACT  Bills 62 and 202
  34-1  ENVIRONMENTAL PROTECTION AMENDMENT ACT         Bills 183 and 218
  33-2  EQUALITY RIGHTS STATUTE LAW AMENDMENT ACT      Bills 7 and 199
Under such a heading, on a day where the heading's paragraphs contain a line that moves a bill, a paragraph
now goes to a bill only from the line that moves that bill ("Hon. Mr. Elston moved second reading of Bill 78")
until a line that moves another one: the same rule already used under procedural and statement headings.
A day with no such line under the shared heading (a committee-of-the-whole day, say) is handled as before.
Nothing changes under any other heading.

Run from the project folder:  python3 scripts/step1_debate_text/patch_ontario_conflicts.py
If the file does not contain the expected code, nothing is changed.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "ontario_rebuild.py"
s = P.read_text(encoding="utf-8")
if "PATCHED_CONFLICTS_2026_10_03" in s:
    print("ontario_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)

EDITS = [
    ("""    topic_hash, conflicts = build_topic_hash(anchors)
    keys_by_session = defaultdict(list)
""",
     """    topic_hash, conflicts = build_topic_hash(anchors)
    # PATCHED_CONFLICTS_2026_10_03: bill headings two bills of one session both use (no topic-hash owner)
    shared = {(c["session"], c["topic"]) for c in conflicts}
    keys_by_session = defaultdict(list)
"""),
    ("""            if is_procedural_topic(nt) or not bill_like(topic):
""",
     """            on_shared = (bill_like(topic) and not is_procedural_topic(nt) and (sess, nt) in shared
                         and any(a["strong"] or official for r in group
                                 for a in find_anchors_en(row_text(r), r.get("speaker"), topic, r.get("typeOfBusiness"))))
            if is_procedural_topic(nt) or not bill_like(topic) or on_shared:
"""),
    ("""                        add(key, day, r, "anchor_split" + ("" if is_procedural_topic(nt) else ":other_heading")
                            + (":official_day" if official else ""))
""",
     """                        add(key, day, r, "anchor_split" + ("" if is_procedural_topic(nt) else
                                                           (":shared_heading" if on_shared else ":other_heading"))
                            + (":official_day" if official else ""))
"""),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"ontario_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. "
             "Send this output to Claude.")
for a, b in EDITS:
    s = s.replace(a, b)
compile(s, str(P), "exec")
backup = P.with_name("ontario_rebuild_before_conflicts_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}).")
