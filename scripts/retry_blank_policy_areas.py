import json
import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")
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
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            policy_area = data.get("subjects", {}).get("policyArea")
            if policy_area is None:
                return "NONE_CONFIRMED"  # genuinely has no policy area
            return policy_area.get("name", "NONE_CONFIRMED")
        return None  # request failed, retry later
    except requests.RequestException:
        return None  # request failed, retry later

if __name__ == "__main__":
    with open(CACHE_PATH) as f:
        cache = json.load(f)

    blanks = [k for k, v in cache.items() if v == ""]
    print(f"Retrying {len(blanks)} blank entries...")

    fixed = 0
    still_failed = 0
    for i, key in enumerate(blanks):
        congress, bill_number = key.split("_", 1)
        bill_type, number = parse_bill(bill_number)
        if not bill_type:
            cache[key] = "NONE_CONFIRMED"
            continue

        result = get_policy_area(congress, bill_type, number)
        if result is None:
            still_failed += 1
            continue  # leave as blank, try again next run
        cache[key] = result
        fixed += 1

        if (i + 1) % 50 == 0:
            print(f"Processed {i+1}/{len(blanks)}, fixed {fixed} so far, {still_failed} still failing")
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f, indent=2)

        time.sleep(0.75)

    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"Done. Fixed {fixed}, still failing {still_failed}")