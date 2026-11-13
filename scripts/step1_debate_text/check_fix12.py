#!/usr/bin/env python3
"""
check_fix12.py   (reads only; a minute)

Checks after Bill 149's evening sitting of December 2, 1997 was added from the page you saved:
  1. every other Ontario bill-day is unchanged
  2. 36-1 Bill 149 on 1997-12-02 holds exactly the 70 rows of the evening page, word for word (17,563 words)
  3. every added paragraph is on that page (parliament 36, session 1, hansard-1) and the day names Bill 149
  4. the new bill-day has sentences, and the audit has no FAIL
  5. Bill 149's outcome is the same as before (passed: third reading carried December 3, 1997)
Writes outputs/audit/fix12_check.txt. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix12.py <copy folder from before fix12>
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
EXP = json.load(open(HERE / "expected_fix12.json", encoding="utf-8"))
KEY, DAY = EXP["bill_key"], EXP["date"]
OUT = Path("outputs/audit/fix12_check.txt")
LINES, RES = [], []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def check(name, ok, detail=""):
    RES.append(bool(ok))
    say(f"CHECK {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def load(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


a = load(B / "hansard_segments_v3.json", {}) if B else {}
b = load("data/canada/ontario/v3/hansard_segments_v3.json", {})
changed = []
for k in set(a) | set(b):
    for d in set(a.get(k, {})) | set(b.get(k, {})):
        if (k, d) == (KEY, DAY):
            continue
        if [p["text"] for p in a.get(k, {}).get(d, [])] != [p["text"] for p in b.get(k, {}).get(d, [])]:
            changed.append(f"{k} {d}")
check("1. every other Ontario bill-day unchanged", bool(a) and not changed, f"{len(changed)} changed {changed[:4]}")

rows = load(f"data/canada/ontario/v3/raw_supplement/{KEY}/{DAY}.json", []) or []
new = b.get(KEY, {}).get(DAY, [])
w_new = " ".join(p["text"] for p in new).split()
w_rows = " ".join(clean(r["paragraph"]) for r in rows).split()
check("2. the new bill-day is the evening page, word for word", len(new) == EXP["rows"] and w_new == w_rows
      and len(w_new) == EXP["words"], f"{len(new)} paragraphs (expected {EXP['rows']}), {len(w_new):,} words "
      f"(expected {EXP['words']:,})")
on_page = all("parliament-36/session-1/1997-12-02/hansard-1" in (p.get("url", "") + p.get("para_url", "")) for p in new)
named = sum(bool(re.search(r"\bBill 149\b", p["text"])) for p in new)
check("3. every added paragraph is on that page, and the day names Bill 149", bool(new) and on_page and named > 0,
      f"on the page: {on_page}; paragraphs naming Bill 149: {named}")

sents = load("data/dbpedia_pipeline/ontario/sentences_v3.json", []) or []
n_s = sum(1 for s in sents if s.get("bill_key") == KEY and str(s.get("date"))[:10] == DAY)
rep = Path("outputs/audit/audit_report.txt")
fails = [l for l in rep.read_text(encoding="utf-8").splitlines() if "[FAIL]" in l] if rep.exists() else ["no audit"]
check("4. the new bill-day has sentences, and the audit has no FAIL", n_s > 0 and not fails,
      f"{n_s} sentences; audit {fails[:2] or '0 FAIL'}")

o_a = (load(B / "v3_outcomes.json", {}) or {}).get("ontario", {}).get(KEY, {}) if B else {}
o_b = (load("data/v3_outcomes.json", {}) or {}).get("ontario", {}).get(KEY, {})
check("5. Bill 149's outcome unchanged", o_a.get("passed") == o_b.get("passed") == 1,
      f"before {o_a.get('passed')}, now {o_b.get('passed')}")
preds = load("data/dbpedia_pipeline/ontario/predications_v3.json", []) or []
before = len(load(B / "ontario_predications_v3.json", []) or []) if B else 0
say(f"\nOntario claims: {before:,} -> {len(preds):,}  (Bill 149 on {DAY}: "
    f"{sum(1 for p in preds if p.get('bill_key') == KEY and str(p.get('date'))[:10] == DAY)})")
say(f"CHECKS: {sum(RES)} passed, {len(RES) - sum(RES)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
sys.exit(2 if not all(RES) else 0)
