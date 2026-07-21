"""
extract_quebec_pre1994_votes.py

Extracts vote outcomes for pre-1994 Quebec health bills from Assembly
debate transcripts in data/canada/quebec_assembly/transcripts/.

Real format confirmed from transcripts:
  "projet de loi 8... est adopté?\nM. Chevrette:\nAdopté.\nLe Président:\nAdopté."
  "projet de loi 65... est adopté?\nDes voix:\nRejeté.\nLe Président:\nRejeté."

Output: data/canada/quebec_bills/quebec_pre1994_vote_outcomes.json
Usage: python3 scripts/extract_quebec_pre1994_votes.py
"""

import os, re, json
filename = '34-2_1992-1994_015-F.pdf'
m = re.match(r'(\d+)-(\d+)_[\d-]+_(\d+)-F\.pdf', filename)
if m:
    session = f"{m.group(1)}-{m.group(2)}"
    bill_number = str(int(m.group(3)))  # strip leading zeros
    print(session, bill_number)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE1994_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills", "pre1994_health_bills.json")
TRANSCRIPTS_DIR = os.path.join(REPO_ROOT, "data", "canada", "quebec_assembly", "transcripts")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills", "quebec_pre1994_vote_outcomes.json")

SESSION_YEAR_RANGES = {
    "33-1": ("1985", "1988"),
    "33-2": ("1988", "1989"),
    "34-1": ("1989", "1992"),
    "34-2": ("1992", "1994"),
    "34-3": ("1994", "1994"),
}

BILL_REF = re.compile(
    r"(?:projet\s+de\s+loi\s+(?:n[o°]?\s*)?|loi\s+(?:portant\s+le\s+num[eé]ro\s+)?|loi\s+n[o°]\s*)(\d+)",
    re.IGNORECASE
)
PRES_ADOPTED = re.compile(r"Le Pr[eé]sident[^\n]*\nAdopt[eé]", re.IGNORECASE)
PRES_REJECTED = re.compile(r"Le Pr[eé]sident[^\n]*\nRejet[eé]", re.IGNORECASE)


def get_transcripts_for_session(session):
    if session not in SESSION_YEAR_RANGES or not os.path.isdir(TRANSCRIPTS_DIR):
        return []
    start_year, end_year = SESSION_YEAR_RANGES[session]
    return sorted(
        os.path.join(TRANSCRIPTS_DIR, f)
        for f in os.listdir(TRANSCRIPTS_DIR)
        if f.endswith(".txt") and start_year <= f[:4] <= end_year
    )


def search_bill(bill_number, session):
    results = []
    for fpath in get_transcripts_for_session(session):
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            continue
        date = os.path.basename(fpath).replace(".txt", "")
        
        # check if bill appears in this file at all
        bill_pattern = rf"(?:projet\s+de\s+loi|loi)\s+(?:n[o°]?\s*)?{re.escape(bill_number)}\b"
        if not re.search(bill_pattern, text, re.IGNORECASE):
            continue
        
        # check if adoption/rejection appears anywhere in same file
        if PRES_ADOPTED.search(text):
            results.append({"date": date, "outcome": "passed",
                           "context": "file-level match"})
        elif PRES_REJECTED.search(text):
            results.append({"date": date, "outcome": "failed",
                           "context": "file-level match"})
    return results


def main():
    with open(PRE1994_PATH, encoding="utf-8") as f:
        bills = json.load(f)

    files = [f for f in os.listdir(TRANSCRIPTS_DIR) if f.endswith(".txt")] if os.path.isdir(TRANSCRIPTS_DIR) else []
    print(f"Processing {len(bills)} pre-1994 health bills")
    print(f"Transcript files available: {len(files)}\n")

    results = {}
    passed = failed = not_found = 0

    for bill in bills:
        filename = bill.get("filename", "")
        fm = re.match(r"(\d+)-(\d+)_[\d-]+_(\d+)-F\.pdf", filename)
        if not fm:
            not_found += 1
            continue
        session = f"{fm.group(1)}-{fm.group(2)}"
        num = str(int(fm.group(3)))  # strip leading zeros
        title = bill.get("description", "")[:60]
        hits = search_bill(num, session)

        if hits:
            final = hits[-1]
            outcome = final["outcome"]
            passed += (outcome == "passed")
            failed += (outcome == "failed")
            results[f"{session}-Bill{num}"] = {
                "bill_number": num, "session": session, "title": bill.get("title",""),
                "outcome": outcome, "vote_date": final["date"],
                "context": final["context"], "total_hits": len(hits),
            }
            print(f"  {session} Bill {num}: {outcome} ({final['date']}) | {title}")
        else:
            not_found += 1
            results[f"{session}-Bill{num}"] = {
                "bill_number": num, "session": session, "title": bill.get("title",""),
                "outcome": None, "vote_date": None,
            }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Pre-1994 bills: {len(bills)} | Passed: {passed} | Failed: {failed} | Not found: {not_found}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
