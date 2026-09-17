import json

with open("data/dbpedia_pipeline/dbpedia_results.json") as f:
    cache = json.load(f)

total = len(cache)
with_evidence = sum(1 for v in cache.values() if v)
empty = sum(1 for v in cache.values() if v == [])
none_val = sum(1 for v in cache.values() if v is None)

print(f"Total cached pairs: {total}")
print(f"With evidence:      {with_evidence}")
print(f"Empty list []:      {empty}")
print(f"None:               {none_val}")

# show a sample entry
sample_key = next(iter(cache))
print(f"\nSample key: {sample_key}")
print(f"Sample value: {cache[sample_key]}")
