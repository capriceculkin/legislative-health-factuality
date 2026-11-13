import json, re, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO, "data/canada/quebec_bills/pre1994_health_bills.json")) as f:
    bills = json.load(f)
with open(os.path.join(REPO, "data/canada/quebec_bills/quebec_pre1994_vote_outcomes.json")) as f:
    outcomes = json.load(f)

added = 0
for b in bills:
    fname = b.get("filename", "")
    m = re.match(r"(\d+)-(\d+)_[\d-]+_(\d+)[\w()]*-F\.pdf", fname)
    if not m:
        continue
    session = f"{m.group(1)}-{m.group(2)}"
    num = str(int(m.group(3)))
    key = f"{session}-Bill{num}"
    if key not in outcomes:
        outcomes[key] = {
            "bill_number": num,
            "session": session,
            "title": b.get("description", ""),
            "outcome": "died_in_session",
            "vote_date": None,
            "context": "Never found in Assembly transcripts - died before adoption",
        }
        added += 1
        print(f"Added {key} as died_in_session")

with open(os.path.join(REPO, "data/canada/quebec_bills/quebec_pre1994_vote_outcomes.json"), "w") as f:
    json.dump(outcomes, f, ensure_ascii=False, indent=2)

passed = sum(1 for v in outcomes.values() if v.get("outcome") == "passed")
died   = sum(1 for v in outcomes.values() if v.get("outcome") == "died_in_session")
print(f"\nTotal: {len(outcomes)} | Passed: {passed} | Died in session: {died}")
print(f"Added {added} new died_in_session entries")
