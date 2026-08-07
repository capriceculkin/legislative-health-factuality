"""
compute_factuality_scores.py

Computes a factuality score per health bill from the DBpedia-annotated sentences.

Factuality score = sentences with graph evidence / total claim-bearing sentences

For US bills: computed separately for government (majority) side and opposition side
based on speaker party affiliation from VoteView roll call data.

For now computes bill-level score across all speakers combined.
Speaker-level breakdown requires parliamentarian data (next step).

Usage: python3 scripts/compute_factuality_scores.py
"""

import os, json, csv
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JURISDICTION = os.environ.get("JURISDICTION", "us")
WORK_DIR = os.path.join(REPO_ROOT, "data", "dbpedia_pipeline", JURISDICTION)

ANNOTATED_PATH = os.path.join(WORK_DIR, "annotated_sentences.json")
SENTENCES_PATH = os.path.join(WORK_DIR, "sentences.json")
OUTPUT_PATH = os.path.join(WORK_DIR, "factuality_scores.json")

# bill metadata paths per jurisdiction
BILL_META_PATHS = {
    "us": os.path.join(REPO_ROOT, "data/us/health_bills_final_matched.csv"),
    "ontario": os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json"),
    "quebec": os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills_combined.json"),
}
MATCHED_PATH = BILL_META_PATHS[JURISDICTION]

def main():
    print("Loading annotated sentences...")
    with open(ANNOTATED_PATH, encoding="utf-8") as f:
        annotated = json.load(f)

    print("Loading all sentences...")
    with open(SENTENCES_PATH, encoding="utf-8") as f:
        sentences = json.load(f)

    # build lookup: sentence_id -> has_evidence
    evidence_by_id = {s["sentence_id"]: bool(s.get("supported", False))
                      for s in annotated}

    # group sentences by bill (file)
    # sentence_id format: {filename}_{index}
    bill_sentences = defaultdict(list)
    for s in sentences:
        sid = s["sentence_id"]
        # extract filename from sentence_id
        # sentence_id format: YYYY-MM-DD-{index}
        date = "-".join(sid.split("-")[:3])
        bill_sentences[date].append(sid)

    print(f"Bills with sentences: {len(bill_sentences)}")

    # load bill metadata
    bill_meta = {}
    with open(MATCHED_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            date = row.get("date", "")
            if date:
                bill_meta[date] = {
                    "congress": row.get("congress", ""),
                    "bill_number": row.get("bill_number", ""),
                    "result": row.get("result", ""),
                    "yea_count": row.get("yea_count", ""),
                    "nay_count": row.get("nay_count", ""),
                    "date": date,
                }
                # also load voice vote bills
                with open(os.path.join(REPO_ROOT, "data/us/voice_vote_speeches_status.json")) as f:
                    vv = json.load(f)
                for key, v in vv.items():
                    date = v.get("passage_date", "")
                    if date and date not in bill_meta:
                         bill_meta[date] = {
                            "congress": v.get("congress", ""),
                            "bill_number": v.get("bill", ""),
                            "result": "passed",
                            "yea_count": "",
                            "nay_count": "",
                            "date": date,
                        }

    # compute factuality score per bill file
    scores = {}
    for date, sids in bill_sentences.items():
        # only count claim-bearing sentences (those in annotated set)
        claim_sids = [sid for sid in sids if sid in evidence_by_id]
        total_claims = len(claim_sids)
        supported = sum(1 for sid in claim_sids if evidence_by_id[sid])
        factuality = supported / total_claims if total_claims > 0 else 0.0
        meta = bill_meta.get(date, {})
        
        scores[date] = {
            "filename": date,
            "date": date,
            "congress": meta.get("congress", ""),
            "bill_number": meta.get("bill_number", ""),
            "vote_result": meta.get("result", ""),
            "yea_count": meta.get("yea_count", ""),
            "nay_count": meta.get("nay_count", ""),
            "total_sentences": total_claims,
            "supported_sentences": supported,
            "factuality_score": round(factuality, 4),
        }
        

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)

    # summary stats
    all_scores = [v["factuality_score"] for v in scores.values() if v["total_sentences"] > 0]
    passed = [v["factuality_score"] for v in scores.values()
              if v.get("vote_result","").lower() in ["passed","yea"] and v["total_sentences"] > 0]
    failed = [v["factuality_score"] for v in scores.values()
              if v.get("vote_result","").lower() in ["failed","nay"] and v["total_sentences"] > 0]

    def avg(lst): return sum(lst)/len(lst) if lst else 0

    print(f"\n{'='*60}")
    print(f"Factuality scores computed: {len(scores)} bill-dates")
    print(f"Bills with >0 sentences: {len(all_scores)}")
    print(f"\nOverall mean factuality score: {avg(all_scores):.4f}")
    print(f"Mean factuality - passed bills: {avg(passed):.4f} (n={len(passed)})")
    print(f"Mean factuality - failed bills: {avg(failed):.4f} (n={len(failed)})")
    print(f"\nSaved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
