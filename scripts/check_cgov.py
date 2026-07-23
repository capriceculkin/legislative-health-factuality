import csv, re, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO, "data/us/health_bills_final_matched.csv"), newline="") as f:
    matched = {}
    for row in csv.DictReader(f):
        m = re.match(r"([A-Za-z]+)(\d+)", row["bill_number"].replace(".",""))
        if m:
            matched[(str(row["congress"]), m.group(2))] = True

print("Matched (VoteView):", len(matched))

cgov_path = os.path.join(REPO, "data/us/congress.gov.advanced.search.csv")
with open(cgov_path, newline="", encoding="utf-8-sig") as f:
    for _ in range(3):
        next(f)
    reader = csv.DictReader(f)
    rows = list(reader)

print("Congress.gov laws:", len(rows))

voice = []
for row in rows:
    bill = row.get("Legislation Number", "").strip()
    congress_str = row.get("Congress", "")
    m = re.match(r"H\.R\.\s*(\d+)", bill)
    cm = re.search(r"(\d+)(?:st|nd|rd|th)", congress_str)
    if m and cm:
        key = (cm.group(1), m.group(1))
        if key not in matched:
            voice.append({
                "congress": cm.group(1),
                "bill": bill,
                "title": row.get("Title", "")[:70]
            })

print("Voice vote bills (became law, not in VoteView):", len(voice))
for v in voice[:10]:
    print(f"  Congress {v['congress']}: {v['bill']} | {v['title']}")

import json
out = os.path.join(REPO, "data/us/voice_vote_bills_authoritative.json")
with open(out, "w") as f:
    json.dump(voice, f, indent=2)
print(f"\nSaved {len(voice)} voice vote bills to {out}")