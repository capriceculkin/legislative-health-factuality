#!/usr/bin/env python3
"""
check_missing_stages.py   (reads only; no downloads; changes nothing)

Why: on 1993-12-08 the Hansard has 44 paragraphs under Bill 50's own heading, including
"Mr O'Connor, on behalf of Mrs Grier, moved third reading of Bill 50" and the vote
("Carried"), but our data has 4 of them. The rebuild downloads a bill's text only from
its first to its last FIRMLY moved stage plus 45 days. A stage moved "on behalf of"
the minister counts as a weak line, so it does not stretch that window, and a later
debate (often third reading) can fall outside it.

For every health bill this lists each day the Hansard moves or names it in a reading
(strong or weak line, from anchors.json, already on disk), whether that day is inside
the download window, how many of our paragraphs that day came from the bill's own
heading, and how many raw paragraphs we downloaded for that day.

Run from the project folder:
  python3 scripts/step1_debate_text/check_missing_stages.py
Writes outputs/audit/missing_stage_days.csv
"""
import csv
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ontario_rebuild as ob  # noqa: E402

master = ob.load_json(ob.MASTER, {}) or sys.exit("bills_master.json missing")
anchors = ob.load_json(ob.ANCHORS, []) or sys.exit("anchors.json missing")
segs = ob.load_json(ob.SEGMENTS, {}) or {}

by_key = defaultdict(list)
for a in anchors:
    if a.get("session"):
        by_key[f"{a['session']}-Bill{a['bill_number']}"].append(a)

rows, summary = [], Counter()
bad_raw = []
bills_hit = set()
for key, b in sorted(master.items()):
    if not b.get("health"):
        continue
    strong = sorted(b.get("anchor_dates") or [])
    if not strong:
        continue
    hi = (dt.date.fromisoformat(strong[-1]) + dt.timedelta(days=45)).isoformat()
    try:
        with open(os.path.join(ob.RAW_DIR, f"{key}.json"), encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raw = []
    except ValueError as e:
        bad_raw.append(f"{key} ({str(e)[:60]})")
        raw = []
    raw_by_day = Counter(ob.row_date(r) for r in raw)
    days = segs.get(key, {})
    seen = set()
    for a in sorted(by_key.get(key, []), key=lambda x: x["date"]):
        d = a["date"]
        if (d, a["stage"], a["strong"]) in seen:
            continue
        seen.add((d, a["stage"], a["strong"]))
        inside = strong[0] <= d <= hi
        ours = len(days.get(d, []))
        own = sum(1 for p in days.get(d, []) if str(p.get("assignment_method", "")).startswith("topic_hash"))
        status = ("ok" if inside and ours else
                  "outside window, no text" if not inside and not ours else
                  "outside window, partial text" if not inside else
                  "inside window, no text")
        summary[status] += 1
        if status != "ok":
            bills_hit.add(key)
        rows.append({"bill_key": key, "date": d, "stage": a["stage"], "line": "strong" if a["strong"] else "weak",
                     "window": f"{strong[0]} to {hi}", "inside_window": "yes" if inside else "no",
                     "our_paragraphs": ours, "from_own_heading": own, "raw_paragraphs_that_day": raw_by_day.get(d, 0),
                     "status": status, "heading": a.get("topic", ""), "text": (a.get("text") or "")[:160]})

print("Days a health bill is moved or named in a reading, by status:")
for k, v in summary.most_common():
    print(f"  {v:>5}  {k}")
print(f"Health bills with at least one such day not fully covered: {len(bills_hit)}")
print(f"Raw files that cannot be read ({len(bad_raw)}): {bad_raw[:10]}")
late = Counter(r["stage"] for r in rows if r["inside_window"] == "no")
print(f"Outside the window, by stage: {dict(late)}")
print("\n35-3-Bill50 in detail:")
b50 = master.get("35-3-Bill50", {})
print(f"  strong anchor dates: {b50.get('anchor_dates')}  topics: {b50.get('topics')}")
for r in rows:
    if r["bill_key"] == "35-3-Bill50":
        print(f"  {r['date']} {r['stage']:<8} {r['line']:<6} inside={r['inside_window']:<3} ours={r['our_paragraphs']:<4} "
              f"raw={r['raw_paragraphs_that_day']:<4} {r['status']}  | {r['text'][:90]}")
os.makedirs(ob.rp("outputs", "audit"), exist_ok=True)
path = ob.rp("outputs", "audit", "missing_stage_days.csv")
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bill_key"])
    w.writeheader()
    w.writerows(rows)
print(f"\nwrote {path}")
