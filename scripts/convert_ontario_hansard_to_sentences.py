"""
convert_ontario_hansard_to_sentences.py

Converts the combined Ontario Hansard health bill debate rows (from HuggingFace)
into the pipeline sentences.json format with sentence_id, date, text, speaker,
party, and is_minister fields.

Splits each Intervention paragraph into individual sentences using spaCy.
Looks up party from existing Ontario member lookup data.

Input:  data/canada/ontario/hansard_health_combined.json
Output: data/canada/ontario/sentences_bill_specific.json
"""
import json, os, re
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Loading data...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/hansard_health_combined.json")) as f:
    rows = json.load(f)

print(f"Input rows: {len(rows):,}")

# ── Load party lookup from existing speaker turns ─────────────────────────────
# Use the existing ontario_speaker_turns.json which has name -> party mapping
speaker_turns_path = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_speaker_turns.json")
name_to_party = {}
name_to_minister = {}

if os.path.exists(speaker_turns_path):
    with open(speaker_turns_path) as f:
        speaker_turns = json.load(f)
    for date, data in speaker_turns.items():
        for turn in data.get("turns", []):
            name = turn.get("speaker_full", "").lower().strip()
            party = turn.get("party", "")
            is_min = turn.get("is_minister", False)
            if name and party:
                name_to_party[name] = party
                if is_min:
                    name_to_minister[name] = True
    print(f"Loaded {len(name_to_party):,} name->party mappings")
else:
    print("Warning: ontario_speaker_turns.json not found")

def extract_name(person_speaking):
    """Extract normalized name from PersonSpeaking field.
    
    Handles formats like:
    - 'Mr Mario Sergio (York West)'
    - 'Hon. Mike Harris (Premier)'
    - 'Ms. Frances Lankin'
    - 'The Speaker (Hon Gary Carr)'
    """
    if not person_speaking:
        return "", False
    
    # Remove titles
    name = re.sub(r'^(Mr\.?|Ms\.?|Mrs\.?|Hon\.?|Dr\.?)\s+', '', person_speaking).strip()
    
    # Extract name before parenthesis
    name = re.sub(r'\s*\([^)]+\)', '', name).strip()
    
    # Check if minister (Hon prefix or Premier/Minister in original)
    is_minister = bool(re.search(r'\bHon\b|\bPremier\b|\bMinister\b', person_speaking, re.IGNORECASE))
    
    return name.lower(), is_minister

def lookup_party(name, is_minister_hint):
    """Look up party for a speaker name."""
    if not name:
        return "Unknown"
    
    # Direct lookup
    if name in name_to_party:
        return name_to_party[name]
    
    # Try last name only
    last = name.split()[-1] if name.split() else ""
    matches = {v for k, v in name_to_party.items() if k.endswith(last) and last}
    if len(matches) == 1:
        return matches.pop()
    
    return "Unknown"

# ── Sentence tokenization ─────────────────────────────────────────────────────
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    nlp.max_length = 2000000
    USE_SPACY = False
    print("Using spaCy for sentence tokenization")
except:
    USE_SPACY = False
    print("spaCy not available, using simple sentence splitting")

def split_sentences(text):
    """Split paragraph text into sentences."""
    if not text:
        return []
    text = str(text).strip()
    if USE_SPACY:
        doc = nlp(text[:10000])  # cap to avoid memory issues
        return [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 20]
    else:
        # Simple split on period/question/exclamation
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        return [s.strip() for s in sentences if len(s.strip()) > 20]

# ── Convert rows to sentences ─────────────────────────────────────────────────
sentences = []
unknown_party = 0
total_rows = len(rows)

for i, row in enumerate(rows):
    if i % 5000 == 0:
        print(f"  Processing row {i:,}/{total_rows:,} | {len(sentences):,} sentences")
    
    date = row.get("Date", "")
    intervention = str(row.get("Intervention", "")).strip()
    person = row.get("PersonSpeaking", "")
    subject = row.get("SubjectofBusiness", "")
    
    if not date or not intervention or len(intervention) < 20:
        continue
    
    # Skip procedural rows that slipped through
    if re.match(r'^(Motion agreed|The House adjourned|Prayers\.|Interjection)', intervention):
        continue
    
    name, is_minister_hint = extract_name(person)
    party = lookup_party(name, is_minister_hint)
    is_minister = is_minister_hint or name in name_to_minister
    
    if party == "Unknown":
        unknown_party += 1
    
    # Split into sentences
    sents = split_sentences(intervention)
    
    for j, sent_text in enumerate(sents):
        sentence_id = f"{date.replace('-','')}-hf{i}-{j}"
        sentences.append({
            "sentence_id": sentence_id,
            "date": date,
            "text": sent_text,
            "speaker": name.split()[-1] if name else "",
            "speaker_full": name,
            "party": party,
            "is_minister": is_minister,
            "subject": subject,
            "source": "huggingface_hansard"
        })

print(f"\nConversion complete:")
print(f"  Input rows: {len(rows):,}")
print(f"  Output sentences: {len(sentences):,}")
print(f"  Unknown party: {unknown_party:,} ({unknown_party/len(rows)*100:.1f}% of rows)")

dates = sorted(set(s["date"] for s in sentences))
print(f"  Date range: {dates[0]} to {dates[-1]}")

# Party distribution
from collections import Counter
parties = Counter(s["party"] for s in sentences)
print(f"\nParty distribution:")
for party, count in parties.most_common(10):
    print(f"  {count:8,}  {party}")

# Save
out_path = os.path.join(REPO_ROOT, "data/canada/ontario/sentences_bill_specific.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(sentences, f, ensure_ascii=False)
print(f"\nSaved to {out_path}")
print(f"File size: {os.path.getsize(out_path)/1024/1024:.1f}MB")
