"""
ontario_aggregate_factuality.py

Produces two additional Ontario factuality analyses:
1. Per-bill aggregated scores (all debate dates grouped per bill)
2. Health-entity-filtered scores (only sentences with health DBpedia entities)

Compares Ontario to US factuality scores.

Usage: python3 scripts/ontario_aggregate_factuality.py
"""
import os, json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ontario paths
ONTARIO_ANNOTATED = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/annotated_sentences.json")
ONTARIO_SENTENCES = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/sentences.json")
ONTARIO_BILL_INDEX = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")
ONTARIO_FSOB = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_fsob_votes.json")
OUTPUT_BILL = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/factuality_scores_per_bill.json")
OUTPUT_FILTERED = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/factuality_scores_health_filtered.json")

# US paths for comparison
US_SCORES = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/us/factuality_scores.json")

# Health-related DBpedia URI patterns
HEALTH_PATTERNS = [
    "health", "Health", "medical", "Medical", "hospital", "Hospital",
    "medicine", "Medicine", "drug", "Drug", "pharmaceutical", "Pharmaceutical",
    "disease", "Disease", "cancer", "Cancer", "mental", "Mental",
    "nursing", "Nursing", "patient", "Patient", "physician", "Physician",
    "surgery", "Surgery", "clinic", "Clinic", "therapy", "Therapy",
    "vaccine", "Vaccine", "epidemic", "Epidemic", "pandemic", "Pandemic",
    "addiction", "Addiction", "tobacco", "Tobacco", "alcohol", "Alcohol",
    "disability", "Disability", "dental", "Dental", "pharmacy", "Pharmacy",
    "Medicare", "Medicaid", "OHIP", "FDA", "CDC", "WHO",
]

ERA_TO_PARLIAMENT = {
    1985: 33, 1989: 34, 1993: 35, 1997: 36,
    2001: 37, 2005: 38, 2009: 39, 2013: 40,
    2017: 41, 2021: 42, 2025: 43,
}

def is_health_entity(uri):
    return any(p in uri for p in HEALTH_PATTERNS)

def avg(lst):
    return sum(lst) / len(lst) if lst else 0

def main():
    print("Loading Ontario data...")
    with open(ONTARIO_ANNOTATED) as f:
        annotated = json.load(f)
    with open(ONTARIO_SENTENCES) as f:
        sentences = json.load(f)
    with open(ONTARIO_BILL_INDEX) as f:
        bill_index = json.load(f)
    with open(ONTARIO_FSOB) as f:
        fsob = json.load(f)

    # build evidence lookup
    evidence_by_id = {s["sentence_id"]: s for s in annotated}

    # build sentence date lookup
    sent_by_date = defaultdict(list)
    for s in sentences:
        sid = s["sentence_id"]
        date = "-".join(sid.split("-")[:3])
        sent_by_date[date].append(sid)

    # build FSOB outcome lookup
    bill_outcomes = {}
    for parl_sess, data in fsob.items():
        parliament = int(parl_sess.split("-")[0])
        for record in data.get("records", []):
            bill_num = record.get("bill_number", "")
            outcome = record.get("outcome", "unknown")
            bill_outcomes[f"{parliament}-{bill_num}"] = outcome

    # ── ANALYSIS 1: Per-bill aggregated scores ────────────────────────────────
    print("\nComputing per-bill aggregated factuality scores...")
    bill_scores = {}

    for bill_key, bill_data in bill_index.items():
        if not bill_data.get("health_tag"):
            continue
        bill_num = bill_data.get("bill_number", "")
        era = bill_data.get("era", 0)
        parliament = ERA_TO_PARLIAMENT.get(int(era), 0)
        outcome = bill_outcomes.get(f"{parliament}-{bill_num}", "unknown")
        dates = bill_data.get("dates", [])

        all_claim_sids = []
        for date in dates:
            for sid in sent_by_date.get(date, []):
                if sid in evidence_by_id:
                    all_claim_sids.append(sid)

        if not all_claim_sids:
            continue

        supported = sum(1 for sid in all_claim_sids if evidence_by_id[sid].get("supported", False))
        total = len(all_claim_sids)
        factuality = supported / total if total > 0 else 0.0

        bill_scores[bill_key] = {
            "bill_number": bill_num,
            "parliament": parliament,
            "outcome": outcome,
            "dates": dates,
            "total_claim_sentences": total,
            "supported_sentences": supported,
            "factuality_score": round(factuality, 4),
        }

    with open(OUTPUT_BILL, "w") as f:
        json.dump(bill_scores, f, indent=2)

    all_f = [v["factuality_score"] for v in bill_scores.values()]
    passed_f = [v["factuality_score"] for v in bill_scores.values()
                if v["outcome"] in ["carried", "passed"]]
    failed_f = [v["factuality_score"] for v in bill_scores.values()
                if v["outcome"] in ["lost", "failed", "defeated"]]

    print(f"Bills scored: {len(bill_scores)}")
    print(f"Mean factuality: {avg(all_f):.4f}")
    print(f"Passed (carried): {avg(passed_f):.4f} (n={len(passed_f)})")
    print(f"Failed (lost): {avg(failed_f):.4f} (n={len(failed_f)})")
    print(f"Saved to {OUTPUT_BILL}")

    # ── ANALYSIS 2: Health-entity-filtered scores ─────────────────────────────
    print("\nComputing health-entity-filtered factuality scores...")
    filtered_scores = {}

    for bill_key, bill_data in bill_index.items():
        if not bill_data.get("health_tag"):
            continue
        bill_num = bill_data.get("bill_number", "")
        era = bill_data.get("era", 0)
        parliament = ERA_TO_PARLIAMENT.get(int(era), 0)
        outcome = bill_outcomes.get(f"{parliament}-{bill_num}", "unknown")
        dates = bill_data.get("dates", [])

        health_claim_sids = []
        for date in dates:
            for sid in sent_by_date.get(date, []):
                if sid in evidence_by_id:
                    ann = evidence_by_id[sid]
                    uris = ann.get("concept_uris", [])
                    if any(is_health_entity(uri) for uri in uris):
                        health_claim_sids.append(sid)

        if not health_claim_sids:
            continue

        supported = sum(1 for sid in health_claim_sids
                       if evidence_by_id[sid].get("supported", False))
        total = len(health_claim_sids)
        factuality = supported / total if total > 0 else 0.0

        filtered_scores[bill_key] = {
            "bill_number": bill_num,
            "parliament": parliament,
            "outcome": outcome,
            "total_health_claim_sentences": total,
            "supported_sentences": supported,
            "factuality_score": round(factuality, 4),
        }

    with open(OUTPUT_FILTERED, "w") as f:
        json.dump(filtered_scores, f, indent=2)

    all_f2 = [v["factuality_score"] for v in filtered_scores.values()]
    passed_f2 = [v["factuality_score"] for v in filtered_scores.values()
                 if v["outcome"] in ["carried", "passed"]]
    failed_f2 = [v["factuality_score"] for v in filtered_scores.values()
                 if v["outcome"] in ["lost", "failed", "defeated"]]

    print(f"Bills scored (health-filtered): {len(filtered_scores)}")
    print(f"Mean factuality (health-filtered): {avg(all_f2):.4f}")
    print(f"Passed (carried): {avg(passed_f2):.4f} (n={len(passed_f2)})")
    print(f"Failed (lost): {avg(failed_f2):.4f} (n={len(failed_f2)})")
    print(f"Saved to {OUTPUT_FILTERED}")

    # ── COMPARISON TO US ──────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("COMPARISON: US vs Ontario Factuality Scores")
    print("="*60)

    with open(US_SCORES) as f:
        us_scores = json.load(f)

    us_all = [v["factuality_score"] for v in us_scores.values() if v["total_sentences"] > 0]
    us_passed = [v["factuality_score"] for v in us_scores.values()
                 if v.get("vote_result","").lower() in ["passed","yea"] and v["total_sentences"] > 0]
    us_failed = [v["factuality_score"] for v in us_scores.values()
                 if v.get("vote_result","").lower() in ["failed","nay"] and v["total_sentences"] > 0]

    print(f"\n{'Metric':<40} {'US':>10} {'Ontario':>10} {'Ontario':>15}")
    print(f"{'':40} {'':>10} {'(per-date)':>10} {'(per-bill)':>15}")
    print("-"*75)
    print(f"{'Mean factuality':<40} {avg(us_all):>10.4f} {0.0989:>10.4f} {avg(all_f):>15.4f}")
    print(f"{'Mean factuality (passed)':<40} {avg(us_passed):>10.4f} {0.0968:>10.4f} {avg(passed_f):>15.4f}")
    print(f"{'Mean factuality (failed)':<40} {avg(us_failed):>10.4f} {0.0922:>10.4f} {avg(failed_f):>15.4f}")
    print(f"{'N passed':<40} {len(us_passed):>10} {939:>10} {len(passed_f):>15}")
    print(f"{'N failed':<40} {len(us_failed):>10} {138:>10} {len(failed_f):>15}")
    print(f"\nNote: Ontario lower factuality reflects full sitting-day corpus")
    print(f"vs US bill-specific debate text. Health-entity-filtered Ontario")
    print(f"score ({avg(all_f2):.4f}) provides a more comparable denominator.")


if __name__ == "__main__":
    main()
