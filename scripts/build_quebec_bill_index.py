"""
build_quebec_bill_index.py

Extracts bill mentions ("projet de loi n° X") from every CSSS committee
transcript HTML file in data/canada/quebec/. Since CSSS stands for
Commission de la santé et des services sociaux, every file in this folder
is already health-committee content, so no classifier is needed, just
extraction of the bill number, title, and session date from each file.

Output: data/canada/quebec_bills/quebec_bill_index.json
Structure:
{
  "157": {
    "bill_number": "157",
    "title": "Loi constituant la Société québécoise du cannabis...",
    "health_tag": true,
    "sessions": ["CSSS-180116", ...],
    "dates": ["2018-01-16", ...]
  },
  ...
}
"""

import os
import re
import json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEBEC_DIR = os.path.join(REPO_ROOT, "data", "canada", "quebec")
OUTPUT_DIR = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "quebec_bill_index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Matches "projet de loi n° 157, Loi constituant..." and captures the
# number plus whatever title text follows up to the next period or tag.
BILL_PATTERN = re.compile(
    r"projet de loi n[°o]\s*(\d+)(?:\s*,?\s*(Loi\s[^<.]{0,200}|sur\s[^<.]{0,200}|"
    r"concernant\s[^<.]{0,200}|relatif\s[^<.]{0,200}|modifiant\s[^<.]{0,200}|"
    r"visant\s[^<.]{0,200}|édictant\s[^<.]{0,200}|portant\s[^<.]{0,200}))?",
    re.IGNORECASE
)


def parse_date_from_filename(filename):
    """
    CSSS-180116.html -> 2018-01-16
    Assumes YYMMDD format, years 00-30 map to 2000-2030,
    years 31-99 map to 1931-1999 (shouldn't occur for this project
    but handled defensively).
    """
    match = re.search(r"CSSS-(\d{6})", filename)
    if not match:
        return None
    yy, mm, dd = match.group(1)[:2], match.group(1)[2:4], match.group(1)[4:6]
    year = int(yy)
    full_year = 2000 + year if year <= 30 else 1900 + year
    return f"{full_year}-{mm}-{dd}"


def clean_title(raw_title):
    if not raw_title:
        return ""
    # collapse whitespace/newlines from the raw HTML text
    return re.sub(r"\s+", " ", raw_title).strip()


def main():
    bill_index = defaultdict(lambda: {
        "bill_number": None,
        "title": "",
        "health_tag": True,  # every file here is CSSS, so this is always true
        "sessions": [],
        "dates": [],
    })

    files = sorted(f for f in os.listdir(QUEBEC_DIR) if f.endswith(".html"))
    print(f"Scanning {len(files)} CSSS transcript files...")

    files_with_no_bill = []

    for filename in files:
        path = os.path.join(QUEBEC_DIR, filename)
        session_id = filename.replace(".html", "")
        date = parse_date_from_filename(filename)

        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        matches = BILL_PATTERN.findall(content)
        if not matches:
            files_with_no_bill.append(filename)
            continue

        seen_numbers_this_file = set()
        for number, raw_title in matches:
            if number in seen_numbers_this_file:
                continue
            seen_numbers_this_file.add(number)

            entry = bill_index[number]
            entry["bill_number"] = number
            title = clean_title(raw_title)
            # accept titles starting with any of the common formal/informal
            # citation openers; mid-sentence references with no such opener
            # right after the number are excluded since those aren't titles
            valid_starts = ("loi", "sur", "concernant", "relatif", "modifiant",
                             "visant", "édictant", "portant")
            if title and title.strip().lower().startswith(valid_starts) and len(title) > len(entry["title"]):
                entry["title"] = title
            entry["sessions"].append(session_id)
            if date:
                entry["dates"].append(date)

    result = dict(bill_index)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with_title = sum(1 for e in result.values() if e["title"])
    print(f"\nTotal unique bills found: {len(result)}")
    print(f"Bills with confirmed formal title: {with_title}")
    print(f"Bills with number only (no formal citation found): {len(result) - with_title}")
    print(f"Files with no bill mention: {len(files_with_no_bill)} of {len(files)}")
    if files_with_no_bill:
        print("Sample files with no bill mention (first 5):")
        for fn in files_with_no_bill[:5]:
            print(f"  {fn}")

    print(f"\nSaved index to: {OUTPUT_PATH}")
    print("\nSample entries:")
    for number, entry in list(result.items())[:3]:
        print(f"  Bill {number}: {entry['title'][:80]}")
        print(f"    Sessions: {len(entry['sessions'])}, Dates: {entry['dates'][:3]}")


if __name__ == "__main__":
    main()
