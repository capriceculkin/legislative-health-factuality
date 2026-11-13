# match_by_policy_area.py
# The final matching step in the US pipeline. Reads the VoteView rollcalls file
# and the policy_areas.json cache built by fetch_policy_areas.py, then filters
# down to only the roll call votes where the bill's official CRS policy area
# is "Health." Produces the final matched dataset used for analysis.
# Output: data/us/health_bills_final_matched.csv
# Result: 384 unique health bills, 663 total vote events, 1985 to present.
# Note: VoteView only contains recorded roll call votes, not voice votes or
# unanimous consent votes. Bills that passed without a recorded tally are not
# in this dataset and cannot be added since no individual vote record was ever
# created. For this project's research question, that is the right population
# since a voice vote has no real winning or losing side to measure.

import csv
import json

# Reading the full VoteView rollcalls file, one row per recorded vote
ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"

# Reading the policy area cache built by fetch_policy_areas.py
# Each key is formatted as "{congress}_{bill_number}" to avoid collisions
# across Congresses where the same bill number refers to different bills
POLICY_AREAS_PATH = "data/us/policy_areas.json"

# Where the final matched health bill votes will be saved
OUTPUT_PATH = "data/us/health_bills_final_matched.csv"

if __name__ == "__main__":
    # Loading the full policy area lookup table into memory
    with open(POLICY_AREAS_PATH) as f:
        policy_areas = json.load(f)

    matched = []
    with open(ROLLCALLS_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            congress = row.get("congress", "").strip()
            bill = row.get("bill_number", "").strip()

            # Building the same key format used in fetch_policy_areas.py
            # so the lookup works correctly across Congress boundaries
            key = f"{congress}_{bill}"
            policy_area = policy_areas.get(key, "")

            # Keeping only votes where the CRS officially classified the bill as Health
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

    # Writing the final matched dataset to CSV
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "congress", "rollnumber", "date", "bill_number", "policy_area",
            "result", "vote_desc", "dtl_desc", "yea_count", "nay_count"
        ])
        writer.writeheader()
        writer.writerows(matched)

    print(f"Matched {len(matched)} health-policy-area votes across 1985-present")
    print(f"Saved to {OUTPUT_PATH}")