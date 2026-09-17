"""
convert_ontario_api_segments_to_sentences.py

Converts Ontario API bill segments to pipeline sentences.json format.
Handles both plain string paragraphs (old format) and dict paragraphs
{"text": ..., "speaker": ...} (new format with speaker info).

Output: data/canada/ontario/sentences_bill_specific_api.json
"""
import json, os, re
from collections import defaultdict, Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Loading segments...")
with open(os.path.join(REPO_ROOT, "data/canada/ontario/hansard_api_bill_segments.json")) as f:
    segments = json.load(f)

print(f"Bills: {len(segments)}")

# Load name->party lookup
name_to_party = defaultdict(dict)
db1_path = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/db1_claim_bearing.json")
if os.path.exists(db1_path):
    with open(db1_path) as f:
        db1 = json.load(f)
    for s in db1:
        name = s.get("speaker_full", "").lower().strip()
        party = s.get("party", "")
        year = s.get("date", "")[:4]
        if name and party and party != "Unknown":
            name_to_party[name][year] = party
    print(f"Loaded party lookup: {len(name_to_party)} names")

PARTY_NORM = {
    "Conservative Party": "Progressive Conservative Party of Ontario",
    "Ontario Party": "Progressive Conservative Party of Ontario",
    "Independent-Conservative": "Progressive Conservative Party of Ontario",
    "Liberal": "Ontario Liberal Party",
    "NDP": "New Democratic Party of Ontario",
}

def get_party(speaker_raw, year):
    if not speaker_raw:
        return "Unknown"
    # Extract name from "Mr. John Smith (Riding)" format
    name = re.sub(r"^(Mr\.?|Ms\.?|Mrs\.?|Hon\.?|Dr\.?)\s+", "", speaker_raw).strip()
    name = re.sub(r"\s*\([^)]+\)", "", name).strip().lower()
    if not name:
        return "Unknown"
    # Direct lookup
    if name in name_to_party:
        yd = name_to_party[name]
        if year in yd:
            return PARTY_NORM.get(yd[year], yd[year])
        # Closest year
        years = sorted(yd.keys())
        if years:
            closest = min(years, key=lambda y: abs(int(y) - int(year)))
            return PARTY_NORM.get(yd[closest], yd[closest])
    # Try last name
    last = name.split()[-1] if name.split() else ""
    matches = {k: v for k, v in name_to_party.items() if k.endswith(last) and last}
    if len(matches) == 1:
        yd = list(matches.values())[0]
        p = yd.get(year) or (list(yd.values())[0] if yd else "Unknown")
        return PARTY_NORM.get(p, p)
    return "Unknown"

def split_sentences(text):
    if not text:
        return []
    text = str(text).strip()
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in sents if len(s.strip()) > 20]

sentences = []
total_paras = 0

for bill_key, date_data in segments.items():
    for date, paragraphs in date_data.items():
        year = date[:4]
        for para_idx, para_item in enumerate(paragraphs):
            # Handle both formats
            if isinstance(para_item, dict):
                para_text = para_item.get("text", "")
                speaker_raw = para_item.get("speaker", "")
            else:
                para_text = str(para_item)
                speaker_raw = ""

            total_paras += 1
            party = get_party(speaker_raw, year)

            sents = split_sentences(para_text)
            date_str = date.replace("-", "")
            bill_str = bill_key.replace("-", "").replace("Bill", "b")

            for sent_idx, sent_text in enumerate(sents):
                sentence_id = f"{date_str}-api-{bill_str}-p{para_idx}-s{sent_idx}"
                sentences.append({
                    "sentence_id": sentence_id,
                    "date": date,
                    "text": sent_text,
                    "speaker": speaker_raw.split("(")[0].strip() if speaker_raw else "",
                    "speaker_full": speaker_raw,
                    "party": party,
                    "is_minister": bool(speaker_raw and ("Hon." in speaker_raw or "Minister" in speaker_raw)),
                    "bill_key": bill_key,
                    "source": "ola_api"
                })

print(f"\nConversion complete:")
print(f"  Input paragraphs: {total_paras:,}")
print(f"  Output sentences: {len(sentences):,}")

dates = sorted(set(s["date"] for s in sentences))
print(f"  Date range: {dates[0]} to {dates[-1]}")
print(f"  Unique bills: {len(set(s['bill_key'] for s in sentences))}")

parties = Counter(s["party"] for s in sentences)
print(f"  Party distribution:")
for p, n in parties.most_common(6):
    print(f"    {n:8,}  {p}")

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/sentences_bill_specific_api.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(sentences, f, ensure_ascii=False)
print(f"\nSaved to {out_path}")
print(f"File size: {os.path.getsize(out_path)/1024/1024:.1f}MB")
