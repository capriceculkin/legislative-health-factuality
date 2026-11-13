"""
quebec_vote_linkage_pilot.py (v2, with User-Agent fix)
"""

import json
import re
import time
import requests

CHEMINEMENT_PATH = "data/canada/quebec_bills/cheminement_all_sessions.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STAGE_MARKERS = {
    "adoption finale": re.compile(r"adoption\s+finale", re.IGNORECASE),
    "adoption du principe": re.compile(r"adoption\s+du\s+principe", re.IGNORECASE),
    "prise en considération": re.compile(r"prise\s+en\s+consid[ée]ration", re.IGNORECASE),
}


def identify_stage(html_text):
    found = []
    for stage_name, pattern in STAGE_MARKERS.items():
        if pattern.search(html_text):
            found.append(stage_name)
    return found


def main():
    with open(CHEMINEMENT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    session = list(data.keys())[0]
    bill = data[session][0]
    print(f"PILOT BILL: {bill['title']}\n")

    debates = bill.get("assembly_debates", [])
    print(f"Checking {len(debates)} assembly debate sessions for stage markers...\n")

    results = []
    for d in debates:
        try:
            resp = requests.get(d["url"], timeout=20, headers=HEADERS)
            resp.raise_for_status()
            stages_found = identify_stage(resp.text)
            results.append((d["label"], d["url"], stages_found))
            print(f"{d['label']}: {stages_found if stages_found else '(no stage marker found)'}")
        except Exception as e:
            print(f"{d['label']}: ERROR - {e}")
            results.append((d["label"], d["url"], []))
        time.sleep(1)

    finale_sessions = [r for r in results if "adoption finale" in r[2]]
    print(f"\n{'='*60}")
    print(f"Sessions identified as adoption finale: {len(finale_sessions)}")
    for label, url, stages in finale_sessions:
        print(f"  {label} -> {url}")

    if finale_sessions:
        last = finale_sessions[-1]
        print(f"\nLAST (chronologically final) adoption finale match: {last[0]}")
        print("This is the strongest candidate for the true final passage session,")
        print("since earlier matches are likely menu/sidebar references.")


if __name__ == "__main__":
    main()
