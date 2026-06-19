import json
import re

LEGISCAN_PATH = "data/us/legiscan_health_search.json"
VOTES_PATH = "data/us/house_votes_all.json"
OUTPUT_PATH = "data/us/health_bill_votes_matched.json"

def load_health_bill_numbers():
    with open(LEGISCAN_PATH) as f:
        data = json.load(f)
    results = data.get("searchresult", {})
    health_bills = set()
    for key, bill in results.items():
        if key == "summary":
            continue
        bn = bill.get("bill_number", "")
        match = re.match(r"([A-Z]+)(\d+)", bn)
        if match:
            bill_type = match.group(1)
            bill_num = match.group(2)
            health_bills.add((bill_type, bill_num))
    return health_bills

def load_votes():
    with open(VOTES_PATH) as f:
        data = json.load(f)
    return data if isinstance(data, list) else []

TYPE_MAP = {
    "HB": "HR",       # LegiScan House Bill -> Congress.gov House Bill
    "HR": "HRES",      # LegiScan House Resolution -> Congress.gov House Resolution
    "HJR": "HJRES",
    "HCR": "HCONRES",
    "SB": "S",         # LegiScan Senate Bill -> Congress.gov Senate Bill
    "SR": "SRES",
    "SJR": "SJRES",
    "SCR": "SCONRES",
}

if __name__ == "__main__":
    health_bills = load_health_bill_numbers()
    votes = load_votes()
    print(f"Loaded {len(health_bills)} health bill identifiers")
    print(f"Loaded {len(votes)} votes")

    matched = []
    for vote in votes:
        v_type = vote.get("legislationType", "")
        v_num = vote.get("legislationNumber", "")
        for bill_type, bill_num in health_bills:
            mapped_type = TYPE_MAP.get(bill_type, bill_type)
            if mapped_type == v_type and bill_num == v_num:
                matched.append(vote)
                break

    with open(OUTPUT_PATH, "w") as f:
        json.dump(matched, f, indent=2)
    print(f"Matched {len(matched)} votes to health bills, saved to {OUTPUT_PATH}")