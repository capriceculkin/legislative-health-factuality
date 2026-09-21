"""
build_ontario_bill_index.py

Extracts bill citations from every Ontario Hansard transcript in
data/canada/ontario/. Bills are keyed by actual parliament-session
(e.g. "33-1-Bill94") instead of 4-year era buckets, which caused
bill number collisions across parliaments.

Parliament-session boundaries sourced from OLA records.

Output: data/canada/ontario/ontario_bill_index.json
"""

import os
import re
import json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONTARIO_DIR = os.path.join(REPO_ROOT, "data", "canada", "ontario")
OUTPUT_PATH = os.path.join(ONTARIO_DIR, "ontario_bill_index.json")

BILL_PATTERN = re.compile(
    r"Bill\s+(\d+)\s*,\s*(An Act[^\n.;]{0,250})",
    re.IGNORECASE
)

BARE_PATTERN = re.compile(r"Bill\s+(\d+)\b")

HEALTH_KEYWORDS = [
    "health", "hospital", "medic", "nurs", "mental", "long-term care",
    "public health", "ambulance", "pharma", "drug", "physician",
    "patient", "disease", "cancer", "tobacco", "smoking", "addiction",
    "disability", "midwif", "dental", "ohip", "home care",
]

# Exact parliament-session boundaries from OLA records
PARLIAMENT_SESSIONS = {
    "29-4": ("1975-10-28", "1977-03-08"),
    "29-5": ("1977-03-09", "1977-09-14"),
    "30-1": ("1977-10-18", "1978-12-15"),
    "30-2": ("1979-03-12", "1980-02-07"),
    "30-3": ("1980-03-10", "1981-03-26"),
    "30-4": ("1981-03-27", "1981-11-19"),
    "31-1": ("1981-11-23", "1982-12-16"),
    "31-2": ("1983-03-14", "1984-03-08"),
    "31-3": ("1984-03-26", "1984-06-21"),
    "31-4": ("1984-10-22", "1985-02-07"),
    "32-1": ("1985-02-11", "1985-05-01"),
    "33-1": ("1985-05-02", "1985-10-31"),
    "33-2": ("1985-11-18", "1986-10-06"),
    "33-3": ("1986-11-17", "1987-09-08"),
    "34-1": ("1987-10-01", "1988-12-16"),
    "34-2": ("1989-03-20", "1990-08-30"),
    "35-1": ("1990-11-20", "1991-12-19"),
    "35-2": ("1992-04-06", "1993-06-17"),
    "35-3": ("1993-11-15", "1995-02-09"),
    "36-1": ("1995-09-26", "1997-12-18"),
    "36-2": ("1998-03-23", "1998-12-10"),
    "36-3": ("1999-03-15", "1999-10-18"),
    "37-1": ("1999-10-25", "2001-12-20"),
    "37-2": ("2002-03-18", "2002-12-19"),
    "37-3": ("2003-03-17", "2003-09-18"),
    "38-1": ("2003-12-09", "2004-12-16"),
    "38-2": ("2005-02-28", "2007-10-01"),
    "39-1": ("2007-10-17", "2008-12-18"),
    "39-2": ("2009-03-02", "2011-10-06"),
    "40-1": ("2011-11-30", "2012-12-20"),
    "40-2": ("2013-02-19", "2014-05-02"),
    "41-1": ("2014-07-02", "2015-12-10"),
    "41-2": ("2016-02-22", "2017-12-07"),
    "41-3": ("2018-03-19", "2018-05-09"),
    "42-1": ("2018-07-11", "2019-12-12"),
    "42-2": ("2020-02-18", "2022-05-04"),
    "43-1": ("2022-08-08", "2024-12-12"),
    "44-1": ("2025-04-14", "2099-12-31"),
}


def date_to_session(date_str):
    """Map a date string to its parliament-session code."""
    for session, (start, end) in PARLIAMENT_SESSIONS.items():
        if start <= date_str <= end:
            return session
    return None


def health_tag_from_title(title):
    t = title.lower()
    return any(kw in t for kw in HEALTH_KEYWORDS)


def main():
    bill_index = {}
    files = sorted(f for f in os.listdir(ONTARIO_DIR) if f.endswith(".txt"))
    print(f"Scanning {len(files)} Ontario Hansard files...")

    files_with_no_bill = 0
    no_session = 0

    for filename in files:
        date = filename.replace(".txt", "")
        session = date_to_session(date)
        if not session:
            no_session += 1
            continue

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
            key = f"{session}-Bill{number}"
            title = re.sub(r"\s+", " ", raw_title).strip()
            # Truncate at first comma to get short title only
            short_title = title.split(",")[0].strip()
            entry = bill_index.setdefault(key, {
                "bill_number": number,
                "session": session,
                "title": "",
                "short_title": "",
                "health_tag": False,
                "dates": [],
            })
            if len(title) > len(entry["title"]):
                entry["title"] = title
                entry["short_title"] = short_title
                entry["health_tag"] = health_tag_from_title(title)
            if date not in entry["dates"]:
                entry["dates"].append(date)
            seen_this_file.add(number)

        for number in bare:
            if number in seen_this_file:
                continue
            seen_this_file.add(number)
            key = f"{session}-Bill{number}"
            entry = bill_index.setdefault(key, {
                "bill_number": number,
                "session": session,
                "title": "",
                "short_title": "",
                "health_tag": False,
                "dates": [],
            })
            if date not in entry["dates"]:
                entry["dates"].append(date)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(bill_index, f, ensure_ascii=False, indent=2)

    total = len(bill_index)
    with_title = sum(1 for e in bill_index.values() if e["title"])
    health = sum(1 for e in bill_index.values() if e["health_tag"])

    print(f"\nTotal unique bills (session-scoped): {total}")
    print(f"Bills with formal title: {with_title}")
    print(f"Bills health-tagged: {health}")
    print(f"Files with no session mapping: {no_session}")
    print(f"Files with no bill mention: {files_with_no_bill}")
    print(f"\nSaved to: {OUTPUT_PATH}")

    print("\nSample health-tagged bills:")
    shown = 0
    for key, entry in bill_index.items():
        if entry["health_tag"] and shown < 5:
            print(f"  {key}: {entry['short_title'][:60]}")
            print(f"    Dates: {entry['dates'][:3]}")
            shown += 1


if __name__ == "__main__":
    main()

