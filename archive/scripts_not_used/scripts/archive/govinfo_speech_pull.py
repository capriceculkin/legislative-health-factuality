# govinfo_speech_pull.py
# Pulls House floor debate text from the Congressional Record Bound Edition
# via the GovInfo API, matched to specific health bill vote dates.
# Uses direct package/granule URL construction rather than search API
# since the bound edition has predictable package IDs by year.
# Output: data/us/congressional_record_speeches/{date}.txt

import requests, os, io, time, csv, re, json
from dotenv import load_dotenv
load_dotenv()

KEY = os.getenv('GOVINFO_KEY')
OUTPUT_DIR = "data/us/congressional_record_speeches"
INDEX_PATH = "data/us/congressional_record_granule_index.json"
BASE = "https://api.govinfo.gov"

def get_granules_for_package(package_id):
    # Fetching all granules for a specific package with retry logic
    granules = []
    offset = '*'
    while True:
        for attempt in range(3):
            try:
                resp = requests.get(
                    f"{BASE}/packages/{package_id}/granules",
                    params={'api_key': KEY, 'pageSize': 100, 'offsetMark': offset},
                    timeout=60,
                )
                if resp.status_code == 200:
                    break
                print(f"  Status {resp.status_code}, waiting...")
                time.sleep(10)
            except requests.RequestException as e:
                print(f"  Retry {attempt+1}: {e}")
                time.sleep(15)
        else:
            return granules
        try:
            data = resp.json()
        except Exception:
            return granules
        results = data.get('granules', [])
        if not results:
            break
        granules.extend(results)
        offset = data.get('offsetMark')
        if not offset:
            break
        time.sleep(1)
    return granules

def extract_date_from_title(title):
    months = {
        'January': '01', 'February': '02', 'March': '03', 'April': '04',
        'May': '05', 'June': '06', 'July': '07', 'August': '08',
        'September': '09', 'October': '10', 'November': '11', 'December': '12'
    }
    match = re.search(r'(\w+)\s+(\d+),\s+(\d{4})', title)
    if match:
        month = months.get(match.group(1))
        day = match.group(2).zfill(2)
        year = match.group(3)
        if month:
            return f"{year}-{month}-{day}"
    return None

def fetch_pdf_text(package_id, granule_id):
    import pdfplumber
    url = f"{BASE}/packages/{package_id}/granules/{granule_id}/pdf"
    try:
        resp = requests.get(url, params={'api_key': KEY}, timeout=120, stream=True)
        if resp.status_code != 200:
            return ""
        tmp_path = f"/tmp/{granule_id}.pdf"
        with open(tmp_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        with pdfplumber.open(tmp_path) as pdf:
            text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        os.remove(tmp_path)
        return text
    except Exception as e:
        print(f"  PDF error: {e}")
        return ""

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Loading vote dates
    vote_dates = set()
    with open('data/us/health_bills_final_matched.csv') as f:
        for row in csv.DictReader(f):
            date = row.get('date', '').strip()
            if date:
                vote_dates.add(date)
    print(f"Total vote dates to cover: {len(vote_dates)}")

    # Load existing index if available
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH) as f:
            date_to_granule = json.load(f)
        print(f"Loaded existing index with {len(date_to_granule)} entries")
    else:
        date_to_granule = {}

    # Building index year by year using known package pattern
    years = sorted(set(d[:4] for d in vote_dates))
    print(f"Years to index: {years[0]} to {years[-1]}")

    for year in years:
        year_dates = {d for d in vote_dates if d.startswith(year)}
        already_covered = {d for d in year_dates if d in date_to_granule}
        if already_covered == year_dates:
            print(f"{year}: already fully indexed, skipping")
            continue

        print(f"\nIndexing {year}...")
        # Each year has roughly 20-30 parts
        for part in range(1, 35):
            package_id = f"GPO-CRECB-{year}-pt{part}"
            granules = get_granules_for_package(package_id)
            if not granules:
                print(f"  Part {part}: no granules, stopping year")
                break

            for g in granules:
                title = g.get('title', '')
                granule_id = g.get('granuleId', '')
                if 'House of Representatives' in title:
                    date = extract_date_from_title(title)
                    if date and date in vote_dates and date not in date_to_granule:
                        date_to_granule[date] = {
                            'packageId': package_id,
                            'granuleId': granule_id,
                        }
                        print(f"  Found: {date}")

            # Save progress after each part
            with open(INDEX_PATH, 'w') as f:
                json.dump(date_to_granule, f, indent=2)
            time.sleep(2)

    print(f"\nIndex complete: {len(date_to_granule)} of {len(vote_dates)} vote dates covered")

    # Pulling speech text for each matched date
    print("\nFetching speech text...")
    for date, info in sorted(date_to_granule.items()):
        out_path = f"{OUTPUT_DIR}/{date}.txt"
        if os.path.exists(out_path):
            continue
        print(f"Fetching {date}...")
        text = fetch_pdf_text(info['packageId'], info['granuleId'])
        if text:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"  Saved {len(text)} chars")
        time.sleep(2)

    print("Done.")