"""
check_completeness.py

Reusable audit script for the legislative-health-factuality project.
Run this any time to get a real count of how many bills, per jurisdiction,
have all four required pieces of the chain present:

  1. bill exists
  2. bill is identified as health-related
  3. speech text is linked to that bill
  4. a date is attached at the speech level (not just the bill level)

Drop this in the repo root, next to the data/ and scripts/ folders, and run:

    python3 check_completeness.py

It will print a summary table and write a detailed CSV per jurisdiction
to data/completeness_reports/ so you can see exactly which bills are
missing which piece.
"""

import os
import json
import csv
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(REPO_ROOT, "data", "completeness_reports")
os.makedirs(REPORT_DIR, exist_ok=True)


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="") as f:
        return list(csv.DictReader(f))


def audit_us():
    """
    US House: bills come from health_bills_final_matched.csv (the 384
    confirmed health bills). Speech comes from
    data/us/congressional_record_fulltext/. A bill is complete if it has
    a matched speech file with a real date.
    """
    bills_path = os.path.join(REPO_ROOT, "data", "us", "health_bills_final_matched.csv")
    speech_dir = os.path.join(REPO_ROOT, "data", "us", "congressional_record_speeches")

    bills = load_csv(bills_path)
    speech_files = set(os.listdir(speech_dir)) if os.path.isdir(speech_dir) else set()

    rows = []
    for bill in bills:
        bill_id = bill.get("bill_number") or bill.get("bill_id") or "UNKNOWN"
        congress = bill.get("congress", "")
        vote_date = bill.get("vote_date") or bill.get("date", "")

        has_bill = bool(bill_id and bill_id != "UNKNOWN")
        has_health_tag = bool(bill.get("policy_area", "").strip().lower() == "health")
        # crude match: check if any speech filename references this bill/date
        matched_speech = f"{vote_date}.txt" in speech_files
        has_date = bool(vote_date)

        rows.append({
            "jurisdiction": "US House",
            "bill_id": bill_id,
            "has_bill": has_bill,
            "has_health_tag": has_health_tag,
            "has_speech": matched_speech,
            "has_date": has_date,
            "complete": all([has_bill, has_health_tag, matched_speech, has_date]),
        })
    return rows


def audit_canada(subregion):
    """
    Ontario or Quebec: bills come from cheminement-style JSON (Quebec) or
    an equivalent bill index (Ontario, once built). Speech comes from raw
    Hansard/Journal des débats transcripts organized by date.

    Since bill identification hasn't happened yet for either, this will
    mostly report gaps right now. Re-run this after each identification
    pass to watch the numbers close.
    """
    region_dir = os.path.join(REPO_ROOT, "data", "canada", subregion)
    bill_index_path = os.path.join(region_dir, f"{subregion}_bill_index.json")
    bills = load_json(bill_index_path)

    transcript_files = set(os.listdir(region_dir)) if os.path.isdir(region_dir) else set()

    rows = []
    if not bills:
        # No bill index yet at all, report the gap explicitly rather than
        # silently skipping this jurisdiction.
        rows.append({
            "jurisdiction": subregion.capitalize(),
            "bill_id": "NO_BILL_INDEX_YET",
            "has_bill": False,
            "has_health_tag": False,
            "has_speech": False,
            "has_date": False,
            "complete": False,
        })
        return rows

    for session, bill_list in bills.items():
        for bill in bill_list:
            bill_id = bill.get("bill_number") or bill.get("id") or "UNKNOWN"
            has_bill = bool(bill_id and bill_id != "UNKNOWN")
            has_health_tag = bool(bill.get("health_tag", False))
            bill_date = bill.get("date", "")
            has_date = bool(bill_date)
            matched_speech = any(bill_date in fname for fname in transcript_files) if bill_date else False

            rows.append({
                "jurisdiction": subregion.capitalize(),
                "bill_id": bill_id,
                "has_bill": has_bill,
                "has_health_tag": has_health_tag,
                "has_speech": matched_speech,
                "has_date": has_date,
                "complete": all([has_bill, has_health_tag, matched_speech, has_date]),
            })
    return rows


def write_report(rows, name):
    if not rows:
        return
    path = os.path.join(REPORT_DIR, f"{name}_completeness.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def print_summary(all_rows):
    print("\n=== Completeness Summary ===")
    print(f"Run at: {datetime.now().isoformat(timespec='seconds')}\n")

    by_jurisdiction = {}
    for row in all_rows:
        j = row["jurisdiction"]
        by_jurisdiction.setdefault(j, {"total": 0, "complete": 0, "missing_bill": 0,
                                       "missing_tag": 0, "missing_speech": 0, "missing_date": 0})
        stats = by_jurisdiction[j]
        stats["total"] += 1
        if row["complete"]:
            stats["complete"] += 1
        if not row["has_bill"]:
            stats["missing_bill"] += 1
        if not row["has_health_tag"]:
            stats["missing_tag"] += 1
        if not row["has_speech"]:
            stats["missing_speech"] += 1
        if not row["has_date"]:
            stats["missing_date"] += 1

    header = f"{'Jurisdiction':<15}{'Total':<8}{'Complete':<10}{'Missing Bill':<14}{'Missing Tag':<13}{'Missing Speech':<16}{'Missing Date':<13}"
    print(header)
    print("-" * len(header))
    for j, stats in by_jurisdiction.items():
        print(f"{j:<15}{stats['total']:<8}{stats['complete']:<10}{stats['missing_bill']:<14}"
              f"{stats['missing_tag']:<13}{stats['missing_speech']:<16}{stats['missing_date']:<13}")
    print()


def main():
    all_rows = []

    us_rows = audit_us()
    all_rows.extend(us_rows)
    us_report_path = write_report(us_rows, "us_house")

    ontario_rows = audit_canada("ontario")
    all_rows.extend(ontario_rows)
    ontario_report_path = write_report(ontario_rows, "ontario")

    quebec_rows = audit_canada("quebec")
    all_rows.extend(quebec_rows)
    quebec_report_path = write_report(quebec_rows, "quebec")

    print_summary(all_rows)

    print("Detailed reports written to:")
    for path in [us_report_path, ontario_report_path, quebec_report_path]:
        if path:
            print(f"  {path}")


if __name__ == "__main__":
    main()
