# ontario_bill_linkage.py
# Scans Ontario Hansard transcripts for explicit bill number references
# and tags each passage with the bill number AND the session year it came from.
# This is critical because Ontario bill numbers reset every session, meaning
# Bill 2 in 1985 and Bill 2 in 2010 are completely unrelated pieces of legislation.
# By storing the year alongside the bill number (e.g. "1985_2"), each bill
# reference becomes unique across the full 40-year dataset.
# Output: data/canada/ontario_bill_passages.json

import os
import re
import json

INPUT_DIR = "data/canada/ontario"
OUTPUT_PATH = "data/canada/ontario_bill_passages.json"

BILL_PATTERN = re.compile(r'\bBill\s+(?:No\.?\s+)?(\d+)\b', re.IGNORECASE)

CONTEXT_WINDOW = 500

def extract_year(date_str):
    # Date filenames are formatted as YYYY-MM-DD
    return date_str[:4]

def extract_passages(text, date):
    year = extract_year(date)
    passages = []
    for match in BILL_PATTERN.finditer(text):
        bill_number = match.group(1)
        # Scoping the bill number to the year it appeared
        # so 1985 Bill 2 and 2010 Bill 2 are treated as different bills
        scoped_id = f"{year}_{bill_number}"
        start = max(0, match.start() - CONTEXT_WINDOW)
        end = min(len(text), match.end() + CONTEXT_WINDOW)
        passage = text[start:end].strip()
        passages.append({
            "date": date,
            "year": year,
            "bill_number": bill_number,
            "scoped_bill_id": scoped_id,
            "passage": passage,
        })
    return passages

if __name__ == "__main__":
    all_passages = []
    files = sorted(os.listdir(INPUT_DIR))
    total = len(files)

    for i, filename in enumerate(files):
        if not filename.endswith(".txt"):
            continue
        date = filename.replace(".txt", "")
        filepath = os.path.join(INPUT_DIR, filename)
        with open(filepath, encoding="utf-8") as f:
            text = f.read()
        passages = extract_passages(text, date)
        all_passages.extend(passages)

        if (i + 1) % 200 == 0:
            print(f"Processed {i+1}/{total} files, {len(all_passages)} passages so far...")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_passages, f, indent=2, ensure_ascii=False)

    print(f"Done. {len(all_passages)} passages extracted from {total} sitting days.")
    print(f"Saved to {OUTPUT_PATH}")