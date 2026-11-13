"""
gov_vs_opposition_quebec.py

Analyzes whether government speakers are more or less factual than opposition
speakers in Quebec National Assembly health bill debates (1985-2026).

Uses quebec sentences.json (has speaker and party per sentence) and
annotated_sentences.json (has graph evidence per sentence).

Governing periods used:
  Liberal Party:    1985-1994, 2003-2012, 2014-2018
  PQ:               1994-2003, 2012-2014
  CAQ:              2018-present
"""
import json, os
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SENTENCES_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/quebec/sentences.json")
ANNOTATED_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/quebec/annotated_sentences.json")

GOVERNING_PERIODS = [
    ("Liberal 1985-1994",              1985, 1994),
    ("Parti québécois 1994-2003",      1994, 2003),
    ("Liberal 2003-2012",              2003, 2012),
    ("Parti québécois minority 2012-2014", 2012, 2014),
    ("Liberal 2014-2018",              2014, 2018),
    ("Coalition Avenir Québec 2018+",  2018, 2030),
]

GOVERNING_PARTIES = {
    (1985, 1994): "Liberal",
    (1994, 2003): "Parti québécois",
    (2003, 2012): "Liberal",
    (2012, 2014): "Parti québécois",
    (2014, 2018): "Liberal",
    (2018, 2030): "Coalition Avenir Québec",
}

def get_gov_party(year):
    for (start, end), party in GOVERNING_PARTIES.items():
        if start <= year < end:
            return party
    return None

def is_governing(party, year):
    gov = get_gov_party(year)
    if not gov or not party:
        return None
    party_lower = party.lower()
    gov_lower = gov.lower()
    if "liberal" in gov_lower and "liberal" in party_lower:
        return True
    if "québécois" in gov_lower and ("québécois" in party_lower or "quebecois" in party_lower):
        return True
    if "coalition" in gov_lower and ("coalition" in party_lower or "avenir" in party_lower):
        return True
    return False

print("Loading Quebec sentences...")
with open(SENTENCES_PATH) as f:
    sentences = json.load(f)

print("Loading annotated sentences...")
with open(ANNOTATED_PATH) as f:
    annotated = json.load(f)

evidence_set = {s["sentence_id"] for s in annotated if s.get("supported")}
health_sentence_ids = {s["sentence_id"] for s in annotated}

print(f"Total sentences: {len(sentences):,}")
print(f"Sentences with graph evidence: {len(evidence_set):,}")

gov_total = 0
gov_supported = 0
opp_total = 0
opp_supported = 0
unmatched = 0

era_gov = defaultdict(lambda: {"total": 0, "supported": 0})
era_opp = defaultdict(lambda: {"total": 0, "supported": 0})

for s in sentences:
    sid = s.get("sentence_id", "")
    if sid not in health_sentence_ids:
        continue
    party = s.get("party", "")
    date = s.get("date", "")
    if not date or not party:
        unmatched += 1
        continue
    try:
        year = int(date[:4])
    except:
        continue

    governing = is_governing(party, year)
    if governing is None:
        unmatched += 1
        continue

    supported = 1 if sid in evidence_set else 0

    # get era label
    era = None
    for label, start, end in GOVERNING_PERIODS:
        if start <= year < end:
            era = label
            break

    if governing:
        gov_total += 1
        gov_supported += supported
        if era:
            era_gov[era]["total"] += 1
            era_gov[era]["supported"] += supported
    else:
        opp_total += 1
        opp_supported += supported
        if era:
            era_opp[era]["total"] += 1
            era_opp[era]["supported"] += supported

print(f"\nUnmatched (no party or date): {unmatched:,}")

print(f"\n{'='*60}")
print("GOVERNMENT VS OPPOSITION FACTUALITY — QUEBEC")
print(f"{'='*60}")

if gov_total > 0:
    gov_rate = gov_supported / gov_total
    print(f"\nSentence-level:")
    print(f"  Government speakers: {gov_total:,} claim-bearing sentences")
    print(f"    Support rate: {gov_rate:.4f} ({gov_rate*100:.1f}%)")
else:
    print("  No government sentences found")

if opp_total > 0:
    opp_rate = opp_supported / opp_total
    print(f"  Opposition speakers: {opp_total:,} claim-bearing sentences")
    print(f"    Support rate: {opp_rate:.4f} ({opp_rate*100:.1f}%)")
else:
    print("  No opposition sentences found")

if gov_total > 0 and opp_total > 0:
    diff = gov_rate - opp_rate
    direction = "MORE" if diff > 0 else "LESS"
    print(f"  Difference (gov - opp): {diff:+.4f}")
    print(f"  Government speakers are {direction} factual than opposition")

print(f"\nFactuality by governing era:")
print(f"  {'Era':<35} {'Gov':>15} {'Opp':>15} {'Diff':>8}")
print(f"  {'-'*75}")
for label, start, end in GOVERNING_PERIODS:
    g = era_gov[label]
    o = era_opp[label]
    if g["total"] > 0 and o["total"] > 0:
        gr = g["supported"] / g["total"]
        or_ = o["supported"] / o["total"]
        diff = gr - or_
        print(f"  {label:<35} {gr:.4f} (n={g['total']:,}) {or_:.4f} (n={o['total']:,})  {diff:+.4f}")
    elif g["total"] > 0:
        gr = g["supported"] / g["total"]
        print(f"  {label:<35} {gr:.4f} (n={g['total']:,}) n/a")
