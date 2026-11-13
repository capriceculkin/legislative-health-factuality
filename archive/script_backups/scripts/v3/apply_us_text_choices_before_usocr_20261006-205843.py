#!/usr/bin/env python3
"""
apply_us_text_choices.py

Decides which US sentences and claims count, from the tag us_rebuild.py segment puts on every
paragraph (segments_index.json "para_tags") and the choices in data/us/v3/text_choices.json:

   printed    bill, amendment and conference-report text printed in the Record,
              not spoken by anyone                                       default: out
   votelist   roll-call name lists                                       default: out
   rule       the debate on the rule (H. Res.) that brings the bill up; rule debates
              were left out by title before, so out keeps that rule      default: out
   companion  the House debate on a House bill when the House then passed
              this (Senate) bill in its place and the House bill is not
              itself in the data                                         default: in
   speech     one-minute speeches, special orders and morning-hour
              speeches that mention the bill (question 8)                default: in
   vehicle    days a bill number carried a different, non-health
              measure through the House (question 9)                     default: in
   held       text the checks could not settle (listed for reading)      default: in
   notbill    text read by hand and found not to be about the bill (fix8,
              outputs/audit/fix8_corrections.txt)                default: out
   no_debate_days  bill-days with no member speaking 40+ words beyond
              motions and requests (passed without debate)               default: in

Rows that do not count are MOVED, not deleted, to sentences_v3_set_aside.json and
predications_v3_set_aside.json (each row keeps the tag that moved it). Running again with other
choices first puts every set-aside row back, so a choice can be changed in a minute without
rebuilding anything. Run it AFTER apply_exclusions.py. When build_sentences_v3.py writes a fresh
file (it then holds the set-aside sentences again), the old set-aside files are renamed *_stale.

Each sentence is placed in its paragraph through its sentence_id (US|bill|day|pN|sM), and the
placement is checked against the sentence's own text. If fewer than 99.5% of a bill-day's
sentences check out, an ordered text search places them instead; if any bill-day still cannot be
placed, NOTHING is changed and the bill-days are listed.

Run from the project folder:   python3 scripts/v3/apply_us_text_choices.py
Report: outputs/audit/us_text_choices.txt
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import para_join as PJ   # PATCHED_SENTENCE_JOINS_2026_10_06: a sentence is placed in its paragraph group

ROOT = Path(__file__).resolve().parent.parent.parent
US = ROOT / "data" / "us"
INDEX = US / "v3" / "segments_index.json"
CHOICES = US / "v3" / "text_choices.json"
STATE = US / "v3" / "text_choices_state.json"
PIPE = ROOT / "data" / "dbpedia_pipeline" / "us"
SENT, PRED = PIPE / "sentences_v3.json", PIPE / "predications_v3.json"
SENT_OUT, PRED_OUT = PIPE / "sentences_v3_set_aside.json", PIPE / "predications_v3_set_aside.json"
REPORT = ROOT / "outputs" / "audit" / "us_text_choices.txt"
DEFAULTS = {"printed": "out", "votelist": "out", "rule": "out", "speech": "in", "vehicle": "in", "companion": "in",
            "held": "in", "no_debate_days": "in", "notbill": "out"}
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def dump(o, p):
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False)
    os.replace(tmp, p)


def stamp(p):
    st = p.stat()
    return [st.st_size, st.st_mtime_ns]


def squash(s):
    return re.sub(r"[^0-9a-z]", "", str(s).lower())


SID = re.compile(r"\|p(\d+)\|s(\d+)$")


def main():
    choices = {**DEFAULTS, **(load(CHOICES, {}) or {})}
    if not CHOICES.exists():
        CHOICES.write_text(json.dumps({**DEFAULTS, "_about": "in = the sentences count; out = set aside "
                                       "(see scripts/v3/apply_us_text_choices.py)"}, indent=1), encoding="utf-8")
    out_tags = {k for k, v in choices.items() if k in DEFAULTS and str(v).lower() == "out"}
    say(f"Choices: {', '.join(f'{k} {choices[k]}' for k in DEFAULTS)}")
    sents, preds = load(SENT), load(PRED)
    if sents is None or preds is None:
        sys.exit("US sentences or claims file not found; nothing changed.")
    old_s, old_p = load(SENT_OUT, []) or [], load(PRED_OUT, []) or []
    have = {r.get("sentence_id") for r in sents}
    if any(r.get("sentence_id") in have for r in old_s):
        # the sentence files were rebuilt since the last run: the old set-aside rows belong to that build
        for p in (SENT_OUT, PRED_OUT):
            if p.exists():
                os.replace(p, Path(str(p).replace(".json", "_stale.json")))
        old_s, old_p = [], []
    idx = load(INDEX, []) or []
    rank = {(e["bill_key"], e["debate_date"]): n for n, e in enumerate(idx)}

    def pos(r):
        m = SID.search(str(r.get("sentence_id", "")))
        return (rank.get((r.get("bill_key", ""), r.get("date", "")), 10 ** 9),
                int(m.group(1)) if m else 0, int(m.group(2)) if m else 0)

    gone = {(r.get("bill_key"), r.get("date")) for r in (load(ROOT / "outputs" / "audit" / "exclusions_confirmed.json", [])
                                                         or []) if r.get("jurisdiction") == "us"}

    def restore(rows, aside):
        if not aside:
            return rows
        back = [{k: v for k, v in r.items() if k not in ("_pos", "_set_aside")} for r in aside
                if (r.get("bill_key"), r.get("date")) in rank and (r.get("bill_key"), r.get("date")) not in gone]
        return sorted(rows + back, key=pos)            # sorted() is stable: claims of one sentence keep their order
    sents, preds = restore(sents, old_s), restore(preds, old_p)
    say(f"US now: {len(sents):,} sentences, {len(preds):,} claims (after putting back {len(old_s):,} sentences and "
        f"{len(old_p):,} claims set aside earlier)")

    tags_of = {}
    for e in idx:
        k = (e["bill_key"], e["debate_date"])
        if "para_tags" not in e:
            sys.exit("segments_index.json has no paragraph tags (run us_rebuild.py segment with the sections patch). "
                     "Nothing changed.")
        try:
            paras = [p.strip() for p in (US / e["file"]).read_text(encoding="utf-8").split("\n\n") if p.strip()]
        except OSError:
            paras = []
        tags = [t for t, n in e["para_tags"] for _ in range(n)]
        if len(paras) != len(tags):
            sys.exit(f"{k}: the text file has {len(paras)} paragraphs but the index tags {len(tags)}; nothing changed.")
        nd = bool(e.get("no_debate"))
        tags_of[k] = (paras, [t + ("+no_debate_days" if nd else "") for t in tags], PJ.us_groups(e, paras))

    by_day = defaultdict(list)
    for i, s in enumerate(sents):
        by_day[(s.get("bill_key", ""), s.get("date", ""))].append(i)
    sent_tag, unplaced, method = {}, {}, Counter()
    for k, ids in by_day.items():
        if k not in tags_of:
            unplaced[k] = len(ids)
            continue
        paras, tags, groups = tags_of[k]
        sq = [squash(p) for p in paras]
        for gi, gt in groups:
            sq[gi] = squash(gt)
        placed, ok = {}, 0
        for i in ids:
            m = SID.search(str(sents[i].get("sentence_id", "")))
            t = squash(sents[i].get("text", ""))
            if m and int(m.group(1)) < len(paras) and (not t or t in sq[int(m.group(1))]):
                placed[i] = int(m.group(1))
                ok += 1
        if ok >= 0.995 * len(ids):
            method["paragraph number"] += 1
        else:                                   # ordered text search
            placed, j = {}, 0
            order = sorted(ids, key=lambda i: tuple(int(x) for x in SID.search(str(sents[i].get("sentence_id", "")) or
                                                                              "|p0|s0").groups()) if SID.search(
                str(sents[i].get("sentence_id", ""))) else (0, 0))
            for i in order:
                t = squash(sents[i].get("text", ""))
                kk = next((q for q in range(j, len(sq)) if t and t in sq[q]), None) if t else j
                if kk is not None:
                    placed[i], j = kk, kk
            method["text search"] += 1
        miss = len(ids) - len(placed)
        if miss > 0.005 * len(ids):
            unplaced[k] = miss
        for i, q in placed.items():
            sent_tag[i] = tags[q]
    if unplaced:
        say(f"\n{len(unplaced)} bill-days could not be matched to their paragraphs; NOTHING was changed:")
        for k, n in sorted(unplaced.items())[:40]:
            say(f"   {k[0]} {k[1]}: {n} sentences")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        sys.exit(1)
    say(f"every sentence placed in its paragraph ({dict(method)} bill-days)")

    sid_tag = {sents[i].get("sentence_id"): t for i, t in sent_tag.items()}
    keep_s, aside_s, keep_p, aside_p = [], [], [], []
    tally = defaultdict(lambda: [0, 0, 0, 0])            # tag -> sentences in, out, claims in, out
    for i, s in enumerate(sents):
        t = sent_tag.get(i, "debate")
        parts = set(t.split("+"))
        out = bool(parts & out_tags)
        tally[t][1 if out else 0] += 1
        (aside_s if out else keep_s).append({**s, "_pos": i, "_set_aside": t} if out else s)
    for i, p in enumerate(preds):
        t = sid_tag.get(p.get("sentence_id"), "debate")
        out = bool(set(t.split("+")) & out_tags)
        tally[t][3 if out else 2] += 1
        (aside_p if out else keep_p).append({**p, "_pos": i, "_set_aside": t} if out else p)
    dump(keep_s, SENT)
    dump(keep_p, PRED)
    dump(aside_s, SENT_OUT)
    dump(aside_p, PRED_OUT)
    STATE.write_text(json.dumps({"choices": choices, "sentences_in": len(keep_s), "claims_in": len(keep_p)}),
                     encoding="utf-8")
    say(f"\n{'tag':<34}{'sentences in':>14}{'set aside':>11}{'claims in':>11}{'set aside':>11}")
    for t in sorted(tally, key=lambda t: -(tally[t][0] + tally[t][1])):
        a = tally[t]
        say(f"{t:<34}{a[0]:>14,}{a[1]:>11,}{a[2]:>11,}{a[3]:>11,}")
    say(f"{'TOTAL':<34}{len(keep_s):>14,}{len(aside_s):>11,}{len(keep_p):>11,}{len(aside_p):>11,}")
    bills_in = {p.get("bill_key") for p in keep_p}
    bills_all = bills_in | {p.get("bill_key") for p in aside_p}
    say(f"\nUS bills with claims that count: {len(bills_in)} (of {len(bills_all)} with any claim)")
    gone = sorted(bills_all - bills_in)
    if gone:
        say(f"bills whose claims are all set aside: {', '.join(gone)}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    say(f"wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
