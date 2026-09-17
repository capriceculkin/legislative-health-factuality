"""
collect_quebec_from_turns.py

Builds Quebec sentences.json from speaker turns.
All 617 Quebec transcript files are already health-relevant
(selected during transcript collection from health bill debates).
Date format in speaker turns is YYYYMMDD, converted to YYYY-MM-DD.
"""
import os, json, re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TURNS_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_speaker_turns.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/quebec/sentences.json")

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

print("Loading Quebec speaker turns...")
with open(TURNS_PATH) as f:
    all_turns = json.load(f)

sentences = []
turns_processed = 0

for raw_date, day_data in sorted(all_turns.items()):
    # convert YYYYMMDD to YYYY-MM-DD
    date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

    for turn in day_data.get("turns", []):
        speaker = turn.get("speaker_normalized", "")
        if not speaker:
            continue
        text = turn.get("text", "").strip()
        if not text:
            continue
        # split turn into sentences
        raw_sents = re.split(r"(?<=[.!?])\s+", text)
        for i, sent in enumerate(raw_sents):
            sent = sent.strip()
            sent = re.sub(r"\s+", " ", sent)
            if 40 < len(sent) < 400:
                sentences.append({
                    "sentence_id": f"{date}-turn{turns_processed}-{i}",
                    "date": date,
                    "text": sent,
                    "speaker": speaker,
                    "party": turn.get("party", ""),
                    "is_minister": turn.get("is_minister", False),
                })
        turns_processed += 1

print(f"Turns processed: {turns_processed}")
print(f"Sentences collected: {len(sentences)}")

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(sentences, f, ensure_ascii=False)

print(f"Saved to {OUTPUT_PATH}")
