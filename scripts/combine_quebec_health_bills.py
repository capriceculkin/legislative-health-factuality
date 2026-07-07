# combine_quebec_health_bills.py
# Combines three sources of Quebec health bills into one unified list:
# 1. Pre-1994 bills from Bibliotheque full-text search (1985-1994)
# 2. Post-1994 bills from Cheminement keyword and committee filter (1994-2026)
# Both source files are preserved unchanged.
# Output: data/canada/quebec_bills/quebec_health_bills_combined.json

import json
import re

PRE1994_PATH = "data/canada/quebec_bills/pre1994_health_bills.json"
POST1994_PATH = "data/canada/quebec_bills/quebec_health_bills.json"
OUTPUT_PATH = "data/canada/quebec_bills/quebec_health_bills_combined.json"

def parse_session_from_filename(filename):
    # Extracting session code from filenames like 33-1_1985-1988_075-F.pdf
    match = re.match(r"(\d+)-(\d+)_", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return ""

def parse_bill_number_from_filename(filename):
    # Pattern: 33-1_1985-1988_092(1986)-F.pdf or 34-3_1994_017-F.pdf
    # Bill number is the last numeric segment before -F or -A
    match = re.search(r"_(\d{2,3})\(?", filename)
    if match:
        return str(int(match.group(1)))
    return ""

if __name__ == "__main__":
    combined = []
    seen = set()

    # Loading pre-1994 bills from Bibliotheque search
    with open(PRE1994_PATH) as f:
        pre1994 = json.load(f)

    print(f"Pre-1994 bills: {len(pre1994)}")
    for bill in pre1994:
        filename = bill.get("filename", "")
        key = filename  # use full filename as unique key
        if key not in seen:
            seen.add(key)
            session = parse_session_from_filename(filename)
            bill_number = parse_bill_number_from_filename(filename)
            combined.append({
                "source": "bibliotheque_pre1994",
                "session": session,
                "bill_number": bill_number,
                "filename": filename,
                "title": bill.get("description", "")[:150],
            })

    # Loading post-1994 bills from Cheminement filter
    with open(POST1994_PATH) as f:
        post1994 = json.load(f)

    print(f"Post-1994 Cheminement bills: {len(post1994)}")
    for bill in post1994:
        session = bill.get("session", "")
        title = bill.get("title", "")
        bill_number = re.search(r"n°\s*(\d+)", title)
        bill_number = bill_number.group(1) if bill_number else ""
        key = f"{session}_{bill_number}"
        if key not in seen:
            seen.add(key)
            combined.append({
                "source": "cheminement_post1994",
                "session": session,
                "bill_number": bill_number,
                "title": title[:150],
                "assembly_debates": bill.get("assembly_debates", []),
                "committee_debates": bill.get("committee_debates", []),
            })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    print(f"\nTotal combined health bills: {len(combined)}")
    print(f"  Pre-1994: {sum(1 for b in combined if b['source'] == 'bibliotheque_pre1994')}")
    print(f"  Post-1994: {sum(1 for b in combined if b['source'] == 'cheminement_post1994')}")
    print(f"Saved to {OUTPUT_PATH}")