#!/usr/bin/env python3
"""
ontario_fix_report.py   (reads only)

How much of the Ontario data changed between a saved copy and now: paragraphs, bill-days,
sentences and claims, by Parliament and by bill, plus any change in pass/fail outcomes.

Paragraphs are matched by their Hansard address AND their text (an address alone is shared
by many paragraphs on some 1990s pages), so removed and added paragraphs are both listed.

Default baseline: the oldest data/_before_ontario_fill_* folder, the state behind the counts
shown at the Sept 29 meeting (1,531 bill-days, 441,180 sentences, 48,522 claims). The report
first checks that the baseline really holds those numbers.

Run from the project folder:
  python3 scripts/step1_debate_text/ontario_fix_report.py [baseline folder]
Writes outputs/audit/ontario_fix_report.txt and outputs/audit/ontario_fix_by_bill.csv
"""
import csv
import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.getcwd() if os.path.isdir("data") else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


if len(sys.argv) > 1:
    base = sys.argv[1]
else:
    cands = sorted(glob.glob(os.path.join(ROOT, "data", "_before_ontario_fill_*")))
    if not cands:
        sys.exit("No data/_before_ontario_fill_* folder; give the baseline folder as an argument.")
    base = cands[0]
say(f"Baseline: {os.path.relpath(base, ROOT)}   Now: data/ (current files)")

old_seg = load(os.path.join(base, "hansard_segments_v3.json"), {}) or {}
new_seg = load(os.path.join(ROOT, "data/canada/ontario/v3/hansard_segments_v3.json"), {}) or {}
old_sent = load(os.path.join(base, "ontario_sentences_v3.json"), []) or []
new_sent = load(os.path.join(ROOT, "data/dbpedia_pipeline/ontario/sentences_v3.json"), []) or []
old_pred = load(os.path.join(base, "ontario_predications_v3.json"), []) or []
new_pred = load(os.path.join(ROOT, "data/dbpedia_pipeline/ontario/predications_v3.json"), []) or []


def parl(k):
    return str(k).split("-")[0]


def keyed(paras):
    out, n = {}, Counter()
    for p in paras:
        k = (p.get("para_url") or "", hashlib.sha1(str(p.get("text", "")).encode()).hexdigest())
        n[k] += 1
        out[k + (n[k],)] = p
    return out


# baseline check against the Sept 29 meeting numbers
bd_old = sum(len(d) for d in old_seg.values())
say(f"Baseline holds: {sum(len(v) for d in old_seg.values() for v in d.values()):,} paragraphs, {bd_old:,} bill-days, "
    f"{len(old_sent):,} sentences, {len(old_pred):,} claims "
    f"(Sept 29 meeting: 1,531 bill-days, 441,180 sentences, 48,522 claims)")

rows = defaultdict(lambda: Counter())
removed_list, gained_days = [], []
for b in set(old_seg) | set(new_seg):
    for d in set(old_seg.get(b, {})) | set(new_seg.get(b, {})):
        o, n = keyed(old_seg.get(b, {}).get(d, [])), keyed(new_seg.get(b, {}).get(d, []))
        gone = [o[k] for k in o if k not in n]
        came = [n[k] for k in n if k not in o]
        r = rows[b]
        r["para_old"] += len(o)
        r["para_new"] += len(n)
        r["para_added"] += len(came)
        r["para_removed"] += len(gone)
        r["days_old"] += bool(o)
        r["days_new"] += bool(n)
        if came:
            gained_days.append((b, d, len(o), len(n)))
        for p in gone:
            removed_list.append((b, d, p))
for s in old_sent:
    rows[s.get("bill_key")]["sent_old"] += 1
for s in new_sent:
    rows[s.get("bill_key")]["sent_new"] += 1
for p in old_pred:
    rows[p.get("bill_key")]["claims_old"] += 1
for p in new_pred:
    rows[p.get("bill_key")]["claims_new"] += 1

tot = Counter()
by_p = defaultdict(Counter)
for b, r in rows.items():
    tot.update(r)
    by_p[parl(b)].update(r)
    if r["para_added"]:
        by_p[parl(b)]["bills_gained"] += 1
        tot["bills_gained"] += 1


def pct(a, b):
    return f"{(b - a) / a:+.1%}" if a else "new"


say()
say(f"ALL ONTARIO   paragraphs {tot['para_old']:,} -> {tot['para_new']:,} ({pct(tot['para_old'], tot['para_new'])}); "
    f"added {tot['para_added']:,}, removed {tot['para_removed']:,}; bill-days {tot['days_old']:,} -> {tot['days_new']:,}")
say(f"              sentences {tot['sent_old']:,} -> {tot['sent_new']:,} ({pct(tot['sent_old'], tot['sent_new'])}); "
    f"claims {tot['claims_old']:,} -> {tot['claims_new']:,} ({pct(tot['claims_old'], tot['claims_new'])})")
say(f"              bills with paragraphs added: {tot['bills_gained']}; bills with claims "
    f"{sum(1 for r in rows.values() if r['claims_old'])} -> {sum(1 for r in rows.values() if r['claims_new'])}")
say()
say("BY PARLIAMENT  (share of the text that was missing = added / paragraphs now)")
say(f"  {'Parl':>4} {'years':<11} {'paragraphs':>19} {'missing':>8} {'bills hit':>9} {'sentences':>21} {'claims':>17}")
YEARS = {"33": "1985-87", "34": "1987-90", "35": "1990-95", "36": "1995-99", "37": "1999-03", "38": "2003-07",
         "39": "2007-11", "40": "2011-14", "41": "2014-18", "42": "2018-22", "43": "2022-25", "44": "2025-"}
for p_ in sorted(by_p, key=lambda x: int(x) if x.isdigit() else 0):
    c = by_p[p_]
    if not (c["para_old"] or c["para_new"] or c["sent_old"] or c["sent_new"]):
        continue
    miss = c["para_added"] / c["para_new"] if c["para_new"] else 0
    say(f"  {p_:>4} {YEARS.get(p_, ''):<11} {c['para_old']:>8,} -> {c['para_new']:>7,} {miss:>8.1%} {c['bills_gained']:>9} "
        f"{c['sent_old']:>9,} -> {c['sent_new']:>8,} {c['claims_old']:>7,} -> {c['claims_new']:>6,}")

say()
say("BILLS WITH THE MOST TEXT ADDED")
for b, r in sorted(rows.items(), key=lambda kv: -kv[1]["para_added"])[:20]:
    if not r["para_added"]:
        break
    say(f"  {b:<14} paragraphs {r['para_old']:>5} -> {r['para_new']:>5}   claims {r['claims_old']:>5} -> {r['claims_new']:>5}")

say()
say(f"PARAGRAPHS REMOVED: {len(removed_list)} (each should have a reason)")
for b, d, p in removed_list[:25]:
    say(f"  {b:<14} {d}  [{str(p.get('topic', ''))[:40]}] {p.get('assignment_method', '')}: {str(p.get('text', ''))[:70]}")

# outcomes
say()
o_now = (load(os.path.join(ROOT, "data/v3_outcomes.json"), {}) or {}).get("ontario", {})
for label, path in (("baseline copy", os.path.join(base, "v3_outcomes.json")),
                    ("Sept 29 (before the royal assent fix)", os.path.join(ROOT, "data/v3_outcomes_before_royal_assent.json"))):
    o_old = (load(path, {}) or {}).get("ontario")
    if o_old is None:
        continue
    study = {b for b, r in rows.items() if r["claims_new"]}
    flag = {1: 1, True: 1, 0: 0, False: 0}
    diff = sorted(b for b in study if flag.get((o_old.get(b) or {}).get("passed")) != flag.get((o_now.get(b) or {}).get("passed")))
    say(f"OUTCOMES of study bills, now vs {label}: {len(diff)} differ {diff[:10]}")

os.makedirs(os.path.join(ROOT, "outputs", "audit"), exist_ok=True)
with open(os.path.join(ROOT, "outputs", "audit", "ontario_fix_by_bill.csv"), "w", newline="", encoding="utf-8") as f:
    cols = ["para_old", "para_new", "para_added", "para_removed", "days_old", "days_new", "sent_old", "sent_new",
            "claims_old", "claims_new"]
    w = csv.writer(f)
    w.writerow(["bill_key", "parliament"] + cols)
    for b in sorted(rows, key=str):
        w.writerow([b, parl(b)] + [rows[b][c] for c in cols])
with open(os.path.join(ROOT, "outputs", "audit", "ontario_fix_report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")
say("\nWrote outputs/audit/ontario_fix_report.txt and outputs/audit/ontario_fix_by_bill.csv")
