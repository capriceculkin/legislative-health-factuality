#!/usr/bin/env python3
"""
diagnose_bound.py  (read-only)
Explains the flagged pages and the days with no House PDF after reextract_bound.py.
Run from project root:
    python3 scripts/step1_debate_text/diagnose_bound.py > outputs/audit/bound_diagnose.txt
"""
import csv, datetime as dt, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AUD = ROOT / "outputs" / "audit"
CACHE = ROOT / "data" / "us" / "v3" / "cache"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def long_date(s):
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2}),\s*(\d{4})", s or "")
    return f"{m.group(3)}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}" if m else ""


def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


rows = list(csv.DictReader(open(AUD / "bound_reextract_pages.csv", encoding="utf-8")))
by_day = defaultdict(list)
for r in rows:
    by_day[r["day"]].append(r)

print("=" * 70 + "\n1. FLAG REASONS BY DAY (days with any flagged page)\n" + "=" * 70)
for day in sorted(by_day):
    rs = by_day[day]
    fl = [r for r in rs if r["decision"].startswith("FLAG")]
    if not fl:
        continue
    reasons = Counter("header date wrong" if "header date" in r["decision"] else "readers differ, unclear"
                      for r in fl)
    hdates = Counter(r["header_date"] for r in fl if r["header_date"])
    c = load(CACHE / "bound_text" / f"{day}.json") or {}
    agree = sorted(float(r["agreement"]) for r in fl)
    print(f"{day} ({dt.date.fromisoformat(day):%a}): {len(fl)}/{len(rs)} flagged; {dict(reasons)}; "
          f"header dates on flagged pages {dict(hdates.most_common(3))}; PDFs {c.get('granules')} "
          f"from {c.get('granule_source')}; median agreement {agree[len(agree) // 2] if agree else ''}")
    if len(fl) / len(rs) > 0.5:
        ex = fl[len(fl) // 2]
        print(f"      example page {ex['page']} of {ex['pdf']}: header {ex['header']!r} gutters {ex['gutters']} "
              f"agreement {ex['agreement']} join geo/stored {ex['join_geo']}/{ex['join_stored']}")

print("\n" + "=" * 70 + "\n2. DAYS WITH NO HOUSE PDF\n" + "=" * 70)
plan = load(ROOT / "data/us/v3/plan.json") or []
vote_days = defaultdict(list)
for b in plan:
    vote_days[b["vote_date"]].append(b["bill_key"])
read_days = set(by_day)
house_titles = defaultdict(list)
for p in (CACHE / "granule_lists").glob("GPO-CRECB-*.json"):
    for g in ((load(p) or {}).get("granules") or []):
        t = str(g.get("title", ""))
        if t.startswith("House of Representatives"):
            house_titles[long_date(t)].append(g["granuleId"])
bound_days = set()
for b in plan:
    if b.get("vote_date", "") < "1994-01-01":
        d0 = dt.date.fromisoformat(b["vote_date"])
        bound_days |= {b["vote_date"], (d0 - dt.timedelta(days=1)).isoformat()}
for day in sorted(bound_days - read_days):
    d = dt.date.fromisoformat(day)
    near = {x: house_titles[x] for x in sorted(house_titles)
            if abs((dt.date.fromisoformat(x) - d).days) <= 3} if house_titles else {}
    role = f"VOTE DAY for {vote_days[day]}" if day in vote_days else "day before a vote (lookback)"
    years = sorted({p.name.split("-pt")[0] for p in (CACHE / "granule_lists").glob(f"GPO-CRECB-{day[:4]}-pt*.json")})
    print(f"{day} ({d:%a}): {role}; GovInfo parts cached for {day[:4]}: "
          f"{len(list((CACHE / 'granule_lists').glob(f'GPO-CRECB-{day[:4]}-pt*.json')))}; "
          f"House days within 3 days: {sorted(near)}")
