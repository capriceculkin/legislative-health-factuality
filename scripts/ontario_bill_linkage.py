# ontario_bill_linkage.py
# Scans Ontario Hansard transcripts for explicit bill number references
# and tags each passage with the bill number it mentions.
# This is the bill-linkage step needed before health-relevant passages
# can be filtered from the raw sitting-day transcripts.
# Output: data/canada/ontario_bill_passages.json
# Each entry contains the date, the bill number referenced, and the
# surrounding text passage for use in factuality scoring later.

import os
import re
import json

INPUT_DIR = "data/canada/ontario"
OUTPUT_PATH = "data/canada/ontario_bill_passages.json"

# Patterns for Ontario bill number references in English Hansard text
# Ontario uses "Bill 123" or "Bill No. 123" consistently
BILL_PATTERN = re.compile(r'\bBill\s+(?:No\.?\s+)?(\d+)\b', re.IGNORECASE)

# How many characters of context to capture around each bill mention
CONTEXT_WINDOW = 500

def extract_passages(text, date):
    passages = []
    for match in BILL_PATTERN.finditer(text):
        bill_number = match.group(1)
        start = max(0, match.start() - CONTEXT_WINDOW)
        end = min(len(text), match.end() + CONTEXT_WINDOW)
        passage = text[start:end].strip()
        passages.append({
            "date": date,
            "bill_number": bill_number,
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

    print(f"Done. {len(all_passages)} bill passages extracted from {total} sitting days.")
    print(f"Saved to {OUTPUT_PATH}")