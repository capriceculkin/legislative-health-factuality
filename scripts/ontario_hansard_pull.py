import requests
from bs4 import BeautifulSoup
import os
import time
import re

OUTPUT_DIR = "data/canada/ontario"
START_URL = "https://www.ola.org/en/legislative-business/house-documents/parliament-37/session-2/2001-05-29/hansard-1"
STOP_DATE = "1985-06-04"  # 33rd Parliament start, our project anchor

def find_previous_link(soup):
    for a in soup.find_all("a", href=True):
        if "previous sitting day" in a.get_text(strip=True).lower():
            href = a["href"]
            return href if href.startswith("http") else "https://www.ola.org" + href
    return None

def extract_date(url):
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

        if resp.status_code != 200:
            print(f"Got status {resp.status_code} at {current_url}, retrying in 10 seconds...")
            time.sleep(10)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        date_str = extract_date(current_url)

        if date_str:
            text = soup.get_text(separator="\n", strip=True)
            out_path = os.path.join(OUTPUT_DIR, f"{date_str}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"Saved {date_str}")

            if date_str <= stop_date:
                print("Reached 1985 boundary, stopping.")
                break

        prev_link = find_previous_link(soup)
        if not prev_link:
            print("No earlier sitting day link found, stopping.")
            break

        current_url = prev_link
        time.sleep(1)

if __name__ == "__main__":
    crawl_backwards(START_URL, STOP_DATE)