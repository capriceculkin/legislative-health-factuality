"""
build_ontario_bill_index.py

Extracts bill citations ("Bill 124, An Act to...") from every Ontario
Hansard transcript in data/canada/ontario/. Unlike Quebec's CSSS files,
Ontario floor debates cover all topics, so bills get a preliminary
health_tag based on title keywords. Bills with no title found stay
untagged for a later classifier pass.

Output: data/canada/ontario/ontario_bill_index.json (keyed by session-era
bill identity: bills renumber each parliament, so the key is
"{first_seen_year}-Bill{number}" to avoid collapsing different bills
that share a number across decades).
"""

import os
import re
import json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONTARIO_DIR = os.path.join(REPO_ROOT, "data", "canada", "ontario")
OUTPUT_PATH = os.path.join(ONTARIO_DIR, "ontario_bill_index.json")

# Formal citation: "Bill 124, An Act to amend..."
BILL_PATTERN = re.compile(
    r"Bill\s+(\d+)\s*,\s*(An Act[^\n.;]{0,250})",
    re.IGNORECASE
)

# Bare references: "Bill 124" with no title, still worth logging the sighting
BARE_PATTERN = re.compile(r"Bill\s+(\d+)\b")

HEALTH_KEYWORDS = [
    "health", "hospital", "medic", "nurs", "mental", "long-term care",
    "public health", "ambulance", "pharma", "drug", "physician",
    "patient", "disease", "cancer", "tobacco", "smoking", "addiction",
    "disability", "midwif", "dental", "ohip", "home care",
]


def health_tag_from_title(title):
    t = title.lower()
    return any(kw in t for kw in HEALTH_KEYWORDS)


def parliament_era(date_str):
    """
    Ontario bills renumber each parliament (roughly every 3-5 years).
    Without a parliament-number source, bucket by year as a conservative
    proxy so 'Bill 1' in 1985 doesn't merge with 'Bill 1' in 2003.
    A 4-year bucket is used: 1985-1988 -> era 1985, etc.
    """
    year = int(date_str[:4])
    return year - ((year - 1985) % 4)


def main():
    bill_index = {}
    files = sorted(f for f in os.listdir(ONTARIO_DIR) if f.endswith(".txt"))
    print(f"Scanning {len(files)} Ontario Hansard files...")

    files_with_no_bill = 0

    for filename in files:
        date = filename.replace(".txt", "")
        era = parliament_era(date)
        path = os.path.join(ONTARIO_DIR, filename)

        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        titled = BILL_PATTERN.findall(content)
        bare = BARE_PATTERN.findall(content)

        if not bare:
            files_with_no_bill += 1
            continue

        seen_this_file = set()

        for number, raw_title in titled:
            key = f"{era}-Bill{number}"
            title = re.sub(r"\s+", " ", raw_title).strip()
            entry = bill_index.setdefault(key, {
                "bill_number": number,
                "era": era,
                "title": "",
                "health_tag": False,
                "sessions": [],
                "dates": [],
            })
            if len(title) > len(entry["title"]):
                entry["title"] = title
                entry["health_tag"] = health_tag_from_title(title)
            if date not in entry["dates"]:
                entry["dates"].append(date)
            seen_this_file.add(number)

        for number in bare:
            if number in seen_this_file:
                continue
            seen_this_file.add(number)
            key = f"{era}-Bill{number}"
            entry = bill_index.setdefault(key, {
                "bill_number": number,
                "era": era,
                "title": "",
                "health_tag": False,
                "sessions": [],
                "dates": [],
            })
            if date not in entry["dates"]:
                entry["dates"].append(date)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(bill_index, f, ensure_ascii=False, indent=2)

    total = len(bill_index)
    with_title = sum(1 for e in bill_index.values() if e["title"])
    health = sum(1 for e in bill_index.values() if e["health_tag"])

    print(f"\nTotal unique bills (era-scoped): {total}")
    print(f"Bills with formal title captured: {with_title}")
    print(f"Bills keyword-tagged as health-related: {health}")
    print(f"Files with no bill mention: {files_with_no_bill} of {len(files)}")
    print(f"\nSaved index to: {OUTPUT_PATH}")

    print("\nSample health-tagged bills:")
    shown = 0
    for key, entry in bill_index.items():
        if entry["health_tag"] and shown < 5:
            print(f"  {key}: {entry['title'][:90]}")
            print(f"    Dates: {entry['dates'][:3]} ({len(entry['dates'])} total)")
            shown += 1


if __name__ == "__main__":
    main()
