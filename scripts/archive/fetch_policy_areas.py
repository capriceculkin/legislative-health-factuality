# fetch_policy_areas.py
# For every unique bill that had a recorded vote (from unique_voted_bills.csv),
# this script calls Congress.gov's subjects API and saves the official CRS policy
# area classification to a local cache file (policy_areas.json).
# Congress.gov assigns every bill exactly one policy area, chosen by a human CRS
# analyst from a controlled vocabulary used consistently since 1979. This is the
# core fix replacing LegiScan's keyword relevance score, which was producing
# false positives like the National Defense Authorization Act showing up as a
# health bill because the word appeared once in 900 pages of text.
# This script takes several hours to run against all 10,430 bills. It saves
# progress every 50 bills so it can be safely interrupted and resumed without
# losing work. If a bill comes back blank due to a transient API failure,
# run retry_blank_policy_areas.py afterward to clean those up.

import csv
import json
import os
import re
import time
import requests
from dotenv import load_dotenv

# Loading the Congress.gov API key from .env
load_dotenv()
KEY = os.getenv("CONGRESS_KEY")

# Reading the list of unique bills to check
INPUT_PATH = "data/us/unique_voted_bills.csv"

# Saving results to a cache file so progress is preserved between runs
CACHE_PATH = "data/us/policy_areas.json"

def parse_bill(bill_number):
    # Breaking the bill number into its type prefix and numeric part
    # so we can build the correct Congress.gov API URL
    # e.g. "HR402" becomes bill_type="hr", number="402"
    match = re.match(r"^([A-Z]+)(\d+)$", bill_number)
    if not match:
        return None, None
    return match.group(1).lower(), match.group(2)

def get_policy_area(congress, bill_type, bill_number):
    # Calling the Congress.gov subjects endpoint for this specific bill
    # The response includes both the single policy area and any legislative subject terms
    # We only want the policy area, which is the one authoritative top-level category
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
        # Returning empty string on failure, which retry_blank_policy_areas.py
        # will come back and fix in a second pass
        return ""

if __name__ == "__main__":
    # Loading any already-cached results so we don't re-fetch bills already checked
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            cache = json.load(f)

    # Reading the full list of unique bills to check
    rows = []
    with open(INPUT_PATH) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Total bills to check: {len(rows)}")
    checked = 0
    for row in rows:
        congress = row["congress"]
        bill_number = row["bill_number"]

        # Keying by congress + bill number together because bill numbers reset
        # every two years, so the same number in different Congresses means
        # completely different bills
        key = f"{congress}_{bill_number}"

        # Skipping anything already in the cache
        if key in cache:
            continue

        bill_type, number = parse_bill(bill_number)
        if not bill_type:
            cache[key] = ""
            continue

        # Fetching and caching the policy area for this bill
        policy_area = get_policy_area(congress, bill_type, number)
        cache[key] = policy_area
        checked += 1

        # Saving progress to disk every 50 bills in case of interruption
        if checked % 50 == 0:
            print(f"Checked {checked} new bills so far...")
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f, indent=2)

        # Pausing between requests to respect Congress.gov's rate limits
        time.sleep(0.75)

    # Final save once all bills are processed
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"Done. Policy areas saved to {CACHE_PATH}")