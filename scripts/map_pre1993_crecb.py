"""
map_pre1993_crecb.py

Maps pre-1993 voice vote bill dates to their CRECB bound edition parts
by scanning package summaries for date range matches.

Usage: python3 scripts/map_pre1993_crecb.py
"""
import os, json, re, time, requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
KEY = os.getenv("GOVINFO_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRANULE_INDEX = os.path.join(REPO_ROOT, "data/us/congressional_record_granule_index.json")
VOICE_STATUS = os.path.join(REPO_ROOT, "data/us/voice_vote_speeches_status.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale)"}
BASE = "https://api.govinfo.gov"


def find_part_for_date(year, target_date_str):
    """Scan CRECB parts for the given year to find which one covers target_date."""
    target = datetime.strptime(target_date_str, "%Y-%m-%d")
    # parse date range from title like "Volume 138, Part 22 (October 5, 1992 to October 7, 1992)"
    date_range_re = re.compile(
        r"\((\w+ \d+, \d{4}) to (\w+ \d+, \d{4})\)"
    )

    for pt in range(1, 35):
        pkg_id = f"GPO-CRECB-{year}-pt{pt}"
        try:
            resp = requests.get(
                f"{BASE}/packages/{pkg_id}/summary",
                params={"api_key": KEY},
                headers=HEADERS, timeout=15,
            )
            if resp.status_code == 404:
                break  # no more parts
            if resp.status_code != 200:
                continue

            title = resp.json().get("title", "")
            m = date_range_re.search(title)
            if m:
                start = datetime.strptime(m.group(1), "%B %d, %Y")
                end = datetime.strptime(m.group(2), "%B %d, %Y")
                if start <= target <= end:
                    return pkg_id, title
            time.sleep(0.15)
        except Exception as e:
            continue

    return None, None


def get_house_granule(pkg_id):
    """Get the first House section granule from a package."""
    try:
        resp = requests.get(
            f"{BASE}/packages/{pkg_id}/granules",
            params={"api_key": KEY, "pageSize": 100, "offsetMark": "*"},
            headers=HEADERS, timeout=20,
        )
        if resp.status_code != 200:
            return None
        granules = resp.json().get("granules", [])
        exclude = ["senate", "extension", "digest", "remarks", "frontmatter"]
        # prefer -2 suffix granules
        for g in granules:
            gid = g.get("granuleId", "")
            title = g.get("title", "").lower()
            if not any(ex in title for ex in exclude) and gid.endswith("-2"):
                return gid
        # fallback to any non-excluded granule
        for g in granules:
            gid = g.get("granuleId", "")
            title = g.get("title", "").lower()
            if not any(ex in title for ex in exclude):
                return gid
    except Exception:
        pass
    return None


def main():
    with open(GRANULE_INDEX) as f:
        granule_index = json.load(f)

    with open(VOICE_STATUS) as f:
        voice_status = json.load(f)

    # find pre-1993 dates missing from index
    missing = set()
    for v in voice_status.values():
        date = v.get("passage_date", "")
        if date and date[:4] < "1993" and not v.get("has_speech") and date not in granule_index:
            missing.add(date)

    print(f"Pre-1993 dates to map: {len(missing)}")

    found = 0
    not_found = 0

    for date in sorted(missing):
        year = date[:4]
        print(f"  {date} ({year})...", end=" ", flush=True)

        pkg_id, title = find_part_for_date(year, date)
        if pkg_id:
            granule_id = get_house_granule(pkg_id)
            if granule_id:
                granule_index[date] = {"packageId": pkg_id, "granuleId": granule_id}
                print(f"FOUND: {pkg_id} -> {granule_id}")
                found += 1
            else:
                print(f"package {pkg_id} found but no house granule")
                not_found += 1
        else:
            print("no matching package")
            not_found += 1
        time.sleep(0.2)

        # manually add 4 bills whose passage dates weren't auto-detected
    manual_dates = ["1988-10-06", "1988-09-26", "1988-10-05", "1987-05-04"]
    for date in manual_dates:
        if date not in granule_index:
            year = date[:4]
            pkg_id, title = find_part_for_date(year, date)
            if pkg_id:
                gran = get_house_granule(pkg_id)
                if gran:
                    granule_index[date] = {"packageId": pkg_id, "granuleId": gran}
                    print(f"Added {date}: {pkg_id}/{gran}")

    with open(GRANULE_INDEX, "w") as f:
        json.dump(granule_index, f, indent=2)

    print(f"\nFound: {found} | Not found: {not_found}")
    print("Granule index updated.")
    print("\nNow rerun: python3 scripts/fetch_voice_vote_speeches.py")


if __name__ == "__main__":
    main()
