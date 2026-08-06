import json, os

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

with open(f"{REPO}/data/dbpedia_pipeline/annotated_sentences.json") as f:
    annotated = {s["sentence_id"]: s for s in json.load(f)}

with open(f"{REPO}/data/dbpedia_pipeline/sentences.json") as f:
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
            "entities": a.get("entities", []),
            "supported": a.get("supported", False),
            "hedged": a.get("hedged", False),
        })
    else:
        db2.append({
            "sentence_id": sid,
            "date": s["date"],
            "text": s["text"],
        })

with open(f"{REPO}/data/dbpedia_pipeline/db1_claim_bearing.json", "w") as f:
    json.dump(db1, f, indent=1)

with open(f"{REPO}/data/dbpedia_pipeline/db2_non_claim_bearing.json", "w") as f:
    json.dump(db2, f, indent=1)

print(f"DB1 claim-bearing:     {len(db1)}")
print(f"DB2 non-claim-bearing: {len(db2)}")
print(f"Total:                 {len(db1)+len(db2)}")
print(f"Support rate:          {sum(1 for s in db1 if s['supported'])/len(db1)*100:.1f}%")
print(f"Hedged in DB1:         {sum(1 for s in db1 if s['hedged'])}")
