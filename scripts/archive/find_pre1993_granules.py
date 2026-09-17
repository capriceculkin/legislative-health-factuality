"""
find_pre1993_granules.py

For voice vote bills from 1985-1992, finds the bound Congressional Record
(GPO-CRECB) granule that covers each date by searching GovInfo packages.

Usage: python3 scripts/find_pre1993_granules.py
"""
import os, json, re, time, requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOVINFO_KEY")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRANULE_INDEX = os.path.join(REPO_ROOT, "data/us/congressional_record_granule_index.json")
VOICE_STATUS = os.path.join(REPO_ROOT, "data/us/voice_vote_speeches_status.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale)"}
BASE = "https://api.govinfo.gov"


def get_crecb_packages_for_year(year):
    """Get all CRECB package IDs for a given year."""
    packages = []
    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{BASE}/collections/CRECB/{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
                params={"api_key": KEY, "pageSize": 100, "offset": offset},
                headers=HEADERS, timeout=20,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            pkgs = data.get("packages", [])
            if not pkgs:
                break
            packages.extend([p["packageId"] for p in pkgs])
            total = data.get("total", 0)
            offset += 100
            if offset >= total:
                break
        except Exception as e:
            print(f"  Error getting packages for {year}: {e}")
            break
    return packages


def find_granule_for_date(date_str, packages):
    """Search through packages to find a granule covering the given date."""
    from datetime import datetime
    target = datetime.strptime(date_str, "%Y-%m-%d")

    for pkg_id in packages:
        try:
            resp = requests.get(
                f"{BASE}/packages/{pkg_id}/granules",
                params={"api_key": KEY, "pageSize": 100, "offsetMark": "*"},
                headers=HEADERS, timeout=20,
            )
            if resp.status_code != 200:
                continue
            granules = resp.json().get("granules", [])
            exclude = ["senate", "extension", "digest", "remarks", "frontmatter", "FrontMatter"]
            for g in granules:
                gid = g.get("granuleId", "")
                title = g.get("title", "").lower()
                if any(ex.lower() in title for ex in exclude):
                    continue
                # check if this granule's title or date matches
                if date_str.replace("-", "") in gid or date_str in g.get("title",""):
                    return {"packageId": pkg_id, "granuleId": gid}
                # try House granules ending in -2
                if gid.endswith("-2") and "PgH" not in gid:
                    # check by fetching granule summary
                    pass
            # if no date match found, check package date range
            time.sleep(0.2)
        except Exception as e:
            continue
    return None


def main():
    with open(GRANULE_INDEX) as f:
        granule_index = json.load(f)

    with open(VOICE_STATUS) as f:
        voice_status = json.load(f)

    # find pre-1993 dates missing from index
    missing = set()
    for v in voice_status.values():
        date = v.get("passage_date","")
        if date and date[:4] < "1993" and not v.get("has_speech") and date not in granule_index:
            missing.add(date)

    print(f"Pre-1993 dates to find: {len(missing)}")
    if not missing:
        print("All pre-1993 dates already in index!")
        return

    # group by year
    by_year = {}
    for date in missing:
        year = date[:4]
        by_year.setdefault(year, []).append(date)

    found = 0
    for year, dates in sorted(by_year.items()):
        print(f"\nYear {year}: {len(dates)} dates to find")
        print(f"  Getting CRECB packages for {year}...")
        packages = get_crecb_packages_for_year(year)
        print(f"  Found {len(packages)} packages: {packages[:3]}")

        for date in sorted(dates):
            if date in granule_index:
                continue
            print(f"  Searching for {date}...", end=" ", flush=True)

            # For CRECB, try to find package by checking summary dates
            # The package title contains the date range
            matched_pkg = None
            for pkg_id in packages:
                try:
                    resp = requests.get(
                        f"{BASE}/packages/{pkg_id}/summary",
                        params={"api_key": KEY},
                        headers=HEADERS, timeout=15,
                    )
                    if resp.status_code == 200:
                        summary = resp.json()
                        date_issued = summary.get("dateIssued","")
                        date_range = summary.get("governmentAuthor2","")
                        title = summary.get("title","")
                        # check if this package covers our date
                        if date.replace("-","") in title.replace(" ","") or date_issued == date:
                            matched_pkg = pkg_id
                            break
                except Exception:
                    continue
                time.sleep(0.1)

            if matched_pkg:
                # get house granule from this package
                resp = requests.get(
                    f"{BASE}/packages/{matched_pkg}/granules",
                    params={"api_key": KEY, "pageSize": 100, "offsetMark": "*"},
                    headers=HEADERS, timeout=20,
                )
                granules = resp.json().get("granules", [])
                exclude = ["senate", "extension", "digest", "remarks"]
                house_gran = None
                for g in granules:
                    gid = g.get("granuleId","")
                    title = g.get("title","").lower()
                    if not any(ex in title for ex in exclude):
                        if gid.endswith("-2") or "PgH" in gid:
                            house_gran = gid
                            break
                if not house_gran and granules:
                    # take first non-excluded granule
                    for g in granules:
                        gid = g.get("granuleId","")
                        title = g.get("title","").lower()
                        if not any(ex in title for ex in exclude):
                            house_gran = gid
                            break

                if house_gran:
                    granule_index[date] = {"packageId": matched_pkg, "granuleId": house_gran}
                    print(f"FOUND: {matched_pkg}/{house_gran}")
                    found += 1
                else:
                    print(f"package found but no house granule")
            else:
                print("not found")

            time.sleep(0.3)

    with open(GRANULE_INDEX, "w") as f:
        json.dump(granule_index, f, indent=2)

    print(f"\nFound: {found} | Updated granule index")
    print("Now rerun: python3 scripts/fetch_voice_vote_speeches.py")


if __name__ == "__main__":
    main()
