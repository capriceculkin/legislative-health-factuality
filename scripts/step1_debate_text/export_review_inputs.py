#!/usr/bin/env python3
"""
export_review_inputs.py   (read-only)
One row per predicated bill in all three jurisdictions, with its official title and
how much of its debate text is about health, so every bill's place on the health
list can be checked against its title AND its text.
  -> outputs/audit/bills_for_title_review.csv
Run from project root:  python3 scripts/step1_debate_text/export_review_inputs.py
"""
import csv, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HEALTH = re.compile(r"\bhealth|hospital|patient|medical|medicine|physician|doctor|\bnurs|\bdrug|pharma|disease|"
                    r"illness|clinic|mental|vaccin|cancer|tobacco|smok|medicare|medicaid|ohip|opioid|addiction|"
                    r"sant[ée]|h[ôo]pital|m[ée]dec|infirmi|maladie|\bsoins\b|pharmac", re.I)


def load(p, default=None):
    p = ROOT / p
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


titles = defaultdict(dict)
for p in (ROOT / "data/v3_status_cache/us").glob("*.bill.json"):
    b = (load(p.relative_to(ROOT), {}) or {}).get("bill") or {}
    titles["us"][p.name[:-len(".bill.json")]] = b.get("title", "")
for k, v in (load("data/canada/ontario/v3/bills_master.json", {}) or {}).items():
    titles["ontario"][k] = v.get("long_title", "")
basis = {k: v.get("health_basis", "") for k, v in (load("data/canada/ontario/v3/bills_master.json", {}) or {}).items()}
for e in load("data/canada/quebec_bills/quebec_health_bills_combined.json", []) or []:
    n = str(e.get("bill_number", "")).strip()
    if n.isdigit():
        titles["quebec"][f"{e.get('session', '')}-Bill{int(n)}"] = e.get("title", "")
oc = load("data/v3_outcomes.json", {}) or {}

rows = []
for j in ("us", "ontario", "quebec"):
    sents = load(f"data/dbpedia_pipeline/{j}/sentences_v3.json", [])
    preds = load(f"data/dbpedia_pipeline/{j}/predications_v3.json", [])
    n_s, n_h, days = Counter(), Counter(), defaultdict(set)
    for s in sents:
        bk = s.get("bill_key", "")
        n_s[bk] += 1
        n_h[bk] += bool(HEALTH.search(str(s.get("text") or s.get("sentence") or s.get("sentence_text") or "")))
        days[bk].add(s.get("date", ""))
    n_p = Counter(p.get("bill_key", "") for p in preds)
    for bk in sorted(n_p):
        o = (oc.get(j) or {}).get(bk, {})
        rows.append({"jurisdiction": j, "bill_key": bk, "title": titles[j].get(bk, ""),
                     "ontario_health_basis": basis.get(bk, "") if j == "ontario" else "",
                     "sitting_days": len(days[bk]), "sentences": n_s[bk], "predications": n_p[bk],
                     "health_sentence_share": round(n_h[bk] / n_s[bk], 3) if n_s[bk] else "",
                     "passed": o.get("passed", "")})
    print(f"{j}: {sum(r['jurisdiction'] == j for r in rows)} bills")
out = ROOT / "outputs/audit/bills_for_title_review.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"wrote {out}")
