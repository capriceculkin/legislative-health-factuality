"""
extract_speaker_turns_us.py

Parses US Congressional Record speech files to extract speaker turns
with party attribution. Uses member_lookup.json to match speaker surnames
to party affiliation by congress number.

Congressional Record speaker label format:
  Mr. SMITH. [speech text]
  Ms. JONES of California. [speech text]
  Mrs. BROWN. [speech text]

Output: data/us/us_speaker_turns.json

Usage: python3 scripts/extract_speaker_turns_us.py
"""
import os, re, json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEECHES_DIR = os.path.join(REPO_ROOT, "data/us/congressional_record_speeches")
MEMBER_LOOKUP_PATH = os.path.join(REPO_ROOT, "data/us/member_lookup.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/us/us_speaker_turns.json")

# Match speaker labels like "Mr. SMITH." or "Ms. JONES of California."
SPEAKER_RE = re.compile(
    r'(?:Mr\.|Ms\.|Mrs\.)\s+([A-Z][A-Za-z\-\']+(?:\s+[A-Z][A-Za-z\-\']+)?)(?:\s+of\s+[A-Za-z\s]+)?[,\.][ \t]'
)

SKIP_SPEAKERS = {
    'SPEAKER', 'CHAIR', 'CLERK', 'PRESIDENT', 'PRESIDING',
    'ACTING', 'CHAPLAIN', 'VICE', 'CHAIRMAN', 'MR', 'MS', 'MRS',
    'SPEAKER PRO', 'CHAIR PRO', 'TEMPORORE', 'TEMPORE',
}

def date_to_congress(date_str):
    year = int(date_str[:4])
    month = int(date_str[5:7])
    # New congress starts Jan 3 of odd years
    if year % 2 == 1 and month >= 1:
        return str(98 + (year - 1983) // 2)
    else:
        return str(98 + (year - 1984) // 2)

def build_member_lookup():
    with open(MEMBER_LOOKUP_PATH) as f:
        data = json.load(f)
    lookup = {}
    for congress_num, members in data.get('by_congress', {}).items():
        lookup[congress_num] = {}
        for member in members:
            full_name = member.get('full_name', '')
            if not full_name:
                continue
            last = full_name.split()[-1].upper()
            lookup[congress_num][last] = {
                'party': member.get('party', 'Unknown'),
                'full_name': full_name,
                'state': member.get('state', ''),
            }
    return lookup

def parse_speech_file(filepath, congress_lookup):
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return []

    # Join OCR-split lines
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    text = re.sub(r'(\w)\n(\w)', r'\1 \2', text)

    # Find all speaker label positions
    matches = list(SPEAKER_RE.finditer(text))
    if not matches:
        return []

    turns = []
    for i, match in enumerate(matches):
        # Handle multi-word names like "Gene Green" or "Jackson-Lee"
        name_parts = match.group(1).upper().split()
        lastname = name_parts[-1]  # use last word as surname

        if lastname in SKIP_SPEAKERS:
            continue

        # Speech text runs from end of label to start of next label
        speech_start = match.end()
        speech_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        speech_text = text[speech_start:speech_end].strip()

        if len(speech_text) < 20:
            continue

        member_info = congress_lookup.get(lastname, {})
        party = member_info.get('party', 'Unknown')
        full_name = member_info.get('full_name', lastname.title())

        turns.append({
            'speaker': lastname.lower(),
            'speaker_full': full_name,
            'party': party,
            'text': speech_text[:3000],
            'is_minister': False,
        })

    return turns

def main():
    print("Building member lookup by congress...")
    member_lookup = build_member_lookup()
    congresses = sorted(member_lookup.keys(), key=int)
    print(f"Congresses: {congresses[0]} to {congresses[-1]}")

    speech_files = sorted([
        f for f in os.listdir(SPEECHES_DIR)
        if f.endswith('.txt') and re.match(r'\d{4}-\d{2}-\d{2}', f)
    ])
    print(f"Speech files: {len(speech_files)}")

    speaker_turns = {}
    total_turns = 0
    matched = 0
    unmatched = defaultdict(int)

    for fname in speech_files:
        date = fname.replace('.txt', '')
        congress_num = date_to_congress(date)
        congress_lookup = member_lookup.get(congress_num, {})
        filepath = os.path.join(SPEECHES_DIR, fname)
        turns = parse_speech_file(filepath, congress_lookup)

        if turns:
            speaker_turns[date] = {'turn_count': len(turns), 'turns': turns}
            total_turns += len(turns)
            for t in turns:
                if t['party'] != 'Unknown':
                    matched += 1
                else:
                    unmatched[t['speaker']] += 1

    print(f"\nDates with turns: {len(speaker_turns)}/{len(speech_files)}")
    print(f"Total turns: {total_turns:,}")
    print(f"Party matched: {matched:,} ({matched/max(total_turns,1)*100:.1f}%)")
    print(f"Top unmatched:")
    for spk, n in sorted(unmatched.items(), key=lambda x: -x[1])[:10]:
        print(f"  {spk}: {n}")

    # Sample
    for date, data in list(speaker_turns.items())[:1]:
        print(f"\nSample ({date}):")
        for t in data['turns'][:3]:
            print(f"  {t['speaker_full']} ({t['party']}): {t['text'][:80]}")

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(speaker_turns, f)
    print(f"\nSaved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()