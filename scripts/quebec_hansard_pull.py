import requests
import urllib3
import os
import time
from datetime import date, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUTPUT_DIR = "data/canada/quebec"
BASE = "https://www.assnat.qc.ca/fr/travaux-parlementaires/commissions"

SESSION_CODES = ["csss-43-1", "csss-43-2", "csss-42-1", "csss-42-2", "csss-41-1"]

START_DATE = date(2018, 1, 1)
END_DATE = date(2026, 6, 23)

def try_fetch(session_code, date_str):
    url = f"{BASE}/{session_code}/journal-debats/CSSS-{date_str}.html"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
        if resp.status_code == 200 and len(resp.text) > 1000:
            return resp.text, url
    except requests.RequestException:
        pass
    return None, None

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    current = START_DATE
    found_count = 0
    checked = 0
    while current <= END_DATE:
        date_str = current.strftime("%y%m%d")
        for session_code in SESSION_CODES:
            html, url = try_fetch(session_code, date_str)
            if html:
                out_path = os.path.join(OUTPUT_DIR, f"CSSS-{date_str}.html")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"Saved {date_str} ({session_code})")
                found_count += 1
                break
        checked += 1
        if checked % 50 == 0:
            print(f"...still checking, on {current.strftime('%Y-%m-%d')}, {found_count} found so far")
        current += timedelta(days=1)
        time.sleep(0.3)
    print(f"Done. Found {found_count} committee transcripts.")