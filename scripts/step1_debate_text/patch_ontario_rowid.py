#!/usr/bin/env python3
"""
patch_ontario_rowid.py   (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)

Three fixes to how the Ontario rebuild downloads and de-duplicates paragraphs:

1. Paragraph ID. row_id() used the paragraph's paraUrl. On many 1993-1997 pages every
   paragraph of a sitting has the same paraUrl ('.../hansard-1#'), so de-duplication kept
   one paragraph per sitting part: Bill 50 kept 4 of 44 paragraphs on 1993-12-08 and 3 of
   79 on 1993-07-27; saved full days lose 10.7% of paragraphs this way (check_row_ids.py).
   The API's own 'id' field is unique on 100% of rows, so row_id() now uses it.
2. Headings downloaded. Each bill heading was fetched as given plus "X (CONTINUED)", but a
   bill anchored only under "X (CONTINUED)" never had its "X" paragraphs fetched. Both
   forms are now fetched for every heading.
3. Window. The download window ran from the first to the last FIRM stage + 45 days. It now
   runs from the first to the last day the bill is moved or named in a reading (weak lines
   too) + 45 days.

Which paragraphs count as the bill's text does not change (assign is untouched).
If the file does not contain the expected code, nothing is changed.

Run from the project folder:
  python3 scripts/step1_debate_text/patch_ontario_rowid.py
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "ontario_rebuild.py"
s = P.read_text(encoding="utf-8")

if "PATCHED_ROWID_2026_10_01" in s:
    print("ontario_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)

EDITS = [
    ("""def row_id(r):
    return row_para_url(r) or r.get("id") or sha(f"{r.get('url')}|{row_date(r)}|{row_text(r)[:300]}")
""",
     """def row_id(r):
    # PATCHED_ROWID_2026_10_01: the API's own paragraph id. The paraUrl used before is shared by
    # every paragraph of a sitting on many 1993-1997 pages ('.../hansard-1#'), so de-duplication
    # kept one paragraph per page part (check_row_ids.py).
    if r.get("id"):
        return "id:" + str(r["id"])
    return sha(f"{row_para_url(r)}|{r.get('url')}|{row_date(r)}|{row_order(r)}|{row_text(r)}")
"""),
    ("""    for a in anchors:
        if a["strong"] and a["session"] and is_procedural_topic(a["topic_norm"]):
            proc_days[f"{a['session']}-Bill{a['bill_number']}"].add(a["date"])
    os.makedirs(RAW_DIR, exist_ok=True)
""",
     """    all_dates = defaultdict(set)
    for a in anchors:
        if a["strong"] and a["session"] and is_procedural_topic(a["topic_norm"]):
            proc_days[f"{a['session']}-Bill{a['bill_number']}"].add(a["date"])
        if a["session"] and a.get("date"):
            all_dates[f"{a['session']}-Bill{a['bill_number']}"].add(a["date"])
    os.makedirs(RAW_DIR, exist_ok=True)
"""),
    ("""        if dates:
            lo = dates[0]
            hi = min(END, (dt.date.fromisoformat(dates[-1]) + dt.timedelta(days=45)).isoformat())
            if use_topic and b["topics"]:
                variants = set(b["topics"])
                for t in list(variants):
                    if t.isupper() and "(CONTINUED)" not in t:
                        variants.add(t + " (CONTINUED)")
""",
     """        if dates:
            # window: first to last day the bill is moved or named in a reading, weak lines included,
            # plus 45 days (before 2026-10-01: last FIRM stage + 45 days)
            every = sorted(set(dates) | all_dates.get(key, set()))
            lo = every[0]
            hi = min(END, (dt.date.fromisoformat(every[-1]) + dt.timedelta(days=45)).isoformat())
            if use_topic and b["topics"]:
                # every heading with and without "(CONTINUED)" (before: only "X" -> "X (CONTINUED)")
                variants = set()
                for t in b["topics"]:
                    base = re.sub(r"\\s*\\(CONTINUED\\)\\s*$", "", t)
                    variants.update({base, base + " (CONTINUED)"})
"""),
]

missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"ontario_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. "
             "Send me scripts/step1_debate_text/ontario_rebuild.py.")
for a, b in EDITS:
    s = s.replace(a, b)
backup = P.with_name("ontario_rebuild_before_rowid_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")

# check the edited module
sys.path.insert(0, str(P.parent))
import importlib  # noqa: E402
ob = importlib.import_module("ontario_rebuild")
a = {"id": "abc1", "paraUrl": "u#", "paragraph": "one", "date": "1993-12-08"}
b = {"id": "abc2", "paraUrl": "u#", "paragraph": "two", "date": "1993-12-08"}
assert ob.row_id(a) != ob.row_id(b), "row_id still collapses paragraphs that share a paraUrl"
c = {"paraUrl": "u#", "paragraph": "one", "date": "1993-12-08"}
d = {"paraUrl": "u#", "paragraph": "two", "date": "1993-12-08"}
assert ob.row_id(c) != ob.row_id(d), "fallback row_id collapses different paragraphs"
assert ob.row_id(a) == ob.row_id(dict(a)), "row_id is not stable"
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}). Checks passed: two paragraphs sharing a "
      "paraUrl now get different IDs; the same paragraph gets the same ID.")
