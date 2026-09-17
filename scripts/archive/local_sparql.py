"""
local_sparql.py

Streams French DBpedia TTL files line by line and finds connections
between Quebec entity pairs. Uses almost no RAM.
"""
import json, re, os

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

print("Loading pairs...")
with open(f"{REPO}/data/dbpedia_pipeline/quebec/unique_pairs.json") as f:
    pairs = json.load(f)

def uri_to_name(uri):
    return uri.split('/')[-1]

entity_names = set()
for p in pairs:
    entity_names.add(uri_to_name(p[0]))
    entity_names.add(uri_to_name(p[1]))

print(f"Unique entities to match: {len(entity_names)}")

results_path = f"{REPO}/data/dbpedia_pipeline/quebec/dbpedia_results.json"
if os.path.exists(results_path):
    with open(results_path) as f:
        cache = json.load(f)
else:
    cache = {f"{p[0]}|{p[1]}": [] for p in pairs}

print(f"Existing cache: {len(cache)} pairs, {sum(1 for v in cache.values() if v)} with evidence")

TTL_FILES = [
    "/tmp/mappingbased_objects_fr.ttl", "/tmp/infobox_fr_fixed.ttl", "/tmp/page_links_fr.ttl",
]

TRIPLE_RE = re.compile(r'<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>')

found = 0
for ttl_file in TTL_FILES:
    if not os.path.exists(ttl_file):
        print(f"Missing: {ttl_file}")
        continue
    print(f"Streaming {ttl_file}...")
    with open(ttl_file, encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f):
            if i % 1000000 == 0:
                print(f"  {i:,} lines, {found} matches so far")
            m = TRIPLE_RE.search(line)
            if not m:
                continue
            subj, pred, obj = m.group(1), m.group(2), m.group(3)
            s_name = subj.split('/')[-1]
            o_name = obj.split('/')[-1]
            if s_name not in entity_names or o_name not in entity_names:
                continue
            s_fr = f"http://fr.dbpedia.org/resource/{s_name}"
            o_fr = f"http://fr.dbpedia.org/resource/{o_name}"
            key = f"{s_fr}|{o_fr}"
            alt = f"{o_fr}|{s_fr}"
            k = key if key in cache else (alt if alt in cache else None)
            if k and pred not in cache[k]:
                cache[k].append(pred)
                found += 1

print(f"Total new matches: {found}")
with open(results_path, 'w') as f:
    json.dump(cache, f)
print(f"Saved to {results_path}")
with_ev = sum(1 for v in cache.values() if v)
print(f"Total with evidence: {with_ev}/{len(cache)} ({with_ev/len(cache)*100:.1f}%)")