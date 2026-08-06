"""
extract_speaker_turns_quebec.py

Extracts speaker-attributed speech turns from Quebec National Assembly transcripts.
Speaker labels follow the pattern: "M. Legault:" or "Mme Anglade:" or "Le Président:"

Usage: python3 scripts/extract_speaker_turns_quebec.py
"""
import os, json, re
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPT_DIR = os.path.join(REPO_ROOT, "data/canada/quebec_assembly/transcripts")
MEMBERS_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_members_recent.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_speaker_turns.json")

# Quebec Assembly speaker patterns
SPEAKER_RE = re.compile(
    r'^((?:M\.|Mme|Le\s+Président|La\s+Présidente|Le\s+Vice-Président|'
    r'La\s+Vice-Présidente|M\.\s+le\s+ministre|Mme\s+la\s+ministre|'
    r'M\.\s+le\s+premier\s+ministre|Le\s+Président)\s*[\w\s\-\'àâäéèêëîïôùûüçœæ]*?):\s*',
    re.MULTILINE | re.IGNORECASE
)

EXCLUDE_SPEAKERS = {
    "le président", "la présidente", "le vice-président", "la vice-présidente",
    "le président suppléant", "la présidente suppléante"
}


def normalize_name(raw):
    """Extract name from 'M. Legault' or 'Mme Anglade'."""
    name = re.sub(r'^(M\.|Mme)\s+', '', raw, flags=re.IGNORECASE)
    name = re.sub(r'^(le\s+ministre|la\s+ministre|le\s+premier\s+ministre)\s*', '', name, flags=re.IGNORECASE)
    return name.strip().lower()


def extract_turns(text):
    turns = []
    matches = list(SPEAKER_RE.finditer(text))

    for i, m in enumerate(matches):
        speaker_raw = m.group(1).strip()
        speaker_norm = normalize_name(speaker_raw)

        if speaker_norm.lower() in EXCLUDE_SPEAKERS:
            continue
        if not speaker_norm or len(speaker_norm) < 2:
            continue

        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        speech = text[start:end].strip()

        if len(speech) > 20:
            is_minister = bool(re.search(r'ministre|premier\s+ministre', speaker_raw, re.IGNORECASE))
            turns.append({
                "speaker_raw": speaker_raw,
                "speaker_normalized": speaker_norm,
                "text": speech[:500],
                "char_count": len(speech),
                "is_minister": is_minister,
            })

    return turns


def build_name_lookup(members):
    import csv
    ppb_path = os.path.join(REPO_ROOT, "data/canada/PPB.csv")
    lookup = {}  # (last_name_lower, year) -> party
    flat = {}    # last_name_lower -> party (most recent)
    
    if os.path.exists(ppb_path):
        with open(ppb_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("province", "").lower() != "quebec":
                    continue
                name = row.get("first_last", "").strip().lower()
                last = name.split("_")[-1] if "_" in name else name
                party = row.get("party", "")
                year = row.get("year", "")
                if last and party:
                    lookup[(last, year)] = party
                    flat[last] = party  # fallback
    return lookup, flat


def main():
    # load member data
    name_to_party = {}
    if os.path.exists(MEMBERS_PATH):
        with open(MEMBERS_PATH, encoding="utf-8") as f:
            members = json.load(f)
        name_to_party, flat_lookup = build_name_lookup(members)
        print(f"Loaded {len(members)} Quebec members")
    else:
        print("Quebec members file not found - party matching will be limited")

    if not os.path.exists(TRANSCRIPT_DIR):
        print(f"Transcript directory not found: {TRANSCRIPT_DIR}")
        return

    transcript_files = sorted(
        f for f in os.listdir(TRANSCRIPT_DIR)
        if f.endswith(".txt")
    )
    print(f"{len(transcript_files)} Quebec transcript files")

    results = {}
    total_turns = 0

    for fname in transcript_files:
        date = fname.replace(".txt", "")
        fpath = os.path.join(TRANSCRIPT_DIR, fname)

        with open(fpath, encoding="utf-8", errors="replace") as f:
            text = f.read()

        turns = extract_turns(text)

        for turn in turns:
            norm = turn["speaker_normalized"]
            last = norm.split()[-1] if norm else ""
            year = date[:4]
            party = name_to_party.get((last, year)) or flat_lookup.get(last, "")
            turn["party"] = party

        results[date] = {
            "date": date,
            "turn_count": len(turns),
            "speakers": list(set(t["speaker_normalized"] for t in turns)),
            "turns": turns,
        }
        total_turns += len(turns)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Processed {len(results)} transcript files")
    print(f"Total speaker turns: {total_turns}")
    print(f"Saved to {OUTPUT_PATH}")

    dates_with_turns = [d for d, v in results.items() if v["turn_count"] > 0]
    if dates_with_turns:
        sample = dates_with_turns[len(dates_with_turns)//2]
        print(f"\nSample from {sample}:")
        for t in results[sample]["turns"][:3]:
            print(f"  {t['speaker_raw']} [{t.get('party','?')}]: {t['text'][:80]}...")


if __name__ == "__main__":
    main()
