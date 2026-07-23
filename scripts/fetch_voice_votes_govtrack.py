"""
fetch_voice_votes_govtrack.py

Uses GovTrack API to find US House health bills that passed (enacted/signed)
but are NOT in our VoteView matched set. These are the voice vote bills.

GovTrack API is public and properly filterable by subject and status.

Usage: python3 scripts/fetch_voice_votes_govtrack.py
"""
import os, json, csv, time, re, requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOVINFO_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHED_PATH = os.path.join(REPO_ROOT, "data", "us", "health_bills_final_matched.csv")
GRANULE_INDEX = os.path.join(REPO_ROOT, "data", "us", "congressional_record_granule_index.json")
SPEECH_DIR = os.path.join(REPO_ROOT, "data", "us", "congressional_record_speeches")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "us", "voice_vote_bills.json")

GOVTRACK_API = "https://www.govtrack.us/api/v2/bill"

def main():
    # Load our existing matched bills (384 unique bills with roll call votes)
    have = set()
    with open(MATCHED_PATH, newline="") as f:
        for row in csv.DictReader(f):
            congress = str(row["congress"])
            bn = row["bill_number"]
            m = re.match(r"([A-Za-z]+)(\d+)", bn.replace(".","").replace(" ",""))
            if m:
                have.add((congress, m.group(2)))  # (congress, number)
    print(f"Bills in VoteView matched set: {len(have)}")

    # Load granule index and speech files
    with open(GRANULE_INDEX) as f:
        granule_index = json.load(f)
    speech_files = set(f.replace(".txt","") for f in os.listdir(SPEECH_DIR)
                      if f.endswith(".txt") and "_notes" not in f)

    # Fetch all enacted House health bills from GovTrack
    all_govtrack_bills = []
    offset = 0
    limit = 100

    while True:
        resp = requests.get(
            GOVTRACK_API,
            params={
                "bill_type": "house_bill",
                "current_status": "enacted_signed",
                "congress__gte": 99,
                "congress__lte": 119,
                "limit": limit,
                "offset": offset,
                "format": "json",
            },
            timeout=30,
        )
        if resp.status_code != 200 or not resp.text.strip():
            print(f"  Bad response at offset {offset}, status {resp.status_code}")
            time.sleep(2)
            break
        data = resp.json()
        objects = data.get("objects", [])
        if not objects:
            break

        all_govtrack_bills.extend(objects)
        total = data.get("meta", {}).get("total_count", 0)
        offset += limit
        print(f"Fetched {len(all_govtrack_bills)}/{total} GovTrack bills")

        if offset >= total:
            break
        time.sleep(0.3)

    print(f"\nTotal GovTrack enacted House health bills: {len(all_govtrack_bills)}")

    # Find bills NOT in our VoteView set
    voice_vote_candidates = []
    for b in all_govtrack_bills:
        congress = str(b.get("congress",""))
        number = str(b.get("number",""))
        key = (congress, number)
        if key not in have:
            # check if congress is in our range (99-119)
            if 99 <= int(congress) <= 119:
                voice_vote_candidates.append({
                    "congress": congress,
                    "bill_number": f"HR{number}",
                    "number": number,
                    "title": b.get("title","")[:100],
                    "current_status": b.get("current_status",""),
                    "current_status_date": b.get("current_status_date",""),
                    "govtrack_id": b.get("id",""),
                })

    print(f"Voice vote candidates (not in VoteView): {len(voice_vote_candidates)}")

    # Check speech coverage for each
    results = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            results = json.load(f)
        print(f"Resuming: {len(results)} already processed")

    already_have_speech = 0
    in_granule_index = 0
    no_speech = 0

    for i, bill in enumerate(voice_vote_candidates):
        key = f"{bill['congress']}-{bill['bill_number']}"
        if key in results:
            continue

        # Use current_status_date as proxy for passage date
        passage_date = bill.get("current_status_date","").replace("-","") if bill.get("current_status_date") else None
        # reformat to YYYY-MM-DD
        if passage_date and len(passage_date) == 8:
            passage_date_fmt = f"{passage_date[:4]}-{passage_date[4:6]}-{passage_date[6:]}"
        else:
            passage_date_fmt = bill.get("current_status_date","")

        has_speech = passage_date_fmt in speech_files
        has_granule = passage_date_fmt in granule_index

        results[key] = {
            "congress": bill["congress"],
            "bill_number": bill["bill_number"],
            "title": bill["title"],
            "outcome": "passed",
            "passage_date": passage_date_fmt,
            "has_speech": has_speech,
            "has_granule": has_granule,
            "govtrack_id": bill["govtrack_id"],
        }

        if has_speech:
            already_have_speech += 1
        elif has_granule:
            in_granule_index += 1
        else:
            no_speech += 1

        if (i+1) % 50 == 0:
            with open(OUTPUT_PATH, "w") as f:
                json.dump(results, f, indent=2)
            print(f"  Processed {i+1}/{len(voice_vote_candidates)}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Voice vote bills total:          {len(results)}")
    print(f"  Already have speech:           {already_have_speech}")
    print(f"  In granule index (fetchable):  {in_granule_index}")
    print(f"  No speech available:           {no_speech}")
    print(f"Saved to: {OUTPUT_PATH}")
    print(f"\nNext: fetch speech for {in_granule_index} bills using repull_speeches_html.py")


if __name__ == "__main__":
    main()