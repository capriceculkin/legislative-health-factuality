"""
add_party_to_ontario_sentences.py

Adds party attribution to sentences_bill_specific.json using:
1. ontario_name_party_lookup.json (from existing db1)
2. PersonSpeaking field normalization

Also builds party from the Ontario bill index government/opposition flags.
"""
import json, os, re
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Loading data...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/sentences_bill_specific.json")) as f:
    sentences = json.load(f)

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_name_party_lookup.json")) as f:
    name_party = json.load(f)

# Also load from db1 for more coverage
db1_path = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/db1_claim_bearing.json")
if os.path.exists(db1_path):
    with open(db1_path) as f:
        db1 = json.load(f)
    # Build lastname -> party by year for better matching
    lastname_year_party = defaultdict(dict)
    for s in db1:
        full = s.get('speaker_full','').lower()
        party = s.get('party','')
        date = s.get('date','')
        if not full or not party or party == 'Unknown' or not date:
            continue
        year = date[:4]
        last = full.split()[-1] if full.split() else ''
        if last:
            lastname_year_party[last][year] = party
    print(f"Lastname->year->party: {len(lastname_year_party):,} lastnames")

def normalize_name(person_speaking):
    """Extract normalized full name from PersonSpeaking."""
    if not person_speaking:
        return "", ""
    # Remove titles
    name = re.sub(r'^(Mr\.?|Ms\.?|Mrs\.?|Hon\.?|Dr\.?|The\s+\w+)\s+', '', str(person_speaking)).strip()
    # Remove riding in parentheses
    name = re.sub(r'\s*\([^)]+\)', '', name).strip()
    full = name.lower()
    last = full.split()[-1] if full.split() else ''
    return full, last

def get_party(full_name, last_name, year):
    # Direct full name lookup
    if full_name in name_party:
        return name_party[full_name]
    # Last name + year lookup
    if last_name in lastname_year_party:
        year_map = lastname_year_party[last_name]
        if year in year_map:
            return year_map[year]
        # Try adjacent years
        for y in [str(int(year)-1), str(int(year)+1)]:
            if y in year_map:
                return year_map[y]
        # Most common party for this lastname
        if year_map:
            return Counter(year_map.values()).most_common(1)[0][0]
    return "Unknown"

print(f"Adding party to {len(sentences):,} sentences...")

matched = 0
for s in sentences:
    full, last = normalize_name(s.get('speaker_full',''))
    year = s.get('date','')[:4]
    party = get_party(full, last, year)
    s['party'] = party
    s['speaker'] = last
    s['speaker_full'] = full
    if party != 'Unknown':
        matched += 1

print(f"Party matched: {matched:,}/{len(sentences):,} ({matched/len(sentences)*100:.1f}%)")

parties = Counter(s['party'] for s in sentences)
print("\nParty distribution:")
for party, count in parties.most_common(8):
    print(f"  {count:8,}  {party}")

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/sentences_bill_specific.json")
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(sentences, f, ensure_ascii=False)
print(f"\nSaved to {out_path}")

PARTY_NORMALIZE = {
    'Conservative Party': 'Progressive Conservative Party of Ontario',
    'Conservative Party of Ontario': 'Progressive Conservative Party of Ontario', 
    'PC Party': 'Progressive Conservative Party of Ontario',
    'Ontario Party': 'Progressive Conservative Party of Ontario',
    'Liberal': 'Ontario Liberal Party',
    'NDP': 'New Democratic Party of Ontario',
    'New Democratic': 'New Democratic Party of Ontario',
}

def normalize_party(party):
    return PARTY_NORMALIZE.get(party, party)
