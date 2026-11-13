#!/usr/bin/env python3
"""
check_row_ids.py   (reads only; 2 API requests; nothing is saved into data/)

Question: does the Ontario rebuild throw paragraphs away because different paragraphs
share one ID?

The rebuild removes duplicate paragraphs with an ID per paragraph (row_id: the
paragraph's paraUrl when it has one). If several different paragraphs share one paraUrl,
only the last of them is kept. Two things point that way:
  - 1993-12-08: 44 paragraphs under Bill 50's own heading in the Hansard (check_days.py,
    which keeps every row), but 4 in our data, none of them the third-reading motion;
  - 1993-07-27: our 3 paragraphs are the closing "business of the House" lines.

Two independent tests:
  A. Every full day already saved in raw_days (saved WITHOUT removing duplicates):
     rows vs distinct IDs, by year, and which field would identify a paragraph uniquely.
  B. 1993-12-08 and 1993-07-27 downloaded now: paragraphs under Bill 50's heading,
     distinct IDs among them, and what our data holds.
  C. Every bill-day in our data whose full day is in raw_days: paragraphs under the
     bill's own heading in the full day vs in our data.

Run from the project folder:
  python3 scripts/step1_debate_text/check_row_ids.py              (A, B, C)
  python3 scripts/step1_debate_text/check_row_ids.py --sample 30  (also D: 30 random bill-days against the full day)
Writes outputs/audit/row_id_check.txt and outputs/audit/row_id_shortfall.csv
"""
import csv
import glob
import os
import sys
from collections import Counter, defaultdict

os.environ.setdefault("OLA_SLEEP", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ontario_rebuild as ob  # noqa: E402

out = []


def say(s=""):
    print(s, flush=True)
    out.append(s)


def keys(r):
    para = ob.row_para_url(r)
    text = ob.row_text(r)[:300]
    return {"row_id (used now)": ob.row_id(r),
            "id field": r.get("id"),
            "paraUrl": para or None,
            "paraUrl + paragraph order": (para, ob.row_order(r)) if para else None,
            "paraUrl + text": (para, text) if para else None,
            "paraUrl + order + text": (para, ob.row_order(r), text) if para else None}


# ------------------------------------------------------------------ A
files = sorted(glob.glob(os.path.join(ob.DAY_DIR, "*.json")))
say(f"A. Full days saved in raw_days: {len(files)}")
by_year = defaultdict(lambda: [0, 0, 0])          # days, rows, rows lost
cand = defaultdict(lambda: [0, 0, 0])             # rows with key, distinct, rows total
example = None
fields = Counter()
for fp in files:
    rows = ob.load_json(fp, []) or []
    if not rows:
        continue
    for r in rows[:3]:
        fields.update(r.keys())
    day = os.path.basename(fp)[:-5]
    ids = [ob.row_id(r) for r in rows]
    lost = len(ids) - len(set(ids))
    y = day[:4]
    by_year[y][0] += 1
    by_year[y][1] += len(rows)
    by_year[y][2] += lost
    per = defaultdict(set)
    for r in rows:
        for name, k in keys(r).items():
            if k is not None:
                per[name].add(k)
                cand[name][0] += 1
        cand["_rows"][2] += 1
    for name, s in per.items():
        cand[name][1] += len(s)
    if lost and example is None:
        groups = defaultdict(list)
        for r in rows:
            groups[ob.row_id(r)].append(r)
        rid, grp = max(groups.items(), key=lambda kv: len(kv[1]))
        example = (day, rid, grp)
say(f"   fields in the API rows: {sorted(fields)}")
say("   year  days   paragraphs   lost to a shared ID")
for y in sorted(by_year):
    d, n, lost = by_year[y]
    say(f"   {y}  {d:>4}  {n:>11,}   {lost:>8,}  ({lost / n:.1%})" if n else f"   {y}  {d:>4}")
tot_n = sum(v[1] for v in by_year.values())
tot_l = sum(v[2] for v in by_year.values())
say(f"   all   {sum(v[0] for v in by_year.values()):>4}  {tot_n:>11,}   {tot_l:>8,}  ({(tot_l / tot_n if tot_n else 0):.1%})")
say("   Which ID would be unique per paragraph (distinct IDs / paragraphs that have that field):")
for name in ["row_id (used now)", "id field", "paraUrl", "paraUrl + paragraph order", "paraUrl + text",
             "paraUrl + order + text"]:
    have, distinct = cand[name][0], cand[name][1]
    if have:
        say(f"     {name:<28} {distinct:>9,} / {have:>9,}  ({distinct / have:.2%})  present on {have / max(cand['_rows'][2], 1):.0%} of rows")
    else:
        say(f"     {name:<28} not present")
if example:
    day, rid, grp = example
    say(f"   Example, {day}: {len(grp)} different paragraphs share the ID {str(rid)[:110]}")
    for r in grp[:4]:
        say(f"     [{r.get('topic')}] {ob.row_text(r)[:110]}")

# ------------------------------------------------------------------ B
say()
say("B. Bill 50 (35-3), downloaded now, all rows kept")
master = ob.load_json(ob.MASTER, {}) or {}
segs = ob.load_json(ob.SEGMENTS, {}) or {}
heads = {ob.norm_topic(t) for t in (master.get("35-3-Bill50", {}).get("topics") or [])}
try:
    ob.load_probe()
except SystemExit:
    pass
for d in ("1993-12-08", "1993-07-27"):
    try:
        rows = ob.query_complete("*", None, d, d, [])
    except Exception as e:  # noqa: BLE001
        say(f"   {d}: could not download ({e.__class__.__name__})")
        continue
    under = [r for r in rows if ob.norm_topic(r.get("topic")) in heads]
    ids = {ob.row_id(r) for r in under}
    ours = len((segs.get("35-3-Bill50") or {}).get(d, []))
    motion = [r for r in under if "moved third reading of Bill 50" in ob.row_text(r)]
    say(f"   {d}: {len(rows)} paragraphs that day; {len(under)} under Bill 50's heading; distinct IDs among them: "
        f"{len(ids)}; in our data: {ours}")
    if motion:
        say(f"     the third-reading motion is in the download: {ob.row_text(motion[0])[:100]}")
    for rid in list(ids)[:3]:
        say(f"     ID {str(rid)[:110]} is shared by {sum(1 for r in under if ob.row_id(r) == rid)} paragraphs")

# ------------------------------------------------------------------ C
say()
say("C. Bill-days in our data whose full day is saved: own-heading paragraphs in the full day vs ours")
have_day = {os.path.basename(f)[:-5] for f in files}
short = []
for key, days in segs.items():
    for d, paras in days.items():
        if d not in have_day:
            continue
        own = {ob.norm_topic(p.get("topic")) for p in paras if str(p.get("assignment_method", "")).startswith("topic_hash")}
        if not own:
            continue
        full = ob.load_json(os.path.join(ob.DAY_DIR, f"{d}.json"), []) or []
        n_full = sum(1 for r in full if ob.norm_topic(r.get("topic")) in own and ob.row_session(r) == key.rsplit("-Bill", 1)[0])
        n_ours = sum(1 for p in paras if ob.norm_topic(p.get("topic")) in own)
        short.append({"bill_key": key, "date": d, "full_day_paragraphs": n_full, "our_paragraphs": n_ours,
                      "missing": max(0, n_full - n_ours)})
miss = [s for s in short if s["missing"]]
say(f"   bill-days compared: {len(short)}; with paragraphs missing: {len(miss)}; paragraphs missing: "
    f"{sum(s['missing'] for s in short):,} of {sum(s['full_day_paragraphs'] for s in short):,}")
for s in sorted(miss, key=lambda s: -s["missing"])[:15]:
    say(f"     {s['bill_key']:<14} {s['date']}  full day {s['full_day_paragraphs']:>4}  ours {s['our_paragraphs']:>4}")

# ------------------------------------------------------------------ D
n_sample = 0
if "--sample" in sys.argv:
    try:
        n_sample = int(sys.argv[sys.argv.index("--sample") + 1])
    except (IndexError, ValueError):
        n_sample = 30
if n_sample:
    import random
    say()
    say(f"D. {n_sample} random bill-days (seed 7), full day downloaded now, all rows kept: "
        "paragraphs under the bill's own heading vs ours")
    pool = sorted((k, d) for k, days in segs.items() for d, paras in days.items()
                  if any(str(p.get("assignment_method", "")).startswith("topic_hash") for p in paras))
    random.Random(7).shuffle(pool)
    tot_full = tot_ours = 0
    for key, d in pool[:n_sample]:
        paras = segs[key][d]
        own = {ob.norm_topic(p.get("topic")) for p in paras if str(p.get("assignment_method", "")).startswith("topic_hash")}
        try:
            rows = ob.query_complete("*", None, d, d, [])
        except Exception as e:  # noqa: BLE001
            say(f"     {key} {d}: could not download ({e.__class__.__name__})")
            continue
        n_full = sum(1 for r in rows if ob.norm_topic(r.get("topic")) in own and ob.row_session(r) == key.rsplit("-Bill", 1)[0])
        n_ours = sum(1 for p in paras if ob.norm_topic(p.get("topic")) in own)
        tot_full += n_full
        tot_ours += n_ours
        flag = "" if n_ours >= n_full else f"   <-- {n_full - n_ours} missing"
        say(f"     {key:<14} {d}  full day {n_full:>4}  ours {n_ours:>4}{flag}")
    say(f"   total under the bills' own headings: full day {tot_full:,}, ours {tot_ours:,}")

os.makedirs(ob.rp("outputs", "audit"), exist_ok=True)
with open(ob.rp("outputs", "audit", "row_id_shortfall.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["bill_key", "date", "full_day_paragraphs", "our_paragraphs", "missing"])
    w.writeheader()
    w.writerows(sorted(short, key=lambda s: (s["bill_key"], s["date"])))
with open(ob.rp("outputs", "audit", "row_id_check.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
say("\nwrote outputs/audit/row_id_check.txt and outputs/audit/row_id_shortfall.csv")
