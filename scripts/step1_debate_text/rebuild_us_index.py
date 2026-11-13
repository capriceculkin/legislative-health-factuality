# rebuild_us_index.py   Rebuilds the US index (data/us/v3/segments_index.json) from the debate text files in
# data/us/v3/cr_segments_v3 and the bill plan (data/us/v3/plan.json).
import json, os

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
seg_dir = os.path.join(REPO, "data/us/v3/cr_segments_v3")
plan_path = os.path.join(REPO, "data/us/v3/plan.json")
index_path = os.path.join(REPO, "data/us/v3/segments_index.json")

with open(plan_path) as f:
    plan = json.load(f)

plan_by_key = {e["bill_key"]: e for e in plan if e.get("bill_key")}

index = []
files = sorted(os.listdir(seg_dir))
skipped = []
for fname in files:
    if not fname.endswith(".txt"):
        continue
    stem = fname[:-4]
    # filename: 116-HR3_2019-12-12.txt — split on last underscore before the date
    # date is always YYYY-MM-DD (10 chars), preceded by underscore
    if len(stem) < 12 or stem[-11] != "_":
        skipped.append(fname)
        continue
    bill_key = stem[:-11]
    debate_date = stem[-10:]
    p = plan_by_key.get(bill_key, {})
    fpath = os.path.join(seg_dir, fname)
    with open(fpath, encoding="utf-8") as f:
        content = f.read()
    paras = [x.strip() for x in content.split("\n\n") if x.strip()]
    index.append({
        "bill_key": bill_key,
        "congress": p.get("congress", ""),
        "type": p.get("type", ""),
        "number": p.get("number", ""),
        "vote_date": p.get("vote_date", ""),
        "result": p.get("result", ""),
        "source": p.get("source", ""),
        "raw_bill": p.get("raw_bill", ""),
        "edition": p.get("edition", ""),
        "debate_date": debate_date,
        "date_source": p.get("date_source", ""),
        "file": os.path.join("v3/cr_segments_v3", fname),
        "units": len(paras),
        "excluded": p.get("excluded", False),
    })

if skipped:
    print(f"Skipped (unexpected names): {skipped[:5]}")

print(f"Rebuilt index: {len(index)} entries from {len(files)} files")
if index:
    print(f"Sample: {index[0]['bill_key']} | {index[0]['debate_date']} | {index[0]['units']} paragraphs")

tmp = index_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(index, f, indent=2)
os.replace(tmp, index_path)
print(f"Saved to {index_path}")
