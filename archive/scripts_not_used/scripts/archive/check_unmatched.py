import json

with open("data/canada/quebec_speaker_turns.json") as f:
    turns = json.load(f)

unmatched = {}
total = 0
matched = 0
for v in turns.values():
    for t in v.get("turns", []):
        total += 1
        if t.get("party", "") and t.get("party", "") != "EXCLUDE":
            matched += 1
        elif not t.get("party", ""):
            name = t.get("speaker_normalized", "")
            unmatched[name] = unmatched.get(name, 0) + 1

print(f"Total turns: {total}, matched: {matched} ({matched/total*100:.1f}%)")
print(f"\nTop unmatched:")
for name, count in sorted(unmatched.items(), key=lambda x: -x[1])[:20]:
    print(f"{count:5d}  {name}")