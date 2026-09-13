"""
convert_quebec_segments_to_sentences.py

Converts Quebec bill segment text files into the pipeline sentences.json format.
Each segment file contains the debate text for one bill on one date.
Speaker turns are extracted using the Quebec speaker pattern (M./Mme name:).

Output: data/dbpedia_pipeline/quebec/sentences_bill_specific.json
"""
import os, re, json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEGMENTS_DIR = os.path.join(REPO_ROOT, "data/canada/quebec_assembly/bill_segments")
INDEX_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_bill_segments_index.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/quebec/sentences_bill_specific.json")

# Load existing Quebec sentences for party lookup
SENTENCES_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/quebec/sentences.json")
name_to_party = {}
if os.path.exists(SENTENCES_PATH):
    with open(SENTENCES_PATH) as f:
        existing = json.load(f)
    for s in existing:
        name = s.get('speaker', '').lower()
        party = s.get('party', '')
        year = s.get('date', '')[:4]
        if name and party and party != 'Unknown':
            name_to_party[(name, year)] = party
    print(f"Loaded {len(name_to_party):,} name->party mappings from existing sentences")

# Load bill segments index
with open(INDEX_PATH) as f:
    idx = json.load(f)

# Build date+bill lookup
date_bill_to_file = {}
for bill_num, dates in idx.items():
    for date, info in dates.items():
        date_bill_to_file[(date, bill_num)] = info['segment_file']

print(f"Bill segments: {len(date_bill_to_file):,} date-bill combinations")

# Speaker pattern for Quebec: "M. Lastname:" or "Mme Lastname:" or "Le Président:"
SPEAKER_RE = re.compile(
    r'^(?:M\.|Mme|Le\s+[Pp]r[ée]sident(?:e)?|La\s+[Pp]r[ée]sidente?|'
    r'M\.\s+le\s+[Pp]r[ée]sident|Mme\s+la\s+[Pp]r[ée]sidente?)\s+'
    r'([A-ZÀ-Ÿ][a-zà-ÿA-ZÀ-Ÿ\-\']+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿA-ZÀ-Ÿ\-\']+)?)\s*:',
    re.MULTILINE
)

def get_party(speaker_name, year):
    name_lower = speaker_name.lower()
    if (name_lower, year) in name_to_party:
        return name_to_party[(name_lower, year)]
    # Try adjacent years
    for y in [str(int(year)-1), str(int(year)+1)]:
        if (name_lower, y) in name_to_party:
            return name_to_party[(name_lower, y)]
    return 'Unknown'

def split_sentences(text):
    """Simple sentence splitting on French text."""
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ÿ«])', text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]

def extract_turns(text, date, bill_num):
    """Extract speaker turns from segment text."""
    turns = []
    year = date[:4]

    matches = list(SPEAKER_RE.finditer(text))
    if not matches:
        # No speaker labels — treat whole segment as one block
        sents = split_sentences(text)
        for j, sent in enumerate(sents):
            turns.append({
                'speaker': 'unknown',
                'speaker_full': 'unknown',
                'party': 'Unknown',
                'is_minister': False,
                'text': sent,
                'sentence_idx': j
            })
        return turns

    for i, match in enumerate(matches):
        speaker_name = match.group(1)
        is_president = bool(re.search(r'[Pp]r[ée]sident', match.group(0)))

        # Get speech text
        speech_start = match.end()
        speech_end = matches[i+1].start() if i+1 < len(matches) else len(text)
        speech_text = text[speech_start:speech_end].strip()

        if len(speech_text) < 20:
            continue

        party = get_party(speaker_name, year)
        is_minister = 'ministre' in match.group(0).lower()

        sents = split_sentences(speech_text)
        for j, sent in enumerate(sents):
            turns.append({
                'speaker': speaker_name.lower().split()[-1],
                'speaker_full': speaker_name.lower(),
                'party': party,
                'is_minister': is_minister,
                'text': sent,
                'sentence_idx': j
            })

    return turns

print("Processing segments...")
sentences = []
processed = 0
errors = 0

for (date, bill_num), seg_file in sorted(date_bill_to_file.items()):
    fpath = os.path.join(SEGMENTS_DIR, seg_file)
    if not os.path.exists(fpath):
        errors += 1
        continue

    try:
        with open(fpath, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception as e:
        errors += 1
        continue

    turns = extract_turns(text, date, bill_num)
    date_str = date.replace('-', '')

    for t_idx, turn in enumerate(turns):
        sentence_id = f"{date_str}-bill{bill_num}-t{t_idx}-s{turn['sentence_idx']}"
        sentences.append({
            'sentence_id': sentence_id,
            'date': date,
            'text': turn['text'],
            'speaker': turn['speaker'],
            'speaker_full': turn['speaker_full'],
            'party': turn['party'],
            'is_minister': turn['is_minister'],
            'bill_number': bill_num,
            'source': 'bill_segment'
        })

    processed += 1
    if processed % 500 == 0:
        print(f"  {processed:,}/{len(date_bill_to_file):,} segments processed | {len(sentences):,} sentences")

print(f"\nDone:")
print(f"  Segments processed: {processed:,}")
print(f"  Errors: {errors:,}")
print(f"  Total sentences: {len(sentences):,}")

from collections import Counter
dates = sorted(set(s['date'] for s in sentences))
print(f"  Date range: {dates[0]} to {dates[-1]}")
parties = Counter(s['party'] for s in sentences)
print(f"  Party distribution:")
for p, n in parties.most_common(8):
    print(f"    {n:8,}  {p}")

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(sentences, f, ensure_ascii=False)
print(f"\nSaved to {OUTPUT_PATH}")
print(f"File size: {os.path.getsize(OUTPUT_PATH)/1024/1024:.1f}MB")
