#!/usr/bin/env python3
"""
patch_compute_scores_outcomes.py
Makes compute_scores_v3.py read data/v3_outcomes.json (built by outcomes_v3.py)
instead of its own outcome code, which had three bugs:
  - Quebec read quebec_health_bills_combined.json, which has no outcome field
  - US kept the LAST plan.json row per bill, even when that row's result is blank
  - outcome_found was Y whenever the bill existed in the file, even with a blank outcome
Saves a backup as compute_scores_v3.py.bak and refuses to write if anything
does not match exactly.
Run from project root:  python3 scripts/step1_debate_text/patch_compute_scores_outcomes.py
"""
import re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
P = ROOT / "scripts" / "step1_debate_text" / "compute_scores_v3.py"
src = P.read_text(encoding="utf-8")

if "v3_outcomes.json" in src:
    sys.exit("Already patched. Nothing changed.")

NEW_FUNC = '''def outcomes(j):
    """Outcomes from data/v3_outcomes.json (scripts/step1_debate_text/outcomes_v3.py).
    Value is the raw outcome text; empty string when no pass/fail is known."""
    table = load_json(rp("data/v3_outcomes.json"), None)
    if table is None:
        sys.exit("data/v3_outcomes.json not found. Run: python3 scripts/step1_debate_text/outcomes_v3.py")
    return {k: (v.get("outcome_raw") or "") if v.get("passed") is not None else ""
            for k, v in (table.get(j) or {}).items()}


def outcome_passed(j):
    table = load_json(rp("data/v3_outcomes.json"), None) or {}
    return {k: v.get("passed") for k, v in (table.get(j) or {}).items()}


'''

m = re.search(r"^def outcomes\(j\):\n.*?(?=^def run\()", src, flags=re.S | re.M)
if not m:
    sys.exit("Could not find 'def outcomes(j):' followed by 'def run('. File not changed.")
new = src[:m.start()] + NEW_FUNC + src[m.end():]

old_found = '"outcome_found": "Y" if b in outc else "N"'
if new.count(old_found) != 1:
    sys.exit(f"Expected exactly one '{old_found}', found {new.count(old_found)}. File not changed.")
new = new.replace(old_found, '"outcome_found": "Y" if outc.get(b) else "N"')

if not re.search(r"^import .*\bsys\b|^import sys", new, flags=re.M):
    new = "import sys\n" + new

compile(new, str(P), "exec")          # refuse to write a file that does not parse
shutil.copy2(P, P.with_suffix(".py.bak"))
P.write_text(new, encoding="utf-8")
print(f"Patched {P.relative_to(ROOT)} (backup: {P.with_suffix('.py.bak').name})")
print("  outcomes(j) now reads data/v3_outcomes.json")
print("  outcome_found is Y only when an outcome value exists")
