# congressional_record_pull.py
# Pulls the full paginated list of daily Congressional Record issues from Congress.gov
# and saves each issue's article metadata (titles and links) to disk.
# This is the production version that loops through all available issues.
# For a quick test pull of just 20 issues, see congressional_record_pull_test.py

import requests
import json
import os
import time
from dotenv import load_dotenv

# Loading the Congress.gov API key from the .env file
load_dotenv()
KEY = os.getenv("CONGRESS_KEY")

# Where the daily issue metadata files will be saved
# Each file is one day's worth of Congressional Record article titles and links
OUTPUT_DIR = "data/us/congressional_record"

def get_record_issues(offset=0, limit=100):
    # Pulling a paginated list of daily Congressional Record issues from Congress.gov
    # Each issue corresponds to one publication day of the Congressional Record
    url = "https://api.congress.gov/v3/daily-congressional-record"
    params = {"api_key": KEY, "offset": offset, "limit": limit, "format": "json"}
    resp = requests.get(url, params=params)
    return resp.json()

def get_articles(volume, issue):
    # Pulling the article list for a specific issue, identified by volume and issue number
    # Each article is one floor speech, debate entry, or procedural item
    # This gives us titles and links to the actual text, not the text itself
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

        # If we get back an empty list, we have reached the end of all available issues
        if not issues:
            print("No more issues, stopping.")
            break

        for issue in issues:
            volume = issue.get("volumeNumber")
            issue_num = issue.get("issueNumber")
            if not volume or not issue_num:
                continue

            # Skipping issues already saved so we can safely stop and restart this script
            out_path = os.path.join(OUTPUT_DIR, f"vol{volume}_issue{issue_num}.json")
            if os.path.exists(out_path):
                continue

            # Pulling the article list for this issue and saving to disk
            articles = get_articles(volume, issue_num)
            with open(out_path, "w") as f:
                json.dump(articles, f, indent=2)
            total_saved += 1
            print(f"  Saved volume {volume} issue {issue_num} (total: {total_saved})")

            # Pausing between requests to stay polite to the API
            time.sleep(0.5)

        # Moving to the next page of issues
        offset += limit

    print(f"Done. Saved {total_saved} new issues.")