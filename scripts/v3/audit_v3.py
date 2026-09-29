import json, os, re
from collections import Counter

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

print("=" * 60)
print("CHECK 1: sentences_v3 fields and ID format")
print("=" * 60)
for j in ["us", "quebec", "ontario"]:
    path = os.path.join(REPO, f"data/dbpedia_pipeline/{j}/sentences_v3.json")
    if not os.path.exists(path):
        print(f"{j}: MISSING")
        continue
    with open(path) as f:
        s = json.load(f)
    print(f"\n{j}: {len(s):,} sentences")
    print(f"  fields: {list(s[0].keys())}")
    print(f"  sample sentence_id: {s[0]['sentence_id']}")
    print(f"  sample bill_key:    {s[0].get('bill_key', 'MISSING')}")

print("\n" + "=" * 60)
print("CHECK 2: US segments — bound editions, Daily Digest, multi-bill")
print("=" * 60)
seg_dir = os.path.join(REPO, "data/us/v3/cr_segments_v3")
bound, digest, multi_bill = 0, 0, 0
total = 0
examples_multi = []
for fname in sorted(os.listdir(seg_dir)):
    if not fname.endswith(".txt"):
        continue
    total += 1
    fpath = os.path.join(seg_dir, fname)
    with open(fpath, encoding="utf-8") as f:
        text = f.read(3000)
    if re.search(r"\bPt\.\s*\d+", text):
        bound += 1
    if "Daily Digest" in text or "DAILY DIGEST" in text:
        digest += 1
    hrs = set(re.findall(r"H\.R\.\s*\d+", text))
    if len(hrs) > 3:
        multi_bill += 1
        if len(examples_multi) < 3:
            examples_multi.append((fname, sorted(hrs)[:5]))

print(f"Total US segment files: {total}")
print(f"  Bound edition (Pt. N): {bound}")
print(f"  Daily Digest present:  {digest}")
print(f"  3+ H.R. numbers:       {multi_bill}")
if examples_multi:
    print("  Examples of multi-bill files:")
    for fname, hrs in examples_multi:
        print(f"    {fname}: {hrs}")

print("\n" + "=" * 60)
print("CHECK 3: Ontario sentences_v3 — bill_key format and count")
print("=" * 60)
path = os.path.join(REPO, "data/dbpedia_pipeline/ontario/sentences_v3.json")
with open(path) as f:
    s = json.load(f)
keys = Counter(x["bill_key"] for x in s)
print(f"Unique bill_keys: {len(keys)}")
print(f"Sample keys: {sorted(keys)[:8]}")
# Check for any bill_keys that look like old format (year-BillN instead of session-BillN)
old_fmt = [k for k in keys if re.match(r"^\d{4}-Bill", k)]
print(f"Old-format keys (YYYY-BillN): {len(old_fmt)}")
if old_fmt:
    print(f"  Examples: {old_fmt[:5]}")

print("\n" + "=" * 60)
print("CHECK 4: duplicate (bill_key, date) pairs")
print("=" * 60)
for j in ["us", "quebec", "ontario"]:
    path = os.path.join(REPO, f"data/dbpedia_pipeline/{j}/sentences_v3.json")
    if not os.path.exists(path):
        continue
    with open(path) as f:
        s = json.load(f)
    pairs = Counter((x["bill_key"], x["date"]) for x in s)
    max_val = max(pairs.values())
    big = [(k, v) for k, v in pairs.items() if v > 5000]
    print(f"\n{j}: {len(pairs)} unique (bill_key, date) pairs")
    print(f"  max sentences in one pair: {max_val}")
    if big:
        print(f"  pairs with >5000 sentences: {len(big)}")
        for k, v in sorted(big, key=lambda x: -x[1])[:3]:
            print(f"    {k}: {v} sentences")

print("\n" + "=" * 60)
print("CHECK 5: Ontario — session format in bill_keys vs old year format")
print("=" * 60)
path = os.path.join(REPO, "data/dbpedia_pipeline/ontario/sentences_v3.json")
with open(path) as f:
    s = json.load(f)
session_fmt = [x["bill_key"] for x in s if re.match(r"^\d+-\d+-Bill", x["bill_key"])]
year_fmt = [x["bill_key"] for x in s if re.match(r"^\d{4}-Bill", x["bill_key"])]
print(f"Session-format keys (N-N-BillN): {len(set(session_fmt))}")
print(f"Year-format keys (YYYY-BillN):   {len(set(year_fmt))}")
if year_fmt:
    print(f"  Year-format examples: {sorted(set(year_fmt))[:5]}")
