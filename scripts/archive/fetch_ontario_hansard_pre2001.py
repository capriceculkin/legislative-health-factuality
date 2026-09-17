"""
fetch_ontario_hansard_pre2001.py

Streams the a2aj/hansard HuggingFace dataset and extracts pre-2001
Ontario health bill debate rows, matched by bill title to health bill dates.

Output: data/canada/ontario/hansard_health_pre2001.json
"""
import json, os
from datasets import load_dataset

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Loading bill index...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    bill_index = json.load(f)

# Build date -> [health bill titles] lookup
date_to_titles = {}
for bill_key, bill_data in bill_index.items():
    if not bill_data.get("health_tag"):
        continue
    title = bill_data.get("title", "").upper().strip()
    for d in bill_data.get("dates", []):
        if d not in date_to_titles:
            date_to_titles[d] = []
        date_to_titles[d].append(title)

health_dates = set(date_to_titles.keys())
print(f"Health bill dates: {len(health_dates)}")

print("Streaming HuggingFace dataset...")
ds = load_dataset("a2aj/hansard", split="train", streaming=True)

health_rows = []
count = 0

for r in ds:
    count += 1
    if count % 200000 == 0:
        print(f"  {count:,} rows scanned | {len(health_rows):,} matched")

    date = r.get("Date", "")

    # Only pre-2001
    if date >= "2001":
        continue

    # Must be on a health bill date
    if date not in health_dates:
        continue

    # Must be speech not procedural
    if r.get("intervention_type") != "speech":
        continue

    # Must have content
    intervention = r.get("Intervention", "")
    if not intervention or len(str(intervention)) < 50:
        continue

    # Match subject to health bill title
    subj = str(r.get("SubjectofBusiness", "")).upper().strip()
    if not subj:
        continue

    matched = False
    for title in date_to_titles.get(date, []):
        if len(title) < 10:
            continue
        # Check overlap between subject and title
        title_words = set(title.split()[:4])
        subj_words = set(subj.split()[:4])
        if len(title_words & subj_words) >= 2:
            matched = True
            break
        # Also check if title start is in subject or vice versa
        if title[:15] in subj or subj[:15] in title:
            matched = True
            break

    if matched:
        health_rows.append(dict(r))

print(f"\nTotal scanned: {count:,}")
print(f"Pre-2001 health rows matched: {len(health_rows):,}")

if health_rows:
    dates = sorted(set(r["Date"] for r in health_rows))
    print(f"Date range: {dates[0]} to {dates[-1]}")
    print("Sample rows:")
    for r in health_rows[:3]:
        print(f"  {r['Date']} | {r.get('SubjectofBusiness','')[:60]} | {r.get('PersonSpeaking','')}")
        print(f"  {str(r.get('Intervention',''))[:100]}")

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/hansard_health_pre2001.json")
with open(out_path, "w") as f:
    json.dump(health_rows, f)
print(f"\nSaved to {out_path}")
