import json
import csv
import re

LEGISCAN_PATH = "data/us/legiscan_health_search.json"
ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"
OUTPUT_PATH = "data/us/health_bills_voteview_matched.csv"

LEGISCAN_CONGRESS = "119"

TYPE_MAP = {
    "HB": "HR",
    "HR": "HRES",
    "HJR": "HJRES",
    "HCR": "HCONRES",
    "SB": "S",
    "SR": "SRES",
    "SJR": "SJRES",
    "SCR": "SCONRES",
}

def load_legiscan_bills():
    with open(LEGISCAN_PATH) as f:
        data = json.load(f)
    results = data.get("searchresult", {})
    bills = {}
    RELEVANCE_THRESHOLD = 90
    for key, bill in results.items():
        if key == "summary":
            continue
        if bill.get("relevance", 0) < RELEVANCE_THRESHOLD:
            continue
        bn = bill.get("bill_number", "")
        match = re.match(r"([A-Z]+)(\d+)", bn)
        if match:
            prefix, number = match.group(1), match.group(2)
            mapped_type = TYPE_MAP.get(prefix, prefix)
            vv_key = f"{mapped_type}{number}"
            bills[vv_key] = bill
    return bills

def parse_result_from_desc(dtl_desc):
    if not dtl_desc:
        return ""
    match = re.search(r"\((?:MOTION )?(PASSED|FAILED|AGREED TO|REJECTED)\)", dtl_desc, re.IGNORECASE)
    return match.group(1).title() if match else ""

if __name__ == "__main__":
    health_bills = load_legiscan_bills()
    print(f"Loaded {len(health_bills)} health bills (VoteView-style keys)")

    matched = []
    with open(ROLLCALLS_PATH) as f:
        reader = csv.DictReader(f)
        total_rows = 0
        for row in reader:
            total_rows += 1
            vv_bill = row.get("bill_number", "").strip()
            if vv_bill and vv_bill in health_bills and row.get("congress") == LEGISCAN_CONGRESS:
                result = row.get("vote_result", "").strip()
                if not result:
                    result = parse_result_from_desc(row.get("dtl_desc", ""))
                matched.append({
                    "congress": row.get("congress"),
                    "rollnumber": row.get("rollnumber"),
                    "date": row.get("date"),
                    "bill_number": vv_bill,
                    "title": health_bills[vv_bill].get("title", ""),
                    "result": result,
                    "vote_desc": row.get("vote_desc", ""),
                    "yea_count": row.get("yea_count"),
                    "nay_count": row.get("nay_count"),
                })

    print(f"Checked {total_rows} total roll calls (1985-present)")
    print(f"Matched {len(matched)} health bill votes")

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "congress", "rollnumber", "date", "bill_number", "title",
            "result", "vote_desc", "yea_count", "nay_count"
        ])
        writer.writeheader()
        writer.writerows(matched)

    print(f"Saved to {OUTPUT_PATH}")
    