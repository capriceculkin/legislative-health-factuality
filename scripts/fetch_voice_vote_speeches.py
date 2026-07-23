"""
fetch_voice_vote_speeches.py

For each of the 67 CRS Health voice vote bills:
1. Fetches the House floor passage date from Congress.gov actions
2. Checks if speech file exists for that date
3. Fetches missing speech files via GovInfo HTML endpoint

Usage: python3 scripts/fetch_voice_vote_speeches.py
"""
import os, json, re, time, requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()
CONGRESS_KEY = os.getenv("CONGRESS_KEY")
GOVINFO_KEY = os.getenv("GOVINFO_KEY")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_PATH = os.path.join(REPO_ROOT, "data/us/voice_vote_bills_authoritative.json")
GRANULE_INDEX = os.path.join(REPO_ROOT, "data/us/congressional_record_granule_index.json")
SPEECH_DIR = os.path.join(REPO_ROOT, "data/us/congressional_record_speeches")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/us/voice_vote_speeches_status.json")

GOVINFO_BASE = "https://api.govinfo.gov"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality)"}


def get_house_passage_date(congress, number):
    url = f"https://api.congress.gov/v3/bill/{congress}/hr/{number}/actions"
    try:
        resp = requests.get(url, params={"api_key": CONGRESS_KEY, "limit": 50}, timeout=20)
        resp.raise_for_status()
        actions = resp.json().get("actions", [])
        for a in actions:
            text = a.get("text", "").lower()
            chamber = a.get("chamber", "").lower()
            if any(p in text for p in [
                "passed by voice vote", "agreed to by voice vote",
                "passed without objection", "on motion to suspend rules and pass",
                "on passage agreed to",
                "passed house", 
                "passed/agreed to in house",  
            ]):
                    return a.get("actionDate", "")
    except Exception as e:
        print(f"  Error fetching actions for {congress}/hr/{number}: {e}")
    return None


def fetch_speech_html(package_id, granule_id):
    url = f"{GOVINFO_BASE}/packages/{package_id}/granules/{granule_id}/htm"
    try:
        resp = requests.get(url, params={"api_key": GOVINFO_KEY}, headers=HEADERS, timeout=30)
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception as e:
        print(f"  Error fetching HTML: {e}")
        return None


def main():
    with open(VOICE_PATH) as f:
        voice_bills = json.load(f)

    with open(GRANULE_INDEX) as f:
        granule_index = json.load(f)

    speech_dates = set(f.replace(".txt","") for f in os.listdir(SPEECH_DIR)
                      if f.endswith(".txt") and "_notes" not in f)

    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
        print(f"Resuming: {len(existing)} already processed")

    print(f"Processing {len(voice_bills)} voice vote bills...\n")

    fetched = 0
    already_have = 0
    no_granule = 0

    for i, bill in enumerate(voice_bills):
        key = f"{bill['congress']}-{bill['bill']}"
        if key in existing:
            continue

        m = re.match(r"H\.R\.\s*(\d+)", bill["bill"])
        if not m:
            continue
        number = m.group(1)
        congress = bill["congress"]

        # get House passage date
        passage_date = get_house_passage_date(congress, number)
        time.sleep(0.3)

        if not passage_date:
            print(f"  [{i+1}] {bill['bill']}: no House passage date found")
            existing[key] = {"bill": bill["bill"], "congress": congress,
                            "outcome": "passed", "passage_date": None,
                            "has_speech": False}
            continue

        # check speech coverage
        has_speech = passage_date in speech_dates
        has_granule = passage_date in granule_index

        existing[key] = {
            "bill": bill["bill"],
            "congress": congress,
            "title": bill["title"],
            "outcome": "passed",
            "passage_date": passage_date,
            "has_speech": has_speech,
            "has_granule": has_granule,
        }

        if has_speech:
            print(f"  [{i+1}] {bill['bill']}: speech already exists ({passage_date})")
            already_have += 1
        elif has_granule:
            # fetch the speech
            granule = granule_index[passage_date]
            pkg_id = granule.get("packageId")
            gran_id = granule.get("granuleId")
            if pkg_id and gran_id:
                gran_ids = gran_id if isinstance(gran_id, list) else [gran_id]
                parts = []
                for gid in gran_ids:
                    text = fetch_speech_html(pkg_id, gid)
                    if text:
                        parts.append(f"--- {gid} ---\n{text}")
                    time.sleep(0.3)
                if parts:
                    out_path = os.path.join(SPEECH_DIR, f"{passage_date}.txt")
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write("\n\n".join(parts))
                    existing[key]["has_speech"] = True
                    fetched += 1
                    print(f"  [{i+1}] {bill['bill']}: fetched speech for {passage_date}")
                else:
                    print(f"  [{i+1}] {bill['bill']}: granule exists but fetch failed ({passage_date})")
        else:
            no_granule += 1
            print(f"  [{i+1}] {bill['bill']}: no granule for {passage_date}")

        if (i+1) % 10 == 0:
            with open(OUTPUT_PATH, "w") as f:
                json.dump(existing, f, indent=2)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Voice vote bills processed: {len(existing)}")
    print(f"  Already had speech:   {already_have}")
    print(f"  Fetched speech:       {fetched}")
    print(f"  No granule available: {no_granule}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
