"""
build_ontario_vote_linkage.py

Extracts recorded division (vote) results from Ontario Hansard files and
links each to a bill already in ontario_bill_index.json by date and bill
number. Ontario recorded divisions appear in a fairly fixed pattern:

  "The House divided on Bill 124, third reading, which was..."
  or
  "AYES / NAYS" vote tables following a bill reference

This is a first pass targeting the clearest, most common citation pattern
(division tied to third reading, which is Ontario's final passage vote,
the equivalent of Quebec's adoption finale). Bills without a matched
division stay flagged, not dropped, so the completeness picture stays
honest.

Output: data/canada/ontario/ontario_vote_index.json
"""

import os
import re
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONTARIO_DIR = os.path.join(REPO_ROOT, "data", "canada", "ontario")
BILL_INDEX_PATH = os.path.join(ONTARIO_DIR, "ontario_bill_index.json")
OUTPUT_PATH = os.path.join(ONTARIO_DIR, "ontario_vote_index.json")

# Matches division/vote language tied to a specific bill and reading stage.
# Third reading = final passage, the Ontario equivalent of Quebec's
# adoption finale (per the agreed unit-of-analysis from the July 5 notes).
DIVISION_PATTERN = re.compile(
    r"(?:House divided|recorded division|the vote|Ayes\s+\d+.{0,10}Nays\s+\d+)"
    r"[^\n.]{0,150}?Bill\s+(\d+)[^\n.]{0,100}?(third reading|second reading|third Reading)",
    re.IGNORECASE
)

OUTCOME_PATTERN = re.compile(
    r"Bill\s+(\d+)[^\n.]{0,100}?\b(carried|defeated|lost|agreed to)\b",
    re.IGNORECASE
)


def parliament_era(date_str):
    year = int(date_str[:4])
    return year - ((year - 1985) % 4)


def main():
    with open(BILL_INDEX_PATH, encoding="utf-8") as f:
        bill_index = json.load(f)

    files = sorted(f for f in os.listdir(ONTARIO_DIR) if f.endswith(".txt"))
    print(f"Scanning {len(files)} Ontario Hansard files for vote outcomes...")

    vote_index = {}
    files_with_division = 0

    for filename in files:
        date = filename.replace(".txt", "")
        era = parliament_era(date)
        path = os.path.join(ONTARIO_DIR, filename)

        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        found_any = False

        for number, stage in DIVISION_PATTERN.findall(content):
            key = f"{era}-Bill{number}"
            found_any = True
            entry = vote_index.setdefault(key, {
                "bill_number": number,
                "era": era,
                "vote_events": [],
            })
            entry["vote_events"].append({
                "date": date,
                "stage": stage.lower(),
                "match_type": "division_pattern",
            })

        for number, outcome in OUTCOME_PATTERN.findall(content):
            key = f"{era}-Bill{number}"
            found_any = True
            entry = vote_index.setdefault(key, {
                "bill_number": number,
                "era": era,
                "vote_events": [],
            })
            entry["vote_events"].append({
                "date": date,
                "outcome": outcome.lower(),
                "match_type": "outcome_pattern",
            })

        if found_any:
            files_with_division += 1

    # cross-reference against the bill index so we know real coverage
    linked = 0
    unlinked_votes = 0
    for key, entry in vote_index.items():
        if key in bill_index:
            linked += 1
        else:
            unlinked_votes += 1

    bills_with_no_vote_found = sum(1 for k in bill_index if k not in vote_index)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(vote_index, f, ensure_ascii=False, indent=2)

    print(f"\nFiles with a detected division/outcome: {files_with_division} of {len(files)}")
    print(f"Distinct bills with at least one vote event found: {len(vote_index)}")
    print(f"  Matched to an existing bill index entry: {linked}")
    print(f"  Vote found but no matching bill index entry (era mismatch or bill missed by extractor): {unlinked_votes}")
    print(f"Bills in index with no vote event found yet: {bills_with_no_vote_found} of {len(bill_index)}")
    print(f"\nSaved to: {OUTPUT_PATH}")

    print("\nSample linked entries:")
    shown = 0
    for key, entry in vote_index.items():
        if key in bill_index and shown < 5:
            title = bill_index[key].get("title", "")[:70]
            print(f"  {key}: {title}")
            print(f"    Vote events: {entry['vote_events'][:2]}")
            shown += 1


if __name__ == "__main__":
    main()
