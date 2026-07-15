import json
import re
import time
import requests

CHEMINEMENT_PATH = "data/canada/quebec_bills/cheminement_all_sessions.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STAGE_MARKERS = {
    "adoption finale": re.compile(r"adoption\s+finale", re.IGNORECASE),
    "adoption du principe": re.compile(r"adoption\s+du\s+principe", re.IGNORECASE),
}

def identify_stage(html_text):
    return [name for name, pat in STAGE_MARKERS.items() if pat.search(html_text)]

with open(CHEMINEMENT_PATH, encoding="utf-8") as f:
    data = json.load(f)

session = list(data.keys())[0]
# pick a different bill this time, index 5 instead of 0
bill = data[session][5]
print(f"PILOT BILL 2: {bill['title']}\n")

debates = bill.get("assembly_debates", [])
print(f"Checking {len(debates)} sessions...\n")

results = []
for d in debates:
    try:
        resp = requests.get(d["url"], timeout=20, headers=HEADERS)
        resp.raise_for_status()
        stages = identify_stage(resp.text)
        results.append((d["label"], stages))
        print(f"{d['label']}: {stages if stages else '(none)'}")
    except Exception as e:
        print(f"{d['label']}: ERROR - {e}")
    time.sleep(1)

finale = [r for r in results if "adoption finale" in r[1]]
print(f"\nadoption finale matches: {len(finale)}")
if finale:
    print(f"Last match: {finale[-1][0]}")
