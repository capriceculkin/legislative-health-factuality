#!/usr/bin/env python3
"""
check_canada_changes.py   (reads only)

Looks inside the sections the Canada fix added or grew, to confirm each one is its own
bill's debate and did not run on into something else:
  QUEBEC   every added or grown section: how often it names its own bill vs other bills,
           and its first and last paragraph (a section that ends inside another bill's
           debate names that other bill more than its own)
  ONTARIO  every bill-day now kept only because a line names the bill under a non-bill
           heading (anchor split), with its first and last paragraph, so it is visible
           where the kept text starts and stops
Run from the project folder:
  python3 scripts/step1_debate_text/check_canada_changes.py
Uses the newest data/_before_canada_fix_* copy. Writes outputs/audit/canada_changes_check.txt
"""
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REPORT = os.path.join(ROOT, "outputs", "audit", "canada_changes_check.txt")
QC = os.path.join(ROOT, "data", "canada", "quebec_assembly")
LINES = []
FR_BILL = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[o°º]?\.?\s*|numero\s+)?(\d+)(?!\d)")
EN_BILL = re.compile(r"\bbill\s+(?:no\.\s*)?(\d+)\b")


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t.replace(" ", " ")).lower()


def short(s, n=130):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 3] + "..."


def paras_of(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [x.strip() for x in f.read().split("\n\n") if x.strip()]
    except OSError:
        return None


def quebec(before):
    say("=" * 78 + "\nQUEBEC: sections added or grown by the fix\n" + "=" * 78)
    old = {(e.get("bill_key"), e.get("date"), str(e.get("page_id"))): e
           for e in load(os.path.join(before, "segments_index.json"), []) or []}
    new = load(os.path.join(QC, "v3", "segments_index.json"), []) or []
    flagged = 0
    rows = []
    for e in new:
        k = (e.get("bill_key"), e.get("date"), str(e.get("page_id")))
        own = int(e.get("bill_number", -1))
        np_ = paras_of(os.path.join(QC, e["file"])) or []
        if k in old:
            op = paras_of(os.path.join(before, "quebec_bill_segments_v3", os.path.basename(old[k]["file"])))
            if op is None or op == np_:
                continue
            added = [p for p in np_ if p not in set(op)]
            label = f"GREW {len(op)} -> {len(np_)} paragraphs"
        else:
            added = np_
            label = f"NEW {len(np_)} paragraphs"
        if not added:
            continue
        c = Counter(int(n) for p in added for n in FR_BILL.findall(norm(p)))
        mine = c.pop(own, 0)
        others = c.most_common(3)
        bad = bool(others) and others[0][1] > max(mine, 1)
        flagged += bad
        rows.append((bad, k, label, mine, others, added))
    rows.sort(key=lambda r: (not r[0], -len(r[5])))
    for bad, k, label, mine, others, added in rows:
        say(f"\n{'CHECK  ' if bad else 'ok     '}{k[0]} {k[1]}  {label}")
        say(f"       in the new text: own bill named {mine} time(s); other bills named: "
            + (", ".join(f"n {b} x{n}" for b, n in others) if others else "none"))
        say(f"       first: {short(added[0])}")
        say(f"       last:  {short(added[-1])}")
    say(f"\nQuebec sections checked: {len(rows)}; flagged CHECK (another bill named more often than its own): {flagged}")


def ontario(before):
    say("\n" + "=" * 78 + "\nONTARIO: bill-days kept through a line naming the bill under a non-bill heading\n" + "=" * 78)
    old = load(os.path.join(before, "hansard_segments_v3.json"), {}) or {}
    new = load(os.path.join(ROOT, "data", "canada", "ontario", "v3", "hansard_segments_v3.json"), {}) or {}
    n = 0
    for bk in sorted(new):
        for d in sorted(new[bk]):
            paras = new[bk][d]
            split = [p for p in paras if str(p.get("assignment_method", "")).startswith("anchor_split:other_heading")]
            if not split:
                continue
            n += 1
            is_new = d not in old.get(bk, {})
            num = bk.rsplit("-Bill", 1)[1]
            c = Counter(x for p in split for x in EN_BILL.findall(norm(p.get("text", ""))))
            mine = c.pop(num, 0)
            heads = Counter(p.get("topic", "") for p in split)
            say(f"\n{'NEW DAY ' if is_new else 'kept    '}{bk} {d}: {len(split)} paragraph(s) under "
                + "; ".join(f"'{short(t, 40)}' {k}" for t, k in heads.most_common(2)))
            say(f"        own bill named {mine} time(s); other bills: "
                + (", ".join(f"Bill {b} x{k}" for b, k in c.most_common(3)) if c else "none"))
            say(f"        first: {short(split[0].get('text'))}")
            if len(split) > 1:
                say(f"        last:  {short(split[-1].get('text'))}")
    say(f"\nOntario bill-days with such paragraphs: {n}")


if __name__ == "__main__":
    dirs = sorted(glob.glob(os.path.join(ROOT, "data", "_before_canada_fix_*")))
    before = sys.argv[1] if len(sys.argv) > 1 else (dirs[-1] if dirs else "")
    if not before or not os.path.isdir(before):
        sys.exit("No data/_before_canada_fix_* folder found; pass the folder as an argument.")
    say(f"comparing with {before}")
    quebec(before)
    ontario(before)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    print(f"\nSaved {REPORT}")
