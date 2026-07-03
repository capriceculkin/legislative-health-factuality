# congressional_record_pull_test.py  
# Lightweight test version of congressional_record_pull.py
# Pulls only 20 Congressional Record issues to verify the API connection
# and check the article metadata structure before running the full pull.
# For the full paginated production pull, see congressional_record_pull.py

import requests
import json
import os
import time
from dotenv import load_dotenv

# Loading the Congress.gov API key from .env
load_dotenv()
KEY = os.getenv("CONGRESS_KEY")

# Where the daily issue metadata files will be saved
OUTPUT_DIR = "data/us/congressional_record"

def get_record_issues(offset=0, limit=20):
    # Pulling a single page of daily Congressional Record issues from Congress.gov
    # This is the lighter version of the pull, only 20 issues at a time, used for testing
    url = "https://api.congress.gov/v3/daily-congressional-record"
    params = {"api_key": KEY, "offset": offset, "limit": limit, "format": "json"}
    resp = requests.get(url, params=params)
    return resp.json()

def get_articles(volume, issue):
    # Pulling article titles and links for one specific issue
    # Each article is one floor speech, debate entry, or procedural item
    # This gives us metadata only, not the actual speech text
    url = f"https://api.congress.gov/v3/daily-congressional-record/{volume}/{issue}/articles"
    params = {"api_key": KEY, "format": "json"}
    resp = requests.get(url, params=params)
    return resp.json()

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Pulling the first page of issues to see what's available
    issues_data = get_record_issues(limit=20)
    issues = issues_data.get("dailyCongressionalRecord", [])
    print(f"Found {len(issues)} issues")

    for issue in issues:
        volume = issue.get("volumeNumber")
        issue_num = issue.get("issueNumber")
        if not volume or not issue_num:
            continue

        # Pulling and saving the article list for this issue
        articles = get_articles(volume, issue_num)
        out_path = os.path.join(OUTPUT_DIR, f"vol{volume}_issue{issue_num}.json")
        with open(out_path, "w") as f:
            json.dump(articles, f, indent=2)
        print(f"Saved volume {volume} issue {issue_num}")

        # Pausing between requests to stay polite to the API
        time.sleep(0.5)