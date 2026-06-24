import csv
import json
import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")

INPUT_PATH = "data/us/unique_voted_bills.csv"
CACHE_PATH = "data/us/policy_areas.json"

def parse_bill(bill_number):
    match = re.match(r"^([A-Z]+)(\d+)$", bill_number)
    if not match:
        return None, None
    return match.group(1).lower(), match.group(2)

def get_policy_area(congress, bill_type, bill_number):
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/subjects"
    params = {"api_key": KEY, "format": "json"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            policy_area = data.get("subjects", {}).get("policyArea", {})
            return policy_area.get("name", "")
        return ""
    except requests.RequestException:
        return ""

if __name__ == "__main__":
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            cache = json.load(f)

    rows = []
    with open(INPUT_PATH) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Total bills to check: {len(rows)}")
    checked = 0
    for row in rows:
        congress = row["congress"]
        bill_number = row["bill_number"]
        key = f"{congress}_{bill_number}"

        if key in cache:
            continue

        bill_type, number = parse_bill(bill_number)
        if not bill_type:
            cache[key] = ""
            continue

        policy_area = get_policy_area(congress, bill_type, number)
        cache[key] = policy_area
        checked += 1

        if checked % 50 == 0:
            print(f"Checked {checked} new bills so far...")
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f, indent=2)

        time.sleep(0.75)

    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"Done. Policy areas saved to {CACHE_PATH}")