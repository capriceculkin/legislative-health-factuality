"""
fix_quebec_pre1994_votes.py

Fixes the 29 Quebec pre-1994 bills where the adoption vote occurred on a
different sitting day than the last debate mention. Searches a 30-day window
AFTER each bill's last mention in transcripts for the adoption confirmation.

Usage: python3 scripts/fix_quebec_pre1994_votes.py
"""

import os, re, json
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTCOMES_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                              "quebec_pre1994_vote_outcomes.json")
TRANSCRIPTS_DIR = os.path.join(REPO_ROOT, "data", "canada", "quebec_assembly", "transcripts")

SESSION_YEARS = {
    "33-1": ("1985","1988"), "33-2": ("1988","1989"),
    "34-1": ("1989","1992"), "34-2": ("1992","1994"), "34-3": ("1994","1994"),
}

BILL_REF    = re.compile(r"(?:projet\s+de\s+loi|loi)\s+(?:n[o\xb0]?\s*)?(\d+)\b", re.IGNORECASE)
PRES_ADOPTED = re.compile(r"Le Pr[eé]sident[^\n]*\nAdopt[eé]", re.IGNORECASE)
PRES_REJECTED = re.compile(r"Le Pr[eé]sident[^\n]*\nRejet[eé]", re.IGNORECASE)


def get_session_files(session):
    if session not in SESSION_YEARS or not os.path.isdir(TRANSCRIPTS_DIR):
        return []
    start, end = SESSION_YEARS[session]
    return sorted(
        f for f in os.listdir(TRANSCRIPTS_DIR)
        if f.endswith(".txt") and start <= f[:4] <= end
    )


def find_last_mention(bill_number, session):
    """Find the last transcript file that mentions this bill."""
    last_file = None
    for fname in get_session_files(session):
        fpath = os.path.join(TRANSCRIPTS_DIR, fname)
        with open(fpath, encoding="utf-8", errors="replace") as f:
            text = f.read()
        pat = rf"(?:projet\s+de\s+loi|loi)\s+(?:n[o\xb0]?\s*)?{re.escape(bill_number)}\b"
        if re.search(pat, text, re.IGNORECASE):
            last_file = fname
    return last_file


def search_after_last_mention(bill_number, session, last_file, days_window=45):
    """Search transcript files in the N days after last_file for adoption confirmation."""
    if not last_file:
        return None, None

    try:
        last_date = datetime.strptime(last_file.replace(".txt",""), "%Y%m%d")
    except ValueError:
        return None, None

    cutoff = last_date + timedelta(days=days_window)
    start, end = SESSION_YEARS.get(session, ("1985","1994"))

    for fname in get_session_files(session):
        try:
            fdate = datetime.strptime(fname.replace(".txt",""), "%Y%m%d")
        except ValueError:
            continue
        if fdate <= last_date or fdate > cutoff:
            continue

        fpath = os.path.join(TRANSCRIPTS_DIR, fname)
        with open(fpath, encoding="utf-8", errors="replace") as f:
            text = f.read()

        if PRES_ADOPTED.search(text):
            return "passed", fname.replace(".txt","")
        if PRES_REJECTED.search(text):
            return "failed", fname.replace(".txt","")

    return None, None


def main():
    with open(OUTCOMES_PATH, encoding="utf-8") as f:
        outcomes = json.load(f)

    not_found = {k: v for k, v in outcomes.items() if not v.get("outcome")}
    print(f"Not found bills to investigate: {len(not_found)}")

    fixed = 0
    for key, v in not_found.items():
        num = v["bill_number"]
        session = v["session"]

        last_file = find_last_mention(num, session)
        if not last_file:
            print(f"  {key}: never found in transcripts")
            continue

        outcome, vote_date = search_after_last_mention(num, session, last_file)
        if outcome:
            outcomes[key]["outcome"] = outcome
            outcomes[key]["vote_date"] = vote_date
            outcomes[key]["context"] = f"Found in window after {last_file}"
            fixed += 1
            print(f"  {key}: {outcome} on {vote_date} (was in {last_file})")
        else:
            print(f"  {key}: last mention {last_file}, no adoption found in 45-day window")

    with open(OUTCOMES_PATH, "w", encoding="utf-8") as f:
        json.dump(outcomes, f, ensure_ascii=False, indent=2)

    passed = sum(1 for v in outcomes.values() if v.get("outcome") == "passed")
    failed = sum(1 for v in outcomes.values() if v.get("outcome") == "failed")
    still_none = sum(1 for v in outcomes.values() if not v.get("outcome"))

    print(f"\n{'='*60}")
    print(f"Fixed this run: {fixed}")
    print(f"Final totals - Passed: {passed} | Failed: {failed} | Unknown: {still_none}")
    print(f"Saved to: {OUTCOMES_PATH}")


if __name__ == "__main__":
    main()
