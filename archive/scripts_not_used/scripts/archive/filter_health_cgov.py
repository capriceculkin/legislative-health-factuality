import csv, re, os, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO, "data/us/health_bills_final_matched.csv"), newline="") as f:
    matched = {}
    for row in csv.DictReader(f):
        m = re.match(r"([A-Za-z]+)(\d+)", row["bill_number"].replace(".",""))
        if m:
            matched[(str(row["congress"]), m.group(2))] = True

print("Matched (VoteView):", len(matched))


import glob

all_rows = []
for csv_file in glob.glob(os.path.join(REPO, "data/us/congress.gov.advanced.search*.csv")):
    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        for _ in range(3):
            next(f)
        all_rows.extend(list(csv.DictReader(f)))

rows = all_rows
print(f"Total Congress.gov rows across all CSVs: {len(rows)}")

health_laws = [r for r in rows if r.get("billPolicyArea","").strip() == "Health"]
print("CRS Health laws that became law:", len(health_laws))

voice = []
for row in health_laws:
    bill = row.get("Legislation Number","").strip()
    congress_str = row.get("Congress","")
    m = re.match(r"H\.R\.\s*(\d+)", bill)
    cm = re.search(r"(\d+)(?:st|nd|rd|th)", congress_str)
    if m and cm:
        key = (cm.group(1), m.group(1))
        if key not in matched:
            voice.append({
                "congress": cm.group(1),
                "bill": bill,
                "title": row.get("Title","")[:80],
                "date": row.get("Latest Action Date",""),
            })

print("Voice vote bills (Health, became law, not in VoteView):", len(voice))
for v in voice[:10]:
    print(f"  Congress {v['congress']}: {v['bill']} | {v['title'][:60]}")

out = os.path.join(REPO, "data/us/voice_vote_bills_authoritative.json")
with open(out, "w") as f:
    json.dump(voice, f, indent=2)
print(f"\nSaved {len(voice)} voice vote bills to {out}")
