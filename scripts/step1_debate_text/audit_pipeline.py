#!/usr/bin/env python3
"""
audit_pipeline.py   (read only, no network, changes nothing)

Measures every structural problem raised in the Sept 24 meeting. Each problem is
checked with two methods that use different logic, so no conclusion rests on a
single test. Run it BEFORE and AFTER the rebuild.

    python3 scripts/step1_debate_text/audit_pipeline.py | tee audit_report_before.txt
"""
import csv
import glob
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import (rp, load_json, norm_topic, is_procedural_topic, url_session, api_session, find_anchors_en,
                       lang_heuristic, health_hits, fr_bill_re, en_bill_re, first_long_date, dates_in)

SUMMARY = []


def header(title):
    print("\n" + "=" * 90 + "\n" + title + "\n" + "=" * 90, flush=True)


def verdict(name, m1, m2, conclusion):
    SUMMARY.append((name, m1, m2, conclusion))
    print(f"\n  METHOD 1: {m1}\n  METHOD 2: {m2}\n  VERDICT : {conclusion}", flush=True)


def pct(a, b):
    return f"{(100.0 * a / b):.1f}%" if b else "n/a"


# =========================================================================== ONTARIO

def audit_ontario():
    seg = load_json(rp("data/canada/ontario/hansard_api_bill_segments.json"), {}) or {}
    idx = load_json(rp("data/canada/ontario/ontario_bill_index.json"), {}) or {}
    fsob = load_json(rp("data/canada/ontario/ontario_fsob_votes.json"), {}) or {}
    if not seg:
        print("  hansard_api_bill_segments.json not found, Ontario checks skipped")
        return

    # ---- O1: session labels
    header("O1  Ontario session labels (David: 'starts in april?')")
    total = url_mis = api_mis = both_known = url_api_disagree = 0
    per_key = Counter()
    for bk, dates in seg.items():
        key_sess = bk.rsplit("-Bill", 1)[0]
        for d, paras in dates.items():
            for p in paras:
                total += 1
                us, asn = url_session(p.get("url")), api_session(p.get("session"))
                if us and us != key_sess:
                    url_mis += 1
                    per_key[bk] += 1
                if asn and asn != key_sess:
                    api_mis += 1
                if us and asn:
                    both_known += 1
                    url_api_disagree += us != asn
    print(f"  paragraphs: {total:,}")
    print(f"  bill keys with at least one paragraph from a different session: {len(per_key)}")
    for bk, n in per_key.most_common(8):
        print(f"     {bk}: {n} paragraphs whose own URL says another session")
    verdict("Ontario session labels",
            f"paragraph URL session differs from bill key session: {url_mis:,} of {total:,} ({pct(url_mis, total)})",
            f"API session field differs from bill key session: {api_mis:,} ({pct(api_mis, total)}); "
            f"URL and API disagree with each other on {url_api_disagree:,} of {both_known:,}",
            "WRONG if both methods show mismatches while URL and API agree with each other: "
            "the hand-written session table is the error, not the API.")

    # ---- O2: mention-only assignment
    header("O2  Ontario paragraphs assigned because a bill number was mentioned")
    methods = Counter()
    proc_assigned = 0
    blocks_mention_only = blocks_total = 0
    examples = []
    for bk, dates in seg.items():
        num = int(bk.rsplit("Bill", 1)[1]) if bk.rsplit("Bill", 1)[1].isdigit() else None
        for d, paras in dates.items():
            by_topic = defaultdict(list)
            for p in paras:
                methods[(p.get("assignment_method") or "none").split(":")[0]] += 1
                by_topic[p.get("topic") or ""].append(p)
                if is_procedural_topic(norm_topic(p.get("topic"))):
                    proc_assigned += 1
            for topic, ps in by_topic.items():
                blocks_total += 1
                if num is None:
                    continue
                has_anchor = any(a["bill_number"] == num and a["strong"]
                                 for p in ps for a in find_anchors_en(p.get("text", ""), p.get("speaker"), topic))
                if not has_anchor and ps[0].get("assignment_method", "").startswith("bill_number"):
                    blocks_mention_only += 1
                    if len(examples) < 8:
                        examples.append(f"{bk} {d} topic='{topic}' ({len(ps)} paras)")
    print(f"  assignment methods: {dict(methods)}")
    for e in examples:
        print(f"     mention-only block: {e}")
    verdict("Ontario mention-only assignment",
            f"paragraphs under procedural headings (Business of the House, Third Readings, etc.) that were "
            f"assigned to a bill: {proc_assigned:,}",
            f"(bill, date, heading) blocks assigned by bill-number-in-text with no procedural anchor for that "
            f"bill: {blocks_mention_only:,} of {blocks_total:,} ({pct(blocks_mention_only, blocks_total)})",
            "Every one of these is a paragraph that mentions a bill without debating it.")

    # ---- O3: index dates
    header("O3  Ontario index dates vs debate evidence (David: 'jan 17 not there')")
    seg_dates_all = defaultdict(set)
    anchors_by_date = defaultdict(set)
    for bk, dates in seg.items():
        for d, paras in dates.items():
            seg_dates_all[bk].add(d)
            for p in paras:
                for a in find_anchors_en(p.get("text", ""), p.get("speaker"), p.get("topic")):
                    if a["strong"]:
                        anchors_by_date[d].add(a["bill_number"])
    idx_only = no_evidence = checked = 0
    ex = []
    for bk, v in idx.items():
        if not v.get("health_tag"):
            continue
        num = v.get("bill_number")
        for d in v.get("dates", []):
            checked += 1
            if d not in seg_dates_all.get(bk, set()):
                idx_only += 1
            try:
                if int(num) not in anchors_by_date.get(d, set()):
                    no_evidence += 1
                    if len(ex) < 6:
                        ex.append(f"{bk} {d}")
            except (TypeError, ValueError):
                pass
    for e in ex:
        print(f"     index date with no procedural anchor for that bill anywhere that day: {e}")
    b94 = idx.get("33-2-Bill94", {}).get("dates", [])
    if b94:
        print(f"  33-2-Bill94 index dates (first 6): {b94[:6]}")
        print(f"  33-2-Bill94 segment dates (first 6): {sorted(seg_dates_all.get('33-2-Bill94', []))[:6]}")
    verdict("Ontario index dates",
            f"health-bill index dates with no fetched text for that bill: {idx_only:,} of {checked:,} ({pct(idx_only, checked)})",
            f"index dates where no procedural anchor names that bill in any fetched paragraph that day: "
            f"{no_evidence:,} ({pct(no_evidence, checked)})",
            "The index dates record mentions, and the scraper only fetched those dates, so real debate days "
            "outside the index were never collected.")

    # ---- O4: stale downstream corpus
    header("O4  Is the Ontario sentence file built from the current segments?")
    sents = load_json(rp("data/dbpedia_pipeline/ontario/sentences.json"), None)
    if sents:
        seg_dates = set().union(*seg_dates_all.values()) if seg_dates_all else set()
        sent_dates = Counter()
        era_ids = sess_ids = 0
        for s in sents:
            sid = s.get("sentence_id", "")
            m = re.match(r"(\d{4})(\d{2})(\d{2})", sid)
            if m:
                sent_dates[f"{m.group(1)}-{m.group(2)}-{m.group(3)}"] += 1
            if re.search(r"-api-\d{4}b\d+-", sid):
                era_ids += 1
            if re.search(r"\d{2}-\d-Bill\d+", sid):
                sess_ids += 1
        outside = sum(n for d, n in sent_dates.items() if d not in seg_dates)
        n_paras = sum(len(p) for dd in seg.values() for p in dd.values())
        print(f"  sentences: {len(sents):,}   segment paragraphs: {n_paras:,}   ratio {len(sents) / max(n_paras, 1):.1f}")
        verdict("Ontario downstream corpus",
                f"sentences dated on days that do not exist in the current segments: {outside:,} of {len(sents):,} "
                f"({pct(outside, len(sents))})",
                f"sentence IDs in the OLD era format (e.g. -api-1985b32-): {era_ids:,}; in session format: {sess_ids:,}",
                "If either number is large, predications, triples and scores were computed on the OLD corpus, "
                "so no Ontario result reported after the rescrape was derived from the rescrape.")
    else:
        print("  data/dbpedia_pipeline/ontario/sentences.json not found")

    # ---- O5: outcome join collisions
    header("O5  Vote outcome join keys")
    by_parl = defaultdict(set)
    if isinstance(fsob, dict):
        for ps, data in fsob.items():
            sess = api_session(ps)
            recs = data.get("records", []) if isinstance(data, dict) else []
            for r in recs:
                if sess:
                    by_parl[(sess.split("-")[0], str(r.get("bill_number")))].add(sess)
    parl_collisions = sum(1 for v in by_parl.values() if len(v) > 1)
    date_bills = defaultdict(set)
    for bk, v in idx.items():
        if v.get("health_tag"):
            for d in v.get("dates", []):
                date_bills[d].add(bk)
    date_collisions = sum(1 for v in date_bills.values() if len(v) > 1)
    verdict("Outcome join keys",
            f"(parliament, bill number) keys that exist in more than one session of the FSOB file: {parl_collisions:,} "
            f"(compute_factuality_scores.py joins on parliament, so these take the wrong session's outcome)",
            f"dates with two or more health bills in the index: {date_collisions:,} "
            f"(the score script keys bill metadata by date, so one bill overwrites the other)",
            "Both joins must use the full key: session plus bill number.")

    # ---- O6: language
    header("O6  French inside the Ontario corpus (Caprice: 'it went through EN')")
    if sents:
        fr = en = unk = 0
        fr_ex = []
        for s in sents[::max(1, len(sents) // 200000)]:
            lang, _ = lang_heuristic(s.get("text", ""))
            if lang == "fr":
                fr += 1
                if len(fr_ex) < 4:
                    fr_ex.append(s.get("text", "")[:100])
            elif lang == "en":
                en += 1
            else:
                unk += 1
        preds = load_json(rp("data/dbpedia_pipeline/ontario/predications.json"), []) or []
        fr_preds = sum(1 for p in preds if lang_heuristic(p.get("subject", "") + " " + p.get("verb", "") + " "
                                                          + p.get("object", ""))[0] == "fr")
        for e in fr_ex:
            print(f"     French sentence routed to English models: {e}")
        verdict("Ontario French routed to English",
                f"sampled sentences detected as French: {fr:,} of {fr + en + unk:,} ({pct(fr, fr + en + unk)})",
                f"predications whose subject+verb+object read as French: {fr_preds:,} of {len(preds):,}",
                "Every one of these went through en_core_web_lg and Spotlight EN (e.g. 'ai' linked to "
                "Artificial_intelligence).")

    # ---- O7: health tagging
    header("O7  Health tagging of Ontario bills (David: 'bill isnt exact')")
    tagged = [(k, v) for k, v in idx.items() if v.get("health_tag")]
    no_term = [(k, v.get("title", "")) for k, v in tagged if not health_hits(v.get("title", ""))]
    topic_no_term = 0
    for k, _ in no_term:
        topics = {p.get("topic", "") for dd in seg.get(k, {}).values() for p in dd}
        if topics and not any(health_hits(t) for t in topics):
            topic_no_term += 1
    for k, t in no_term[:10]:
        print(f"     tagged health, no health term in title: {k}: {t[:90]}")
    verdict("Ontario health tags",
            f"health-tagged bills whose title contains no health term: {len(no_term)} of {len(tagged)}",
            f"of those, bills whose assigned Hansard headings also contain no health term: {topic_no_term}",
            "These need a manual yes/no from Joanie and David before they stay in the corpus.")


# =========================================================================== QUEBEC

def audit_quebec():
    seg_dir = rp("data/canada/quebec_assembly/bill_segments")
    health = load_json(rp("data/canada/quebec_bills/quebec_health_bills_combined.json"), []) or []
    files = sorted(glob.glob(os.path.join(seg_dir, "*.txt")))
    header("Q1  Quebec segment files: does each file mention its own bill? (Joanie: 'the bill is not mentioned')")
    if not files:
        print("  no Quebec segment files found")
        return
    mention = lower_start = 0
    by_date = defaultdict(dict)
    no_mention_ex = []
    for f in files:
        m = re.match(r"(\d{8})_bill(\d+)\.txt$", os.path.basename(f))
        if not m:
            continue
        d, num = m.group(1), int(m.group(2))
        with open(f, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        by_date[d][num] = text
        if fr_bill_re(num).search(text) or en_bill_re(num).search(text):
            mention += 1
        elif len(no_mention_ex) < 6:
            no_mention_ex.append(os.path.basename(f))
        first = re.search(r"[A-Za-z\u00c0-\u00ff]", text)
        if first and first.group(0).islower():
            lower_start += 1
    n = sum(len(v) for v in by_date.values())
    for e in no_mention_ex:
        print(f"     file never mentions its own bill number: {e}")
    verdict("Quebec file vs bill number",
            f"files whose text mentions their own bill number: {mention:,} of {n:,} ({pct(mention, n)})",
            f"files that begin mid-sentence (first letter lowercase): {lower_start:,} ({pct(lower_start, n)})",
            "A file that never names its bill, or starts mid-sentence, was cut by a marker that fired in the "
            "wrong place.")

    header("Q2  Quebec coverage against the legislative history (Joanie: 'it should be 116')")
    expected = set()
    for rec in health:
        num = str(rec.get("bill_number", "")).strip()
        if not num.isdigit():
            continue
        for deb in rec.get("assembly_debates") or []:
            mm = re.search(r"/(\d{8})/", deb.get("url", ""))
            if mm:
                expected.add((mm.group(1), int(num)))
    have_file = sum(1 for d, num in expected if num in by_date.get(d, {}))
    in_any_text = sum(1 for d, num in expected
                      if any(fr_bill_re(num).search(t) for t in by_date.get(d, {}).values()))
    missing_ex = [f"{d}_bill{num}" for d, num in sorted(expected) if num not in by_date.get(d, {})][:8]
    for e in missing_ex:
        print(f"     cheminement lists this debate, no segment file: {e}")
    post94_files = sum(len(v) for d, v in by_date.items() if d >= "19940101")
    health_files = sum(1 for d, v in by_date.items() for num in v if (d, num) in expected)
    verdict("Quebec coverage",
            f"(date, bill) debates listed in the cheminement that have a segment file: {have_file:,} of {len(expected):,} "
            f"({pct(have_file, len(expected))})",
            f"same debates where the bill number appears in ANY file of that date: {in_any_text:,} "
            f"({pct(in_any_text, len(expected))})",
            f"Separately: of {post94_files:,} post-1994 files, only {health_files:,} are listed health-bill debates; "
            "the rest are other bills that entered the corpus.")


# =========================================================================== US

def audit_us():
    files = sorted(glob.glob(rp("data/us/congressional_record_speeches/*.txt")))
    header("U1  US Congressional Record files")
    if not files:
        print("  no US files found")
        return
    date_mis = date_checked = bound = daily = 0
    interleave_hyph = interleave_sec = lines_total = 0
    whole_day = multi_bill = 0
    ex_date, ex_inter = [], []
    for f in files:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
        if not m:
            continue
        fdate = m.group(1)
        with open(f, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        head = text[:2000]
        pdate = first_long_date(head)
        if pdate:
            date_checked += 1
            if pdate != fdate:
                date_mis += 1
                if len(ex_date) < 6:
                    ex_date.append(f"{os.path.basename(f)} says {pdate}")
        if "GPO-CRECB" in head or re.search(r"Pt\.\s*\d+", head):
            bound += 1
        if re.search(r"Vol(?:ume)?\.?\s*\d+,\s*(?:No|Number)\.?\s*\d+", head):
            daily += 1
        lines = text.splitlines()
        lines_total += len(lines)
        h = sum(1 for ln in lines if re.search(r"\b[a-z]{2,}-\s+[A-Z][a-z]", ln))
        s = sum(1 for ln in lines if re.search(r"[a-z,;]\s+(?:\u2018\u2018|'')?(?:SEC\.|SECTION)\s+\d", ln))
        interleave_hyph += h
        interleave_sec += s
        if (h + s) > 5 and len(ex_inter) < 4:
            ex_inter.append(os.path.basename(f))
        if re.search(r"The Chaplain|offered the following prayer|THE JOURNAL|Daily Digest|Resume of Congressional",
                     text):
            whole_day += 1
        bills = set(re.findall(r"(?<![A-Za-z.])H\.\s?R\.\s?(\d{1,5})\b", text))
        if len(bills) > 3:
            multi_bill += 1
    for e in ex_date:
        print(f"     filename date differs from printed date: {e}")
    for e in ex_inter:
        print(f"     column interleaving detected: {e}")
    verdict("US file dates",
            f"files whose filename date differs from the date printed in the Record header: {date_mis} of {date_checked}",
            f"files from the bound edition (Pt. N) instead of the daily edition (Vol. N, No. N): {bound} of {len(files)} "
            f"(daily edition headers found: {daily})",
            "Late-night sittings put the vote on the next calendar day. The debate lives in the Record of the "
            "legislative day, and David wants the daily edition issue.")
    verdict("US column parsing",
            f"lines with a word broken by a hyphen and followed by a new capitalized word on the same line "
            f"(e.g. '$20 mil- The Clerk'): {interleave_hyph:,} per {lines_total:,} lines",
            f"lines where bill section text (SEC. 2, SECTION 1) is glued onto speech text: {interleave_sec:,}",
            "Both patterns mean two columns were read across as one line.")
    verdict("US bill specificity",
            f"files containing prayer / Journal / Daily Digest boilerplate: {whole_day} of {len(files)}",
            f"files naming more than 3 distinct H.R. numbers: {multi_bill} of {len(files)}",
            "These files are whole days or whole sections, not one bill's debate, so the US denominator was never "
            "bill specific.")
    sents = load_json(rp("data/dbpedia_pipeline/us/sentences.json"), None)
    if sents:
        print(f"  US sentence record keys: {sorted(sents[0].keys())} (no bill key means scores are joined by date)")


def main():
    t0 = time.time()
    audit_ontario()
    audit_quebec()
    audit_us()
    header("SUMMARY")
    for name, m1, m2, c in SUMMARY:
        print(f"\n* {name}\n    1) {m1}\n    2) {m2}\n    -> {c}")
    out = rp("audit_summary.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["check", "method_1", "method_2", "conclusion"])
        w.writerows(SUMMARY)
    print(f"\nWrote {out} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
