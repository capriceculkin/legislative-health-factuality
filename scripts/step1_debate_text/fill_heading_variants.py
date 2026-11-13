#!/usr/bin/env python3
"""
fill_heading_variants.py

Why: after the paragraph-ID fix, one known bill-day is still short: Bill 174 (34-1) on
1988-12-15 has 135 paragraphs under its own heading in the full day, 15 in our data. The
download asks the API for each heading by its exact spelling ("topic eq '...'"), but the
rebuild matches headings after normalising them (upper case, spaces, "(CONTINUED)"). A
heading printed with a different spelling on some days (case, spacing, "(Continued)") is
assigned correctly once downloaded, but it is never downloaded.

What it does:
  1. Local check, no downloads: for every health bill, heading spellings that appear in
     its anchors or its raw file but were never requested from the API.
  2. Downloads the full Hansard of every day on which a health bill has text under its own
     heading or is moved or named in a reading (each day once), and keeps the paragraphs
     under any spelling of that bill's own headings (same session).
  3. Compares, per bill-day, the full day with what the raw file already had, and adds the
     missing paragraphs to data/canada/ontario/v3/raw/<bill>.json.
Which paragraphs count as the bill's text does not change: the assign step still takes
only paragraphs under the bill's own heading, or after a line that moves it.

Resumable: each day's matching paragraphs are kept in data/canada/ontario/v3/fullday_matches/,
so a second run skips days already downloaded.

Run from the project folder:
  python3 scripts/step1_debate_text/fill_heading_variants.py            plan and local check only
  python3 scripts/step1_debate_text/fill_heading_variants.py --apply    download and add (run_ontario_variants_fix.sh)
Changed raw files are copied first to data/canada/ontario/v3/raw/_before_variants_<time>/.
Writes outputs/audit/heading_variants_fill.csv (one row per bill-day)
"""
import csv
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict

os.environ.setdefault("OLA_SLEEP", "4")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ontario_rebuild as ob  # noqa: E402

APPLY = "--apply" in sys.argv
with open(os.path.join(HERE, "ontario_rebuild.py"), encoding="utf-8") as f:
    if "PATCHED_ROWID_2026_10_01" not in f.read():
        sys.exit("Run scripts/step1_debate_text/patch_ontario_rowid.py first (paragraph IDs). Nothing done.")
ob.load_probe()
master = ob.load_json(ob.MASTER, {}) or sys.exit("bills_master.json missing")
anchors = ob.load_json(ob.ANCHORS, []) or sys.exit("anchors.json missing")
topic_hash, _ = ob.build_topic_hash(anchors)
CACHE = os.path.join(ob.OUT, "fullday_matches")


def read_raw(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_atomic(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


anchor_days, anchor_topics = defaultdict(set), defaultdict(set)
for a in anchors:
    if a.get("session") and a.get("date"):
        k = f"{a['session']}-Bill{a['bill_number']}"
        anchor_days[k].add(a["date"])
        if a.get("topic"):
            anchor_topics[k].add(a["topic"])

plan, need_day = {}, defaultdict(set)
spell_bills = []
for key, b in sorted(master.items()):
    if not b.get("health"):
        continue
    path = os.path.join(ob.RAW_DIR, f"{key}.json")
    raw = read_raw(path)
    if raw is None:
        continue
    sess, num = b["session"], str(b["bill_number"])
    own = {nt for (s, nt), o in topic_hash.items() if s == sess and str(o) == num}
    own |= {ob.norm_topic(t) for t in (b.get("topics") or []) if not ob.is_procedural_topic(ob.norm_topic(t))}
    own.discard("")
    if not own:
        continue
    queried = set()
    for t in b.get("topics") or []:
        base = re.sub(r"\s*\(CONTINUED\)\s*$", "", t)
        queried |= {base, base + " (CONTINUED)"}
    seen = {t for t in anchor_topics[key] if ob.norm_topic(t) in own}
    seen |= {r.get("topic") for r in raw if r.get("topic") and ob.norm_topic(r.get("topic")) in own}
    never = sorted(t for t in seen if t not in queried)
    if never:
        spell_bills.append((key, never))
    text_days = {ob.row_date(r) for r in raw if ob.norm_topic(r.get("topic")) in own and ob.row_session(r) == sess}
    days = {d for d in text_days | anchor_days.get(key, set()) if d and ob.START <= d <= ob.END}
    plan[key] = {"sess": sess, "own": own, "days": days, "raw": raw, "path": path}
    for d in days:
        need_day[d].add(key)

print("1. Local check (no downloads): heading spellings seen but never requested from the API")
print(f"   health bills with such a spelling: {len(spell_bills)} of {len(plan)}")
for key, never in spell_bills[:15]:
    print(f"     {key:<14} {' | '.join(repr(t) for t in never[:3])}")
days = sorted(need_day)
per = ob.SLEEP + 1.5
print(f"\n2. Days to download in full: {len(days)} (about {len(days) * per / 3600:.1f} hours at OLA_SLEEP={ob.SLEEP:g}s; "
      f"days already done: {sum(1 for d in days if os.path.exists(os.path.join(CACHE, d + '.json')))})")
if not APPLY:
    print("\nPlan only. Run with --apply to download (run_ontario_variants_fix.sh does this).")
    sys.exit(0)

os.makedirs(CACHE, exist_ok=True)
capped = []
t0 = time.time()
for i, d in enumerate(days, 1):
    cp = os.path.join(CACHE, f"{d}.json")
    if os.path.exists(cp):
        continue
    rows = ob.query_complete("*", None, d, d, capped)
    wanted = {(plan[k]["sess"], nt) for k in need_day[d] for nt in plan[k]["own"]}
    keep = [r for r in rows if ob.row_date(r) == d and (ob.row_session(r), ob.norm_topic(r.get("topic"))) in wanted]
    save_atomic({"n_day": len(rows), "rows": keep}, cp)
    if i % 25 == 0 or i == len(days):
        el = time.time() - t0
        print(f"   [{i}/{len(days)}] {d}: {len(rows)} paragraphs that day, {len(keep)} under a health bill's own heading "
              f"({el / 60:.0f} min so far)", flush=True)

print("\n3. Full day vs raw file, per bill-day, and paragraphs added")
stamp = time.strftime("%Y%m%d-%H%M%S")
backup = os.path.join(ob.RAW_DIR, "_before_variants_" + stamp)
report, spellings = [], Counter()
for key, p in sorted(plan.items()):
    have = {ob.row_id(r) for r in p["raw"]}
    raw_by_day = Counter(ob.row_date(r) for r in p["raw"]
                         if ob.norm_topic(r.get("topic")) in p["own"] and ob.row_session(r) == p["sess"])
    adds = []
    for d in sorted(p["days"]):
        c = read_raw(os.path.join(CACHE, f"{d}.json")) or {}
        mine = [r for r in c.get("rows", []) if ob.row_session(r) == p["sess"] and ob.norm_topic(r.get("topic")) in p["own"]]
        new = []
        for r in mine:
            rid = ob.row_id(r)
            if rid not in have:
                have.add(rid)
                new.append(r)
        adds += new
        spellings.update(r.get("topic") or "" for r in new)
        if mine or raw_by_day.get(d):
            report.append({"bill_key": key, "date": d, "full_day_own_heading": len(mine),
                           "raw_before": raw_by_day.get(d, 0), "added": len(new),
                           "spellings_added": " | ".join(sorted({r.get("topic") or "" for r in new}))})
    if adds:
        os.makedirs(backup, exist_ok=True)
        shutil.copy2(p["path"], os.path.join(backup, os.path.basename(p["path"])))
        save_atomic(p["raw"] + adds, p["path"])

os.makedirs(ob.rp("outputs", "audit"), exist_ok=True)
out = ob.rp("outputs", "audit", "heading_variants_fill.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["bill_key", "date", "full_day_own_heading", "raw_before", "added", "spellings_added"])
    w.writeheader()
    w.writerows(report)
short = [r for r in report if r["added"]]
by_parl = Counter(r["bill_key"].split("-")[0] for r in short)
added_by_parl = Counter()
for r in short:
    added_by_parl[r["bill_key"].split("-")[0]] += r["added"]
print(f"   bill-days compared: {len(report)}; with paragraphs added: {len(short)}; paragraphs added: "
      f"{sum(r['added'] for r in report):,} (full days held {sum(r['full_day_own_heading'] for r in report):,} "
      f"paragraphs under the bills' own headings)")
print(f"   bills changed: {len({r['bill_key'] for r in short})}")
for p_ in sorted(by_parl, key=int):
    print(f"     Parliament {p_}: {by_parl[p_]} bill-days, {added_by_parl[p_]:,} paragraphs added")
for r in sorted(short, key=lambda r: -r["added"])[:15]:
    print(f"     {r['bill_key']:<14} {r['date']}  full day {r['full_day_own_heading']:>4}  had {r['raw_before']:>4}  "
          f"+{r['added']}")
print("   heading spellings the added paragraphs were filed under (most common):")
for t, n in spellings.most_common(10):
    print(f"     {n:>5}  {t!r}")
print(f"   days that hit the API row cap (partial): {len(capped)} {capped[:5]}")
if short:
    print(f"   copies of changed raw files: {backup}")
print(f"Wrote {out}. Next: python3 scripts/step1_debate_text/ontario_rebuild.py assign (the run script does this).")
