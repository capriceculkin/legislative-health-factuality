#!/usr/bin/env python3
"""
canada_before_after.py   (reads only)

Shows exactly what the Canada fix changed, bill-day by bill-day, by comparing the copies
run_canada_fix.sh saved before the fix with the rebuilt files:
  Ontario  data/canada/ontario/v3/hansard_segments_v3.json
  Quebec   data/canada/quebec_assembly/v3/segments_index.json and the section text files

Every change should be one of:
  removed   paragraphs filed under a non-bill heading with no line naming the bill
            (HOSPITAL RESTRUCTURING in Bill 149), or a Quebec section cut under the wrong bill
  added     official debate days that had no text (Ontario raw_official, Quebec parser fix)
Anything else (a bill heading's paragraphs disappearing, a section changing for no stated
reason) is listed separately under UNEXPECTED so it can be looked at.

Run from the project folder:  python3 scripts/v3/canada_before_after.py <folder the fix saved>
Writes outputs/audit/canada_before_after.txt
"""
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REPORT = os.path.join(ROOT, "outputs", "audit", "canada_before_after.txt")
BILL_WORDS = re.compile(r"\b(ACTS?|LOIS?|CODE|BILL|STATUTES?)\b")
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


def pid(p):
    return p.get("para_url") or hashlib.sha1(str(p.get("text", ""))[:400].encode()).hexdigest()


def short(s, n=60):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 3] + "..."


def ontario(before_dir):
    old = load(os.path.join(before_dir, "hansard_segments_v3.json"), {}) or {}
    new = load(os.path.join(ROOT, "data/canada/ontario/v3/hansard_segments_v3.json"), {}) or {}
    say("=" * 78 + "\nONTARIO before -> after\n" + "=" * 78)
    n_old = sum(len(v) for d in old.values() for v in d.values())
    n_new = sum(len(v) for d in new.values() for v in d.values())
    bd_old = {(b, d) for b, days in old.items() for d in days}
    bd_new = {(b, d) for b, days in new.items() for d in days}
    say(f"paragraphs {n_old:,} -> {n_new:,}; bill-days {len(bd_old):,} -> {len(bd_new):,}; "
        f"bills {len(old)} -> {len(new)}")
    removed_heads, added_methods = Counter(), Counter()
    odir = os.path.join(ROOT, "data/canada/ontario/v3/raw_official")
    official = {(b, f[:-5]) for b in (os.listdir(odir) if os.path.isdir(odir) else [])
                for f in os.listdir(os.path.join(odir, b)) if f.endswith(".json")}
    removed_days, added_days, changed = [], [], []
    unexpected = []
    for b, d in sorted(bd_old | bd_new):
        o = {pid(p): p for p in old.get(b, {}).get(d, [])}
        n = {pid(p): p for p in new.get(b, {}).get(d, [])}
        gone = [o[k] for k in o if k not in n]
        came = [n[k] for k in n if k not in o]
        for p in gone:
            removed_heads[p.get("topic", "")] += 1
            if BILL_WORDS.search(str(p.get("topic", "")).upper()):
                unexpected.append((b, d, "removed", p))
        for p in came:
            m = str(p.get("assignment_method", ""))
            added_methods[m] += 1
            # on an official OLA day that was just downloaded, paragraphs under the bill's own
            # heading arrive through the topic hash too; that is expected
            if not (m.startswith("official_day") or "official_day" in m or m.startswith("anchor_split")
                    or (b, d) in official):
                unexpected.append((b, d, "added", p))
        if o and not n:
            removed_days.append((b, d, len(gone), Counter(p.get("topic", "") for p in gone)))
        elif n and not o:
            added_days.append((b, d, len(came), Counter(p.get("assignment_method", "") for p in came)))
        elif gone or came:
            changed.append((b, d, len(gone), len(came)))
    say(f"\nparagraphs removed, by heading ({sum(removed_heads.values()):,}):")
    for t, k in removed_heads.most_common(12):
        say(f"   {k:>6}  {short(t, 70)}")
    say(f"paragraphs added, by how they were found ({sum(added_methods.values()):,}):")
    for t, k in added_methods.most_common():
        say(f"   {k:>6}  {t}")
    say(f"\nbill-days REMOVED entirely: {len(removed_days)}")
    for b, d, k, c in removed_days[:60]:
        say(f"   {b:<14} {d}  {k:>4} paras  " + "; ".join(f"{short(t, 30)} {x}" for t, x in c.most_common(2)))
    say(f"bill-days ADDED: {len(added_days)}")
    for b, d, k, c in added_days[:60]:
        say(f"   {b:<14} {d}  {k:>4} paras  {dict(c)}")
    say(f"bill-days CHANGED (paragraphs removed / added): {len(changed)}")
    for b, d, g, c in changed[:40]:
        say(f"   {b:<14} {d}  -{g} +{c}")
    say(f"\nUNEXPECTED Ontario changes (should be 0): {len(unexpected)}")
    for b, d, what, p in unexpected[:20]:
        say(f"   {what} {b} {d} '{short(p.get('topic'), 40)}' {p.get('assignment_method', '')}: {short(p.get('text'), 70)}")


def paras_of(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [x.strip() for x in f.read().split("\n\n") if x.strip()]
    except OSError:
        return None


def quebec(before_dir):
    qc = os.path.join(ROOT, "data/canada/quebec_assembly")
    old = load(os.path.join(before_dir, "segments_index.json"), []) or []
    new = load(os.path.join(qc, "v3/segments_index.json"), []) or []
    old_dir = os.path.join(before_dir, "quebec_bill_segments_v3")
    say("\n" + "=" * 78 + "\nQUEBEC before -> after\n" + "=" * 78)
    key = lambda e: (e.get("bill_key"), e.get("date"), str(e.get("page_id")))
    o = {key(e): e for e in old}
    n = {key(e): e for e in new}
    say(f"sections {len(o):,} -> {len(n):,}")
    removed = sorted(set(o) - set(n))
    added = sorted(set(n) - set(o))
    changed, same = [], 0
    for k in sorted(set(o) & set(n)):
        op = paras_of(os.path.join(old_dir, os.path.basename(o[k]["file"])))
        np_ = paras_of(os.path.join(qc, n[k]["file"]))
        if op is None or np_ is None:
            changed.append((k, "text file missing", 0, 0, {}))
            continue
        if op == np_:
            same += 1
            continue
        so, sn = set(op), set(np_)
        changed.append((k, "", len(so - sn), len(sn - so), n[k].get("methods", {})))
    say(f"unchanged sections: {same:,}")
    say(f"sections REMOVED: {len(removed)}")
    for k in removed:
        e = o[k]
        say(f"   {k[0]:<14} {k[1]}  {e.get('n_paragraphs')} paras  methods {e.get('methods')}")
    say(f"sections ADDED: {len(added)}")
    for k in added:
        e = n[k]
        say(f"   {k[0]:<14} {k[1]}  {e.get('n_paragraphs')} paras  methods {e.get('methods')}")
    say(f"sections CHANGED (paragraphs removed / added): {len(changed)}")
    for k, note, g, c, m in changed[:60]:
        say(f"   {k[0]:<14} {k[1]}  -{g} +{c}  {note or ''} methods now {m}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit("usage: canada_before_after.py <folder saved before the fix>")
    ontario(sys.argv[1])
    quebec(sys.argv[1])
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    print(f"\nSaved {REPORT}")
