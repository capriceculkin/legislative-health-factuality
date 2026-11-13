# check_aca.py   Prints the size and checksum of the saved debate text for the three Affordable Care Act bills
# (111-HR3590, 111-HR4872, 111-HR3962) and what the US index says about them. Changes nothing.
import json, os, hashlib

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
seg_dir = os.path.join(REPO, "data/us/v3/cr_segments_v3")

targets = ["111-HR3590", "111-HR4872", "111-HR3962"]
for fname in sorted(os.listdir(seg_dir)):
    for t in targets:
        if fname.startswith(t + "_"):
            fpath = os.path.join(seg_dir, fname)
            size = os.path.getsize(fpath)
            with open(fpath, "rb") as f:
                h = hashlib.md5(f.read()).hexdigest()[:8]
            print(f"{fname}: {size:,} bytes  md5={h}")

# Also check: how many sentences does the index say each has?
idx_path = os.path.join(REPO, "data/us/v3/segments_index.json")
with open(idx_path) as f:
    idx = json.load(f)
for e in idx:
    if e["bill_key"] in targets:
        print(f"Index: {e['bill_key']} | {e['debate_date']} | {e['units']} paragraphs | result={e.get('result','?')}")
