# ontario_hansard_pull.py
# Crawls the Ontario Legislative Assembly Hansard backward from a known recent
# sitting day, following each page's built-in "previous sitting day" navigation
# link all the way back to June 1985, the Canada Health Act anchor date.
# Saves each sitting day's full transcript as a plain text file in
# data/canada/ontario/, named by date (e.g. 1995-03-14.txt).
# This approach avoids guessing parliament or session numbers entirely since
# the site's own navigation handles the transitions between parliaments.
# Result: 3,429 sitting day files, June 1985 through present.
# If the script hits a 503 or temporary server error, it waits 10 seconds
# and retries the same page rather than stopping entirely.

import requests
from bs4 import BeautifulSoup
import os
import time
import re

# Where the sitting day transcript files will be saved
OUTPUT_DIR = "data/canada/ontario"

# Starting from a known working recent URL and crawling backward from there
# This is a mid-session URL used as the entry point after a previous 503 interruption
START_URL = "https://www.ola.org/en/legislative-business/house-documents/parliament-37/session-2/2001-05-29/hansard-1"

# Stopping at the first sitting day of the 33rd Parliament, which opened in June 1985
# matching the Canada Health Act anchor date for the project
STOP_DATE = "1985-06-04"

def find_previous_link(soup):
    # Looking for the site's built-in previous sitting day navigation link
    # which handles all parliament and session transitions automatically
    for a in soup.find_all("a", href=True):
        if "previous sitting day" in a.get_text(strip=True).lower():
            href = a["href"]
            return href if href.startswith("http") else "https://www.ola.org" + href
    return None

def extract_date(url):
    # Pulling the date out of the URL since the filenames are date-based
    match = re.search(r"(\d{4}-\d{2}-\d{2})", url)
    return match.group(1) if match else None

def crawl_backwards(start_url, stop_date):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    current_url = start_url
    visited = set()

    while current_url and current_url not in visited:
        visited.add(current_url)
        try:
            resp = requests.get(current_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        except requests.RequestException as e:
            print(f"Error: {e}")
            break

        # If the server returns a temporary error, wait and retry the same page
        # rather than stopping and losing progress
        if resp.status_code != 200:
            print(f"Got status {resp.status_code} at {current_url}, retrying in 10 seconds...")
            time.sleep(10)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        date_str = extract_date(current_url)

        if date_str:
            # Extracting plain text from the HTML and saving to a dated file
            text = soup.get_text(separator="\n", strip=True)
            out_path = os.path.join(OUTPUT_DIR, f"{date_str}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"Saved {date_str}")

            # Stopping once we reach the 1985 project boundary
            if date_str <= stop_date:
                print("Reached 1985 boundary, stopping.")
                break

        # Finding the link to the previous sitting day and following it
        prev_link = find_previous_link(soup)
        if not prev_link:
            print("No earlier sitting day link found, stopping.")
            break

        current_url = prev_link

        # Pausing between requests to stay polite to the server
        time.sleep(1)

if __name__ == "__main__":
    crawl_backwards(START_URL, STOP_DATE)