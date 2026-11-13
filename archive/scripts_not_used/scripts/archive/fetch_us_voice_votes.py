"""
fetch_us_voice_votes.py

Fetches pass/fail outcomes for US health bills that passed by voice vote
(not in VoteView) using the Congress.gov bill actions API.

The 668 CRS-tagged health bills - 384 with recorded roll calls = 284 voice vote bills.
The Congress.gov API records "Passed by voice vote" / "Failed" in the actions text.

Usage: python3 scripts/fetch_us_voice_votes.py
"""

import os, re, json, time, csv
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE = "https://api.congress.gov/v3"
MATCHED_PATH = os.path.join(REPO_ROOT, "data", "us", "health_bills_final_matched.csv")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "us", "health_bills_voice_votes.json")

# Congress number to year range mapping
CONGRESS_YEARS = {str(c): 1983 + (c-98)*2 for c in range(99, 120)}


def get_bill_actions(congress, bill_number):
    """Fetch actions for a bill from Congress.gov API."""
    # bill_number is like HR2369, extract type and number
    m = re.match(r"([A-Z]+)(\d+)", bill_number.upper().replace(".", "").replace(" ", ""))
    if not m:
        return []
    bill_type_raw = m.group(1)
    num = m.group(2)

    # map to Congress.gov bill type
    type_map = {"HR": "hr", "S": "s", "HJRES": "hjres", "SJRES": "sjres",
                "HRES": "hres", "SRES": "sres", "HCONRES": "hconres", "SCONRES": "sconres"}
    bill_type = type_map.get(bill_type_raw, "hr")

    url = f"{BASE}/bill/{congress}/{bill_type}/{num}/actions"
    try:
        resp = requests.get(url, params={"api_key": KEY, "limit": 50}, timeout=20)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("actions", [])
    except Exception as e:
        print(f"  ERROR {congress}/{bill_type}/{num}: {e}")
        return []


def parse_floor_outcome(actions):
    """Extract House floor outcome from actions list."""
    for action in actions:
        text = action.get("text", "").lower()
        action_type = action.get("type", "")
        # look for House floor passage actions
        if any(phrase in text for phrase in [
            "passed by voice vote",
            "agreed to by voice vote",
            "passed without objection",
            "on passage agreed to",
            "on motion to suspend the rules and pass"
        ]):
            if "failed" in text or "not agreed" in text:
                return "failed", action.get("actionDate",""), action.get("text","")
            return "passed", action.get("actionDate",""), action.get("text","")
        if "failed" in text and ("passage" in text or "house" in text.lower()):
            return "failed", action.get("actionDate",""), action.get("text","")
    return None, None, None


def main():
    # load already-matched bills (these have VoteView roll call outcomes)
    matched_dates = set()
    matched_bills = set()
    with open(MATCHED_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            matched_bills.add((row["congress"], row["bill_number"]))
            matched_dates.add(row.get("date",""))

    print(f"Already matched (VoteView): {len(matched_bills)} bills")

    # load existing voice vote results if resuming
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
        print(f"Resuming: {len(existing)} voice vote bills already fetched")

    # we need to find the 284 voice vote bills
    # use Congress.gov search for CRS health bills not in our matched set
    print("\nFetching CRS health bills from Congress.gov to find voice vote bills...")

    voice_vote_bills = []
    offset = 0
    limit = 20

    while True:
        url = f"{BASE}/bill"
        params = {
            "api_key": KEY,
            "policyArea": "Health",
            "chamber": "House",
            "billType": "HR",
            "limit": limit,
            "offset": offset,
        }
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Error fetching bill list at offset {offset}: {e}")
            break

        bills = data.get("bills", [])
        if not bills:
            break

        for bill in bills:
            congress = str(bill.get("congress",""))
            num = str(bill.get("number",""))
            bill_type = bill.get("type","hr").lower()
            bill_id = f"{bill_type.upper()}{num}"
            key = (congress, bill_id)

            # skip if already in VoteView matched set
            if key in matched_bills:
                continue

            # check if it passed (became law or has passed status)
            latest_action = bill.get("latestAction",{}).get("text","").lower()
            if any(p in latest_action for p in ["became public law", "signed by president",
                                                  "passed", "enacted"]):
                voice_vote_bills.append({
                    "congress": congress,
                    "bill_number": bill_id,
                    "title": bill.get("title",""),
                    "latest_action": bill.get("latestAction",{}).get("text",""),
                })

        total = data.get("pagination",{}).get("count", 0)
        offset += limit
        print(f"  Scanned offset {offset}/{total}, found {len(voice_vote_bills)} voice vote candidates so far")

        if offset >= total or offset >= 700:
            break
        time.sleep(0.5)

    print(f"\nVoice vote candidates: {len(voice_vote_bills)}")
    todo = [b for b in voice_vote_bills
            if f"{b['congress']}-{b['bill_number']}" not in existing]
    print(f"To fetch actions for: {len(todo)}")

    for i, bill in enumerate(todo):
        key = f"{bill['congress']}-{bill['bill_number']}"
        actions = get_bill_actions(bill["congress"], bill["bill_number"])
        outcome, date, text = parse_floor_outcome(actions)
        existing[key] = {
            "congress": bill["congress"],
            "bill_number": bill["bill_number"],
            "title": bill["title"],
            "outcome": outcome,
            "date": date,
            "action_text": text,
        }
        if outcome:
            print(f"  [{i+1}] {key}: {outcome} ({date})")
        else:
            print(f"  [{i+1}] {key}: no floor outcome found")

        if (i+1) % 20 == 0:
            with open(OUTPUT_PATH, "w") as f:
                json.dump(existing, f, indent=2)
        time.sleep(0.5)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(existing, f, indent=2)

    passed = sum(1 for v in existing.values() if v.get("outcome") == "passed")
    failed = sum(1 for v in existing.values() if v.get("outcome") == "failed")
    print(f"\n{'='*60}")
    print(f"Voice vote bills processed: {len(existing)}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  No outcome found: {len(existing)-passed-failed}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
