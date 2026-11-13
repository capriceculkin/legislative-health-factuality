#!/usr/bin/env python3
"""
check_fix7d.py   (reads only; about a minute)

Checks the Quebec 1985-1994 text after the Oct 5 fix against the two copies saved before: the one from before the
Oct 4 run (data/_before_fix7c_*) and the one from before this run (data/_before_fix7d_*).
  1. sections from 1994 on: must be unchanged
  2. 1985-1994 sections: before Oct 4, after Oct 4, now
  3. Bill 2 of 1985: every day, with the title the Journal prints that day; no day may belong to the 1987 Bill 2
  4. CHECKS on every 1985-1994 bill: no accepted day before the year of its library file, and no accepted day that
     prints another bill's title
  5. the headings that now end a bill's text on the pages without "Affaires du jour" (for reading through)
  6. claims per 1985-1994 bill: before Oct 4, after Oct 4, now
Writes outputs/audit/fix7d_check.txt and prints PASS or FAIL for each check.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix7d.py
"""
import glob
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "quebec_pre1994.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
import quebec_pre1994 as M   # noqa: E402
Q = M.Q
OUT = ROOT / "outputs" / "audit" / "fix7d_check.txt"
QC = "data/canada/quebec_assembly"
PRE = f"{QC}/v3/pre1994"
LINES, RESULTS = [], []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    say(f"CHECK {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return d


def md5(p):
    try:
        return hashlib.md5(open(p, "rb").read()).hexdigest()
    except OSError:
        return None


b7c = sorted(glob.glob("data/_before_fix7c_2*"))
b7d = sorted(glob.glob("data/_before_fix7d_2*"))
if not b7c or not b7d:
    sys.exit("The copies from before Oct 4 (data/_before_fix7c_*) or before this run (data/_before_fix7d_*) are "
             "missing. Send this output to Claude.")
A, B = b7c[0], b7d[-1]          # A: before Oct 4 (the first copy); B: before this run
say(f"before Oct 4: {A}\nbefore this run: {B}")
k_ = lambda e: (e["bill_key"], e["date"], str(e["page_id"]))
IA = {k_(e): e for e in load(f"{A}/segments_index.json", [])}
IB = {k_(e): e for e in load(f"{B}/segments_index.json", [])}
IN = {k_(e): e for e in load(f"{QC}/v3/segments_index.json", [])}
pre = lambda I: {x: e for x, e in I.items() if e.get("source") == "bibliotheque_pre1994"}
post = lambda I: {x: e for x, e in I.items() if e.get("source") != "bibliotheque_pre1994"}

say("\n" + "=" * 100 + "\n1. Sections from 1994 on\n" + "=" * 100)
pb, pn = post(IB), post(IN)
diff = [x for x in set(pb) & set(pn)
        if md5(f"{B}/quebec_bill_segments_v3/{os.path.basename(pb[x]['file'])}") != md5(f"{QC}/{pn[x]['file']}")]
check("sections from 1994 on unchanged", set(pb) == set(pn) and not diff,
      f"{len(pb)} before, {len(pn)} now, text changed {len(diff)}")

say("\n" + "=" * 100 + "\n2. 1985-1994 sections: before Oct 4 | after Oct 4 | now\n" + "=" * 100)
ra, rb, rn = pre(IA), pre(IB), pre(IN)
for name, r in (("before Oct 4", ra), ("after Oct 4", rb), ("now", rn)):
    say(f"   {name:<13} sections {len(r):>4}   bills {len({e['bill_key'] for e in r.values()}):>4}   "
        f"paragraphs {sum(e['n_paragraphs'] for e in r.values()):>7,}")
keys = set(ra) | set(rb) | set(rn)
n = lambda r, x: r.get(x, {}).get("n_paragraphs", 0)
ch = sorted((x for x in keys if n(ra, x) != n(rn, x)), key=lambda x: -abs(n(ra, x) - n(rn, x)))
say(f"   sections that differ from before Oct 4: {len(ch)} (shorter {sum(1 for x in ch if 0 < n(rn, x) < n(ra, x))}, "
    f"gone {sum(1 for x in ch if n(rn, x) == 0)}, longer {sum(1 for x in ch if n(rn, x) > n(ra, x) > 0)}, "
    f"new {sum(1 for x in ch if n(ra, x) == 0)})")
say("   the 40 largest differences (before Oct 4 | after Oct 4 | now):")
for x in ch[:40]:
    say(f"      {x[0]:<14} {x[1]}  {n(ra, x):>5} | {n(rb, x):>5} | {n(rn, x):>5}")

say("\n" + "=" * 100 + "\n3. Bill 2 of 1985\n" + "=" * 100)
found = load(f"{PRE}/bill_days_found.json", []) or []
b2 = sorted((x for x in found if x.get("bill_key") == "33-1-Bill2"), key=lambda x: x["date"])
for x in b2:
    k = ("33-1-Bill2", x["date"], str(x["page_id"]))
    say(f"   {x['date']}  accepted {str(x['accepted']):<5}  paragraphs before Oct 4 {n(ra, k):>5} | after Oct 4 {n(rb, k):>5} | "
        f"now {n(rn, k):>5}   title printed: {str(x.get('title', ''))[:70]!r}")
if b2:
    say(f"   reason: {b2[0].get('why', '')[:250]}")
late = [x["date"] for x in b2 if x["accepted"] and x["date"] >= "19870101"]
check("Bill 2 of 1985 has no day from 1987 on (those belong to the 1987 Bill 2, the voter census law)", not late,
      f"days from 1987 on: {late}")
own = [x["date"] for x in b2 if x["accepted"]]
had = sorted({x["date"] for x in (load(f"{A}/pre1994/bill_days_found.json", []) or [])
              if x.get("bill_key") == "33-1-Bill2" and x.get("accepted")})
check("Bill 2 of 1985 keeps every day it had before Oct 4", set(had) <= set(own), f"before Oct 4 {had}; now {own}")

say("\n" + "=" * 100 + "\n4. Every 1985-1994 bill\n" + "=" * 100)
year_of = {}
for r in load("data/canada/quebec_bills/quebec_health_bills_combined.json", []) or []:
    if r.get("source") == "bibliotheque_pre1994" and r.get("number_source"):
        for f in r.get("library_files") or []:
            year_of[f] = r.get("library_year")
early = [(x["bill_key"], x["date"], year_of.get(x.get("library_file"))) for x in found if x.get("accepted")
         and year_of.get(x.get("library_file")) and int(x["date"][:4]) < int(year_of[x["library_file"]])]
check("no accepted day before the year of the bill's library file", not early, f"{len(early)}: {early[:10]}")
title_of = {f"{r['session']}-Bill{r['bill_number']}": r.get("title", "")
            for r in load(f"{PRE}/scan_result.json", []) or [] if r.get("days")}
foreign = [(x["bill_key"], x["date"], x.get("title", "")[:50]) for x in found if x.get("accepted") and x.get("title")
           and title_of.get(x["bill_key"]) and not M.same_bill(x["title"], title_of[x["bill_key"]])]
check("no accepted day prints another bill's title", not foreign, f"{len(foreign)}: {foreign[:10]}")
fa = {(x["bill_key"], x["date"]) for x in (load(f"{A}/pre1994/bill_days_found.json", []) or []) if x.get("accepted")}
fb = {(x["bill_key"], x["date"]) for x in (load(f"{B}/pre1994/bill_days_found.json", []) or []) if x.get("accepted")}
fn = {(x["bill_key"], x["date"]) for x in found if x.get("accepted")}
say(f"   accepted bill-days: before Oct 4 {len(fa)}, after Oct 4 {len(fb)}, now {len(fn)}")
say(f"   accepted before Oct 4 but not now ({len(fa - fn)}): {sorted(fa - fn)[:40]}")
say(f"   accepted now but not before Oct 4 ({len(fn - fa)}): {sorted(fn - fa)[:60]}")
why = {x["bill_key"]: x.get("why", "") for x in found}
for k, d in sorted(fa - fn):
    say(f"      {k} {d}: {why.get(k, '')[:160]}")

say("\n" + "=" * 100 + "\n5. Headings that end a bill's text on pages without Affaires du jour\n" + "=" * 100)
ended, pieces, n_strict = {}, 0, 0
for path in sorted({Q.cache_path(e["url"]) for e in rn.values()}):
    if not os.path.exists(path):
        continue
    with open(path, encoding="utf-8", errors="ignore") as f:
        segs, blocks = Q.parse_page(f.read(), old_format=True)
    if any(b["heading"] and Q._OLD_STRUCT.match(Q._norm(b["text"])) for b in blocks):
        continue
    n_strict += 1
    for i in range(len(blocks) - 1):
        b = blocks[i]
        if b["heading"] and b["bill"] is not None and blocks[i + 1]["bill"] is None:
            k = Q._norm(b["text"])[:60]
            c = ended.setdefault(k, [0, b["text"][:90], os.path.basename(path), b["bill"]])
            c[0] += 1
            pieces += b["text"][:1].islower()
say(f"   pages read with the stricter rules: {n_strict}; headings that ended a bill's text: "
    f"{sum(c[0] for c in ended.values())} ({len(ended)} different)")
say(f"   bills' text ended at a heading line starting with a small letter: {pieces} (was about 130 on Oct 4; "
    "for reading, not a check)")
for k, (c, text, page, bill) in sorted(ended.items(), key=lambda kv: -kv[1][0])[:60]:
    say(f"      {c:>4}x  {text:<90}  e.g. {page} (bill {bill})")

say("\n" + "=" * 100 + "\n6. Claims per 1985-1994 bill: before Oct 4 | after Oct 4 | now\n" + "=" * 100)


def per_bill(path):
    p = load(path, [])
    if isinstance(p, dict):
        p = p.get("predications") or p.get("results") or list(p.values())
    p = p or []
    return len(p), Counter(str(x.get("bill_key")) for x in p if isinstance(x, dict))


(ta, ca), (tb, cb), (tn, cn) = (per_bill(f"{A}/quebec/predications_v3.json"), per_bill(f"{B}/quebec/predications_v3.json"),
                                per_bill("data/dbpedia_pipeline/quebec/predications_v3.json"))
say(f"   Quebec claims: before Oct 4 {ta:,} | after Oct 4 {tb:,} | now {tn:,}")
prek = {e["bill_key"] for e in list(ra.values()) + list(rn.values())}
d = sorted(((cn.get(k, 0) - ca.get(k, 0), k) for k in prek if cn.get(k, 0) != ca.get(k, 0)))
for v, k in d[:15] + d[-15:]:
    say(f"      {k:<16} {ca.get(k, 0):>6} | {cb.get(k, 0):>6} | {cn.get(k, 0):>6}")

say("\n" + "=" * 100)
say(f"CHECKS: {sum(1 for _, ok in RESULTS if ok)} passed, {sum(1 for _, ok in RESULTS if not ok)} failed")
for name, ok in RESULTS:
    say(f"   {'PASS' if ok else 'FAIL'}  {name}")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
print(f"\nSaved {OUT}")
