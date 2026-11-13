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

# Use known good bills
good_bills = ["33-2-Bill94", "33-2-Bill54", "42-2-Bill175"]
for bk in good_bills:
    if bk not in seg:
        continue
    dates = list(seg[bk].keys())
    print(f"  Bill: {bk}")
    print(f"  Title: {idx.get(bk,{}).get('title','')[:60]}")
    print(f"  Debate dates: {len(dates)}")
    for d in dates[:2]:
        paras = seg[bk][d]
        # Find paragraph with bill number in text
        anchor = next((p for p in paras if f"Bill {bk.split('Bill')[1]}" in p.get('text','')), paras[0])
        print(f"    Date: {d} | Paragraphs: {len(paras)}")
        print(f"    Topic: {anchor.get('topic','')}")
        print(f"    Speaker: {anchor.get('speaker','')}")
        print(f"    Text: {anchor.get('text','')[:150]}")
        print(f"    URL: {anchor.get('url','')[:80]}")
    print()

# Quebec examples
print("  QUEBEC examples:")
print("  File: data/canada/quebec_assembly/bill_segments/")
print("  GitHub: https://github.com/capriceculkin/legislative-health-factuality/tree/main/data/canada/quebec_assembly/bill_segments")
seg_dir = f"{REPO}/data/canada/quebec_assembly/bill_segments"
if os.path.exists(seg_dir):
    files = sorted(os.listdir(seg_dir))[:3]
    for f in files:
        path = os.path.join(seg_dir, f)
        with open(path, encoding='utf-8', errors='ignore') as fh:
            text = fh.read()[:300]
        print(f"  File: {f}")
        print(f"  Text: {text[:200]}")
        print()

# US examples
print("  US examples:")
print("  File: data/us/congressional_record_speeches/")
print("  GitHub: https://github.com/capriceculkin/legislative-health-factuality/tree/main/data/us/congressional_record_speeches")
us_dir = f"{REPO}/data/us/congressional_record_speeches"
if os.path.exists(us_dir):
    files = [f for f in sorted(os.listdir(us_dir)) if f.endswith('.txt') and '2006' in f][:2]
    for f in files:
        path = os.path.join(us_dir, f)
        with open(path, encoding='utf-8', errors='ignore') as fh:
            text = fh.read()
        # Find a good sentence
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 50]
        print(f"  File: {f}")
        print(f"  Text: {lines[0][:200] if lines else 'empty'}")
        print()

print("=== 3. PREDICATIONS EXTRACTED FROM HANSARD RECORDS ===")
print()

# Ontario - find good ones with named entities
with open(f"{REPO}/data/dbpedia_pipeline/ontario/predications.json") as f:
    on_preds = json.load(f)

good_on = [p for p in on_preds if
    len(p['subject'].split()) > 1 and
    len(p['object'].split()) > 1 and
    p['subject'][0].isupper() and
    not p['subject'].lower().startswith('those') and
    not p['subject'].lower().startswith('this') and
    not p['object'].lower().startswith('some')][:5]

print(f"  ONTARIO: {len(on_preds):,} predications total")
print(f"  File: data/dbpedia_pipeline/ontario/predications.json")
for p in good_on:
    print(f"    [{p['sentence_id']}]")
    print(f"    subject: {p['subject']} | verb: {p['verb_lemma']} | object: {p['object']}")
    print(f"    hedged: {p.get('hedged',False)}")
    ft = p.get('full_text','')
    if ft: print(f"    text: {ft[:100]}")
    print()

# Quebec - find good ones
with open(f"{REPO}/data/dbpedia_pipeline/quebec/predications.json") as f:
    qc_preds = json.load(f)

good_qc = [p for p in qc_preds if
    len(p['subject'].split()) > 1 and
    len(p['object'].split()) > 1 and
    p['subject'][0].isupper()][:5]

print(f"  QUEBEC: {len(qc_preds):,} predications total")
print(f"  File: data/dbpedia_pipeline/quebec/predications.json")
for p in good_qc:
    print(f"    [{p['sentence_id']}]")
    print(f"    subject: {p['subject']} | verb: {p['verb_lemma']} | object: {p['object']}")
    ft = p.get('full_text','')
    if ft: print(f"    text: {ft[:100]}")
    print()

# US - find good post-2000 ones
with open(f"{REPO}/data/dbpedia_pipeline/us/predications.json") as f:
    us_preds = json.load(f)

good_us = [p for p in us_preds if
    p['sentence_id'][:4] >= '2000' and
    len(p['subject'].split()) > 1 and
    len(p['object'].split()) > 1 and
    not p['subject'].startswith('GPO')][:5]

print(f"  US: {len(us_preds):,} predications total")
print(f"  File: data/dbpedia_pipeline/us/predications.json")
for p in good_us:
    print(f"    [{p['sentence_id']}]")
    print(f"    subject: {p['subject']} | verb: {p['verb_lemma']} | object: {p['object']}")
    ft = p.get('full_text','')
    if ft: print(f"    text: {ft[:100]}")
    print()

print("=== 4. SVO TRIPLES WITH DBPEDIA ENTITY RECOGNITION ===")
print()
print("NOTE: Current triples were extracted using full sentence text (more entities")
print("but introduces false positives per David's Sept 11 guidance). Pipeline is")
print("reverting to subject/object string approach. Examples below are illustrative.")
print()

for j, label in [("us","US"), ("quebec","QUEBEC"), ("ontario","ONTARIO")]:
    p = f"{REPO}/data/dbpedia_pipeline/{j}/triples_v2.json"
    if not os.path.exists(p):
        p = f"{REPO}/data/dbpedia_pipeline/{j}/triples_v2.json.checkpoint"
    if os.path.exists(p):
        with open(p) as f:
            triples = json.load(f)
        # Find good examples - named subjects
        good = [t for t in triples if
            len(t['subject'].split()) > 1 and
            not t['subject'].lower().startswith('my') and
            any('dbpedia' in u for u in t['concept_uris'])]
        print(f"  {label}: {len(triples):,} triples total")
        print(f"  File: data/dbpedia_pipeline/{j}/triples_v2.json")
        for t in good[:3]:
            print(f"    [{t['sentence_id']}]")
            print(f"    subject: {t['subject']} | verb: {t['verb']} | object: {t['object']}")
            print(f"    DBpedia URIs: {t['concept_uris'][:2]}")
            print()
    else:
        print(f"  {label}: no triples yet")
