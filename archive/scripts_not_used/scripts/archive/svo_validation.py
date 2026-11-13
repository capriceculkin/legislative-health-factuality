import json, random
random.seed(42)

with open("data/dbpedia_pipeline/triples.json") as f:
    triples = json.load(f)
with open("data/dbpedia_pipeline/sentences.json") as f:
    sents = {s["sentence_id"]: s["text"] for s in json.load(f)}

health_terms = [
    "health", "medicare", "medicaid", "drug", "hospital",
    "disease", "patient", "medical", "fda", "cancer",
    "insurance", "vaccine", "aids", "hiv", "supplement",
    "pharmaceutical", "nursing", "physician", "clinical"
]

health_triples = []
for t in triples:
    uris = " ".join(t.get("concept_uris", [])).lower()
    text = sents.get(t["sentence_id"], "").lower()
    if any(term in uris or term in text for term in health_terms):
        health_triples.append(t)

print(f"Health-relevant triples: {len(health_triples)}")
sample = random.sample(health_triples, min(15, len(health_triples)))

for t in sample:
    sid = t["sentence_id"]
    text = sents.get(sid, "?")
    entities = [u.split("/")[-1] for u in t.get("concept_uris", [])]
    print(f"DATE: {sid[:10]}")
    print(f"TEXT: {text[:200]}")
    print(f"VERB: {t.get('verb', '')}")
    print(f"ENTITIES: {entities}")
    print()
