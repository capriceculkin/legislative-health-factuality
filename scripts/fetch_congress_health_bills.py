"""
fetch_us_voice_votes.py

Finds and fetches outcomes for US health bills that passed by voice vote
(not in VoteView). Queries Congress.gov per-congress (99th-119th) to stay
within manageable result sizes, then cross-references with our matched set.

Usage: python3 scripts/fetch_us_voice_votes.py
"""
import os, json, csv, time, re
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHED_PATH = os.path.join(REPO_ROOT, "data", "us", "health_bills_final_matched.csv")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "us", "health_bills_voice_votes.json")

def get_actions(congress, bill_type, number):
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type.lower()}/{number}/actions"
    try:
        resp = requests.get(url, params={"api_key": KEY, "limit": 50}, timeout=20)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("actions", [])
    except Exception as e:
        print(f"  ERROR {congress}/{bill_type}/{number}: {e}")
        return []

def parse_outcome(actions):
    for a in actions:
        text = a.get("text", "").lower()
        date = a.get("actionDate", "")
        if any(p in text for p in [
            "passed by voice vote", "agreed to by voice vote",
            "passed without objection", "on passage agreed to",
        ]):
            return "passed", date, a.get("text","")
        if "failed" in text and "passage" in text:
            return "failed", date, a.get("text","")
        if "became public law" in text or "signed by president" in text:
            return "passed", date, a.get("text","")
    return None, None, None

def main():
    # Load our existing matched set
    have = set()
    with open(MATCHED_PATH, newline="") as f:
        for row in csv.DictReader(f):
            congress = str(row["congress"])
            bn = row["bill_number"]
            m = re.match(r"([A-Za-z]+)(\d+)", bn.replace(".","").replace(" ",""))
            if m:
                have.add((congress, m.group(1).upper(), m.group(2)))

    print(f"Bills already in VoteView set: {len(have)}")

    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
        print(f"Resuming: {len(existing)} already processed")

    voice_vote_candidates = []

    # Query per congress (99th=1985 through 119th=2025-2026)
    for congress_num in range(99, 120):
        print(f"\nCongress {congress_num}...")
        offset = 0
        while True:
            try:
                resp = requests.get(
                    "https://api.congress.gov/v3/bill",
                    params={
                        "api_key": KEY,
                        "congress": congress_num,
                        "policyArea": "Health",
                        "chamber": "House",
                        "limit": 250,
                        "offset": offset,
                        "format": "json",
                    },
                    timeout=30,
                )
                data = resp.json()
            except Exception as e:
                print(f"  Error at offset {offset}: {e}")
                break

            bills = data.get("bills", [])
            if not bills:
                break

            for b in bills:
                num = str(b.get("number",""))
                btype = b.get("type","HR").upper()
                key_tuple = (str(congress_num), btype, num)

                if key_tuple in have:
                    continue  # already in VoteView

                # check if it passed
                latest = b.get("latestAction",{}).get("text","").lower()
                if any(p in latest for p in [
                    "became public law", "signed by president",
                    "passed", "agreed to", "enacted"
                ]):
                    voice_vote_candidates.append({
                        "congress": congress_num,
                        "bill_type": btype,
                        "bill_number": f"{btype}{num}",
                        "title": b.get("title","")[:80],
                        "latest_action": b.get("latestAction",{}).get("text",""),
                    })

            total = data.get("pagination",{}).get("count", 0)
            offset += 250
            if offset >= total:
                break
            time.sleep(0.3)

        print(f"  Congress {congress_num}: {len([v for v in voice_vote_candidates if v['congress']==congress_num])} voice vote candidates")
        time.sleep(0.5)

    print(f"\nTotal voice vote candidates: {len(voice_vote_candidates)}")

    # Now fetch actions for each candidate
    todo = [v for v in voice_vote_candidates
            if f"{v['congress']}-{v['bill_number']}" not in existing]
    print(f"Fetching actions for {len(todo)} bills...")

    for i, bill in enumerate(todo):
        key = f"{bill['congress']}-{bill['bill_number']}"
        actions = get_actions(bill["congress"], bill["bill_type"],
                             bill["bill_number"].replace(bill["bill_type"],""))
        outcome, date, text = parse_outcome(actions)

        existing[key] = {
            "congress": bill["congress"],
            "bill_number": bill["bill_number"],
            "title": bill["title"],
            "outcome": outcome or "unknown",
            "date": date,
            "action_text": text,
        }

        if outcome:
            print(f"  [{i+1}] {key}: {outcome} ({date})")

        if (i+1) % 20 == 0:
            with open(OUTPUT_PATH, "w") as f:
                json.dump(existing, f, indent=2)
        time.sleep(0.4)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(existing, f, indent=2)

    passed = sum(1 for v in existing.values() if v.get("outcome") == "passed")
    print(f"\nVoice vote bills found: {len(existing)}")
    print(f"  Passed: {passed}")
    print(f"Saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()