"""
compute_factuality_scores.py
Computes a factuality score per health bill from the DBpedia-annotated sentences.
Factuality score = sentences with graph evidence / total claim-bearing sentences
Usage: JURISDICTION=ontario python3 scripts/compute_factuality_scores.py
"""
import os, json, csv
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JURISDICTION = os.environ.get("JURISDICTION", "us")
WORK_DIR = os.path.join(REPO_ROOT, "data", "dbpedia_pipeline", JURISDICTION)

ANNOTATED_PATH = os.path.join(WORK_DIR, "annotated_sentences.json")
SENTENCES_PATH = os.path.join(WORK_DIR, "sentences.json")
OUTPUT_PATH = os.path.join(WORK_DIR, "factuality_scores.json")

BILL_META_PATHS = {
    "us": os.path.join(REPO_ROOT, "data/us/health_bills_final_matched.csv"),
    "ontario": os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json"),
    "quebec": os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills_combined.json"),
}
MATCHED_PATH = BILL_META_PATHS[JURISDICTION]


def load_bill_meta():
    bill_meta = {}

    if JURISDICTION == "us":
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
        vv_path = os.path.join(REPO_ROOT, "data/us/voice_vote_speeches_status.json")
        with open(vv_path) as f:
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

    elif JURISDICTION == "ontario":
        with open(MATCHED_PATH, encoding="utf-8") as f:
            idx = json.load(f)
        fsob_path = os.path.join(REPO_ROOT, "data/canada/ontario/ontario_fsob_votes.json")
        with open(fsob_path, encoding="utf-8") as f:
            fsob = json.load(f)

        ERA_TO_PARLIAMENT = {
            1985: 33, 1989: 34, 1993: 35, 1997: 36,
            2001: 37, 2005: 38, 2009: 39, 2013: 40,
            2017: 41, 2021: 42, 2025: 43,
        }

        bill_outcomes = {}
        for parl_sess, data in fsob.items():
            parliament = int(parl_sess.split("-")[0])
            for record in data.get("records", []):
                bill_num = record.get("bill_number", "")
                outcome = record.get("outcome", "unknown")
                bill_outcomes[f"{parliament}-{bill_num}"] = outcome

        for bill_key, bill_data in idx.items():
            if not bill_data.get("health_tag"):
                continue
            bill_num = bill_data.get("bill_number", "")
            era = bill_data.get("era", 0)
            parliament = ERA_TO_PARLIAMENT.get(int(era), 0)
            outcome = bill_outcomes.get(f"{parliament}-{bill_num}", "unknown")
            for date in bill_data.get("dates", []):
                bill_meta[date] = {
                    "bill_number": bill_num,
                    "result": outcome,
                    "date": date,
                }

    elif JURISDICTION == "quebec":
        # Load bill metadata from cheminement which has debate dates in URLs
        cheminement_path = os.path.join(REPO_ROOT, "data/canada/quebec_bills/cheminement_all_sessions.json")
        health_bills_path = os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills_combined.json")
        
        with open(health_bills_path, encoding="utf-8") as f:
            health_bills = json.load(f)
        
        # build set of health bill identifiers (session + number)
        health_set = set()
        for b in health_bills:
            session = b.get("session", "")
            num = b.get("bill_number", "")
            if session and num:
                health_set.add((session, num))
        
        with open(cheminement_path, encoding="utf-8") as f:
            cheminement = json.load(f)
        
        import re as re2
                # Load vote outcomes
        outcomes_path = os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_vote_outcomes_combined.json")
        vote_outcomes = {}
        if os.path.exists(outcomes_path):
            with open(outcomes_path, encoding="utf-8") as f:
                outcomes_data = json.load(f)
            for url, v in outcomes_data.items():
                sess = v.get("session", "")
                t = v.get("title", "")
                import re as re3
                m2 = re3.search(r"n[°o\xa0]\s*(\d+)", t)
                if m2 and sess:
                    vote_outcomes[(sess, m2.group(1))] = v.get("outcome", "unknown")
        for session, bills in cheminement.items():
            for b in bills:
                title = b.get("title", "")
                m = re2.search(r"n[°o\xa0]\s*(\d+)", title)
                if not m:
                    continue
                bill_num = m.group(1)
                if (session, bill_num) not in health_set:
                    continue
                result = vote_outcomes.get((session, bill_num), b.get("result", "unknown"))
                # extract dates from assembly_debates URLs
                for debate in b.get("assembly_debates", []):
                    url = debate.get("url", "")
                    date_m = re2.search(r'/(\d{4})(\d{2})(\d{2})/', url)
                    if date_m:
                        date = f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}"
                        bill_meta[date] = {
                            "bill_number": bill_num,
                            "session": session,
                            "result": result,
                            "date": date,
                        }

    return bill_meta


def main():
    print("Loading annotated sentences...")
    with open(ANNOTATED_PATH, encoding="utf-8") as f:
        annotated = json.load(f)

    print("Loading all sentences...")
    with open(SENTENCES_PATH, encoding="utf-8") as f:
        sentences = json.load(f)

    evidence_by_id = {s["sentence_id"]: bool(s.get("supported", False))
                      for s in annotated}

    bill_sentences = defaultdict(list)
    for s in sentences:
        sid = s["sentence_id"]
        date = "-".join(sid.split("-")[:3])
        bill_sentences[date].append(sid)

    print(f"Bills with sentences: {len(bill_sentences)}")

    bill_meta = load_bill_meta()
    print(f"Bill metadata loaded: {len(bill_meta)} dates")

    scores = {}
    for date, sids in bill_sentences.items():
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

    all_scores = [v["factuality_score"] for v in scores.values() if v["total_sentences"] > 0]
    passed = [v["factuality_score"] for v in scores.values()
            if (v.get("vote_result") or "").lower() in ["passed", "yea", "carried"] and v["total_sentences"] > 0]
    failed = [v["factuality_score"] for v in scores.values()
            if (v.get("vote_result") or "").lower() in  ["failed", "nay", "lost", "defeated"] and v["total_sentences"] > 0]

    def avg(lst): return sum(lst) / len(lst) if lst else 0

    print(f"\n{'='*60}")
    print(f"Factuality scores computed: {len(scores)} bill-dates")
    print(f"Bills with >0 sentences: {len(all_scores)}")
    print(f"\nOverall mean factuality score: {avg(all_scores):.4f}")
    print(f"Mean factuality - passed bills: {avg(passed):.4f} (n={len(passed)})")
    print(f"Mean factuality - failed bills: {avg(failed):.4f} (n={len(failed)})")
    print(f"\nSaved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()