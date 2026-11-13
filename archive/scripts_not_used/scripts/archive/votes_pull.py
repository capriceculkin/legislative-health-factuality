import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")
OUTPUT_PATH = "data/us/house_votes_all.json"

def get_votes_for_session(congress, session):
    votes = []
    offset = 0
    limit = 50
    while True:
        url = f"https://api.congress.gov/v3/house-vote/{congress}/{session}"
        params = {"api_key": KEY, "limit": limit, "offset": offset, "format": "json"}
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            break
        data = resp.json()
        batch = data if isinstance(data, list) else data.get("houseRollCallVotes", [])
        if not batch:
            break
        votes.extend(batch)
        if not data.get("pagination", {}).get("next") if isinstance(data, dict) else False:
            break
        offset += limit
        time.sleep(0.3)
    return votes

if __name__ == "__main__":
    all_votes = []
    for congress in range(99, 120):  # 99th (1985) through 119th (current)
        for session in [1, 2]:
            print(f"Pulling Congress {congress}, Session {session}...")
            votes = get_votes_for_session(congress, session)
            print(f"  Got {len(votes)} votes")
            all_votes.extend(votes)
            time.sleep(0.5)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_votes, f, indent=2)
    print(f"Saved {len(all_votes)} total votes across all sessions to {OUTPUT_PATH}")