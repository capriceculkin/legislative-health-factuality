"""
extract_speaker_turns_ontario.py

Extracts speaker-attributed speech turns from Ontario Hansard plain text files.
Speaker labels follow the pattern: "Hon. Mr. Smith:" or "Mr. Jones:" or "Ms. Brown:"

For each health bill date, produces a list of (speaker_name, speech_text, party) tuples.
Party is matched by name against the Ontario member lookup.

Usage: python3 scripts/extract_speaker_turns_ontario.py
"""
import os, json, re
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANSARD_DIR = os.path.join(REPO_ROOT, "data/canada/ontario")
MEMBERS_PATH = os.path.join(REPO_ROOT, "data/canada/ontario_members.json")
FSOB_PATH = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_fsob_votes.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/canada/ontario_speaker_turns.json")

# speaker label pattern
SPEAKER_RE = re.compile(
    r'^((?:Hon\.\s+)?(?:Mr\.?\s+|Mrs\.?\s+|Ms\.?\s+|Miss\.?\s+|Dr\.?\s+|The\s+(?:Speaker|Chair|Deputy\s+Speaker|Acting\s+Speaker))'
    r'[\w\.\-\'\s]+?):\s*',
    re.MULTILINE
)

# speakers to exclude (procedural)
EXCLUDE_SPEAKERS = {
    "the speaker", "the chair", "the deputy speaker", "the acting speaker",
    "the clerk", "mr. speaker", "mrs. speaker", "ms. speaker",
    "the honourable the lieutenant governor"
}


def normalize_name(name):
    """Normalize speaker name for matching."""
    name = re.sub(r'^Hon\.\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss\.|Dr\.)\s+', '', name, flags=re.IGNORECASE)
    return name.strip().lower()


def extract_turns(text):
    """Extract (speaker, text) turns from a Hansard file."""
    turns = []
    matches = list(SPEAKER_RE.finditer(text))

    for i, m in enumerate(matches):
        speaker = m.group(1).strip()
        norm = normalize_name(speaker.lower())

        if norm in EXCLUDE_SPEAKERS:
            continue

        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        speech = text[start:end].strip()

        if len(speech) > 20:
            turns.append({
                "speaker_raw": speaker,
                "speaker_normalized": norm,
                "text": speech[:500],
                "char_count": len(speech),
            })

    return turns


def build_name_to_party(members):
    """Build name -> party lookup from member list."""
    lookup = {}
    for m in members:
        name = m.get("name", "").replace(",", "").strip()
        parts = name.split()
        if len(parts) >= 2:
            last = parts[0].lower()
            lookup[last] = m.get("party", "")
            full_norm = normalize_name(name.lower())
            lookup[full_norm] = m.get("party", "")
    return lookup


def main():
    print("Loading member data...")
    with open(MEMBERS_PATH, encoding="utf-8") as f:
        members = json.load(f)
    name_to_party = build_name_to_party(members)
    print(f"  {len(members)} Ontario MPPs loaded")

    # get health bill dates
    hansard_files = sorted(
        f for f in os.listdir(HANSARD_DIR)
        if f.endswith(".txt")
    )
    print(f"  {len(hansard_files)} Hansard files")

    results = {}
    total_turns = 0

    for fname in hansard_files:
        date = fname.replace(".txt", "")
        fpath = os.path.join(HANSARD_DIR, fname)

        with open(fpath, encoding="utf-8", errors="replace") as f:
            text = f.read()

        turns = extract_turns(text)

        # match party for each speaker
        for turn in turns:
            norm = turn["speaker_normalized"]
            last_name = norm.split()[-1] if norm else ""
            party = name_to_party.get(norm) or name_to_party.get(last_name, "")
            turn["party"] = party

            # classify government vs opposition based on party
            # governing party changes by parliament — flag for later resolution
            turn["is_minister"] = "hon." in turn["speaker_raw"].lower()

        results[date] = {
            "date": date,
            "turn_count": len(turns),
            "speakers": list(set(t["speaker_normalized"] for t in turns)),
            "turns": turns,
        }
        total_turns += len(turns)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nProcessed {len(results)} Hansard files")
    print(f"Total speaker turns: {total_turns}")
    print(f"Avg turns per file: {total_turns // len(results) if results else 0}")
    print(f"Saved to {OUTPUT_PATH}")

    # sample output
    sample_date = list(results.keys())[10]
    print(f"\nSample from {sample_date}:")
    for t in results[sample_date]["turns"][:3]:
        print(f"  {t['speaker_raw']} [{t['party'] or 'unknown'}]: {t['text'][:80]}...")


if __name__ == "__main__":
    main()
