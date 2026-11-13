#!/usr/bin/env python3
"""
check_fix7f.py   (reads only; about a minute)

The last check on the Quebec 1985-1994 text. Claude ran the same scripts on a copy of your saved pages and read every
section against its page; this compares what your machine produced with that reference, section by section:
  1. sections from 1994 on: unchanged
  2. every 1985-1994 bill-day and its paragraph count: identical to the reference (419 bill-days of 115 bills)
  3. every 1985-1994 outcome: identical to the reference (from the Journal's final-adoption votes)
  4. the three sections that looked odd on the reference and were read: Bill 7 (1985-12-19), Bill 130 (1987-03-10) and
     Bill 411 (1991-12-06); any other section whose text never names its bill or drifts into another bill is a FAIL
Writes outputs/audit/fix7f_check.txt and prints PASS or FAIL for each check. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix7f.py
"""
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "quebec_pre1994.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
import quebec_rebuild as Q   # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "audit" / "fix7f_check.txt"
QC = "data/canada/quebec_assembly"
NUM = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[°ºo]\.?\s*|num[eé]ro\s+)?(\d+)\b", re.I)
KNOWN = {("33-1-Bill7", "19851219"), ("33-1-Bill130", "19870310"), ("34-1-Bill411", "19911206")}
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


ref = load(HERE / "expected_fix7f.json")
if not ref:
    sys.exit("expected_fix7f.json is missing next to this script. Nothing checked.")
befores = sorted(glob.glob("data/_before_fix7f_2*"))
if not befores:
    sys.exit("No copy from before this run (data/_before_fix7f_*). Nothing checked.")
B = befores[-1]
say(f"copy from before this run: {B}")
k_ = lambda e: (e["bill_key"], e["date"], str(e["page_id"]))
IB = {k_(e): e for e in load(f"{B}/segments_index.json", [])}
IN = {k_(e): e for e in load(f"{QC}/v3/segments_index.json", [])}
pb = {x: e for x, e in IB.items() if e.get("source") != "bibliotheque_pre1994"}
pn = {x: e for x, e in IN.items() if e.get("source") != "bibliotheque_pre1994"}
diff = [x for x in set(pb) & set(pn)
        if md5(f"{B}/quebec_bill_segments_v3/{os.path.basename(pb[x]['file'])}") != md5(f"{QC}/{pn[x]['file']}")]
check("1. sections from 1994 on unchanged", set(pb) == set(pn) and not diff, f"{len(pb)} before, {len(pn)} now, text changed {len(diff)}")

pre = [e for e in IN.values() if e.get("source") == "bibliotheque_pre1994"]
got = {f"{e['bill_key']}|{e['date']}": e["n_paragraphs"] for e in pre}
exp = ref["days"]
missing = sorted(set(exp) - set(got)); extra = sorted(set(got) - set(exp))
sized = sorted((k, exp[k], got[k]) for k in set(exp) & set(got) if exp[k] != got[k])
say(f"   1985-1994 bill-days: reference {len(exp)}, here {len(got)}; bills here {len({e['bill_key'] for e in pre})}; paragraphs {sum(got.values()):,}")
for k in missing[:20]:
    say(f"      missing here: {k} ({exp[k]} paragraphs on the reference)")
for k in extra[:20]:
    say(f"      extra here: {k} ({got[k]} paragraphs)")
for k, a, b in sized[:20]:
    say(f"      size differs: {k} reference {a}, here {b}")
check("2. every 1985-1994 bill-day and its size matches the reference", not missing and not extra and not sized,
      f"missing {len(missing)}, extra {len(extra)}, size differs {len(sized)}")

po = load("data/canada/quebec_bills/quebec_pre1994_vote_outcomes.json", {}) or {}
items = po if isinstance(po, dict) else {f"{v['session']}-Bill{int(v['bill_number'])}": v for v in po}
oc = {k: [v.get("outcome"), v.get("vote_date")] for k, v in items.items() if "journal_outcome" in v}
odiff = sorted((k, ref["outcomes"].get(k), oc.get(k)) for k in set(ref["outcomes"]) | set(oc) if ref["outcomes"].get(k) != oc.get(k))
for k, a, b in odiff[:20]:
    say(f"      outcome differs: {k} reference {a}, here {b}")
say(f"   outcomes from the Journal: {dict(Counter(v[0] for v in oc.values()))}")
check("3. every 1985-1994 outcome matches the reference", len(oc) >= 100 and not odiff, f"{len(oc)} bills with a Journal outcome, differ {len(odiff)}")

flags, cache = [], {}
for e in pre:
    p = Q.cache_path(e["url"])
    if not os.path.exists(p):
        flags.append((e["bill_key"], e["date"], "page not saved")); continue
    if p not in cache:
        with open(p, encoding="utf-8", errors="ignore") as f:
            cache[p] = Q.parse_page(f.read(), old_format=True)
    segs, blocks = cache[p]
    bill = int(e["bill_number"])
    mine = [i for i, b in enumerate(blocks) if b["bill"] == bill and not b["heading"]]
    if len(mine) != e["n_paragraphs"]:
        flags.append((e["bill_key"], e["date"], f"the page gives {len(mine)} paragraphs, the index {e['n_paragraphs']}")); continue
    own = Counter(int(m.group(1)) for j in mine for m in NUM.finditer(blocks[j]["text"]))
    f = []
    s0 = mine[0]
    if not any(any(int(m.group(1)) == bill for m in NUM.finditer(blocks[j]["text"])) for j in range(max(0, s0 - 4), s0 + 1)):
        f.append("starts without the bill being named")
    for k in range(0, len(mine), 40):
        w = mine[k:k + 40]
        c = Counter(int(m.group(1)) for j in w for m in NUM.finditer(blocks[j]["text"]))
        oth = [(n, x) for n, x in c.most_common() if n != bill and x >= 3]
        if oth and c.get(bill, 0) == 0:
            f.append(f"drifts into Bill {oth[0][0]} at paragraph {k}"); break
    if own.get(bill, 0) == 0 and len(mine) > 10:
        f.append("never names its bill")
    top = [(n, x) for n, x in own.most_common(2) if n != bill and x > own.get(bill, 0) and x >= 3]
    if top:
        f.append(f"names Bill {top[0][0]} more often ({top[0][1]}x)")
    if f and (e["bill_key"], e["date"]) not in KNOWN:
        flags.append((e["bill_key"], e["date"], "; ".join(f)))
for x in flags[:20]:
    say(f"      {x}")
check("4. no section starts unnamed, drifts, or names another bill more (beyond the three read on the reference)", not flags, f"{len(flags)}")

say("\nBill 2 of 1985, paragraphs per day:")
for e in sorted((e for e in pre if e["bill_key"] == "33-1-Bill2"), key=lambda e: e["date"]):
    say(f"   {e['date']}  {e['n_paragraphs']:>4}  stages {e.get('stages')}")
say(f"\nCHECKS: {sum(1 for _, ok in RESULTS if ok)} passed, {sum(1 for _, ok in RESULTS if not ok)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
print(f"Saved {OUT}")
sys.exit(2 if any(not ok for _, ok in RESULTS) else 0)
