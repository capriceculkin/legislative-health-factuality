#!/usr/bin/env python3
"""Read-only. Every section that names a US bill but was NOT used for it, with the
reason, so each rule's exclusions can be checked. Prints:
  1. counts by reason
  2. every distinct excluded title with how often (to confirm each is procedural)
  3. every 'title names another bill' exclusion in full (the rule to check most closely)
  4. bills with no debate at all
Writes outputs/audit/us_sections_excluded.csv
Run from project root:  python3 scripts/v3/list_excluded_sections.py > outputs/audit/us_sections_excluded.txt
"""
import csv, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_rebuild as U

idx = U.load_json(U.INDEX) or []
miss = U.load_json(os.path.join(U.OUT, "segments_missing.json")) or []
rows, seen = [], set()
for e in idx + miss:
    for x in e.get("excluded", []):
        k = (e["bill_key"], e["vote_date"], x["day"], x["id"])
        if k in seen:
            continue
        seen.add(k)
        rows.append({"bill_key": e["bill_key"], "vote_date": e["vote_date"], "day": x["day"], "granule": x["id"],
                     "title": x["title"], "why": x["why"], "bill_has_debate": "no" if e in miss else "yes"})
print(f"sections naming a bill but not used for it: {len(rows)}")
print("\n1. BY REASON")
for w, n in Counter(r["why"] for r in rows).most_common():
    print(f"  {n:>5}  {w}")
print("\n2. EVERY EXCLUDED TITLE (normalized) and count")
for t, n in Counter(U.norm_title(r["title"]) for r in rows).most_common():
    print(f"  {n:>5}  {t[:110]}")
print("\n3. 'TITLE NAMES ANOTHER BILL' IN FULL")
for r in rows:
    if r["why"] == "title names another bill":
        print(f"  {r['bill_key']:<16} {r['day']}  {r['title'][:100]}")
print("\n4. BILLS WITH NO DEBATE FOUND")
for b in miss:
    print(f"  {b['bill_key']} vote {b['vote_date']} ({b.get('result', '')}, {b.get('source', '')})")
out = os.path.join(U.rp("outputs", "audit"), "us_sections_excluded.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bill_key"])
    w.writeheader()
    w.writerows(rows)
print(f"\nwrote {out}")
