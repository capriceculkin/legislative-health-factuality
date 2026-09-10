"""
fetch_ontario_hansard_pre2001_v2.py

Streams a2aj/hansard and extracts pre-2001 Ontario health bill debate rows
using a health keyword filter on the SubjectofBusiness field.

This approach works because SubjectofBusiness uses short bill titles
(e.g. "HEALTH CARE ACCESSIBILITY ACT") rather than full legal titles.

Output: data/canada/ontario/hansard_health_pre2001.json
"""
import json, os
from datasets import load_dataset

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Health-related keywords to match against SubjectofBusiness
HEALTH_KEYWORDS = [
    'HEALTH', 'HOSPITAL', 'MEDICINE', 'MEDICAL', 'DRUG', 'PHARMACY',
    'PHARMAC', 'NURSING', 'NURSE', 'DENTAL', 'DENTIST', 'MENTAL',
    'DISABILITY', 'LONG-TERM CARE', 'LONG TERM CARE', 'EXTRA BILLING',
    'EXTRA-BILLING', 'ABORTION', 'CANCER', 'HIV', 'AIDS', 'AMBULANCE',
    'PHYSIOTHERAPY', 'MIDWIFERY', 'MIDWIFE', 'CHIROPODY', 'OPTOMETRY',
    'OPTOMETRI', 'OCCUPATIONAL HEALTH', 'WORKPLACE SAFETY', 'PUBLIC HEALTH',
    'VACCINATION', 'IMMUNIZATION', 'PANDEMIC', 'COVID', 'EPIDEMIC',
    'REPRODUCTIVE', 'SEXUAL HEALTH', 'ADDICTION', 'SUBSTANCE',
    'DEVELOPMENTAL', 'AUTISM', 'DEMENTIA', 'ALZHEIMER', 'PALLIATIVE',
    'HOSPICE', 'TRANSPLANT', 'BLOOD', 'LABORATORY', 'PATHOLOGY',
    'RADIOLOGY', 'RADIATION TECHNOL', 'CHIROPRACTIC', 'NATUROPATH',
    'ACUPUNCTURE', 'HOMEOPATH', 'PSYCHOLOG', 'PSYCHIATR', 'THERAPY',
    'REHABILITATION', 'PROSTHETI', 'ORTHOTICS', 'HEARING AID',
    'INDEPENDENT HEALTH', 'REGULATED HEALTH', 'HEALTH PROFESSIONS',
    'HEALTH CARE', 'HEALTH SERVICES', 'HEALTH INSURANCE', 'OHIP',
    'HEALTH PROTECTION', 'HEALTH PROMOTION', 'COMMUNITY HEALTH',
    'COMMUNITY CARE', 'HOME CARE', 'CHRONIC CARE', 'ACUTE CARE',
]

def is_health_subject(subject):
    if not subject:
        return False
    subject_upper = subject.upper()
    return any(kw in subject_upper for kw in HEALTH_KEYWORDS)

print("Loading bill index for date filtering...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    bill_index = json.load(f)

# Get all health bill dates pre-2001
health_dates = set()
for bill_data in bill_index.values():
    if bill_data.get("health_tag"):
        for d in bill_data.get("dates", []):
            if d < "2001":
                health_dates.add(d)

print(f"Pre-2001 health bill dates: {len(health_dates)}")

print("Streaming HuggingFace dataset...")
ds = load_dataset("a2aj/hansard", split="train", streaming=True)

health_rows = []
count = 0
skipped_date = 0
skipped_type = 0
skipped_subject = 0
skipped_length = 0

for r in ds:
    count += 1
    if count % 200000 == 0:
        print(f"  {count:,} scanned | {len(health_rows):,} matched | "
              f"date={skipped_date:,} type={skipped_type:,} "
              f"subj={skipped_subject:,} len={skipped_length:,} skipped")

    date = r.get("Date", "")

    if date >= "2001":
        skipped_date += 1
        continue

    if date not in health_dates:
        skipped_date += 1
        continue

    if r.get("intervention_type") != "speech":
        skipped_type += 1
        continue

    subject = r.get("SubjectofBusiness", "")
    if not is_health_subject(subject):
        skipped_subject += 1
        continue

    intervention = r.get("Intervention", "")
    if not intervention or len(str(intervention)) < 50:
        skipped_length += 1
        continue

    health_rows.append(dict(r))

print(f"\nTotal scanned: {count:,}")
print(f"Pre-2001 health rows matched: {len(health_rows):,}")

if health_rows:
    dates = sorted(set(r["Date"] for r in health_rows))
    print(f"Date range: {dates[0]} to {dates[-1]}")

    from collections import Counter
    subjects = Counter(r["SubjectofBusiness"] for r in health_rows)
    print(f"\nTop subjects matched:")
    for subj, n in subjects.most_common(15):
        print(f"  {n:5d}  {subj[:70]}")

    print(f"\nSample rows:")
    for r in health_rows[:3]:
        print(f"  {r['Date']} | {r.get('SubjectofBusiness','')[:60]}")
        print(f"  Speaker: {r.get('PersonSpeaking','')}")
        print(f"  Text: {str(r.get('Intervention',''))[:100]}")
        print()

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/hansard_health_pre2001.json")
with open(out_path, "w") as f:
    json.dump(health_rows, f)
print(f"Saved to {out_path}")
