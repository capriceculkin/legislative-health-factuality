"""
fetch_ontario_missing_dates.py

Fetches Orders of the Day rows from HuggingFace a2aj/hansard for
Ontario health bill dates that are missing from the current bill-specific corpus.

For these dates, we know they are health bill debate dates from the bill index,
so we take all Orders of the Day speech regardless of subject matching.

Output: data/canada/ontario/hansard_missing_dates.json
"""
import json, os
from datasets import load_dataset

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Loading bill index...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)

print("Loading existing bill-specific sentences...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/sentences_bill_specific.json")) as f:
    existing = json.load(f)

covered = set(s["date"] for s in existing)

health_dates = set()
for v in idx.values():
    if v.get("health_tag"):
        for d in v.get("dates", []):
            health_dates.add(d)

missing_dates = health_dates - covered
print(f"Health bill dates: {len(health_dates)}")
print(f"Already covered: {len(covered & health_dates)}")
print(f"Missing: {len(missing_dates)}")

BILL_ORDERS = {"ORDERS OF THE DAY", "Orders of the Day", "orders of the day", None, "None", ""}

print("Streaming HuggingFace dataset...")
ds = load_dataset("a2aj/hansard", split="train", streaming=True)

missing_rows = []
count = 0

for r in ds:
    count += 1
    if count % 200000 == 0:
        print(f"  {count:,} scanned | {len(missing_rows):,} matched")

    date = r.get("Date", "")
    if date not in missing_dates:
        continue
    if r.get("intervention_type") != "speech":
        continue
    intervention = r.get("Intervention", "")
    if not intervention or len(str(intervention)) < 50:
        continue

    missing_rows.append(dict(r))

print(f"\nTotal scanned: {count:,}")
print(f"Rows found: {len(missing_rows):,}")

dates_found = set(r["Date"] for r in missing_rows)
print(f"Dates covered: {len(dates_found)}/{len(missing_dates)}")
print(f"Dates still missing: {len(missing_dates - dates_found)}")

if missing_rows:
    from collections import Counter
    subjects = Counter(r.get("SubjectofBusiness", "") for r in missing_rows)
    print("\nTop subjects found:")
    for s, n in subjects.most_common(10):
        print(f"  {n:5d}  {str(s)[:70]}")

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/hansard_missing_dates.json")
with open(out_path, "w") as f:
    json.dump(missing_rows, f)
print(f"\nSaved to {out_path}")
