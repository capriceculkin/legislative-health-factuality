import json

with open("data/canada/quebec_speaker_turns.json") as f:
    turns = json.load(f)

targets = [
    "st-roch", "saint-roch", "morneau", "mockle", "le président le président",
    "l'heureux", "quérido", "le président- une voix", "abgral",
    "le vice-présidente", "va liera nd", "bougie", "d'astous",
    "la présidente- la vice-présidente", "boisvert", "prémont",
    "rocheieau", "le président du conseil du trésor dit",
    "macdonakj", "disait tantôt"
]

for target in targets:
    hits = []
    for date, v in sorted(turns.items()):
        for t in v.get("turns", []):
            if t.get("speaker_normalized", "") == target:
                hits.append((date, t.get("speaker_raw",""), t.get("text","")[:200]))
    if hits:
        print(f"\n=== {target} ({len(hits)} turns) ===")
        for date, raw, text in hits[:2]:
            print(f"  DATE: {date} | RAW: {raw}")
            print(f"  TEXT: {text[:150]}")
