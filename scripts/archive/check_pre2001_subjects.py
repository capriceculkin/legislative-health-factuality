"""
check_pre2001_subjects.py

Checks what SubjectofBusiness values appear in the HuggingFace Hansard dataset
on Ontario health bill dates before 2001, to understand the matching problem.
"""
import json, os
from datasets import load_dataset
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    bill_index = json.load(f)

# Get health bill dates and titles pre-2001
date_to_titles = {}
for bill_key, bill_data in bill_index.items():
    if not bill_data.get("health_tag"):
        continue
    title = bill_data.get("title", "").upper().strip()
    for d in bill_data.get("dates", []):
        if d >= "2001":
            continue
        if d not in date_to_titles:
            date_to_titles[d] = []
        date_to_titles[d].append(title)

health_dates = set(date_to_titles.keys())
print(f"Pre-2001 health bill dates: {len(health_dates)}")
print(f"Sample health dates: {sorted(health_dates)[:5]}")
print(f"Sample health titles for {sorted(health_dates)[0]}:")
for t in date_to_titles[sorted(health_dates)[0]]:
    print(f"  {t}")

print("\nStreaming dataset to find matching rows...")
ds = load_dataset("a2aj/hansard", split="train", streaming=True)

subjects_on_health_dates = Counter()
rows_on_health_dates = 0

for r in ds:
    date = r.get("Date", "")
    if date >= "2001":
        continue
    if date not in health_dates:
        continue
    if r.get("intervention_type") != "speech":
        continue
    rows_on_health_dates += 1
    subj = str(r.get("SubjectofBusiness", "NO SUBJECT"))
    subjects_on_health_dates[subj] += 1

print(f"\nTotal speech rows on pre-2001 health dates: {rows_on_health_dates:,}")
print(f"\nTop 30 SubjectofBusiness values:")
for subj, count in subjects_on_health_dates.most_common(30):
    print(f"  {count:5d}  {subj[:80]}")

print("\nHealth bill titles we are trying to match:")
all_titles = set()
for titles in date_to_titles.values():
    for t in titles:
        all_titles.add(t)
for t in sorted(all_titles)[:20]:
    print(f"  {t[:80]}")
