#!/usr/bin/env python3
"""
apply_royal_assent.py   (run after outcomes_v3.py; changes data/v3_outcomes.json)

Ontario bills with no OLA bill status page (all bills before 1995, and non-study bills
after) get their outcome from the FSOB vote file. Two readings of that file can be
wrong: "bill absent = not passed" and "empty royal assent field = not passed". Bill 50
(35-3) is one case: absent from FSOB, yet listed under ROYAL ASSENT in the Hansard of
1993-12-14.

This step uses the Hansard's own ROYAL ASSENT lists (saved by check_royal_assent.py)
as a second source. A bill named in a royal assent list of its session is marked
passed. Not being named is NOT used as "not passed", because the lists in the API
have gaps.

The rule is used only if it holds up against the references we already trust: among
bills named in a list, the share that the reference says passed must be at least 95%
for every reference with 30 or more bills (OLA status pages; the FSOB royal assent
field). Otherwise nothing is changed.

Bills with an OLA status page are never changed (that page is the ground truth).
A backup of the outcome file is kept as data/v3_outcomes_before_royal_assent.json.
Every change is listed in outputs/audit/royal_assent_changes.csv.

Run from the project folder, after outcomes_v3.py:
  python3 scripts/step1_debate_text/apply_royal_assent.py
"""
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "data" / "v3_outcomes.json"
BACKUP = ROOT / "data" / "v3_outcomes_before_royal_assent.json"
CACHE = ROOT / "data" / "canada" / "ontario" / "v3" / "royal_assent_lists.json"
PREDS = ROOT / "data" / "dbpedia_pipeline" / "ontario" / "predications_v3.json"
REPORT = ROOT / "outputs" / "audit" / "royal_assent_changes.csv"
AGREE_MIN, MIN_N = 0.95, 30
SRC = "Hansard royal assent list"


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def flag(v):
    return {1: 1, True: 1, 0: 0, False: 0}.get(v)


outcomes = load(OUT_JSON) or sys.exit(f"missing {OUT_JSON}; run outcomes_v3.py first")
cache = load(CACHE) or sys.exit(f"missing {CACHE}; run check_royal_assent.py first")
named = cache.get("bills", {})
covered = set(cache.get("sessions_covered", []))
on = outcomes.get("ontario", {})
study = {str(p.get("bill_key")) for p in (load(PREDS, []) or [])}


def sess(k):
    return k.rsplit("-Bill", 1)[0]


# 1. how far "named in a royal assent list = passed" holds against each reference
refs = {"OLA bill status page": [], "FSOB royal assent field": []}
for k, o in on.items():
    if k not in named or sess(k) not in covered:
        continue
    src = str(o.get("source") or "")
    before = o.get("before_royal_assent") or {}
    if src == SRC:                       # already changed by an earlier run: use the old reading
        src, f = str(before.get("source") or ""), flag(before.get("passed"))
    else:
        f = flag(o.get("passed"))
    if f is None:
        continue
    if src == "OLA bill status page":
        refs["OLA bill status page"].append(f)
    elif src == "ontario_fsob_votes.json (royal assent field)":
        refs["FSOB royal assent field"].append(f)

print("Bills named in a royal assent list, and what each trusted reference says about them:")
usable, enough = True, False
for name, fl in refs.items():
    if not fl:
        print(f"  {name}: no overlap")
        continue
    p = sum(fl) / len(fl)
    print(f"  {name}: {sum(fl)}/{len(fl)} passed ({p:.1%})" + ("" if len(fl) >= MIN_N else f"  (fewer than {MIN_N}, not counted)"))
    if len(fl) >= MIN_N:
        enough = True
        usable = usable and p >= AGREE_MIN
use = usable and enough
print(f"Use royal assent lists to correct 'not passed': {use} (needs >= {AGREE_MIN:.0%} on every reference "
      f"with >= {MIN_N} bills)\n")
if not use:
    sys.exit("No changes made.")

# 2. apply (a fresh outcomes_v3.py run has no royal-assent entries yet: keep that file as the backup)
if not any(o.get("source") == SRC for o in on.values()):
    shutil.copy(OUT_JSON, BACKUP)
changes = []
for k, o in sorted(on.items()):
    if k not in named or o.get("source") in ("OLA bill status page", SRC):
        continue
    if flag(o.get("passed")) == 1:
        continue
    before = {"passed": o.get("passed"), "source": o.get("source"), "outcome_raw": o.get("outcome_raw")}
    d = named[k].get("date", "")
    o["before_royal_assent"] = before
    o["passed"] = 1
    o["source"] = SRC
    o["outcome_raw"] = f"Hansard: named in the ROYAL ASSENT list of {d}"
    o["outcome_date"] = d
    p_, s_, n_ = k.split("-")[0], k.split("-")[1], k.rsplit("Bill", 1)[1]
    url = f"https://www.ola.org/en/legislative-business/house-documents/parliament-{p_}/session-{s_}/{d}/hansard"
    o["check"] = (str(o.get("check") or "") + ("; " if o.get("check") else "")
                  + f"royal assent list {d} overrides {before['source']} ({before['outcome_raw']})")
    changes.append({"bill_key": k, "in_study": "yes" if k in study else "no",
                    "before": {1: "passed", 0: "not passed"}.get(flag(before["passed"]), "pending/none"),
                    "before_source": before["source"], "after": "passed", "royal_assent_date": d, "hansard": url})

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(outcomes, f, ensure_ascii=False, indent=1)
# the report lists every bill corrected so far (this run and earlier ones), not only this run's
new_keys = {c["bill_key"] for c in changes}
for k, o in sorted(on.items()):
    if o.get("source") == SRC and k not in new_keys:
        bf = o.get("before_royal_assent") or {}
        p_, s_ = k.split("-")[0], k.split("-")[1]
        d = o.get("outcome_date", "")
        changes.append({"bill_key": k, "in_study": "yes" if k in study else "no",
                        "before": {1: "passed", 0: "not passed"}.get(flag(bf.get("passed")), "pending/none"),
                        "before_source": bf.get("source"), "after": "passed", "royal_assent_date": d,
                        "hansard": f"https://www.ola.org/en/legislative-business/house-documents/parliament-{p_}/session-{s_}/{d}/hansard"})
changes.sort(key=lambda c: c["bill_key"])
REPORT.parent.mkdir(parents=True, exist_ok=True)
with open(REPORT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["bill_key", "in_study", "before", "before_source", "after",
                                      "royal_assent_date", "hansard"])
    w.writeheader()
    w.writerows(changes)

ins = [c for c in changes if c["in_study"] == "yes"]
print(f"Corrected to passed (all runs): {len(changes)} Ontario bills, {len(ins)} of them study bills (bills with claims); "
      f"new this run: {len(new_keys)}")
for c in ins:
    print(f"  {c['bill_key']:<14} {c['before']:<12} -> passed   royal assent {c['royal_assent_date']}   ({c['before_source']})")


def split(src_on):
    c = {"passed": 0, "not passed": 0, "pending/none": 0}
    for k in study:
        o = src_on.get(k)
        if o is None:
            continue
        c[{1: "passed", 0: "not passed"}.get(flag(o.get("passed")), "pending/none")] += 1
    return c


old_on = (load(BACKUP) or {}).get("ontario", {})
print(f"\nOntario study bills, passed / not passed / pending:  before {split(old_on)}  now {split(on)}")
print(f"Wrote {OUT_JSON} (backup {BACKUP.name}) and {REPORT}")
