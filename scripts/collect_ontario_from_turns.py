"""
collect_ontario_from_turns.py

Builds Ontario sentences.json from speaker turns already matched to health bills,
rather than full Hansard day files. This is equivalent to the US approach where
speech files were bill-specific debate text only.

Output: data/dbpedia_pipeline/ontario/sentences.json
"""
import os, json, re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TURNS_PATH = os.path.join(REPO_ROOT, "data/canada/ontario_speaker_turns.json")
BILL_INDEX_PATH = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/sentences.json")

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# get all dates from health-tagged bills only
print("Loading Ontario bill index...")
with open(BILL_INDEX_PATH) as f:
    bill_index = json.load(f)

health_dates = set()
for v in bill_index.values():
    if v.get("health_tag"):
        for d in v.get("dates", []):
            health_dates.add(d)

print(f"Health bill debate dates: {len(health_dates)}")

# load speaker turns
print("Loading Ontario speaker turns...")
with open(TURNS_PATH) as f:
    all_turns = json.load(f)

# build sentences from turns on health bill dates
sentences = []
dates_found = 0
turns_processed = 0

for date, day_data in sorted(all_turns.items()):
    if date not in health_dates:
        continue
    dates_found += 1
    for turn in day_data.get("turns", []):
        # skip procedural speakers
        speaker = turn.get("speaker_normalized", "")
        if not speaker or speaker in {"speaker", "the speaker", "deputy speaker"}:
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

print(f"Dates processed: {dates_found}")
print(f"Turns processed: {turns_processed}")
print(f"Sentences collected: {len(sentences)}")

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(sentences, f, ensure_ascii=False)

print(f"Saved to {OUTPUT_PATH}")
