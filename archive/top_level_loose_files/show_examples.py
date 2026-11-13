import json, os

REPO = "."

print("=== 1. SESSION-BASED BILL ALIGNMENT ===")
print("File: data/canada/ontario/ontario_bill_index.json")
print("GitHub: https://github.com/capriceculkin/legislative-health-factuality/blob/main/data/canada/ontario/ontario_bill_index.json")
print()

with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    idx = json.load(f)

health = {k:v for k,v in idx.items() if v.get("health_tag")}
print(f"Total health bills: {len(health)}")
print()

for k in ["33-2-Bill94", "34-2-Bill52", "42-2-Bill175", "35-3-Bill50", "33-2-Bill113"]:
    if k in idx:
        v = idx[k]
        print(f"  Key: {k}")
        print(f"  Title: {v.get('title','')[:80]}")
        print(f"  Session: {v.get('session')}")
        print(f"  Debate dates: {v.get('dates',[])[:3]}")
        print()

print("=== 2. DAY-BASED BILL-SPEECH ALIGNMENT ===")
print("File: data/canada/ontario/hansard_api_bill_segments.json")
print("Yale OneDrive: https://yaleedu-my.sharepoint.com/:u:/g/personal/caprice_culkin_yale_edu/IQCAGMCyyH_0ToGTWu1erpwpAV8Bcot0NVoBJZ5BJPxiTYI?e=NO1Els")
print()

with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments.json") as f:
    seg = json.load(f)

print(f"Total bills: {len(seg)}")
total_paras = sum(len(p) for d in seg.values() for p in d.values())
print(f"Total paragraphs: {total_paras:,}")
print()

for bk in list(seg.keys())[:3]:
    dates = list(seg[bk].keys())
    print(f"  Bill: {bk}")
    print(f"  Debate dates: {len(dates)}")
    for d in dates[:2]:
        paras = seg[bk][d]
        print(f"    Date: {d} | Paragraphs: {len(paras)}")
        p = paras[0]
        print(f"    Topic: {p.get('topic','')}")
        print(f"    Speaker: {p.get('speaker','')}")
        print(f"    Text: {p.get('text','')[:120]}")
        print(f"    Session: {p.get('session','')} | URL: {p.get('url','')[:60]}")
    print()

print("=== 3. PREDICATIONS EXTRACTED FROM HANSARD RECORDS ===")
print("File: data/dbpedia_pipeline/ontario/predications.json")
print()

for j in ["ontario", "us", "quebec"]:
    p = f"{REPO}/data/dbpedia_pipeline/{j}/predications.json"
    if os.path.exists(p):
        with open(p) as f:
            preds = json.load(f)
        print(f"  {j.upper()}: {len(preds):,} predications")
        for pred in preds[:3]:
            print(f"    sentence_id: {pred['sentence_id']}")
            print(f"    subject: {pred['subject']}")
            print(f"    verb: {pred['verb_lemma']}")
            print(f"    object: {pred['object']}")
            print(f"    hedged: {pred.get('hedged',False)}")
            ft = pred.get('full_text','')
            if ft:
                print(f"    full text: {ft[:100]}")
            print()

print("=== 4. SVO TRIPLES WITH DBPEDIA ENTITY RECOGNITION ===")
print()

for j in ["us", "quebec", "ontario"]:
    p = f"{REPO}/data/dbpedia_pipeline/{j}/triples_v2.json.checkpoint"
    if os.path.exists(p):
        with open(p) as f:
            triples = json.load(f)
        print(f"  {j.upper()}: {len(triples):,} triples")
        for t in triples[-3:]:
            print(f"    sentence_id: {t['sentence_id']}")
            print(f"    subject: {t['subject']}")
            print(f"    verb: {t['verb']}")
            print(f"    object: {t['object']}")
            print(f"    hedged: {t.get('hedged',False)}")
            print(f"    DBpedia URIs: {t['concept_uris'][:3]}")
            print()
    else:
        print(f"  {j.upper()}: no checkpoint yet")
