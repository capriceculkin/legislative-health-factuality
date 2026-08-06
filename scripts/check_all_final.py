import json

with open("data/canada/quebec_speaker_turns.json") as f:
    turns = json.load(f)

# get all unmatched
unmatched = {}
for v in turns.values():
    for t in v.get("turns", []):
        if not t.get("party", ""):
            name = t.get("speaker_normalized", "")
            unmatched[name] = unmatched.get(name, 0) + 1

# show context for every unmatched name
for target, count in sorted(unmatched.items(), key=lambda x: -x[1]):
    hits = []
    for date, v in sorted(turns.items()):
        for t in v.get("turns", []):
            if t.get("speaker_normalized", "") == target:
                hits.append((date, t.get("speaker_raw",""), t.get("text","")[:150]))
    print(f"\n=== {target} ({count} turns) ===")
    for date, raw, text in hits[:2]:
        print(f"  {date} | {raw} | {text[:120]}")
