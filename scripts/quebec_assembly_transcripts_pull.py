# quebec_assembly_transcripts_pull.py
# Downloads the full Assembly debate transcript text for all 621 pre-1994
# Quebec sitting days identified by quebec_assembly_pull.py.
# Saves each transcript as a plain text file in data/canada/quebec_assembly/transcripts/
# named by date, e.g. 19851219.txt
# Uses plain requests since these pages load as static HTML without JS rendering.

import requests
import json
import os
import time
from bs4 import BeautifulSoup

INPUT_PATH = "data/canada/quebec_assembly/sitting_day_links.json"
OUTPUT_DIR = "data/canada/quebec_assembly/transcripts"

def fetch_transcript(url):
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            return soup.get_text(separator="\n", strip=True)
        return None
    except requests.RequestException:
        return None

def extract_date(url):
    import re
    match = re.search(r"/(\d{8})/", url)
    return match.group(1) if match else None

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(INPUT_PATH) as f:
        data = json.load(f)

    total = sum(len(v) for v in data.values())
    print(f"Total sitting days to fetch: {total}")

    fetched = 0
    failed = 0

    for session, links in data.items():
        print(f"\nFetching session {session} ({len(links)} days)...")
        for link in links:
            url = link["url"]
            date = extract_date(url)
            if not date:
                continue

            out_path = os.path.join(OUTPUT_DIR, f"{date}.txt")
            if os.path.exists(out_path):
                continue

            text = fetch_transcript(url)
            if text:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                fetched += 1
                print(f"  Saved {date}")
            else:
                failed += 1
                print(f"  Failed {date}")

            time.sleep(0.5)

    print(f"\nDone. {fetched} transcripts saved, {failed} failed.")