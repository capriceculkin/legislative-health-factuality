#!/usr/bin/env python3
"""
check_us_not_listed.py   (reads only)
Shows what each US section is on a day Congress.gov lists no House floor action for its bill
("NOT LISTED on Congress.gov" in debate_days_vs_congress.csv): the Record headings of the
section, how it was chosen, how often it names its bill, and how it starts. A floor debate
continued from the day before, a rule debate, or members' speeches about the bill each look
different here, so this decides whether those days belong.
Run from the project folder (after compare_debate_days.py):
  python3 scripts/step1_debate_text/check_us_not_listed.py
Writes outputs/audit/us_not_listed_check.txt
"""
import csv
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from v3_common import us_bill_mention_re          # the same bill-name pattern the rebuild uses
except Exception:                                     # noqa: BLE001
    us_bill_mention_re = None

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV = os.path.join(ROOT, "outputs", "audit", "debate_days_vs_congress.csv")
REPORT = os.path.join(ROOT, "outputs", "audit", "us_not_listed_check.txt")
PFX = {"hr": r"H\.\s?R\.", "s": r"S\.", "hres": r"H\.\s?Res\.", "hjres": r"H\.\s?J\.\s?Res\.",
       "hconres": r"H\.\s?Con\.\s?Res\.", "sjres": r"S\.\s?J\.\s?Res\.", "sconres": r"S\.\s?Con\.\s?Res\.",
       "sres": r"S\.\s?Res\."}
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def short(s, n=150):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 3] + "..."


with open(CSV, encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["status"] == "NOT LISTED on Congress.gov"]
with open(os.path.join(ROOT, "data", "us", "v3", "segments_index.json"), encoding="utf-8") as f:
    idx = {(e["bill_key"], e["debate_date"]): e for e in json.load(f)}
kinds = Counter()
say(f"US sections on days Congress.gov lists no House action for the bill: {len(rows)}")
for r in rows:
    e = idx.get((r["bill_key"], r["date"]))
    if not e:
        say(f"\n{r['bill_key']} {r['date']}: not in the index")
        continue
    try:
        with open(os.path.join(ROOT, "data", "us", e["file"]), encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        text = ""
    try:
        rx = us_bill_mention_re(e["type"], e["number"])
    except Exception:                                 # noqa: BLE001
        rx = re.compile(PFX.get(str(e.get("type", "")).lower(), "x^") + r"\s?" + str(e.get("number")) + r"\b", re.I)
    titles = Counter(u.get("title", "") for u in e.get("units", []))
    methods = Counter(u.get("method", "") for u in e.get("units", []))
    t0 = " ".join(titles).upper()
    kind = ("rule / procedure" if re.search(r"PROVIDING FOR|WAIVING|RULE|MOTION TO INSTRUCT|CONFEREES", t0) else
            "speeches (one-minute / special orders)" if re.search(r"SPECIAL ORDER|ONE MINUTE|MORNING[- ]HOUR", t0) else
            "the bill's own debate heading" if rx.search(t0) or re.search(r"\bACT\b", t0) else "other")
    kinds[kind] += 1
    say(f"\n{r['bill_key']} {r['date']}  (vote {e.get('vote_date')}, {e.get('date_source')}; {kind})")
    say(f"   headings: " + "; ".join(f"{short(t, 70)} x{n}" for t, n in titles.most_common(3)))
    say(f"   chosen by: {dict(methods)}; names the bill {len(rx.findall(text))} time(s); {len(text.split()):,} words")
    say(f"   starts: {short(text)}")
say("\nby kind: " + ", ".join(f"{k} {n}" for k, n in kinds.most_common()))
os.makedirs(os.path.dirname(REPORT), exist_ok=True)
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")
print(f"Saved {REPORT}")
