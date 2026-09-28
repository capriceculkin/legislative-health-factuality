#!/usr/bin/env python3
"""Read-only diagnostic.
Part 1: why H.R. 7667's June 8, 2022 debate was not picked up. Lists every House
        granule on 2022-06-07/08/09 that mentions H.R. 7667 or its title.
Part 2: every section title the segmenter chose for any US bill, with counts, so
        procedural items (budget notices, earmark statements, amendment lists,
        Senate messages) that are not debate can be listed and excluded at the source.
Run from project root:  python3 scripts/v3/diag_us_sections.py > outputs/audit/us_sections_diag.txt
"""
import json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_rebuild as U

rx = U.us_bill_mention_re("hr", 7667)
print("PART 1: H.R. 7667 (Food and Drug Amendments of 2022), House granules 2022-06-07..09")
for day in ("2022-06-07", "2022-06-08", "2022-06-09"):
    units = U.daily_units(day)
    print(f"\n{day}: {len(units)} House granules")
    for u in units:
        t = u["text"]
        hits = len(rx.findall(t))
        fda = "FOOD AND DRUG AMENDMENTS" in (u["title"] or "").upper() or "Food and Drug Amendments of 2022" in t
        if hits or fda:
            nt = U.norm_title(u["title"])
            print(f"  {u['id']} | {u['title'][:70]} | H.R. 7667 mentions: {hits} | in first 2500 chars: "
                  f"{bool(rx.search(t[:2500]))} | title mentions FDA amendments: {fda} | procedural title: "
                  f"{U.is_proc_title(nt)} | {len(t):,} chars")
            if hits == 0:
                i = t.find("7667")
                print(f"      '7667' appears as: {t[max(0, i - 40):i + 20]!r}" if i >= 0 else "      '7667' not in text")

print("\n\nPART 2: section titles chosen for US bills (all bill-days)")
idx = U.load_json(U.INDEX) or []
c, how, days = Counter(), Counter(), {}
for e in idx:
    for u in e.get("units", []):
        nt = U.norm_title(u.get("title", ""))
        c[nt] += 1
        how[(nt, u.get("method", ""))] += 1
        days.setdefault(nt, set()).add((e["bill_key"], e["debate_date"]))
for nt, n in c.most_common(80):
    m = ", ".join(f"{k[1]} {v}" for k, v in how.items() if k[0] == nt)
    print(f"  {n:>4}  {nt[:90]}   [{m}]  e.g. {sorted(days[nt])[:2]}")
