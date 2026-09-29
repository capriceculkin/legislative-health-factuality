#!/usr/bin/env python3
"""
compute_scores_v3.py

Per-bill factuality scores. Replaces the date-keyed join in compute_factuality_scores.py.

Old problems fixed here:
  * Bill metadata was keyed by date, so two health bills debated on the same day
    overwrote each other. Here everything is keyed by bill_key, which is carried from
    the segment all the way into each triple (or recovered from the sentence_id).
  * Ontario outcomes were keyed by parliament plus bill number, so Bill 52 in 33-1 and
    Bill 52 in 33-2 shared one outcome. Here the key is the full session plus bill number.
  * Both denominators David asked about are reported side by side:
      score_over_claims       = supported / triples where both ends linked to DBpedia
      score_over_predications = supported / all predications for the bill

    python3 scripts/v3/compute_scores_v3.py ontario|quebec|us|all [path/to/annotated.json]
"""
import csv
import glob
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import rp, load_json, api_session


def bill_of(rec):
    if rec.get("bill_key"):
        return rec["bill_key"]
    parts = str(rec.get("sentence_id", "")).split("|")
    return parts[1] if len(parts) >= 3 else None


def is_supported(t):
    for k in ("supported", "is_supported", "factual", "verified"):
        if k in t:
            v = t[k]
            return v is True or str(v).lower() in ("true", "1", "yes", "supported")
    for k in ("verdict", "label", "status", "result"):
        if k in t:
            return str(t[k]).lower() in ("supported", "true", "verified", "match")
    return False


def has_both_links(t):
    for sk, ok in (("subj_uris", "obj_uris"), ("subject_uris", "object_uris"), ("subject_uri", "object_uri"),
                   ("subj_uri", "obj_uri")):
        if sk in t or ok in t:
            return bool(t.get(sk)) and bool(t.get(ok))
    return True  # file only holds linked triples


def outcomes(j):
    """Outcomes from data/v3_outcomes.json (scripts/v3/outcomes_v3.py).
    Value is the raw outcome text; empty string when no pass/fail is known."""
    table = load_json(rp("data/v3_outcomes.json"), None)
    if table is None:
        sys.exit("data/v3_outcomes.json not found. Run: python3 scripts/v3/outcomes_v3.py")
    return {k: (v.get("outcome_raw") or "") if v.get("passed") is not None else ""
            for k, v in (table.get(j) or {}).items()}


def outcome_passed(j):
    table = load_json(rp("data/v3_outcomes.json"), None) or {}
    return {k: v.get("passed") for k, v in (table.get(j) or {}).items()}


def run(j, annotated_path=None):
    d = rp("data/dbpedia_pipeline", j)
    if not annotated_path:
        default = os.path.join(d, "annotated_sentences.json")
        cands = sorted(glob.glob(os.path.join(d, "annotated*.json")), key=os.path.getmtime)
        annotated_path = default if os.path.exists(default) else (cands[-1] if cands else None)
    if not annotated_path:
        sys.exit(f"No annotated*.json in {d}. Pass the path as the second argument.")
    triples = load_json(annotated_path) or []
    if isinstance(triples, dict):
        triples = triples.get("triples") or triples.get("results") or list(triples.values())
    preds = load_json(os.path.join(d, "predications_v3.json"), []) or []
    sents = load_json(os.path.join(d, "sentences_v3.json"), []) or []
    print(f"{j}: annotated file {annotated_path}  ({len(triples):,} records)")
    if triples:
        print(f"   first record keys: {sorted(triples[0].keys())}")
    n_sent, n_pred = Counter(), Counter()
    sess_of, fr_pred = {}, Counter()
    for s in sents:
        n_sent[s["bill_key"]] += 1
        sess_of[s["bill_key"]] = s.get("session", "")
    for p in preds:
        n_pred[p["bill_key"]] += 1
        fr_pred[p["bill_key"]] += p.get("language") == "fr"
    claims, supp, no_bill = Counter(), Counter(), 0
    for t in triples:
        b = bill_of(t)
        if not b:
            no_bill += 1
            continue
        if has_both_links(t):
            claims[b] += 1
            supp[b] += is_supported(t)
    if no_bill:
        print(f"   WARNING: {no_bill:,} triples have no bill key. They came from the old pipeline. Rerun extract_v2 "
              "after patch_dbpedia_v3.py.")
    outc = outcomes(j)
    rows = []
    for b in sorted(set(n_pred) | set(claims)):
        rows.append({"bill_key": b, "session": sess_of.get(b, ""), "sentences": n_sent[b], "predications": n_pred[b],
                     "french_predications": fr_pred[b], "claim_bearing_triples": claims[b], "supported": supp[b],
                     "score_over_claims": round(supp[b] / claims[b], 4) if claims[b] else "",
                     "score_over_predications": round(supp[b] / n_pred[b], 4) if n_pred[b] else "",
                     "outcome": outc.get(b, ""), "outcome_found": "Y" if outc.get(b) else "N"})
    out = os.path.join(d, "factuality_scores_v3.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bill_key"])
        w.writeheader()
        w.writerows(rows)
    have = [r for r in rows if r["claim_bearing_triples"]]
    tot_c, tot_s, tot_p = sum(claims.values()), sum(supp.values()), sum(n_pred.values())
    print(f"   bills scored: {len(have)} of {len(rows)}; outcome found for {sum(r['outcome_found'] == 'Y' for r in rows)}")
    print(f"   pooled supported/claims: {tot_s}/{tot_c} = {tot_s / max(tot_c, 1):.4f}   "
          f"supported/predications: {tot_s}/{tot_p} = {tot_s / max(tot_p, 1):.4f}")
    print(f"   supported flag resolved on {sum(is_supported(t) for t in triples):,} records; check that this matches "
          "the annotate stage's own count before using these numbers (second check).")
    print(f"   saved {out}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    path = sys.argv[2] if len(sys.argv) > 2 else None
    for j in (["ontario", "quebec", "us"] if which == "all" else [which]):
        run(j, path)
