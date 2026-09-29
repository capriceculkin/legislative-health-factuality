#!/usr/bin/env python3
"""
diagnose_remaining.py  (read-only, changes nothing)
Collects the facts needed to fix the audit FAILs:
  1. where compute_scores_v3.py gets outcomes
  2. what Quebec outcome data exists (cheminement)
  3. the real Ontario health list (bills_master.json) vs the predicated bills
  4. US granule caches and text headers (to rebuild bill-specific US links)
  5. Ontario bill-dates with 0 or 2+ Hansard URLs
Run from project root:  python3 scripts/v3/diagnose_remaining.py > outputs/audit/diagnose.txt
"""
import glob, json, os, re
from collections import Counter

def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        print(f"  cannot load {p}: {ex}")
        return None

def hdr(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)

# 1 ---------------------------------------------------------------
hdr("1. compute_scores_v3.py outcome code")
p = "scripts/v3/compute_scores_v3.py"
if os.path.exists(p):
    for i, line in enumerate(open(p, encoding="utf-8"), 1):
        if re.search(r"outcome|fsob|plan\.json|quebec|cheminement|result|json\.load|open\(", line, re.I):
            print(f"{i:4}: {line.rstrip()}")
else:
    print("  not found")

# 2 ---------------------------------------------------------------
hdr("2. Quebec outcome sources")
for p in sorted(glob.glob("data/canada/quebec_bills/*")):
    print(f"  {p}  ({os.path.getsize(p):,} bytes)")
comb = load("data/canada/quebec_bills/quebec_health_bills_combined.json") or []
post = [e for e in comb if e.get("source") == "cheminement_post1994"]
if post:
    e = post[0]
    print("\n  combined entry (post-1994) fields:")
    for k, v in e.items():
        print(f"    {k}: {json.dumps(v, ensure_ascii=False)[:300]}")
che = load("data/canada/quebec_bills/cheminement_all_sessions.json")
if che is not None:
    print(f"\n  cheminement_all_sessions type={type(che).__name__} len={len(che)}")
    items = che if isinstance(che, list) else list(che.values())
    first = items[0] if items else {}
    if isinstance(che, dict):
        print(f"  first keys: {list(che.keys())[:5]}")
    print("  first entry:", json.dumps(first, ensure_ascii=False)[:1500])
    txt = json.dumps(che, ensure_ascii=False).lower()
    for w in ["sanction", "adopt", "retir", "mort au feuilleton", "étape", "etape", "stage"]:
        print(f"  occurrences of '{w}': {txt.count(w)}")

# 3 ---------------------------------------------------------------
hdr("3. Ontario health definition: bills_master.json vs predicated bills")
m = load("data/canada/ontario/v3/bills_master.json")
preds = load("data/dbpedia_pipeline/ontario/predications_v3.json") or []
pk = {p["bill_key"] for p in preds}
if m:
    health = {k for k, v in m.items() if v.get("health")}
    print(f"  master bills: {len(m)}, health=True: {len(health)}")
    print(f"  health_basis among health bills: {dict(Counter(m[k].get('health_basis', '') for k in health))}")
    print(f"  predicated bills: {len(pk)}; in master health list: {len(pk & health)}; "
          f"in master but health=False: {len(pk & (set(m) - health))}; not in master: {len(pk - set(m))}")
    print(f"  e.g. predicated but not health in master: {sorted(pk & (set(m) - health))[:10]}")
    print(f"  e.g. predicated and not in master: {sorted(pk - set(m))[:10]}")
    k0 = next(iter(health), None)
    if k0:
        print(f"  sample master entry {k0}: " + json.dumps(m[k0], ensure_ascii=False)[:800])
rev = "data/canada/ontario/v3/health_bills_review.csv"
print(f"  review CSV exists: {os.path.exists(rev)}")
if os.path.exists(rev):
    import csv
    rows = list(csv.DictReader(open(rev, encoding="utf-8")))
    print(f"  review rows: {len(rows)}; keep_yes_no filled: {Counter(r.get('keep_yes_no', '') for r in rows)}")

# 4 ---------------------------------------------------------------
hdr("4. US granule caches and text headers")
gl = glob.glob("data/us/v3/cache/granule_lists/*.json")
print(f"  granule_lists files: {len(gl)}; by prefix: {dict(Counter(os.path.basename(f).split('-')[0] + '-' + os.path.basename(f).split('-')[1] for f in gl))}")
crecb = [f for f in gl if "CRECB" in f][:2]
crec = [f for f in gl if "CRECB" not in f][:1]
for f in crecb + crec:
    g = (load(f) or {}).get("granules") or []
    print(f"  {os.path.basename(f)}: {len(g)} granules; first 3: "
          + json.dumps([{k: x.get(k) for k in ('granuleId', 'title', 'granuleClass', 'dateIssued')} for x in g[:3]])[:700])
print(f"  bound_pdf files: {len(glob.glob('data/us/v3/cache/bound_pdf/*.pdf'))}; e.g. "
      f"{[os.path.basename(x) for x in glob.glob('data/us/v3/cache/bound_pdf/*.pdf')[:3]]}")
print(f"  daily cache dirs: {len(glob.glob('data/us/v3/cache/daily/*'))}")
idx = load("data/us/v3/segments_index.json") or []
for e in [x for x in idx if x.get("edition") == "bound"][:1] + [x for x in idx if x.get("edition") != "bound"][:1]:
    fp = os.path.join("data/us", e["file"])
    head = open(fp, encoding="utf-8", errors="ignore").read(700) if os.path.exists(fp) else "(missing)"
    print(f"\n  --- {e['bill_key']} {e['debate_date']} ({e.get('edition')}) first 700 chars:\n{head}")
    body = open(fp, encoding="utf-8", errors="ignore").read() if os.path.exists(fp) else ""
    pages = re.findall(r"\[Pages? (H\d+)", body)[:10]
    print(f"  --- page refs in file: {pages}")
other = [f for f in glob.glob("data/us/v3/*") if os.path.isfile(f)]
print(f"\n  other files in data/us/v3: {[os.path.basename(f) for f in other]}")

# 5 ---------------------------------------------------------------
hdr("5. Ontario bill-dates with 0 or 2+ Hansard URLs")
seg = load("data/canada/ontario/v3/hansard_segments_v3.json") or {}
n = 0
for bk, days in seg.items():
    for d, paras in days.items():
        urls = Counter(p.get("url", "") for p in paras)
        if len(urls) != 1 or "" in urls:
            n += 1
            if n <= 12:
                print(f"  {bk} {d}: {dict(urls)}")
print(f"  total: {n}")
