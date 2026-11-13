#!/usr/bin/env python3
"""
build_sentences_v3.py

Turns the rebuilt segments into data/dbpedia_pipeline/<jurisdiction>/sentences_v3.json.

Fixes carried here:
  * Every sentence carries bill_key, session and date, and the sentence_id encodes the
    bill key (ON|33-1-Bill94|1986-01-14|p3|s2), so scores can be joined per bill
    instead of per date.
  * Every sentence carries its own language. Language is detected per paragraph and
    per sentence with two different detectors (function-word/diacritic counts and the
    lingua model, when installed). Short or disputed sentences inherit the paragraph's
    language. French in Ontario goes to the French models, English in Quebec goes to
    the English models.

    python3 scripts/v3/build_sentences_v3.py ontario|quebec|us|all
"""
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import rp, load_json, save_json, detect_lang
import para_join as PJ   # PATCHED_SENTENCE_JOINS_2026_10_06: sentences broken across paragraphs are joined (see para_join.py)
TALLY = {}
US_WORDS = PJ.load_us_words(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'us_words.txt'))

DEFAULT_LANG = {"ontario": "en", "quebec": "fr", "us": "en"}
PREFIX = {"ontario": "ON", "quebec": "QC", "us": "US"}
ABBREV = {"mr", "mrs", "ms", "dr", "hon", "st", "no", "nos", "vol", "pp", "p", "sec", "jr", "sr", "gen", "rev",
          "messrs", "mme", "mmes", "m", "mm", "art", "etc", "inc", "ltd", "co", "corp", "dept", "govt", "ont", "que",
          "vs", "pt", "ch", "res", "con", "u.s", "h.r", "e.g", "i.e", "c", "l.r.o", "l.q", "s.o", "r.s.o"}
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"\u201c\u00ab(]?[A-Z\u00c0-\u00dd0-9])")


def split_sentences(text):
    parts = _SPLIT.split(text or "")
    out = []
    for p in parts:
        if out:
            prev = out[-1]
            last = re.search(r"([A-Za-z\u00c0-\u00ff.]+)\.$", prev)
            if (last and last.group(1).lower().rstrip(".") in ABBREV) or re.search(r"(?:^|\s)[A-Z]\.$", prev):
                out[-1] = prev + " " + p
                continue
        out.append(p)
    return [s.strip() for s in out if s.strip()]


def units_ontario():
    seg = load_json(rp("data/canada/ontario/v3/hansard_segments_v3.json")) or sys.exit(
        "Ontario v3 segments not found. Run ontario_rebuild.py first.")
    for key, days in seg.items():
        sess = key.rsplit("-Bill", 1)[0]
        for day, paras in sorted(days.items()):
            yield key, sess, day, list(enumerate(p["text"] for p in paras))


def units_quebec():
    base = rp("data/canada/quebec_assembly")
    idx = load_json(os.path.join(base, "v3", "segments_index.json")) or sys.exit(
        "Quebec v3 index not found. Run quebec_rebuild.py first.")
    vocab = PJ.quebec_vocab(base, idx)
    fixes = PJ.load_ocr_fixes(os.path.join(base, "v3", "ocr_word_fixes.json"))
    for e in idx:
        with open(os.path.join(base, e["file"]), encoding="utf-8") as f:
            text = f.read()
        pre = e.get("source") == "bibliotheque_pre1994"
        if pre:
            text = PJ.fix_quebec_text(text, fixes.get(e["file"]), vocab, TALLY)
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        groups = PJ.quebec_groups(paras, vocab if pre else None, TALLY)
        TALLY["paragraph_joins"] = TALLY.get("paragraph_joins", 0) + len(paras) - len(groups)
        day = f"{e['date'][:4]}-{e['date'][4:6]}-{e['date'][6:]}"
        yield e["bill_key"], e["bill_session"], day, groups


def units_us():
    base = rp("data/us")
    idx = load_json(os.path.join(base, "v3", "segments_index.json")) or sys.exit(
        "US v3 index not found. Run us_rebuild.py first.")
    for e in idx:
        with open(os.path.join(base, e["file"]), encoding="utf-8") as f:
            paras = [p.strip() for p in f.read().split("\n\n") if p.strip()]
        groups = PJ.us_groups(e, paras, US_WORDS, TALLY)
        TALLY["paragraph_joins"] = TALLY.get("paragraph_joins", 0) + len(paras) - len(groups)
        yield e["bill_key"], e["congress"], e["debate_date"], groups


def build(j):
    src = {"ontario": units_ontario, "quebec": units_quebec, "us": units_us}[j]
    out, c_lang, c_method, c_para = [], Counter(), Counter(), Counter()
    for key, sess, day, paras in src():
        for pi, para in paras:
            plang, pmethod = detect_lang(para, DEFAULT_LANG[j])
            c_para[plang] += 1
            for si, s in enumerate(split_sentences(para)):
                if len(s) < 20:
                    continue
                if len(s.split()) < 6:
                    lang, method = plang, "inherited_short"
                else:
                    lang, method = detect_lang(s, plang)
                c_lang[lang] += 1
                c_method[method] += 1
                out.append({"sentence_id": f"{PREFIX[j]}|{key}|{day}|p{pi}|s{si}", "bill_key": key,
                            "session": sess, "date": day, "lang": lang, "lang_method": method, "text": s})
    path = rp("data/dbpedia_pipeline", j, "sentences_v3.json")
    save_json(out, path)
    print(f"{j}: {len(out):,} sentences, {len({s['bill_key'] for s in out})} bills -> {path}")
    print(f"   text repairs: {dict(TALLY)}")
    TALLY.clear()
    print(f"   sentence language: {dict(c_lang)}   paragraph language: {dict(c_para)}")
    print(f"   language method: {dict(c_method)}")
    if not any(m in c_method for m in ("agree", "lingua_only", "disagree_inherited")):
        print("   NOTE: lingua is not installed, so language was checked ONE way (function words). "
              "pip install lingua-language-detector for the second detector.")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for j in (["ontario", "quebec", "us"] if which == "all" else [which]):
        build(j)
