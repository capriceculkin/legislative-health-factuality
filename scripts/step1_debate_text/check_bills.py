#!/usr/bin/env python3
"""
check_bills.py   (reads the data, changes nothing)

Everything the data holds for one or more bills, so a bill can be checked live:
health-list status, outcome and its source, every sitting day with its paragraphs,
the headings the text sits under, whether each day's text names the bill, and the
sentences and claims per day.

Run from the project folder:
  python3 scripts/step1_debate_text/check_bills.py 33-2-Bill94 34-2-Bill52
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def jur_of(bk):
    if re.match(r"^\d{2,3}-(HR|S|HRES|HJRES|HCONRES)\d+$", bk):
        return "us"
    return "quebec" if (ROOT / "data/canada/quebec_assembly/v3/segments_index.json").exists() and \
        any(e.get("bill_key") == bk for e in load(ROOT / "data/canada/quebec_assembly/v3/segments_index.json", [])) \
        else "ontario"


keys = sys.argv[1:]
if not keys:
    sys.exit("usage: python3 scripts/step1_debate_text/check_bills.py 33-2-Bill94 34-2-Bill52")

outcomes = load(ROOT / "data/v3_outcomes.json", {}) or {}
proposals = load(ROOT / "data/v3_health_proposals.json", []) or []
on_segs = load(ROOT / "data/canada/ontario/v3/hansard_segments_v3.json", {}) or {}
cache = {}

for bk in keys:
    j = jur_of(bk)
    print("=" * 90)
    print(f"{bk}   ({j})")
    print("=" * 90)

    props = [p for p in proposals if p.get("bill_key") == bk]
    if props:
        for p in props:
            print(f"health list: {p.get('decision', '')}")
            print(f"   reason:   {p.get('reason', '')}")
            print(f"   evidence: {str(p.get('evidence', ''))[:200]}")
    else:
        print("health list: kept (not among the bills proposed for exclusion)")

    o = (outcomes.get(j) or {}).get(bk) or {}
    passed = {1: "PASSED", True: "PASSED", 0: "NOT PASSED", False: "NOT PASSED"}.get(o.get("passed"), "no pass/fail")
    print(f"outcome: {passed}")
    for k in ("outcome_raw", "source", "check"):
        if o.get(k):
            print(f"   {k}: {str(o[k])[:200]}")
    page = ROOT / "data/v3_status_cache" / j / f"{bk}.html"
    print(f"official status page saved: {'yes, ' + str(page.relative_to(ROOT)) if page.exists() else 'no'}")

    if j not in cache:
        cache[j] = (load(ROOT / f"data/dbpedia_pipeline/{j}/sentences_v3.json", []) or [],
                    load(ROOT / f"data/dbpedia_pipeline/{j}/predications_v3.json", []) or [])
    sents, preds = cache[j]
    n_s = Counter(str(s.get("date", ""))[:10] for s in sents if s.get("bill_key") == bk)
    n_p = Counter(str(p.get("date", ""))[:10] for p in preds if p.get("bill_key") == bk)

    num = re.search(r"(\d+)$", bk).group(1)
    names_bill = re.compile(rf"\bBill\s+{num}\b|projet de loi (?:n\S*\s*)?{num}\b", re.I)

    if j == "ontario":
        days = on_segs.get(bk) or {}
        print(f"\nsitting days with text: {len(days)}")
        for d in sorted(days):
            paras = days[d]
            text = " ".join(str(p.get("text", "")) for p in paras)
            heads = Counter(str(p.get("topic") or p.get("heading") or p.get("section") or "") for p in paras)
            head = ", ".join(f"{h[:40]} ({n})" for h, n in heads.most_common(3) if h)
            words = len(text.split())
            print(f"  {d}  {len(paras):>4} paragraphs  {words:>6,} words  names Bill {num}: "
                  f"{len(names_bill.findall(text))}x  sentences {n_s.get(str(d)[:10], 0):>5}  claims {n_p.get(str(d)[:10], 0):>4}")
            if head:
                print(f"              headings: {head}")
            first = str(paras[0].get("text", ""))[:150] if paras else ""
            print(f"              first:    {first}")
    else:
        print("\nsentences and claims per day:")
        for d in sorted(set(n_s) | set(n_p)):
            print(f"  {d}  sentences {n_s.get(d, 0):>5}  claims {n_p.get(d, 0):>4}")
    print(f"\ntotal: {sum(n_s.values()):,} sentences, {sum(n_p.values()):,} claims\n")
