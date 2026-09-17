import json, random
random.seed(42)
REPO="/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments_clean.json") as f:
    ont=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/predications.json") as f:
    us_pred=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/predications.json") as f:
    qc_pred=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/sentences.json") as f:
    us_sents=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/sentences.json") as f:
    qc_sents=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/annotated_sentences.json") as f:
    us_ann=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/annotated_sentences.json") as f:
    qc_ann=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/factuality_scores.json") as f:
    us_scores=json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/factuality_scores.json") as f:
    qc_scores=json.load(f)

good_us=[p for p in us_pred if len(p.get("subject",""))>5 and len(p.get("object",""))>8
         and p.get("verb_lemma","") not in ["be","have","do","get","say"] and not p.get("hedged")]
good_qc=[p for p in qc_pred if len(p.get("subject",""))>5 and len(p.get("object",""))>8
         and p.get("verb_lemma","") not in ["etre","avoir","faire","aller"]]
random.shuffle(good_us); random.shuffle(good_qc)

supported_us=[s for s in us_ann if s.get("supported") and s.get("concept_uris")]
not_supported_us=[s for s in us_ann if not s.get("supported") and s.get("concept_uris") and len(s.get("concept_uris",[]))>=2]

print("=== US PREDICATION EXAMPLES ===")
for p in good_us[:3]:
    print(f"TEXT: {p['full_text'][:150]}")
    print(f"  subject: {p['subject']}")
    print(f"  verb: {p['verb_lemma']}")
    print(f"  object: {p['object']}")
    print()

print("=== QC PREDICATION EXAMPLES ===")
for p in good_qc[:3]:
    print(f"TEXT: {p['full_text'][:150]}")
    print(f"  sujet: {p['subject']}")
    print(f"  verbe: {p['verb_lemma']}")
    print(f"  objet: {p['object']}")
    print()

print("=== SUPPORTED SENTENCE EXAMPLE ===")
for s in supported_us[:2]:
    print(f"TEXT: {s.get('text','')[:150]}")
    uris=[u.split('/')[-1] for u in s.get('concept_uris',[])[:2]]
    print(f"  entities: {uris}")
    print(f"  supported: True")
    print()

print("=== NOT SUPPORTED EXAMPLE ===")
for s in not_supported_us[:2]:
    print(f"TEXT: {s.get('text','')[:150]}")
    uris=[u.split('/')[-1] for u in s.get('concept_uris',[])[:2]]
    print(f"  entities: {uris}")
    print(f"  supported: False")
    print()

print("=== ONTARIO BILL 94 PARAS ===")
paras=ont.get("1985-Bill94",{}).get("1986-01-14",[])
texts=[p if isinstance(p,str) else p.get("text","") for p in paras]
for t in [x for x in texts if len(x)>150][:3]:
    print(t[:250])
    print()

print("=== FACTUALITY SCORE EXAMPLES ===")
import random
sample=random.sample(list(us_scores.items()),3)
for date,v in sample:
    print(f"US {date}: score={v.get('factuality_score',0):.3f} supported={v.get('supported_sentences',0)} total={v.get('total_sentences',0)} outcome={v.get('vote_result','')}")
