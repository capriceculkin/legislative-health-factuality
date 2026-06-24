import csv
import json

ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"
POLICY_AREAS_PATH = "data/us/policy_areas.json"
OUTPUT_PATH = "data/us/health_bills_final_matched.csv"

if __name__ == "__main__":
    with open(POLICY_AREAS_PATH) as f:
        policy_areas = json.load(f)

    matched = []
    with open(ROLLCALLS_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            congress = row.get("congress", "").strip()
            bill = row.get("bill_number", "").strip()
            key = f"{congress}_{bill}"
            policy_area = policy_areas.get(key, "")
            if policy_area == "Health":
                matched.append({
                    "congress": congress,
                    "rollnumber": row.get("rollnumber"),
                    "date": row.get("date"),
                    "bill_number": bill,
                    "policy_area": policy_area,
                    "result": row.get("vote_result", ""),
                    "vote_desc": row.get("vote_desc", ""),
                    "dtl_desc": row.get("dtl_desc", ""),
                    "yea_count": row.get("yea_count"),
                    "nay_count": row.get("nay_count"),
                })

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "congress", "rollnumber", "date", "bill_number", "policy_area",
            "result", "vote_desc", "dtl_desc", "yea_count", "nay_count"
        ])
        writer.writeheader()
        writer.writerows(matched)

    print(f"Matched {len(matched)} health-policy-area votes across 1985-present")
    print(f"Saved to {OUTPUT_PATH}")