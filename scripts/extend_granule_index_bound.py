"""
extend_granule_index_bound.py

For voice vote bill dates not found in the daily CREC index,
searches GovInfo for the bound Congressional Record (CRECB) package
that covers that date.

Usage: python3 scripts/extend_granule_index_bound.py
"""
import os, json, re, time, requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOVINFO_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRANULE_INDEX = os.path.join(REPO_ROOT, "data/us/congressional_record_granule_index.json")
VOICE_STATUS = os.path.join(REPO_ROOT, "data/us/voice_vote_speeches_status.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality)"}
BASE = "https://api.govinfo.gov"


def search_govinfo_for_date(date_str):
    """Search GovInfo for Congressional Record packages covering this date."""
    year = date_str[:4]

    # Try daily CREC first
    crec_id = f"CREC-{date_str}"
    try:
        resp = requests.get(
            f"{BASE}/packages/{crec_id}/granules",
            params={"api_key": KEY, "pageSize": 100, "offsetMark": "*"},
            headers=HEADERS,
            timeout=20,
        )
        if resp.status_code == 200:
            granules = resp.json().get("granules", [])
            exclude = ["senate", "extension", "digest", "remarks"]
            # prefer granules with -2 suffix (House section) or PgH (House pages)
        house_granules = []
        for g in granules:
            title = g.get("title", "").lower()
            gid = g.get("granuleId", "")
            if any(ex in title for ex in exclude):
                continue
            if "PgH" in gid or gid.endswith("-2"):
                house_granules.insert(0, gid)  # prioritize
            else:
                house_granules.append(gid)
        if house_granules:
            return {"packageId": crec_id, "granuleId": house_granules[0]}
    except Exception:
        pass

    # Try GovInfo search for this date in Congressional Record
    try:
        resp = requests.get(
            f"{BASE}/search",
            params={
                "api_key": KEY,
                "query": f"publishdate:{date_str} collection:CRECB",
                "pageSize": 5,
                "offset": 0,
                "sortBy": "relevancy",
            },
            headers=HEADERS,
            timeout=20,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            for r in results:
                pkg_id = r.get("packageId", "")
                if "CRECB" in pkg_id or "CREC" in pkg_id:
                    # now get granules for this package
                    gran_resp = requests.get(
                        f"{BASE}/packages/{pkg_id}/granules",
                        params={"api_key": KEY, "pageSize": 100},
                        headers=HEADERS,
                        timeout=20,
                    )
                    if gran_resp.status_code == 200:
                        granules = gran_resp.json().get("granules", [])
                        exclude = ["senate", "extension", "digest", "remarks"]
                        for g in granules:
                            title = g.get("title", "").lower()
                            gid = g.get("granuleId", "")
                            if not any(ex in title for ex in exclude):
                                return {"packageId": pkg_id, "granuleId": gid}
    except Exception as e:
        print(f"  Search error: {e}")

    return None


def main():
    with open(GRANULE_INDEX) as f:
        granule_index = json.load(f)

    with open(VOICE_STATUS) as f:
        voice_status = json.load(f)

    # get all missing dates
    missing_dates = set()
    for v in voice_status.values():
        date = v.get("passage_date")
        if date and not v.get("has_granule") and not v.get("has_speech"):
            if date not in granule_index:
                missing_dates.add(date)

    # also get dates from bills not yet processed
    with open(os.path.join(REPO_ROOT, "data/us/voice_vote_bills_authoritative.json")) as f:
        voice_bills = json.load(f)

    print(f"Missing dates to search: {len(missing_dates)}")
    print(f"Voice bills not yet processed: will be handled by fetch script\n")

    found = 0
    not_found = 0

    for date in sorted(missing_dates):
        print(f"  Searching {date}...", end=" ", flush=True)
        granule = search_govinfo_for_date(date)

        if granule:
            granule_index[date] = granule
            print(f"FOUND: {granule['packageId']}")
            found += 1
        else:
            print("not found")
            not_found += 1

        time.sleep(0.5)

    with open(GRANULE_INDEX, "w") as f:
        json.dump(granule_index, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Found: {found} | Not found: {not_found}")
    print(f"Granule index updated.")
    print(f"\nNow rerun: python3 scripts/fetch_voice_vote_speeches.py")


if __name__ == "__main__":
    main()
