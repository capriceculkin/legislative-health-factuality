#!/usr/bin/env python3
"""
ontario_missing_check.py   (reads only)

For each Ontario health bill that the old health list had and the rebuild gives no debate text, says why,
from the rebuild's own files. Run after ontario_rebuild.py assign.
  old list:  data/canada/ontario/v3/old_health_bills_not_rediscovered.csv
  also:      every health bill in bills_master.json with no bill-day
Reasons, per bill (from its downloaded paragraphs in data/canada/ontario/v3/raw/<bill>.json):
  has text now            bill-days exist after this run
  never downloaded        no raw file
  other session only      every downloaded paragraph is dated in another session
  heading of another bill paragraphs are under a heading the topic hash gives to another bill
  shared heading          under a bill heading two bills of the session use, with no line moving this bill
  heading not in hash     under a bill heading no moving line of any bill was filed under
  no moving line          under procedural or statement headings, with no line moving this bill before them
Writes outputs/audit/ontario_missing_check.txt
"""
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import ontario_rebuild as O    # noqa: E402

ON = ROOT / "data" / "canada" / "ontario" / "v3"
REPORT = ROOT / "outputs" / "audit" / "ontario_missing_check.txt"
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


master = load(ON / "bills_master.json", {}) or {}
seg = load(ON / "hansard_segments_v3.json", {}) or {}
anchors = load(ON / "anchors.json", []) or []
topic_hash, conflicts = O.build_topic_hash(anchors)
shared = {(c["session"], c["topic"]) for c in conflicts}
span = {}
strong = defaultdict(list)
for a in anchors:
    s, d = a.get("session"), a.get("date")
    if s and d:
        lo, hi = span.get(s, (d, d))
        span[s] = (min(lo, d), max(hi, d))
    if a.get("strong") and s:
        strong[f"{s}-Bill{a['bill_number']}"].append((d, a.get("topic_norm", "")))


def session_of(d):
    hits = [s for s, (lo, hi) in span.items() if lo <= d <= hi]
    return hits[0] if len(hits) == 1 else ("/".join(sorted(hits)) or "?")


old_rows = []
p = ON / "old_health_bills_not_rediscovered.csv"
if p.exists():
    with open(p, newline="", encoding="utf-8") as f:
        old_rows = list(csv.DictReader(f))
keys = {}
for r in old_rows:
    k = r.get("old_key") or ""
    if k in master and master[k].get("health"):
        keys[k] = r.get("old_dates", "")
no_days = [k for k, b in master.items() if b.get("health") and not seg.get(k)]
say(f"old health-list bills not found again: {len(old_rows)}; of those, in the rebuild's list as health: {len(keys)}")
say(f"health bills in bills_master.json with no bill-day now: {len(no_days)}")

why, lines = Counter(), []
for k in sorted(set(keys) | set(no_days)):
    b = master[k]
    sess, num = b["session"], b["bill_number"]
    days = sorted(seg.get(k, {}))
    if days:
        reason, detail = "has text now", f"{len(days)} bill-days: {', '.join(days[:6])}"
    else:
        rows = load(ON / "raw" / f"{k}.json")
        if rows is None:
            reason, detail = "never downloaded", "no raw file"
        else:
            own = [r for r in rows if O.row_session(r) == sess]
            if not own:
                ds = sorted({O.row_date(r) for r in rows})
                reason = "other session only"
                detail = f"{len(rows)} paragraphs dated {ds[:3]}..{ds[-1:]} (session {session_of(ds[0]) if ds else '?'})"
            else:
                kinds = Counter()
                for r in own:
                    t = r.get("topic") or ""
                    nt = O.norm_topic(t)
                    if O.is_procedural_topic(nt) or not O.bill_like(t):
                        kinds["no moving line"] += 1
                    elif (sess, nt) in shared:
                        kinds["shared heading"] += 1
                    elif topic_hash.get((sess, nt)) is not None and str(topic_hash[(sess, nt)]) != str(num):
                        kinds[f"heading of another bill"] += 1
                    elif topic_hash.get((sess, nt)) is None:
                        kinds["heading not in hash"] += 1
                    else:
                        kinds["own heading (should be assigned)"] += 1
                reason = kinds.most_common(1)[0][0]
                tops = Counter(r.get("topic") or "" for r in own).most_common(3)
                detail = (f"{len(own)} paragraphs in its session: {dict(kinds)}; headings "
                          + "; ".join(f"{t[:40]} x{n}" for t, n in tops))
    why[reason] += 1
    st = sorted(strong.get(k, []))
    lines.append((reason, k, b.get("long_title", "")[:70], detail, st[:4], keys.get(k, "")))
say("")
say("why, by bill:")
for r, n in why.most_common():
    say(f"   {n:>4}  {r}")
for reason, k, title, detail, st, od in sorted(lines):
    say(f"   [{reason}] {k:<14} {title}")
    say(f"        {detail}")
    say(f"        moving lines in its session: {[d for d, _ in st]}" + (f" | old dates: {od[:80]}" if od else ""))
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
print(f"\nSaved {REPORT}")
