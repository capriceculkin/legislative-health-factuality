import json, os

import os

import unicodedata

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
JURISDICTION = os.environ.get("JURISDICTION", "us")
WORK_DIR = f"{REPO}/data/dbpedia_pipeline/{JURISDICTION}"

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()

# build speaker full name lookup for Ontario
name_lookup = {}
ont_members_path = os.path.join(REPO, "data/canada/ontario_members.json")
if os.path.exists(ont_members_path):
    with open(ont_members_path) as f:
        members = json.load(f)
    for m in members:
        raw = m.get("name", "")
        if "," in raw:
            last = raw.split(",")[0].strip()
            first = raw.split(",")[1].strip()
            full = f"{first} {last}"
            key = strip_accents(last).lower()
            name_lookup[key] = full
with open(f"{WORK_DIR}/annotated_sentences.json") as f:
    annotated = {s["sentence_id"]: s for s in json.load(f)}

with open(f"{WORK_DIR}/sentences.json") as f:
    all_sents = json.load(f)

db1 = []  # claim-bearing (has 2+ grounded entities)
db2 = []  # non-claim-bearing (no grounded entities)

for s in all_sents:
    sid = s["sentence_id"]
    if sid in annotated:
        a = annotated[sid]
        db1.append({
            "sentence_id": sid,
            "date": s["date"],
            "text": s["text"],
            "speaker": s.get("speaker", ""),
            "party": s.get("party", ""),
            "is_minister": s.get("is_minister", False),
            "concept_uris": a.get("concept_uris", []),
            "supported": a.get("supported", False),
            "hedged": a.get("hedged", False),
                        "speaker_full": name_lookup.get(strip_accents(s.get("speaker", "")), s.get("speaker", "")),
        })
    else:
        db2.append({
            "sentence_id": sid,
            "date": s["date"],
            "text": s["text"],
            "speaker": s.get("speaker", ""),
            "party": s.get("party", ""),
        })

with open(f"{WORK_DIR}/db1_claim_bearing.json", "w") as f:
    json.dump(db1, f, indent=1)

with open(f"{WORK_DIR}/db2_non_claim_bearing.json", "w") as f:
    json.dump(db2, f, indent=1)

print(f"DB1 claim-bearing:     {len(db1)}")
print(f"DB2 non-claim-bearing: {len(db2)}")
print(f"Total:                 {len(db1)+len(db2)}")
print(f"Support rate:          {sum(1 for s in db1 if s['supported'])/len(db1)*100:.1f}%")
print(f"Hedged in DB1:         {sum(1 for s in db1 if s['hedged'])}")
