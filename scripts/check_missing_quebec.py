import json, os, re, subprocess
from collections import Counter

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

with open(f"{REPO}/data/canada/quebec_bills/quebec_bill_segments_index.json") as f:
    idx = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/factuality_scores.json") as f:
    scores = json.load(f)

covered = set()
for bill_num, dates in idx.items():
    for date in dates:
        covered.add(date)

missing = sorted([d for d in scores if d not in covered])

DIRS = [
    f"{REPO}/data/canada/quebec_assembly",
    f"{REPO}/data/canada/quebec_assembly/transcripts"
]

# Sample 20 missing files and show first 10 lines of actual content
patterns_found = Counter()
for d in missing[:30]:
    fname = d.replace('-','') + '.txt'
    for dir_ in DIRS:
        fpath = os.path.join(dir_, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding='utf-8', errors='replace') as f:
                text = f.read()
            # Find any line mentioning loi or projet
            matches = re.findall(r'.{0,20}(?:projet|loi|lecture|adoption|étude|débat).{0,40}', 
                                text, re.IGNORECASE)
            # Get unique patterns
            for m in matches[:3]:
                m_clean = re.sub(r'\s+', ' ', m.strip())
                if len(m_clean) > 10:
                    patterns_found[m_clean[:80]] += 1
            break

print("Most common patterns in missing files:")
for pattern, count in patterns_found.most_common(30):
    print(f"  {count:3d}x  {pattern}")
