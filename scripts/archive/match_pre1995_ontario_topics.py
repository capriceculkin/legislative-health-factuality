"""
match_pre1995_ontario_topics.py

For pre-1995 Ontario Hansard where SubjectofBusiness uses ALL CAPS topic labels
instead of bill short titles, this script matches topic labels to health bills
in the bill index using keyword overlap scoring.

Output: data/canada/ontario/pre1995_topic_bill_mapping.json
  {topic_label: {bill_key: bill_title, score: float}}
"""
import json, os, re
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)
with open(os.path.join(REPO_ROOT, "data/canada/ontario/hansard_health_combined.json")) as f:
    rows = json.load(f)

# Pre-1995 health bills
pre95_bills = {k: v for k, v in idx.items()
               if v.get("health_tag") and any(d < "1995" for d in v.get("dates", []))}
print(f"Pre-1995 health bills: {len(pre95_bills)}")

# Pre-1995 unique subjects on health dates
pre95_subjects = set(
    r.get("SubjectofBusiness", "")
    for r in rows
    if r.get("Date", "") < "1995" and r.get("SubjectofBusiness")
)
print(f"Pre-1995 unique subjects: {len(pre95_subjects)}")

STOP = {"AN", "ACT", "TO", "THE", "OF", "AND", "FOR", "IN", "A", "BY", "OR",
        "THAT", "WITH", "BE", "IS", "ARE", "THIS", "AS", "AT", "FROM", "ON",
        "NOT", "NO", "ANY", "ALL", "ITS", "THEIR", "MAKE", "AMEND", "PROVIDE",
        "RESPECTING", "RELATING", "REGARDING", "CONCERNING"}

def keywords(text):
    words = set(re.sub(r"[^A-Z ]", "", text.upper()).split())
    return words - STOP

matches = {}
for subj in sorted(pre95_subjects):
    if not subj:
        continue
    subj_kw = keywords(subj)
    if not subj_kw:
        continue

    candidates = []
    for bill_key, bill_data in pre95_bills.items():
        title = bill_data.get("title", "")
        title_kw = keywords(title)
        if not title_kw:
            continue
        overlap = subj_kw & title_kw
        score = len(overlap) / len(subj_kw)
        if score >= 0.4:
            candidates.append((score, bill_key, title[:60]))

    if candidates:
        candidates.sort(reverse=True)
        best_score, best_key, best_title = candidates[0]
        matches[subj] = {
            "bill_key": best_key,
            "title": best_title,
            "score": round(best_score, 3),
            "all_candidates": [(s, k, t) for s, k, t in candidates[:3]]
        }

print(f"\nSubjects matched: {len(matches)}/{len(pre95_subjects)}")
print(f"Unmatched: {len(pre95_subjects) - len(matches)}")

print("\nSample matches:")
for subj, m in list(matches.items())[:15]:
    print(f"  {subj[:40]:40s} → {m['bill_key']}: score={m['score']:.2f}")
    print(f"    {m['title']}")

print("\nUnmatched subjects:")
unmatched = [s for s in sorted(pre95_subjects) if s not in matches]
for s in unmatched[:15]:
    print(f"  {s}")

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/pre1995_topic_bill_mapping.json")
with open(out_path, "w") as f:
    json.dump(matches, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_path}")
