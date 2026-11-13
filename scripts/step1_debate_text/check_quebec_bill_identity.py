#!/usr/bin/env python3
"""
check_quebec_bill_identity.py   (reads only)

Checks that every Quebec bill's official page and debate links belong to that bill's own
legislature. Three bill pages list dates that cannot belong to them (36-1 Bill 53 lists
"17 juin 1996"; 36-1 bills belong to 1999-2003), and if a page or link belongs to a different
bill, both the debate text and the pass/fail outcome taken from it would be wrong.
For each predicated Quebec bill:
  1. the bill_url in the health bill list names the same number and session as the key
  2. the bill page's own text names the same legislature (when the page states it)
  3. every assembly_debates link is a Journal page of the bill's own legislature
  4. every date on the bill page falls inside the bill's legislature
Run from the project folder:  python3 scripts/step1_debate_text/check_quebec_bill_identity.py
Writes outputs/audit/quebec_bill_identity.csv
"""
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_debate_days_canada as CC     # noqa: E402  (same page reader as the day check)

ROOT = HERE.parent.parent
OUT = ROOT / "outputs" / "audit" / "quebec_bill_identity.csv"
URL_BILL = re.compile(r"projet-loi-(\d+)-(\d+)-(\d+)\.html")
URL_JOURNAL = re.compile(r"assemblee-nationale/(\d+)-(\d+)/journal-debats/(\d{8})/")
PAGE_LEG = re.compile(r"(\d{2})e\s+l[ée]gislature,?\s+(\d)(?:re|e)\s+session", re.I)


def main():
    comb = json.load(open(ROOT / "data/canada/quebec_bills/quebec_health_bills_combined.json", encoding="utf-8"))
    preds = json.load(open(ROOT / "data/dbpedia_pipeline/quebec/predications_v3.json", encoding="utf-8"))
    predicated = {p.get("bill_key") for p in preds}
    try:
        outcomes = json.load(open(ROOT / "data/v3_outcomes.json", encoding="utf-8"))
    except (OSError, ValueError):
        outcomes = {}
    def outside(lg, d):
        return CC.outside_legislature_dates(lg, d)

    rows, tally = [], Counter()
    for e in comb:
        n = str(e.get("bill_number", "")).strip()
        if not n.isdigit():
            continue
        bk = f"{e.get('session', '')}-Bill{int(n)}"
        if bk not in predicated:
            continue
        lg, ss = str(e.get("session", "")).split("-") if "-" in str(e.get("session", "")) else ("", "")
        problems = []
        m = URL_BILL.search(e.get("bill_url") or "")
        if not m:
            problems.append("bill_url has no bill number/session")
        elif (m.group(1), m.group(2), m.group(3)) != (str(int(n)), lg, ss):
            problems.append(f"bill_url is bill {m.group(1)} of {m.group(2)}-{m.group(3)}")
        page = ROOT / "data/v3_status_cache/quebec" / f"{bk}.html"
        if page.exists():
            text = CC.page_text(page)
            legs = {x for x, _ in PAGE_LEG.findall(text)}
            if legs and lg not in legs:
                problems.append(f"bill page names legislature(s) {sorted(legs)}")
            bad_dates = sorted(d for d in CC.assnat_all(page) if outside(lg, d))
            if bad_dates:
                problems.append(f"bill page dates outside legislature {lg}: {bad_dates}")
        else:
            problems.append("no cached bill page")
        other = sorted({f"{a}-{b} {c}" for a, b, c in URL_JOURNAL.findall(json.dumps(e.get("assembly_debates") or []))
                        if a != lg})
        if other:
            problems.append(f"debate links to another legislature's Journal: {other}")
        o = outcomes.get("quebec", {}).get(bk, {}) if isinstance(outcomes, dict) else {}
        tally["flagged" if problems else "ok"] += 1
        rows.append({"bill_key": bk, "status": "CHECK" if problems else "ok", "problems": " | ".join(problems),
                     "bill_url": e.get("bill_url", ""), "outcome": str(o.get("outcome", o) if isinstance(o, dict) else o)[:60]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bill_key"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["status"] == "ok", r["bill_key"])))
    print(f"Quebec predicated bills checked: {len(rows)}; ok {tally['ok']}; flagged {tally['flagged']}")
    for r in rows:
        if r["status"] == "CHECK":
            print(f"   {r['bill_key']:<14} {r['problems']}")
    print(f"full list: {OUT}")


if __name__ == "__main__":
    main()
