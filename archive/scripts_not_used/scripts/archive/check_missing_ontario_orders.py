"""
check_missing_ontario_orders.py

Streams HuggingFace dataset and shows what OrderofBusiness values
exist for the 244 still-missing Ontario health bill dates.
"""
import json, os
from datasets import load_dataset
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)
with open(os.path.join(REPO_ROOT, "data/canada/ontario/sentences_bill_specific.json")) as f:
    s = json.load(f)

covered = set(x["date"] for x in s)
health_dates = set()
for v in idx.values():
    if v.get("health_tag"):
        for d in v.get("dates", []):
            health_dates.add(d)

missing = health_dates - covered
print(f"Missing dates: {len(missing)}")

ds = load_dataset("a2aj/hansard", split="train", streaming=True)

orders_on_missing = Counter()
subjects_on_missing = Counter()
count = 0
rows_on_missing = 0

for r in ds:
    count += 1
    if count % 200000 == 0:
        print(f"  {count:,} scanned | {rows_on_missing:,} on missing dates")
    date = r.get("Date", "")
    if date not in missing:
        continue
    rows_on_missing += 1
    orders_on_missing[str(r.get("OrderofBusiness", "None"))] += 1
    if r.get("intervention_type") == "speech":
        subjects_on_missing[str(r.get("SubjectofBusiness", "None"))[:60]] += 1

print(f"\nTotal rows on missing dates: {rows_on_missing:,}")
print(f"\nOrderofBusiness values:")
for order, n in orders_on_missing.most_common(20):
    print(f"  {n:6d}  {order}")

print(f"\nTop SubjectofBusiness on missing dates (speech rows):")
for subj, n in subjects_on_missing.most_common(15):
    print(f"  {n:6d}  {subj}")
