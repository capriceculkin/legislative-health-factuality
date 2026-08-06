"""
extract_speaker_turns_quebec.py

Extracts speaker-attributed speech turns from Quebec National Assembly transcripts.
Speaker labels follow the pattern: "M. Legault:" or "Mme Anglade:" or "Le Président:"

Usage: python3 scripts/extract_speaker_turns_quebec.py
"""
import os, json, re
from collections import defaultdict
import unicodedata

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


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

def normalize_name(raw):
    name = re.sub(r'\s+', ' ', raw)  # collapse all whitespace including newlines
    name = re.sub(r'^(M\.|Mme)\s+', '', name, flags=re.IGNORECASE)
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
    lookup = {}
    flat = {}

    if os.path.exists(ppb_path):
        with open(ppb_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("province", "").lower() != "quebec":
                    continue
                name = row.get("first_last", "").strip().lower()
                last = name.split("_")[-1] if "_" in name else name
                last_stripped = strip_accents(last)
                party = row.get("party", "")
                year = row.get("year", "")
                if last and party:
                    lookup[(last, year)] = party
                    lookup[(last_stripped, year)] = party
                    flat[last] = party
                    flat[last_stripped] = party
                    if '-' in last_stripped:
                        last_final = last_stripped.split('-')[-1]
                        lookup[(last_final, year)] = party
                        flat[last_final] = party

    OCR_FIXES = {
        # garbled name → correct PPB last name (must exist in flat)
        "bouierice": "bourgeois",
        "uncoln": "lincoln",
        "béiisle": "belisle",
        "bélisie": "belisle",
        "gobei": "gobeil",
        "joiivet": "jolivet",
        "harei": "harel",
        "boisciair": "boisclair",
        "rémilard": "remillard",
        "rémiilard": "remillard",
        "blackbum": "blackburn",
        "vailières": "vallieres",
        "ubman": "libman",
        "lefevbre": "lefebvre",
        "fiiion": "filion",
        "va liera nd": "vallerand",
        "robiilard": "robillard",
        "charbomeau": "charbonneau",
        "charbornneau": "charbonneau",
        "pouiin": "poulin",
        "beauine": "beaudin",
        "rocheieau": "rocheleau",   # Gilles Rocheleau, Liberal
        "macdonakj": "macdonald",   # Pierre MacDonald, Liberal 
        "la porte": "laporte",
        "rémiliard": "remillard",
        "oufour": "dufour",
        "howen": "holden",  
        "loiseile": "loiselle",
        "hoiden": "holden",
        "bordeieau": "bordeleau", # Additional OCR fixes - all confirmed MNAs
"rémiiiard": "remillard",
"hard": "harel",
"jolrvet": "jolivet",
"jollvet": "jolivet", 
"jollivet": "jolivet",
"jotivet": "jolivet",
"jotlvet": "jolivet",
"j olivet": "jolivet",
"jcjivet": "jolivet",
"joli vet": "jolivet",
"vaiiières": "vallieres",
"valiières": "vallieres",
"homen": "holden",
"hokjen": "holden",
"hotden": "holden",
"macmilian": "macmillan",
"macoonald": "macdonald",
"macdonaw": "macdonald",
"macdonaid": "macdonald",
"gobefl": "gobeil",
"gobel": "gobeil",
"gobeii": "gobeil",
"lederc": "leclerc",
"vailerand": "vallerand",
"lefebbre": "lefebvre",
"leîebvre": "lefebvre",
"chabonneau": "charbonneau",
"charbonnea": "charbonneau",
"charbomeau": "charbonneau",
"charbonoeau": "charbonneau",
"charbormeau": "charbonneau",
"roeheleau": "rocheleau",
"rocnefort": "rocheleau",
"rocherfort": "rocheleau",
"ver mette": "vermette",
"latuiippe": "latulippe",
"séguln": "seguin",
"rlvard": "rivard",
"rivant": "rivard",
"fition": "filion",
"fllion": "filion",
"grattoin": "gratton",
"ooyon": "doyon",
"oesbiens": "desbiens",
"leveaque": "levesque",
"levesgue": "levesque",
"bourrassa": "bourassa",
"bourasa": "bourassa",
"boursssa": "bourassa",
"trench": "french",
"camion": "cannon",
"bout beau": "bourbeau",
"marcl": "marcil",
"mardi": "marcil",
"marcii": "marcil",
"béiisie": "belisle",
"m.bélisle": "belisle",
    "m.middlemiss": "middlemiss",
    "mkjdlemiss": "middlemiss",
    "m.trudel": "trudel",
    "eikas": "elkas",
    "carrier-perreauh": "carrier-perreault",
    "carrier-perreauk": "carrier-perreault",
    "trépanler": "trepanier",
    "nicole loiselie mme loiselie": "loiselle",
    "liza frulia mme frulia": "frulla",
    "oupuis": "dupuis",
    "luce dupuis mme oupuis": "dupuis",
    "france dionne mme oionne": "dionne",
    "hotden": "holden",
    "qendron": "gendron",
    "hamei": "hamel",
    "sûtos": "sirros",
    "trudd": "trudel",
    "chary": "cherry",
    "bourbon": "bourbeau",
    "gagnon-trernblay": "gagnon-tremblay",
        "théorôt": "theoret",
    "boulerlce": "bourgeois",
    "momeau": "moreau",
    "m.middlemiss": "middlemiss",
    "panneau": "cannon",
    "fllion": "filion",
    "khelta": "khelfa",
    "gagnon-trernblay": "gagnon-tremblay",
    "warner": None,
        "diamant": None,
        # confirmed civil servants/procedural — exclude entirely
        "mockle": None,
        "abgral": None,
        "d'astous": None,
        "querido": None,
        "quérido": None,
        "bougie": None,
        "st-roch": None,
        "saint-roch": None,
        "le président le président": None,
        "le président- une voix": None,
        "le vice-présidente": None,
        "la présidente- la vice-présidente": None,
        "boisvert": None,    # civil servant, student aid program
        "prémont": None,     # parliamentary librarian/official
        "disait tantôt": None,   # regex false positive on "M. le ministre disait tantôt"
        "le président du conseil du trésor dit": None,   # regex false positive
        "noël de tilly": None,
"noël de tiliy": None,
"gabrièle": None,
"warner": None,
"khelta": None,
"mettais": None,
"la présidente-la vice-présidente": None,
"le président du conseil du trésor nous dit": None,
"dit": None,
"johnson disait": None,
"yvon lemire adjoint parlementaire au ministre de la main-d'oeuvre et de la sécurité du revenu et ministre du travail 11 mars 1986 membres de l'assemblée nationale du québec président": None,
"le président du conseil du trésor disait": None,
"lesage écrit toujours": None,
"la présidente - cela me permet de terminer - cela me fait penser immédiatement au dire d'un homme politique pas tout à fait inconnu du chef de l'opposition qui disait": None,
"pourrait me dire": None,
"le président du conseil du trésor a dit": None,
"le député de lévis disait tout à l'heure": None,
"le président du conseil du trésor très honnêtement avait dit": None,
"le président de l'association des hôpitaux du québec nous dit": None,
"le président du conseil du trésor disait ceci le 2 juin": None,
"le président du conseil du trésor a eu également l'occasion de dire ceci": None,
"le président du conseil du trésor dit ceci": None,
"le président du conseil du trésor a eu l'occasion d'ajouter ceci": None,
"le président de l'association des hôpitaux du québec disait récemment": None,
"gagnon-trernblay": "gagnon-tremblay",
"trépanler": "trepanier",
    "gagnon-trernblay": "gagnon-tremblay",  # fix this one
"rivard disait aussi": None,
"dubuc concluait ainsi": None,
"dubuc poursuivait dans son éditorial": None,
"dubuc termine son développement sur cette notion de ticket modérateur en disant": None,
"dubuc ajoutait": None,
"la députée de dorion semblait dire": None,
"le député de gouin pour sa part nous disait": None,
"nous disait tout à l'heure": None,
"des affaires culturelles des voix": None,
"mulroney rassure le canada anglais": None,
"le président de l'assemblée nationale ajoutait même": None,
"le président de l'upa continue": None,
"scott a dit à un autre moment": None,
"létourneau continue": None,
"le vice-président le vice-président": None,
"réjean doyon adjoint parlementaire au ministre des relations internationales octobre 1987 président": None,
"comeau continue": None,
"rémy poulin le vice-président": None,
"herbert marx le vice-président": None,
"lesage écrit": None,
"oumais": None,
"francoeur titre": None,
"la députée va dire": None,
"lesage continue dans le journal le devoir": None,
"bourassa avait comme argument à cette époque": None,
"la présidente- une voix": None,
"michel roy continuait": None,
"bernard saint-laurent": None,
"jdy": None,
"me demande": None,
"admet qu'il y a eu une baisse": None,
"disait": None,
"a dit à plusieurs reprises": None,
"dufour je la répète": None,
"la députée de marie-victorin présente la motion suivante": None,
"le président du conseil du trésor nous disait": None,
"lesage continuait": None,
"le député de louis-hébert nous disait": None,
    }

    for garbled, correct in OCR_FIXES.items():
        if correct is None:
            flat[garbled] = "EXCLUDE"
            flat[strip_accents(garbled)] = "EXCLUDE"
        elif correct in flat:
            flat[garbled] = flat[correct]
            flat[strip_accents(garbled)] = flat[correct]

    MANUAL_PARTY = {
        # Verified from 33rd legislature cabinet list
        "lincoln": "Liberal",
        "gobeil": "Liberal",
        "remillard": "Liberal",
        "blackburn": "Liberal",
        "trepanier": "Liberal",
        # Verified from 34th legislature cabinet list
        "frulla": "Liberal",
        "lefebvre": "Liberal",
        # Confirmed opposition MNAs from transcript content
        "biais": "Parti québécois",
        "marais": "Parti québécois",
        "wilson": "Parti québécois",
        # Civil servants — exclude
        "morneau": "EXCLUDE",
        "l'heureux": "EXCLUDE",
        
        #other confirmed
        "outil": "dutil",
        "st-roch": "Liberal",
        "saint-roch": "Liberal",
        "baron": "Liberal",
        "gagnon-trernblay": "Liberal",
        "gagnon-tremblay": "Liberal",
        
    }

    for name, party in MANUAL_PARTY.items():
        flat[name] = party
        flat[strip_accents(name)] = party

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
        name_to_party, flat_lookup = {}, {}

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

        kept_turns = []
        for turn in turns:
            norm = turn["speaker_normalized"]
            last = norm.split()[-1] if norm else ""
            last_stripped = strip_accents(last)
            norm_stripped = strip_accents(norm)
            year = date[:4]
            last_final = last_stripped.split('-')[-1] if '-' in last_stripped else last_stripped
            party = (flat_lookup.get(norm) or
                     flat_lookup.get(norm_stripped) or
                     name_to_party.get((last_stripped, year)) or
                     name_to_party.get((last_final, year)) or
                     name_to_party.get((last, year)) or
                     flat_lookup.get(last_stripped) or
                     flat_lookup.get(last_final) or
                     flat_lookup.get(last, ""))
            if party == "EXCLUDE":
                continue
            turn["party"] = party
            kept_turns.append(turn)

        results[date] = {
            "date": date,
            "turn_count": len(kept_turns),
            "speakers": list(set(t["speaker_normalized"] for t in kept_turns)),
            "turns": kept_turns,
        }
        total_turns += len(kept_turns)

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

