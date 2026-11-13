#!/usr/bin/env python3
"""
patch_ontario_order.py   (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)

1. Paragraph order. Paragraphs are put in Hansard order by the number in their paraUrl
   ('...#PARA7'). On the 1990s pages where every paragraph shares '...hansard-1#' there is no
   number, so all of them tie and keep the order the API returned them in. Bill 50's text on
   1993-12-08 starts with "How much heat?" instead of the third-reading motion. The API's own
   id carries the place in the day ('19931208-0000512'), so the order now comes from it.
   Before changing anything, this script checks on every saved full day (raw_days) that the
   id order agrees with the PARA-number order wherever both exist; if it does not agree on at
   least 99% of neighbouring paragraphs, nothing is changed.
2. Missing address. 2 Ontario bill-days fail audit check D1 because one paragraph came without
   its page address ('url'). The address is now taken from the paragraph's paraUrl when the
   url field is empty.
Which paragraphs count as a bill's text does not change.

Run from the project folder:
  python3 scripts/step1_debate_text/patch_ontario_order.py
"""
import glob
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "ontario_rebuild.py"
DAYS = ROOT / "data" / "canada" / "ontario" / "v3" / "raw_days"
s = P.read_text(encoding="utf-8")
if "PATCHED_ORDER_2026_10_02" in s:
    print("ontario_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)
if "PATCHED_ROWID_2026_10_01" not in s:
    sys.exit("Run patch_ontario_rowid.py first. Nothing changed.")

ID = re.compile(r"^\d{8}-(\d+)$")


def para_num(r):
    tail = str(r.get("paraUrl") or r.get("para_url") or "").split("#")[-1]
    m = re.findall(r"\d+", tail)
    return int(m[-1]) if m else None


# --- check: does the id order follow the Hansard order?
pairs = agree = days = no_id = 0
for fp in sorted(glob.glob(str(DAYS / "*.json"))):
    try:
        rows = json.load(open(fp, encoding="utf-8"))
    except (OSError, ValueError):
        continue
    days += 1
    by_url = {}
    for r in rows:
        m = ID.match(str(r.get("id") or ""))
        if not m:
            no_id += 1
            continue
        n = para_num(r)
        if n is not None:
            by_url.setdefault(r.get("url") or "", []).append((n, int(m.group(1))))
    for lst in by_url.values():
        lst.sort()
        for (n1, s1), (n2, s2) in zip(lst, lst[1:]):
            if n1 == n2:
                continue
            pairs += 1
            agree += s1 < s2
share = agree / pairs if pairs else 0
print(f"Check on {days} saved full days: id order agrees with the PARA-number order on {agree:,} of {pairs:,} "
      f"neighbouring paragraphs ({share:.2%}); rows without a dated id: {no_id}")
if pairs < 500 or share < 0.99:
    sys.exit("Not enough agreement (needs 500+ pairs and 99%). Nothing changed. Send me this output.")

EDITS = [
    ("""def row_order(r):
""", """def row_order(r):
    # PATCHED_ORDER_2026_10_02: the API id ('19931208-0000512') gives the paragraph's place in the day;
    # paraUrl has no number on pages where every paragraph shares '...#'
    m = re.match(r"^\\d{8}-(\\d+)$", str(r.get("id") or ""))
    if m:
        return int(m.group(1))
"""),
    ("""        rows.sort(key=lambda r: (row_date(r), r.get("url") or "", row_order(r)))""",
     """        rows.sort(key=lambda r: (row_date(r), r.get("url") or row_para_url(r).split("#")[0], row_order(r)))"""),
    ("""            "session": row_session(r), "session_api": api_session(r.get("session")), "url": r.get("url") or "",""",
     """            "session": row_session(r), "session_api": api_session(r.get("session")),
            "url": r.get("url") or row_para_url(r).split("#")[0],"""),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"ontario_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed.")
for a, b in EDITS:
    s = s.replace(a, b)
backup = P.with_name("ontario_rebuild_before_order_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")

sys.path.insert(0, str(P.parent))
import importlib  # noqa: E402
ob = importlib.import_module("ontario_rebuild")
a = {"id": "19931208-0000512", "paraUrl": "u#"}
b = {"id": "19931208-0000516", "paraUrl": "u#"}
assert ob.row_order(a) < ob.row_order(b), "order still ignores the id"
assert ob.row_order({"paraUrl": "u#PARA7"}) == 7, "old order lost for rows without an id"
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}). Checks passed.")
