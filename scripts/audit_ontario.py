"""
audit_ontario.py
Audits hansard_api_bill_segments.json for wrong bill assignments.
Categories:
1. Correct: assigned bill number mentioned in text
2. Wrong: text starts with "Resuming debate on Bill X" where X != assigned bill
3. Uncertain: no bill number in text, no clear wrong signal
"""
import json, re

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments.json") as f:
    seg = json.load(f)
with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    idx = json.load(f)

BILL_RE = re.compile(r"Bill\s+(\d+)", re.IGNORECASE)
RESUME_RE = re.compile(r"(?:Resuming|second reading of Bill|debate on Bill)\s+(\d+)", re.IGNORECASE)

correct = []
wrong = []
uncertain = []

for bk, dates in seg.items():
    bnum = str(idx.get(bk, {}).get("bill_number", ""))
    title = idx.get(bk, {}).get("title", "")[:50]
    if not bnum:
        continue
    for date, paras in dates.items():
        all_text = " ".join(p if isinstance(p, str) else p.get("text", "") for p in paras)
        first = paras[0] if isinstance(paras[0], str) else paras[0].get("text", "")
        mentioned = set(BILL_RE.findall(all_text))

        if bnum in mentioned:
            correct.append((bk, date, bnum, title))
        else:
            # Check if first paragraph is explicitly about a different bill
            resume_match = RESUME_RE.search(first)
            if resume_match and resume_match.group(1) != bnum:
                wrong.append((bk, date, bnum, resume_match.group(1), title, first[:120]))
            else:
                uncertain.append((bk, date, bnum, title, first[:120]))

print(f"CORRECT (bill number in text): {len(correct)}")
print(f"WRONG (text is about different bill): {len(wrong)}")
print(f"UNCERTAIN (no bill number, no clear signal): {len(uncertain)}")
print()

print("=== WRONG ASSIGNMENTS ===")
for bk, date, bnum, other_bnum, title, first in wrong:
    print(f"{bk} | Bill {bnum} | {title}")
    print(f"  Date: {date}")
    print(f"  Text about: Bill {other_bnum}")
    print(f"  First para: {first}")
    print()

print("=== UNCERTAIN (sample of 20) ===")
for bk, date, bnum, title, first in uncertain[:20]:
    print(f"{bk} | Bill {bnum} | {title}")
    print(f"  Date: {date}")
    print(f"  First para: {first}")
    print()
