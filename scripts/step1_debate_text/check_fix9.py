#!/usr/bin/env python3
"""
check_fix9.py   (reads only; a minute)

Checks after the Ontario rebuild with the vetted supplement:
  1. every Ontario bill-day that existed before is unchanged, except 33-2 Bill 55 on 1986-07-10, which only grows
  2. the new and extended bill-days are exactly the 34 Claude tested on your files, with the same paragraph counts
  3. every added paragraph is in its bill's own session and the day names the bill (Bill 29 of 1999: by title)
  4. 33-1 Bill 55 is not passed (it died at prorogation; the final-stages file's "royal assent December 6" is
     impossible, since its second reading was January 13, 1986)
  5. Ontario sentences and claims cover the new bill-days, and the audit has no FAIL
Writes outputs/audit/fix9_check.txt. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix9.py <copy folder from before fix9>
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "ontario_rebuild.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT)
B = Path(sys.argv[1]) if len(sys.argv) > 1 else None
HERE = Path(__file__).resolve().parent
EXP = json.load(open(HERE / "expected_fix9.json", encoding="utf-8"))
OUT = Path("outputs/audit/fix9_check.txt")
LINES, RES = [], []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def check(name, ok, detail=""):
    RES.append(ok)
    say(f"CHECK {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return d


a = load(B / "hansard_segments_v3.json", {})
b = load("data/canada/ontario/v3/hansard_segments_v3.json", {})
bm = load("data/canada/ontario/v3/bills_master.json", {})
altered, changed = [], {}
for k in set(a) | set(b):
    for d in set(a.get(k, {})) | set(b.get(k, {})):
        x = [p["text"] for p in a.get(k, {}).get(d, [])]
        y = [p["text"] for p in b.get(k, {}).get(d, [])]
        if x == y:
            continue
        changed[f"{k}|{d}"] = [len(x), len(y)]
        if y[:len(x)] != x:
            altered.append(f"{k} {d}")
check("1. no bill-day that existed before lost or changed a paragraph", not altered, f"{len(altered)} {altered[:5]}")
check("2. the added bill-days and paragraph counts are exactly the ones tested", changed == EXP["changed"],
      f"{len(changed)} changed (expected {len(EXP['changed'])}); bill-days {sum(len(v) for v in b.values())} "
      f"(expected {EXP['bill_days_after']}); paragraphs {sum(len(p) for v in b.values() for p in v.values()):,} "
      f"(expected {EXP['paragraphs_after']:,})")

bad = []
for kd, (n0, n1) in changed.items():
    k, d = kd.split("|")
    new = b[k][d][n0:]
    s = k.split("-Bill")[0].split("-")
    sess_ok = all(re.search(rf"parliament-{s[0]}/session-{s[1]}/", p.get("url", "")) for p in new)
    num = bm.get(k, {}).get("bill_number")
    txt = " ".join(p["text"] for p in new)
    named = bool(re.search(rf"\bBills?\s+{num}\b", txt)) or (k == "37-1-Bill29" and "Ambulance Act" in txt)
    if not (sess_ok and named):
        bad.append(f"{k} {d} session_ok={sess_ok} named={named}")
check("3. every added paragraph is in its bill's session and the day names the bill", not bad, "; ".join(bad[:4]) or "34 of 34")

o = load("data/v3_outcomes.json", {}).get("ontario", {})
check("4. 33-1 Bill 55 is not passed", o.get("33-1-Bill55", {}).get("passed") == 0, str(o.get("33-1-Bill55", {}).get("outcome_raw", ""))[:120])

sents = load("data/dbpedia_pipeline/ontario/sentences_v3.json", [])
have = {(r.get("bill_key"), str(r.get("date"))[:10]) for r in sents}
missing = [kd for kd in changed if tuple(kd.split("|")) not in have]
rep = Path("outputs/audit/audit_report.txt")
fails = [l for l in rep.read_text(encoding="utf-8").splitlines() if "[FAIL]" in l] if rep.exists() else ["no audit report"]
check("5. the new bill-days have sentences, and the audit has no FAIL", not missing and not fails,
      f"bill-days without sentences {missing[:5]}; audit {fails[:2] or '0 FAIL'}")
preds = load("data/dbpedia_pipeline/ontario/predications_v3.json", [])
before = len(load(B / "ontario_predications_v3.json", []) or [])
say(f"\nOntario claims: {before:,} -> {len(preds):,}")
say(f"CHECKS: {sum(RES)} passed, {len(RES) - sum(RES)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
sys.exit(2 if not all(RES) else 0)
