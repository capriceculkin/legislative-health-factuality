#!/usr/bin/env python3
"""
check_days.py   (reads only; saves nothing into data/)

For a few Ontario sitting days, downloads that day's Hansard from the same OLA API
the rebuild uses and prints every paragraph that names the bill, with the heading
(topic) and the type of business it sits under. It also lists all headings that day,
so a day with no debate on the bill is easy to see.

Days already saved in data/canada/ontario/v3/raw_days are read from disk. Other days
are downloaded but NOT saved, so the rebuild's inputs do not change.

Run from the project folder:
  python3 scripts/step1_debate_text/check_days.py
Output is also written to outputs/audit/check_days.txt
"""
import os
import re
import sys
from collections import Counter

os.environ.setdefault("OLA_SLEEP", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ontario_rebuild as ob  # noqa: E402

CHECKS = [
    ("1986-01-17", "94", "Sept 24 comment: 'jan 17 not there'. Our data has 75 paragraphs for this date."),
    ("1993-11-15", "50", "Shown Sept 24, not in the rebuilt data."),
    ("1993-11-16", "50", "Shown Sept 24, not in the rebuilt data. The committee also met on Bill 50 this day."),
    ("1993-11-17", "50", "Shown Sept 24, not in the rebuilt data."),
    ("1993-12-07", "50", "In the old index, not in the rebuilt data. Checked for the outcome."),
    ("1993-12-14", "50", "In the old index, not in the rebuilt data. Checked for the outcome."),
]
STAGE = re.compile(r"third reading|read a third time|royal assent|assent|second reading|committee of the whole|"
                   r"standing committee|reported|carried|lost", re.I)

out_lines = []


def say(s=""):
    print(s, flush=True)
    out_lines.append(s)


def clean(t):
    t = re.sub(r"<[^>]+>", " ", str(t or ""))
    return re.sub(r"\s+", " ", t).strip()


try:
    ob.load_probe()
except SystemExit:
    pass

for day, num, note in CHECKS:
    say("=" * 100)
    say(f"{day}   Bill {num}   ({note})")
    say("=" * 100)
    saved = os.path.join(ob.DAY_DIR, f"{day}.json")
    if os.path.exists(saved):
        rows = ob.load_json(saved, []) or []
        src = "saved raw day"
    else:
        try:
            rows = ob.query_complete("*", None, day, day, [])
            src = "downloaded now from the OLA API (not saved)"
        except Exception as e:  # noqa: BLE001
            say(f"  could not download: {e.__class__.__name__}: {str(e)[:200]}")
            continue
    rows = sorted(rows, key=ob.row_order)
    say(f"  {len(rows)} paragraphs ({src})")
    if not rows:
        say("  NO SITTING TEXT for this date in the OLA Hansard.")
        continue
    urls = sorted({str(r.get('url') or '') for r in rows if r.get('url')})
    for u in urls[:3]:
        say(f"  page: {u}")
    topics = Counter(f"{r.get('topic') or '?'} | {r.get('typeOfBusiness') or '?'}" for r in rows)
    say("  headings that day (heading | business: paragraphs):")
    for t, n in topics.most_common():
        say(f"     {n:>4}  {t}")
    rx = re.compile(rf"\bBill\s+{num}\b")
    hits = [r for r in rows if rx.search(clean(r.get("paragraph") or r.get("text") or r.get("content")))]
    say(f"  paragraphs that name Bill {num}: {len(hits)}")
    for r in hits:
        t = clean(r.get("paragraph") or r.get("text") or r.get("content"))
        m = rx.search(t)
        a, b = max(0, m.start() - 150), min(len(t), m.end() + 250)
        flag = "  <-- stage/outcome words" if STAGE.search(t[a:b]) else ""
        say(f"   [{r.get('topic') or '?'} | {r.get('typeOfBusiness') or '?'}]{flag}")
        say(f"      ...{t[a:b]}...")
    say()

os.makedirs(ob.rp("outputs", "audit"), exist_ok=True)
dest = ob.rp("outputs", "audit", "check_days.txt")
with open(dest, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines) + "\n")
print(f"wrote {dest}")
