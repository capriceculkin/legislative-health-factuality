"""
build_subject_billnum_mapping.py

For each SubjectofBusiness value in the Ontario HuggingFace Hansard dataset,
finds which health bill number is most mentioned in the Intervention text
for rows with that subject.

This gives us SubjectofBusiness → bill number mapping without scraping OLA.

Output: data/canada/ontario/subject_to_billnum.json
"""
import json, os, re
from collections import defaultdict, Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Loading data...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/hansard_health_combined.json")) as f:
    rows = json.load(f)

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)

# Build bill number → bill key lookup for health bills
# Also build era-aware lookup: (bill_number, year_range) → bill_key
billnum_to_keys = defaultdict(list)
for k, v in idx.items():
    if v.get("health_tag"):
        num = str(v.get("bill_number", ""))
        if num:
            dates = v.get("dates", [])
            years = [int(d[:4]) for d in dates if d]
            min_year = min(years) if years else 0
            max_year = max(years) if years else 9999
            billnum_to_keys[num].append((k, min_year, max_year))

all_health_billnums = set(billnum_to_keys.keys())
print(f"Health bill numbers: {len(all_health_billnums)}")

# For each subject + date, find which health bill numbers appear
BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)

# Group rows by subject
subject_rows = defaultdict(list)
for r in rows:
    subj = r.get("SubjectofBusiness", "")
    if subj:
        subject_rows[subj].append(r)

print(f"Unique subjects: {len(subject_rows)}")

# For each subject, vote on which health bill it belongs to
subject_to_billnum = {}
subject_to_billkey = {}

for subj, subj_rows in subject_rows.items():
    # Get date range for these rows
    dates = [r.get("Date", "") for r in subj_rows if r.get("Date")]
    if not dates:
        continue
    min_date = min(dates)
    max_date = max(dates)
    year_range = (int(min_date[:4]), int(max_date[:4]))

    # Count bill number mentions, weighted by frequency
    bill_votes = Counter()
    for r in subj_rows:
        text = str(r.get("Intervention", ""))
        for m in BILL_RE.findall(text):
            if m in all_health_billnums:
                # Check if this bill was active around these dates
                for bill_key, min_year, max_year in billnum_to_keys[m]:
                    if min_year <= year_range[1] + 2 and max_year >= year_range[0] - 2:
                        bill_votes[m] += 1
                        break

    if bill_votes:
        best_num = bill_votes.most_common(1)[0][0]
        subject_to_billnum[subj] = best_num
        # Find the bill key
        for bill_key, min_year, max_year in billnum_to_keys[best_num]:
            if min_year <= year_range[1] + 2 and max_year >= year_range[0] - 2:
                subject_to_billkey[subj] = bill_key
                break

print(f"\nResults:")
print(f"Subjects mapped: {len(subject_to_billnum)}/{len(subject_rows)}")
print(f"Coverage: {len(subject_to_billnum)/len(subject_rows)*100:.1f}%")

print("\nSample mappings:")
for subj, num in list(subject_to_billnum.items())[:10]:
    key = subject_to_billkey.get(subj, "?")
    print(f"  {subj[:50]} → Bill {num} ({key})")

print("\nUnmapped subjects (sample):")
unmapped = [s for s in subject_rows if s not in subject_to_billnum]
for s in unmapped[:10]:
    print(f"  {s[:60]}")

# Save both mappings
out1 = os.path.join(REPO_ROOT, "data/canada/ontario/subject_to_billnum.json")
out2 = os.path.join(REPO_ROOT, "data/canada/ontario/subject_to_billkey.json")

with open(out1, "w") as f:
    json.dump(subject_to_billnum, f, ensure_ascii=False)
with open(out2, "w") as f:
    json.dump(subject_to_billkey, f, ensure_ascii=False)

print(f"\nSaved to {out1}")
print(f"Saved to {out2}")
