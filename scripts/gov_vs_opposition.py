"""
gov_vs_opposition.py

Computes factuality scores separately for government and opposition speakers
in Ontario health bill debates.

Uses ontario_speaker_turns.json (has party field per turn) and
ontario sentences.json (has speaker and party per sentence).

Usage: python3 scripts/gov_vs_opposition.py
"""
import os, json
from collections import defaultdict
from datetime import date as Date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SENTENCES_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/sentences.json")
ANNOTATED_PATH = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/annotated_sentences.json")
BILL_INDEX_PATH = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")
FSOB_PATH = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_fsob_votes.json")

# Verified governing party periods from Wikipedia
GOVERNING_PERIODS = [
    ("Progressive Conservative Party of Ontario", "1985-02-08", "1985-06-26"),
    ("Ontario Liberal Party",                      "1985-06-26", "1990-10-01"),
    ("New Democratic Party of Ontario",            "1990-10-01", "1995-06-26"),
    ("Progressive Conservative Party of Ontario", "1995-06-26", "2003-10-23"),
    ("Ontario Liberal Party",                      "2003-10-23", "2018-06-29"),
    ("Progressive Conservative Party of Ontario", "2018-06-29", "2030-01-01"),
]

ERA_TO_PARLIAMENT = {
    1985: 33, 1989: 34, 1993: 35, 1997: 36,
    2001: 37, 2005: 38, 2009: 39, 2013: 40,
    2017: 41, 2021: 42, 2025: 43,
}

def get_governing_party(date_str):
    """Return governing party name for a given date string YYYY-MM-DD."""
    try:
        d = Date.fromisoformat(date_str)
    except:
        return None
    for party, start, end in GOVERNING_PERIODS:
        if Date.fromisoformat(start) <= d < Date.fromisoformat(end):
            return party
    return None

def is_governing(speaker_party, date_str):
    """Return True if speaker_party is the governing party on date_str."""
    gov = get_governing_party(date_str)
    if not gov or not speaker_party:
        return None
    # normalize party names for comparison
    sp = speaker_party.lower()
    gp = gov.lower()
    if "liberal" in sp and "liberal" in gp:
        return True
    if "progressive conservative" in sp and "progressive conservative" in gp:
        return True
    if "new democratic" in sp and "new democratic" in gp:
        return True
    if "conservative" in sp and "conservative" in gp and "progressive" not in sp:
        return True
    return False

def avg(lst): return sum(lst)/len(lst) if lst else None


def main():
    print("Loading Ontario sentences...")
    with open(SENTENCES_PATH) as f:
        sentences = json.load(f)

    print("Loading annotated sentences...")
    with open(ANNOTATED_PATH) as f:
        annotated = json.load(f)
    evidence_by_id = {s["sentence_id"]: s.get("supported", False) for s in annotated}

    print("Loading bill index and FSOB...")
    with open(BILL_INDEX_PATH) as f:
        bill_index = json.load(f)
    with open(FSOB_PATH) as f:
        fsob = json.load(f)

    bill_outcomes = {}
    for parl_sess, data in fsob.items():
        parliament = int(parl_sess.split("-")[0])
        for record in data.get("records", []):
            bill_num = record.get("bill_number", "")
            outcome = record.get("outcome", "unknown")
            bill_outcomes[f"{parliament}-{bill_num}"] = outcome

    # build date -> health bill info lookup
    date_to_bill = {}
    for bill_key, bill_data in bill_index.items():
        if not bill_data.get("health_tag"):
            continue
        bill_num = bill_data.get("bill_number", "")
        era = bill_data.get("era", 0)
        parliament = ERA_TO_PARLIAMENT.get(int(era), 0)
        outcome = bill_outcomes.get(f"{parliament}-{bill_num}", "unknown")
        for d in bill_data.get("dates", []):
            date_to_bill[d] = {"bill_number": bill_num, "outcome": outcome}

    # classify each sentence as gov or opposition
    gov_claim = []
    gov_supported = []
    opp_claim = []
    opp_supported = []

    gov_passed_f = []
    gov_failed_f = []
    opp_passed_f = []
    opp_failed_f = []

    # group by bill for per-bill breakdown
    bill_gov = defaultdict(lambda: {"claim": [], "supported": [], "outcome": "unknown"})
    bill_opp = defaultdict(lambda: {"claim": [], "supported": [], "outcome": "unknown"})

    for s in sentences:
        sid = s["sentence_id"]
        date = s.get("date", "")
        party = s.get("party", "")
        bill_info = date_to_bill.get(date)
        if not bill_info:
            continue
        if sid not in evidence_by_id:
            continue

        supported = evidence_by_id[sid]
        gov = is_governing(party, date)
        bill_key = f"{date}-{bill_info['bill_number']}"
        outcome = bill_info["outcome"]

        if gov is True:
            gov_claim.append(sid)
            gov_supported.append(supported)
            bill_gov[bill_key]["claim"].append(supported)
            bill_gov[bill_key]["outcome"] = outcome
        elif gov is False:
            opp_claim.append(sid)
            opp_supported.append(supported)
            bill_opp[bill_key]["claim"].append(supported)
            bill_opp[bill_key]["outcome"] = outcome

    # compute per-bill factuality for gov and opp
    for bill_key in set(list(bill_gov.keys()) + list(bill_opp.keys())):
        outcome = bill_gov[bill_key]["outcome"] or bill_opp[bill_key]["outcome"]
        passed = outcome.lower() in ["carried", "passed"]
        failed = outcome.lower() in ["lost", "failed", "defeated"]

        gov_c = bill_gov[bill_key]["claim"]
        opp_c = bill_opp[bill_key]["claim"]

        if gov_c:
            gf = sum(gov_c) / len(gov_c)
            if passed: gov_passed_f.append(gf)
            if failed: gov_failed_f.append(gf)

        if opp_c:
            of = sum(opp_c) / len(opp_c)
            if passed: opp_passed_f.append(of)
            if failed: opp_failed_f.append(of)

    # summary
    total_gov = len(gov_claim)
    total_opp = len(opp_claim)
    gov_rate = sum(gov_supported)/total_gov if total_gov else 0
    opp_rate = sum(opp_supported)/total_opp if total_opp else 0

    print(f"\n{'='*60}")
    print(f"GOVERNMENT VS OPPOSITION FACTUALITY — ONTARIO")
    print(f"{'='*60}")
    print(f"\nSentence-level:")
    print(f"  Government speakers: {total_gov} claim-bearing sentences")
    print(f"    Support rate: {gov_rate:.4f} ({gov_rate*100:.1f}%)")
    print(f"  Opposition speakers: {total_opp} claim-bearing sentences")
    print(f"    Support rate: {opp_rate:.4f} ({opp_rate*100:.1f}%)")
    print(f"  Difference (gov - opp): {gov_rate-opp_rate:+.4f}")

    print(f"\nBill-level factuality by outcome:")
    print(f"  Government speech — passed bills: {avg(gov_passed_f):.4f} (n={len(gov_passed_f)})")
    print(f"  Government speech — failed bills: {avg(gov_failed_f):.4f} (n={len(gov_failed_f)})")
    print(f"  Opposition speech — passed bills: {avg(opp_passed_f):.4f} (n={len(opp_passed_f)})")
    print(f"  Opposition speech — failed bills: {avg(opp_failed_f):.4f} (n={len(opp_failed_f)})")

    print(f"\nInterpretation:")
    if gov_rate > opp_rate:
        print(f"  Government speakers are MORE factual than opposition (+{gov_rate-opp_rate:.4f})")
    else:
        print(f"  Opposition speakers are MORE factual than government ({opp_rate-gov_rate:+.4f})")

    # by governing era
    print(f"\nFactuality by governing era:")
    era_gov = defaultdict(list)
    era_opp = defaultdict(list)
    for s in sentences:
        sid = s["sentence_id"]
        date = s.get("date", "")
        party = s.get("party", "")
        if sid not in evidence_by_id:
            continue
        if not date_to_bill.get(date):
            continue
        gov_party = get_governing_party(date)
        if not gov_party:
            continue
        supported = evidence_by_id[sid]
        gov = is_governing(party, date)
        era_label = gov_party.replace(" Party of Ontario", "").replace("Ontario ", "")
        if gov is True:
            era_gov[era_label].append(supported)
        elif gov is False:
            era_opp[era_label].append(supported)

    all_eras = sorted(set(list(era_gov.keys()) + list(era_opp.keys())))
    print(f"  {'Era':<35} {'Gov factuality':>15} {'Opp factuality':>15} {'Diff':>8}")
    print(f"  {'-'*73}")
    for era in all_eras:
        gv = sum(era_gov[era])/len(era_gov[era]) if era_gov[era] else None
        ov = sum(era_opp[era])/len(era_opp[era]) if era_opp[era] else None
        diff = (gv - ov) if (gv and ov) else None
        gv_str = f"{gv:.4f} (n={len(era_gov[era])})" if gv is not None else "N/A"
        ov_str = f"{ov:.4f} (n={len(era_opp[era])})" if ov is not None else "N/A"
        diff_str = f"{diff:+.4f}" if diff is not None else "N/A"
        print(f"  {era:<35} {gv_str:>15} {ov_str:>15} {diff_str:>8}")


if __name__ == "__main__":
    main()
