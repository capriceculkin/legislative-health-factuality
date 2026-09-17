import json

with open("data/canada/quebec_speaker_turns.json") as f:
    turns = json.load(f)

targets = ["morneau", "marais", "wilson", "querido", "biais", "l'heureux"]

for target in targets:
    print(f"\n=== {target} ===")
    count = 0
    for date, v in sorted(turns.items()):
        for t in v.get("turns", []):
            if t.get("speaker_normalized", "") == target:
                print(f"DATE: {date}")
                print(f"RAW: {t.get('speaker_raw','')}")
                print(f"TEXT: {t.get('text','')[:200]}")
                print()
                count += 1
                if count >= 2:
                    break
        if count >= 2:
            break
