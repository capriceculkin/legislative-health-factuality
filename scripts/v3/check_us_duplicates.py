#!/usr/bin/env python3
"""
check_us_duplicates.py   (reads only)
1. US bill-days listed twice in segments_index.json (two votes can point to the same debate day)
2. whether those days' sentences and claims are stored twice
3. bill-days that were in the index before the floor-days run but are not now (H.R. 2454, Oct 31, 1991)
Run from the project folder:  python3 scripts/v3/check_us_duplicates.py
"""
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def key(e):
    return (e["bill_key"], e["debate_date"])


new = load("data", "us", "v3", "segments_index.json")
c = collections.Counter(key(e) for e in new)
dups = sorted(k for k, n in c.items() if n > 1)
print(f"1. index entries: {len(new)}; distinct bill-days: {len(c)}; bill-days listed twice: {len(dups)}")
for k in dups:
    srcs = [e["date_source"] + " (vote " + e["vote_date"] + ")" for e in new if key(e) == k]
    print(f"     {k[0]} {k[1]}: {', '.join(srcs)}")

s = load("data", "dbpedia_pipeline", "us", "sentences_v3.json")
sc = collections.Counter(x["sentence_id"] for x in s)
extra_s = sum(n - 1 for n in sc.values() if n > 1)
days_s = sorted({"|".join(i.split("|")[1:3]) for i, n in sc.items() if n > 1})
print(f"\n2. US sentences: {len(s):,}; extra copies of the same sentence: {extra_s:,} on {len(days_s)} bill-days")
p = load("data", "dbpedia_pipeline", "us", "predications_v3.json")
pc = collections.Counter((x.get("sentence_id"), x.get("subject"), x.get("verb"), x.get("object")) for x in p)
extra_p = sum(n - 1 for n in pc.values() if n > 1)
print(f"   US claims: {len(p):,}; extra copies of the same claim: {extra_p:,}")

try:
    old = load("data", "us", "v3", "segments_index_before_floordays.json")
    lost = sorted(set(map(key, old)) - set(map(key, new)))
    print(f"\n3. bill-days in the index before the floor-days run but not now: {len(lost)}")
    for k in lost[:20]:
        print(f"     {k[0]} {k[1]}")
    print("   H.R. 2454 before the run:", sorted(k[1] for k in map(key, old) if k[0] == "102-HR2454"),
          "| now:", sorted(k[1] for k in map(key, new) if k[0] == "102-HR2454"))
except OSError:
    print("\n3. no copy of the index from before the floor-days run was found")
