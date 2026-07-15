# cr_speech_pull_daily.py
# Pulls House floor debate text from the Congress.gov daily Congressional Record
# for vote dates from 1999 onward, using the already-downloaded issue metadata
# in data/us/congressional_record/.
# Complements govinfo_speech_pull.py which covers 1985-1998 via the bound edition.
# Output: data/us/congressional_record_speeches/{date}.txt

import json, os, csv, re, time
import requests
from bs4 import BeautifulSoup

CR_DIR = "data/us/congressional_record"
OUTPUT_DIR = "data/us/congressional_record_speeches"

def build_date_index():
    print("Building date index from daily CR files...")
    date_to_urls = {}
    for fname in os.listdir(CR_DIR):
        path = f"{CR_DIR}/{fname}"
        with open(path) as f:
            data = json.load(f)
        for section in data.get('articles', []):
            for article in section.get('sectionArticles', []):
                for text in article.get('text', []):
                    if text.get('type') != 'Formatted Text':
                        continue
                    url = text.get('url', '')
                    match = re.search(r'CREC-(\d{4}-\d{2}-\d{2})', url)
                    if match:
                        date = match.group(1)
                        if date not in date_to_urls:
                            date_to_urls[date] = []
                        date_to_urls[date].append({
                            'url': url,
                            'title': article.get('title', '')
                        })
    print(f"Indexed {len(date_to_urls)} dates")
    return date_to_urls

def fetch_text(url):
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            return soup.get_text(separator='\n', strip=True)
    except requests.RequestException as e:
        print(f"  Error: {e}")
    return ""

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_to_urls = build_date_index()

    vote_dates = set()
    with open('data/us/health_bills_final_matched.csv') as f:
        for row in csv.DictReader(f):
            date = row.get('date', '').strip()
            if date and date >= '1999-01-01':
                vote_dates.add(date)

    covered = [d for d in vote_dates if d in date_to_urls]
    print(f"Vote dates 1999-2026: {len(vote_dates)}")
    print(f"Covered by daily CR files: {len(covered)}")

    fetched = 0
    for date in sorted(covered):
        out_path = f"{OUTPUT_DIR}/{date}.txt"
        if os.path.exists(out_path):
            continue

        articles = date_to_urls[date]
        all_text = []
        for article in articles:
            text = fetch_text(article['url'])
            if text:
                all_text.append(f"=== {article['title']} ===\n{text}")
            time.sleep(0.5)

        if all_text:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(all_text))
            fetched += 1
            print(f"Saved {date} ({fetched} total)")
        else:
            print(f"No text found for {date}")

    print(f"\nDone. {fetched} speech files saved.")