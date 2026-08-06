import csv, json, os

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

# 1. PPB Quebec coverage
with open(f"{REPO}/data/canada/PPB.csv", newline="", encoding="utf-8") as f:
    ppb = list(csv.DictReader(f))
qc = [r for r in ppb if r.get("province","").lower()=="quebec"]
years = sorted(set(r["year"] for r in qc if r.get("year")))
with_career = [r for r in qc if r.get("career","").strip() not in ("", "NA")]
print(f"PPB Quebec rows: {len(qc)}, year range: {years[0]}-{years[-1]}")
print(f"PPB Quebec rows with career: {len(with_career)}")

# 2. Speaker turn party match rate
with open(f"{REPO}/data/canada/quebec_speaker_turns.json") as f:
    turns = json.load(f)
total = 0
matched = 0
for date, v in turns.items():
    for t in v.get("turns", []):
        total += 1
        if t.get("party", ""):
            matched += 1
print(f"Quebec speaker turns: {total}, party matched: {matched} ({matched/total*100:.1f}%)")

# 3. PPB coverage of post-2018 Quebec members
post2018 = [r for r in qc if int(r.get("year","0") or 0) >= 2018]
print(f"PPB Quebec rows 2018+: {len(post2018)}")
careers_2018 = [r for r in post2018 if r.get("career","").strip() not in ("","NA")]
print(f"PPB Quebec 2018+ with career: {len(careers_2018)}")
