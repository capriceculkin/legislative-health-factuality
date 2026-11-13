#!/usr/bin/env python3
"""
fill_missing_stages.py

Why: the rebuild downloads a health bill's own debate headings only from its first to its
last FIRMLY moved stage plus 45 days. A stage moved "on behalf of" the minister counts as
a weak line, so it does not stretch that window. Bill 50 (35-3) shows the result: its
third reading on 1993-12-08 (44 paragraphs under the bill's own heading, "Mr O'Connor, on
behalf of Mrs Grier, moved third reading ... Carried.") fell outside the window, and the
data kept only 4 paragraphs of it.

What it does, for every health bill:
  1. The window now ends 45 days after the LAST day the bill is moved or named in a
     reading, weak lines included (anchors.json, already on disk). Only the added part of
     the window is downloaded, for the bill's own headings (the headings the per-session
     heading table assigns to this bill, with their "(CONTINUED)" forms). New paragraphs
     are added to data/canada/ontario/v3/raw/<bill>.json; nothing already there changes.
  2. A raw file that cannot be read (for example two copies written into one file) is
     moved aside and downloaded again in full with the wider window.
Which paragraphs count as the bill's text is unchanged: the assign step still takes only
paragraphs under the bill's own heading, or after a line that moves it.

Run from the project folder:
  python3 scripts/step1_debate_text/fill_missing_stages.py            plan only (no downloads)
  python3 scripts/step1_debate_text/fill_missing_stages.py --apply    download and add (run_ontario_fill.sh does this)
Every changed raw file is copied first to data/canada/ontario/v3/raw/_before_fill_<time>/.
Writes outputs/audit/fill_missing_stages.csv
"""
import csv
import datetime as dt
import json
import os
import shutil
import sys
import time
from collections import OrderedDict, defaultdict

os.environ.setdefault("OLA_SLEEP", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ontario_rebuild as ob  # noqa: E402

APPLY = "--apply" in sys.argv
END = ob.END
probe = ob.load_probe()
if not probe["decisions"].get("use_topic_filter"):
    sys.exit("The probe found the API topic filter unreliable; this fill needs it. Nothing done.")
master = ob.load_json(ob.MASTER, {}) or sys.exit("bills_master.json missing")
anchors = ob.load_json(ob.ANCHORS, []) or sys.exit("anchors.json missing")
topic_hash, _ = ob.build_topic_hash(anchors)

by_key = defaultdict(list)
proc_days = defaultdict(set)
for a in anchors:
    if not a.get("session") or not a.get("date"):
        continue
    k = f"{a['session']}-Bill{a['bill_number']}"
    by_key[k].append(a)
    if a["strong"] and ob.is_procedural_topic(a["topic_norm"]):
        proc_days[k].add(a["date"])


def plus(d, n):
    return (dt.date.fromisoformat(d) + dt.timedelta(days=n)).isoformat()


def read_raw(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), ""
    except FileNotFoundError:
        return None, "missing"
    except ValueError as e:
        return None, f"unreadable ({str(e)[:70]})"


def own_headings(key, b):
    sess, num = b["session"], str(b["bill_number"])
    v = set(b.get("topics") or [])
    for a in by_key.get(key, []):
        t = a.get("topic") or ""
        nt = ob.norm_topic(t)
        if t and not ob.is_procedural_topic(nt) and str(topic_hash.get((sess, nt))) == num:
            v.add(t)
    for t in list(v):
        if t.isupper() and "(CONTINUED)" not in t:
            v.add(t + " (CONTINUED)")
    return sorted(v)


plan = []
missing_raw = 0
for key, b in sorted(master.items()):
    if not b.get("health") or not b.get("anchor_dates"):
        continue
    strong = sorted(b["anchor_dates"])
    every = sorted({a["date"] for a in by_key.get(key, [])} | set(strong))
    old_hi = min(END, plus(strong[-1], 45))
    new_hi = min(END, plus(every[-1], 45))
    path = os.path.join(ob.RAW_DIR, f"{key}.json")
    raw, err = read_raw(path)
    if err == "missing":
        missing_raw += 1
        continue
    heads = own_headings(key, b)
    if err:
        plan.append({"key": key, "action": "re-download (" + err + ")", "lo": strong[0], "hi": new_hi,
                     "heads": heads, "days": sorted(proc_days.get(key, ())), "path": path, "raw": None})
    elif new_hi > old_hi and heads:
        later = [d for d in every if d > old_hi]
        plan.append({"key": key, "action": "extend window", "lo": plus(old_hi, 1), "hi": new_hi, "heads": heads,
                     "days": [], "path": path, "raw": raw, "later": later})

n_q = sum(len(p["heads"]) + len(p["days"]) for p in plan)
print(f"Health bills: {sum(1 for b in master.values() if b.get('health'))}; with no raw file (not fetched by the "
      f"rebuild either): {missing_raw}")
print(f"Raw files that cannot be read: {sum(1 for p in plan if p['action'].startswith('re-download'))}")
for p in plan:
    if p["action"].startswith("re-download"):
        print(f"  {p['key']}: {p['action']}")
print(f"Bills whose window grows (a stage moved or named after the old window): "
      f"{sum(1 for p in plan if p['action'] == 'extend window')}")
for p in plan[:12]:
    if p["action"] == "extend window":
        print(f"  {p['key']:<14} adds {p['lo']} to {p['hi']}  (later reading days: {', '.join(p['later'][:4])})")
print(f"API requests needed: about {n_q} (about {n_q * ob.SLEEP / 60:.0f} min at OLA_SLEEP={ob.SLEEP:g}s, "
      f"plus any splits of large windows)")

if not APPLY:
    print("\nPlan only. Run with --apply to download (run_ontario_fill.sh does this).")
    sys.exit(0)

backup = os.path.join(ob.RAW_DIR, "_before_fill_" + time.strftime("%Y%m%d-%H%M%S"))
os.makedirs(backup, exist_ok=True)
report, capped = [], []
for i, p in enumerate(plan, 1):
    shutil.copy2(p["path"], os.path.join(backup, os.path.basename(p["path"])))
    rows = list(p["raw"] or [])
    before = len(rows)
    for t in p["heads"]:
        rows += ob.query_complete("*", "topic eq '" + t.replace("'", "''") + "'", p["lo"], p["hi"], capped)
    for d in p["days"]:
        rows += ob.fetch_day(d, capped)
    uniq = OrderedDict((ob.row_id(r), r) for r in rows)
    ob.save_json(list(uniq.values()), p["path"])
    old_ids = {ob.row_id(r) for r in (p["raw"] or [])}
    new_dates = sorted({ob.row_date(r) for r in uniq.values() if ob.row_id(r) not in old_ids})
    report.append({"bill_key": p["key"], "action": p["action"], "window_added": f"{p['lo']} to {p['hi']}",
                   "headings": " | ".join(p["heads"]), "paragraphs_before": before,
                   "paragraphs_after": len(uniq), "dates_with_new_paragraphs": " ".join(new_dates)})
    print(f"  [{i}/{len(plan)}] {p['key']}: {before} -> {len(uniq)} paragraphs; new on {', '.join(new_dates[:5]) or 'no day'}",
          flush=True)

os.makedirs(ob.rp("outputs", "audit"), exist_ok=True)
out = ob.rp("outputs", "audit", "fill_missing_stages.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["bill_key", "action", "window_added", "headings", "paragraphs_before",
                                      "paragraphs_after", "dates_with_new_paragraphs"])
    w.writeheader()
    w.writerows(report)
grew = sum(1 for r in report if r["paragraphs_after"] > r["paragraphs_before"])
print(f"\nBills with new paragraphs: {grew} of {len(report)}; paragraphs added: "
      f"{sum(r['paragraphs_after'] - r['paragraphs_before'] for r in report):,}")
print(f"Single days that hit the API row cap: {len(capped)}")
print(f"Copies of the raw files before this step: {backup}")
print(f"Wrote {out}. Next: python3 scripts/step1_debate_text/ontario_rebuild.py assign (run_ontario_fill.sh does this).")
