"""
refetch_us_speeches_with_speakers.py

Re-fetches US Congressional Record granule HTML files and parses
speaker turns with party attribution. Uses the granule index to
construct direct URLs to govinfo.gov HTML files.

Output: data/us/us_speaker_turns.json
  {date: {turn_count, turns: [{speaker, speaker_full, party, text, is_minister}]}}

Usage: python3 scripts/refetch_us_speeches_with_speakers.py
"""
import os, re, json, time
import requests
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRANULE_INDEX = os.path.join(REPO_ROOT, "data/us/congressional_record_granule_index.json")
MEMBER_LOOKUP  = os.path.join(REPO_ROOT, "data/us/member_lookup.json")
OUTPUT_PATH    = os.path.join(REPO_ROOT, "data/us/us_speaker_turns.json")

# Speaker label: Mr. SMITH. or Ms. JONES. or Mr. Smith of California.
# Handles both pre-1995 ALL-CAPS and post-1995 Title Case
SPEAKER_RE = re.compile(
    r'(?:Mr\.|Ms\.|Mrs\.)\s+([A-Z][A-Za-z\-\']+(?:\s+[A-Z][A-Za-z\-\']+)?)(?:\s+of\s+[A-Za-z\s]+)?[,\.]'
)

SKIP = {'SPEAKER', 'CHAIR', 'CLERK', 'PRESIDENT', 'PRESIDING',
        'ACTING', 'CHAPLAIN', 'VICE', 'SPEAKER PRO', 'CHAIR PRO'}

def date_to_congress(date_str):
    year = int(date_str[:4])
    month = int(date_str[5:7])
    if year % 2 == 1 and month >= 1:
        return str(98 + (year - 1983) // 2)
    return str(98 + (year - 1984) // 2)

def build_member_lookup():
    with open(MEMBER_LOOKUP) as f:
        data = json.load(f)
    lookup = {}
    for congress_num, members in data.get('by_congress', {}).items():
        lookup[congress_num] = {}
        for member in members:
            full_name = member.get('full_name', '')
            if not full_name: continue
            last = full_name.split()[-1].upper()
            lookup[congress_num][last] = {
                'party': member.get('party', 'Unknown'),
                'full_name': full_name,
                'state': member.get('state', ''),
            }
    return lookup

def fetch_html(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30,
                           headers={'User-Agent': 'legislative-factuality-research/1.0'})
            if r.status_code == 200:
                return r.text
            print(f"  HTTP {r.status_code} for {url}")
            return None
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(2 * (attempt + 1))
    return None

def strip_html(html):
    """Remove HTML tags and decode entities, preserving line structure."""
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ').replace('&#39;', "'").replace('&quot;', '"')
    text = re.sub(r'[ \t]+', ' ', text)
    return text

def parse_turns(text, congress_lookup):
    matches = list(SPEAKER_RE.finditer(text))
    if not matches:
        return []

    turns = []
    for i, match in enumerate(matches):
        name_parts = match.group(1).upper().split()
        lastname = name_parts[-1]

        if lastname in SKIP or any(s in match.group(0).upper() for s in SKIP):
            continue

        speech_start = match.end()
        speech_end = matches[i+1].start() if i+1 < len(matches) else len(text)
        speech_text = text[speech_start:speech_end].strip()

        if len(speech_text) < 20:
            continue

        member_info = congress_lookup.get(lastname, {})
        party = member_info.get('party', 'Unknown')
        full_name = member_info.get('full_name', match.group(1).title())

        turns.append({
            'speaker': lastname.lower(),
            'speaker_full': full_name,
            'party': party,
            'text': speech_text[:3000],
            'is_minister': False,
        })
    return turns

def main():
    print("Loading granule index and member lookup...")
    with open(GRANULE_INDEX) as f:
        granule_idx = json.load(f)
    member_lookup = build_member_lookup()

    # Load existing results to allow resuming
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            speaker_turns = json.load(f)
        print(f"Resuming — {len(speaker_turns)} dates already done")
    else:
        speaker_turns = {}

    total = len(granule_idx)
    done = 0
    total_turns = 0
    matched = 0
    unmatched = defaultdict(int)

    dates = sorted(granule_idx.keys())

    for date in dates:
        if date in speaker_turns:
            done += 1
            continue

        v = granule_idx[date]
        pkg  = v['packageId']
        gran = v['granuleId']
        url  = f"https://www.govinfo.gov/content/pkg/{pkg}/html/{gran}.htm"

        congress_num = date_to_congress(date)
        congress_lookup = member_lookup.get(congress_num, {})

        print(f"[{done+1}/{total}] {date} (Congress {congress_num})...")
        html = fetch_html(url)

        if not html:
            speaker_turns[date] = {'turn_count': 0, 'turns': []}
            done += 1
            continue

        text = strip_html(html)
        turns = parse_turns(text, congress_lookup)

        speaker_turns[date] = {
            'turn_count': len(turns),
            'turns': turns
        }

        for t in turns:
            total_turns += 1
            if t['party'] != 'Unknown':
                matched += 1
            else:
                unmatched[t['speaker']] += 1

        done += 1

        # Save after every date
        with open(OUTPUT_PATH, 'w') as f:
            json.dump(speaker_turns, f)

        # Be polite to GovInfo
        time.sleep(0.5)

    print(f"\nDone. {total} dates processed.")
    print(f"Total turns: {total_turns:,}")
    if total_turns > 0:
        print(f"Party matched: {matched:,} ({matched/total_turns*100:.1f}%)")
    print(f"Top unmatched:")
    for spk, n in sorted(unmatched.items(), key=lambda x: -x[1])[:10]:
        print(f"  {spk}: {n}")

    print(f"\nSaved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
