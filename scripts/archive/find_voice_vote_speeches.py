"""
find_voice_vote_speeches.py

For each of the 284 US health bills that passed by voice vote (not in VoteView),
finds the passage date from Congress.gov actions, checks if we already have
the Congressional Record speech file for that date, and fetches missing ones.

Usage: python3 scripts/find_voice_vote_speeches.py
"""
import os, json, csv, time, re
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")
GOVINFO_KEY = os.getenv("GOVINFO_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHED_PATH = os.path.join(REPO_ROOT, "data", "us", "health_bills_final_matched.csv")
GRANULE_INDEX_PATH = os.path.join(REPO_ROOT, "data", "us", "congressional_record_granule_index.json")
SPEECH_DIR = os.path.join(REPO_ROOT, "data", "us", "congressional_record_speeches")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "us", "voice_vote_bills_status.json")

def get_bill_actions(congress, bill_type, number):
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type.lower()}/{number}/actions"
    try:
        resp = requests.get(url, params={"api_key": KEY, "limit": 50}, timeout=20)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("actions", [])
    except Exception as e:
        print(f"  ERROR fetching actions: {e}")
        return []

def find_passage_date(actions):
    """Find the House floor passage date from actions."""
    for a in actions:
        text = a.get("text", "").lower()
        date = a.get("actionDate", "")
        chamber = a.get("chamber", "").lower()
        if chamber != "house" and "house" not in text:
            continue
        if any(p in text for p in [
            "passed by voice vote", "agreed to by voice vote",
            "passed without objection", "on motion to suspend rules and pass",
            "on passage agreed to",
        ]):
            return date, a.get("text", "")
    return None, None

def main():
    # Load our existing matched bills
    have_bills = set()
    with open(MATCHED_PATH, newline="") as f:
        for row in csv.DictReader(f):
            m = re.match(r"([A-Za-z]+)(\d+)", row["bill_number"].replace(".",""))
            if m:
                have_bills.add((str(row["congress"]), m.group(1).upper(), m.group(2)))

    print(f"Bills in VoteView matched set: {len(have_bills)}")

    # Load granule index to know which dates we can fetch
    with open(GRANULE_INDEX_PATH) as f:
        granule_index = json.load(f)
    speech_files = set(f.replace(".txt","") for f in os.listdir(SPEECH_DIR)
                      if f.endswith(".txt") and "_notes" not in f)
    print(f"Speech files on disk: {len(speech_files)}")
    print(f"Dates in granule index: {len(granule_index)}")

    # Load existing results
    results = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            results = json.load(f)
        print(f"Resuming: {len(results)} bills already processed")

    # For each congress, get health bills from Congress.gov and find ones not in our set
    voice_vote_bills = []
    for congress_num in range(99, 120):
        offset = 0
        while True:
            try:
                resp = requests.get(
                    "https://api.congress.gov/v3/bill",
                    params={
                        "api_key": KEY,
                        "congress": congress_num,
                        "policyArea": "Health",
                        "limit": 250,
                        "offset": offset,
                        "format": "json",
                    },
                    timeout=30,
                )
                data = resp.json()
                bills = data.get("bills", [])
                if not bills:
                    break

                for b in bills:
                    if b.get("originChamber","").lower() != "house":
                        continue
                    num = str(b.get("number",""))
                    btype = b.get("type","HR").upper()
                    if (str(congress_num), btype, num) not in have_bills:
                        latest = b.get("latestAction",{}).get("text","").lower()
                        if any(p in latest for p in ["became public law","signed by president","passed","agreed to","enacted"]):
                            voice_vote_bills.append({
                                "congress": congress_num,
                                "bill_type": btype,
                                "number": num,
                                "bill_id": f"{btype}{num}",
                                "title": b.get("title","")[:80],
                            })

                total = data.get("pagination",{}).get("count",0)
                offset += 250
                if offset >= min(total, 5000):  # cap per congress
                    break
                time.sleep(0.3)

            except Exception as e:
                print(f"  Error congress {congress_num} offset {offset}: {e}")
                break

        time.sleep(0.5)

    print(f"\nVoice vote candidates found: {len(voice_vote_bills)}")

    # For each, get passage date and check speech coverage
    already_have_speech = 0
    in_granule_index = 0
    missing_speech = 0

    todo = [b for b in voice_vote_bills
            if f"{b['congress']}-{b['bill_id']}" not in results]

    for i, bill in enumerate(todo):
        key = f"{bill['congress']}-{bill['bill_id']}"
        actions = get_bill_actions(bill["congress"], bill["bill_type"], bill["number"])
        passage_date, passage_text = find_passage_date(actions)

        has_speech = passage_date and passage_date in speech_files
        has_granule = passage_date and passage_date in granule_index

        results[key] = {
            "congress": bill["congress"],
            "bill_id": bill["bill_id"],
            "title": bill["title"],
            "outcome": "passed",
            "passage_date": passage_date,
            "passage_text": passage_text,
            "has_speech": has_speech,
            "has_granule": has_granule,
        }

        if has_speech:
            already_have_speech += 1
        elif has_granule:
            in_granule_index += 1
        else:
            missing_speech += 1

        if (i+1) % 20 == 0:
            with open(OUTPUT_PATH, "w") as f:
                json.dump(results, f, indent=2)
            print(f"  [{i+1}/{len(todo)}] {key}: {passage_date} | speech={'yes' if has_speech else 'no'}")

        time.sleep(0.4)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Voice vote bills processed: {len(results)}")
    print(f"  Already have speech file:  {already_have_speech}")
    print(f"  In granule index (fetchable): {in_granule_index}")
    print(f"  No speech available:       {missing_speech}")
    print(f"\nSaved to: {OUTPUT_PATH}")
    print(f"\nNext step: fetch speech for the {in_granule_index} bills in granule index")


if __name__ == "__main__":
    main()
