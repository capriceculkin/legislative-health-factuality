import json, re

REPO = '/Users/caprice/MiscellaneousProjects/legislative-health-factuality'

with open(f'{REPO}/data/dbpedia_pipeline/quebec/unique_pairs.json') as f:
    pairs = json.load(f)

entity_names = set(uri.split('/')[-1] for p in pairs for uri in p)
print(f'Entities: {len(entity_names)}')

with open(f'{REPO}/data/dbpedia_pipeline/quebec/dbpedia_results.json') as f:
    cache = json.load(f)

print(f'Cache loaded: {len(cache)} pairs, {sum(1 for v in cache.values() if v)} with evidence')

TRIPLE_RE = re.compile(r'<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>')
found = 0

print('Streaming /tmp/page_links_fr.ttl...')
with open('/tmp/page_links_fr.ttl', encoding='utf-8', errors='replace') as f:
    for i, line in enumerate(f):
        if i % 2000000 == 0:
            print(f'  {i:,} lines, {found} new matches')
        m = TRIPLE_RE.search(line)
        if not m:
            continue
        s_name = m.group(1).split('/')[-1]
        o_name = m.group(3).split('/')[-1]
        if s_name not in entity_names or o_name not in entity_names:
            continue
        pred = m.group(2)
        sf = f'http://fr.dbpedia.org/resource/{s_name}'
        of = f'http://fr.dbpedia.org/resource/{o_name}'
        key = f'{sf}|{of}'
        alt = f'{of}|{sf}'
        if key in cache:
            if pred not in cache[key]:
                cache[key].append(pred)
                found += 1
        elif alt in cache:
            if pred not in cache[alt]:
                cache[alt].append(pred)
                found += 1

print(f'New matches: {found}')
with open(f'{REPO}/data/dbpedia_pipeline/quebec/dbpedia_results.json', 'w') as f:
    json.dump(cache, f)
with_ev = sum(1 for v in cache.values() if v)
print(f'Total with evidence: {with_ev}/{len(cache)} ({with_ev/len(cache)*100:.1f}%)')
