import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("CONGRESS_KEY")
OUTPUT_DIR = "data/us/congressional_record"

def get_record_issues(offset=0, limit=100):
    url = "https://api.congress.gov/v3/daily-congressional-record"
    params = {"api_key": KEY, "offset": offset, "limit": limit, "format": "json"}
    resp = requests.get(url, params=params)
    return resp.json()

def get_articles(volume, issue):
    url = f"https://api.congress.gov/v3/daily-congressional-record/{volume}/{issue}/articles"
    params = {"api_key": KEY, "format": "json"}
    resp = requests.get(url, params=params)
    return resp.json()

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    offset = 0
    limit = 100
    total_saved = 0

    while True:
        print(f"Fetching issue list, offset {offset}...")
        issues_data = get_record_issues(offset=offset, limit=limit)
        issues = issues_data.get("dailyCongressionalRecord", [])
        if not issues:
            print("No more issues, stopping.")
            break

        for issue in issues:
            volume = issue.get("volumeNumber")
            issue_num = issue.get("issueNumber")
            if not volume or not issue_num:
                continue
            out_path = os.path.join(OUTPUT_DIR, f"vol{volume}_issue{issue_num}.json")
            if os.path.exists(out_path):
                continue  # skip already-pulled issues
            articles = get_articles(volume, issue_num)
            with open(out_path, "w") as f:
                json.dump(articles, f, indent=2)
            total_saved += 1
            print(f"  Saved volume {volume} issue {issue_num} (total: {total_saved})")
            time.sleep(0.5)

        offset += limit

    print(f"Done. Saved {total_saved} new issues.")