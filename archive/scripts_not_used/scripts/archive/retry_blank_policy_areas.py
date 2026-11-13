# retry_blank_policy_areas.py
# One-time cleanup script to re-check bills that came back blank in
# fetch_policy_areas.py due to transient API failures during the original run.
# fetch_policy_areas.py caches empty strings for any failed request, which makes
# it impossible to distinguish a genuine API absence from a network timeout.
# This script retries only the blank entries and correctly marks bills that truly
# have no policy area as "NONE_CONFIRMED" rather than leaving them empty, so
# future runs of match_by_policy_area.py do not silently drop real health bills
# that just had a bad connection moment.
# Run this after any full fetch_policy_areas.py run that produces blank entries.
# After two passes on the original 10,430 bills, only 2 entries remained blank,
# both confirmed as real API gaps rather than transient failures.

import json
import os
import re
import time
import requests
from dotenv import load_dotenv

# Loading the Congress.gov API key from .env
load_dotenv()
KEY = os.getenv("CONGRESS_KEY")

# The same cache file that fetch_policy_areas.py writes to
# This script reads it, finds the blanks, fixes them, and writes back
CACHE_PATH = "data/us/policy_areas.json"

def parse_bill(bill_number):
    # Breaking the bill number into type prefix and numeric part
    # so we can build the correct Congress.gov API URL
    match = re.match(r"^([A-Z]+)(\d+)$", bill_number)
    if not match:
        return None, None
    return match.group(1).lower(), match.group(2)

def get_policy_area(congress, bill_type, bill_number):
    # Calling the Congress.gov subjects endpoint for this bill
    # Returns the policy area name if found, "NONE_CONFIRMED" if the bill
    # genuinely has no policy area assigned, or None if the request itself failed
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/subjects"
    params = {"api_key": KEY, "format": "json"}
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            policy_area = data.get("subjects", {}).get("policyArea")
            if policy_area is None:
                # Bill exists but CRS has not assigned it a policy area
                return "NONE_CONFIRMED"
            return policy_area.get("name", "NONE_CONFIRMED")
        # Non-200 status means the request failed, leave blank and try again next run
        return None
    except requests.RequestException:
        # Network error, leave blank and try again next run
        return None

if __name__ == "__main__":
    # Loading the existing cache and finding all entries that came back blank
    with open(CACHE_PATH) as f:
        cache = json.load(f)

    blanks = [k for k, v in cache.items() if v == ""]
    print(f"Retrying {len(blanks)} blank entries...")

    fixed = 0
    still_failed = 0
    for i, key in enumerate(blanks):
        congress, bill_number = key.split("_", 1)
        bill_type, number = parse_bill(bill_number)

        # If the bill number format is unrecognizable, mark it confirmed empty
        if not bill_type:
            cache[key] = "NONE_CONFIRMED"
            continue

        result = get_policy_area(congress, bill_type, number)

        if result is None:
            # Request failed again, leave blank so this script can be rerun
            still_failed += 1
            continue

        cache[key] = result
        fixed += 1

        # Saving progress to disk every 50 entries in case of interruption
        if (i + 1) % 50 == 0:
            print(f"Processed {i+1}/{len(blanks)}, fixed {fixed} so far, {still_failed} still failing")
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f, indent=2)

        # Pausing between requests to respect Congress.gov's rate limits
        time.sleep(0.75)

    # Final save once all blanks have been attempted
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"Done. Fixed {fixed}, still failing {still_failed}")