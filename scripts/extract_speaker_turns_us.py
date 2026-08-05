"""
extract_speaker_turns_us.py

Extracts speaker-attributed speech turns from US Congressional Record files.
Speaker labels follow the pattern: "Mr. SMITH." or "Ms. JONES." (all-caps surname)

For each health bill date, produces speaker turns with party affiliation
matched from the member_lookup.json by congress number.

Usage: python3 scripts/extract_speaker_turns_us.py
"""
import os, json, re, csv
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEECH_DIR = os.path.join(REPO_ROOT, "data/us/congressional_record_speeches")
MEMBER_LOOKUP_PATH = os.path.join(REPO_ROOT, "data/us/member_lookup.json")
MATCHED_PATH = os.path.join(REPO_ROOT, "data/us/health_bills_final_matched.csv")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/us/speaker_turns.json")

# US Congressional Record speaker pattern: "Mr. SMITH." or "Ms. JONES of Texas."
SPEAKER_RE = re.compile(
    r'^\s{2}((?:Mr\.|Mrs\.|Ms\.|Miss\.|Dr\.|The\s+(?:SPEAKER|CHAIR|PRESIDING\s+OFFICER))'
    r'\s+[A-Z][A-Z\s\-\']+?(?:\s+of\s+\w+)?)\.\s+',
    re.MULTILINE
)

EXCLUDE_SPEAKERS = {
    "the speaker", "the chair", "the presiding officer",
    "the speaker pro tempore", "the acting speaker"
}


def normalize_speaker(raw):
    """Extract just the surname from 'Mr. SMITH of Texas'."""
    name = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss\.|Dr\.)\s+', '', raw, flags=re.IGNORECASE)
    name = re.sub(r'\s+of\s+\w+$', '', name, flags=re.IGNORECASE)
    return name.strip().upper()


def extract_turns(text):
    """Extract (speaker, text) turns from a CR file."""
    turns = []
    matches = list(SPEAKER_RE.finditer(text))

    for i, m in enumerate(matches):
        speaker_raw = m.group(1).strip()
        speaker_norm = normalize_speaker(speaker_raw)

        if speaker_norm.lower() in EXCLUDE_SPEAKERS:
            continue

        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        speech = text[start:end].strip()

        if len(speech) > 20:
            turns.append({
                "speaker_raw": speaker_raw,
                "speaker_surname": speaker_norm,
                "text": speech[:500],
                "char_count": len(speech),
            })

    return turns


def build_congress_name_lookup(member_lookup):
    """Build congress -> surname -> {party, state, gender} lookup."""
    lookup = {}
    for congress, members in member_lookup.get("by_congress", {}).items():
        by_surname = defaultdict(list)
        for m in members:
            surname = m["full_name"].split()[-1].upper() if m["full_name"] else ""
            if surname:
                by_surname[surname].append(m)
        lookup[congress] = by_surname
    return lookup


def main():
    print("Loading member lookup...")
    with open(MEMBER_LOOKUP_PATH, encoding="utf-8") as f:
        member_lookup = json.load(f)
    congress_lookup = build_congress_name_lookup(member_lookup)
    print(f"  Congresses loaded: {sorted(congress_lookup.keys())}")

    # load date -> congress mapping from matched bills
    date_to_congress = {}
    with open(MATCHED_PATH, newline="") as f:
        for row in csv.DictReader(f):
            date_to_congress[row["date"]] = row["congress"]
    print(f"  {len(date_to_congress)} bill dates mapped to congress")

    speech_files = sorted(
        f for f in os.listdir(SPEECH_DIR)
        if f.endswith(".txt") and "_notes" not in f
    )
    print(f"  {len(speech_files)} speech files")

    results = {}
    total_turns = 0
    matched_party = 0

    for fname in speech_files:
        date = fname.replace(".txt", "")
        congress = date_to_congress.get(date, "")
        members_this_congress = congress_lookup.get(congress, {})

        fpath = os.path.join(SPEECH_DIR, fname)
        with open(fpath, encoding="utf-8", errors="replace") as f:
            text = f.read()

        turns = extract_turns(text)

        # match party by surname within congress
        for turn in turns:
            surname = turn["speaker_surname"]
            candidates = members_this_congress.get(surname, [])
            if len(candidates) == 1:
                turn["party"] = candidates[0]["party"]
                turn["state"] = candidates[0]["state"]
                turn["gender"] = candidates[0]["gender"]
                matched_party += 1
            elif len(candidates) > 1:
                # multiple members with same surname — flag as ambiguous
                parties = list(set(c["party"] for c in candidates))
                turn["party"] = parties[0] if len(parties) == 1 else "ambiguous"
                turn["state"] = candidates[0]["state"]
                turn["gender"] = ""
            else:
                turn["party"] = ""
                turn["state"] = ""
                turn["gender"] = ""

            # classify government vs opposition
            # majority party per congress (simplified — Republican/Democrat varies)
            turn["is_presiding"] = "SPEAKER" in surname or "CHAIR" in surname

        results[date] = {
            "date": date,
            "congress": congress,
            "turn_count": len(turns),
            "speakers": list(set(t["speaker_surname"] for t in turns)),
            "turns": turns,
        }
        total_turns += len(turns)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nProcessed {len(results)} speech files")
    print(f"Total speaker turns: {total_turns}")
    print(f"Turns with party matched: {matched_party}")
    print(f"Saved to {OUTPUT_PATH}")

    # sample
    dates_with_turns = [d for d, v in results.items() if v["turn_count"] > 0]
    if dates_with_turns:
        sample = dates_with_turns[len(dates_with_turns)//2]
        print(f"\nSample from {sample} (Congress {results[sample]['congress']}):")
        for t in results[sample]["turns"][:3]:
            print(f"  {t['speaker_raw']} [{t.get('party','unknown')}]: {t['text'][:80]}...")


if __name__ == "__main__":
    main()
