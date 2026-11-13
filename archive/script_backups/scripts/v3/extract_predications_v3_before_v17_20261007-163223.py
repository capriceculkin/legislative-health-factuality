#!/usr/bin/env python3
"""
extract_predications_v3.py

Bilingual version of extract_predications.py. The old script loaded one spaCy model
per jurisdiction, so French sentences in Ontario were parsed by the English model
("Tout a l'heure je vous --ai--> parler", which Spotlight then linked to
Artificial_intelligence) and English sentences in Quebec by the French model.

Here each sentence goes to the model for its own language (the lang field written by
build_sentences_v3.py), and every predication keeps language, bill_key, session and
date. The Spotlight step then uses the matching Spotlight server per predication
(see patch_dbpedia_v3.py).

Rules kept from the original extractor: root verb only, existential roots excluded
(be/have/do; etre/avoir/faire), subject from nsubj/nsubjpass/csubj, object from
dobj/obj/iobj or a prepositional/oblique object, pronoun subjects and objects removed,
subject and object must differ, hedging and negation flagged.

This is a reimplementation, so spot check 50 predications per language (Joanie for the
French ones) before the Spotlight run.

    python3 scripts/v3/extract_predications_v3.py ontario|quebec|us|all
"""
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import rp, load_json, save_json

MODELS = {"en": "en_core_web_lg", "fr": "fr_core_news_lg"}
EXCLUDE_ROOT = {"en": {"be", "have", "do"}, "fr": {"\u00eatre", "avoir", "faire"}}
SUBJ = {"nsubj", "nsubjpass", "csubj", "nsubj:pass", "csubj:pass"}
OBJ = {"dobj", "obj", "iobj"}
OBL = {"obl", "obl:arg", "obl:mod", "obl:agent"}
DROP = {"relcl", "acl", "acl:relcl", "appos", "punct", "cc", "conj", "advcl", "parataxis", "mark", "dep"}
PRON = {
    "en": {"i", "me", "my", "mine", "we", "us", "our", "ours", "you", "your", "yours", "he", "him", "his", "she",
           "her", "hers", "it", "its", "they", "them", "their", "theirs", "this", "that", "these", "those", "who",
           "whom", "which", "what", "there", "here", "one", "someone", "somebody", "everyone", "everybody",
           "anyone", "anybody", "nobody", "none", "something", "anything", "everything", "nothing", "all", "some",
           "each", "both", "myself", "ourselves", "yourself", "yourselves", "himself", "herself", "itself",
           "themselves"},
    "fr": {"je", "j'", "me", "m'", "moi", "tu", "te", "toi", "il", "elle", "on", "nous", "vous", "ils", "elles",
           "le", "la", "les", "lui", "leur", "eux", "se", "s'", "soi", "ce", "c'", "cela", "\u00e7a", "ceci", "celui",
           "celle", "ceux", "celles", "qui", "que", "qu'", "quoi", "dont", "lequel", "laquelle", "lesquels",
           "lesquelles", "y", "en", "tout", "tous", "toutes", "rien", "personne", "quelqu'un", "chacun", "aucun",
           "certains", "plusieurs", "l'un", "l'autre"},
}
HEDGE = {"en": {"may", "might", "could", "would", "should", "possibly", "perhaps", "probably", "likely", "suggest",
                "appear", "seem", "believe", "think"},
         "fr": {"pouvoir", "devoir", "peut-\u00eatre", "probablement", "sembler", "para\u00eetre", "croire", "penser",
                "pourrait", "pourraient", "devrait", "devraient", "sans doute", "vraisemblablement"}}
NEG_FR = {"ne", "n'", "pas", "jamais", "plus", "aucunement", "nullement"}


def span_text(tok, max_tokens=15):
    keep = []

    def walk(t):
        keep.append(t)
        for ch in t.children:
            if ch.dep_ not in DROP:
                walk(ch)
    walk(tok)
    keep.sort(key=lambda t: t.i)
    if len(keep) > max_tokens:
        keep = [t for t in keep if abs(t.i - tok.i) <= 6]
    # PATCHED_CLAIM_SPANS_2026_10_07: join with the sentence's own spacing; a left-out comma or dash becomes a space, and a word joined
    # by hyphens ("not-for-profit") keeps its hyphens
    out = ""
    for k, t in enumerate(keep):
        if k:
            prev = keep[k - 1]
            if t.i == prev.i + 1:
                out += prev.whitespace_
            else:
                gap = [t.doc[j] for j in range(prev.i + 1, t.i)]
                if not prev.whitespace_ and all(g.text in HYPHENS and not g.whitespace_ for g in gap):
                    out += "".join(g.text for g in gap)
                else:
                    out += " "
        out += t.text
    return " ".join(out.split())


HYPHENS = {"-", "\u2010", "\u2011"}
ADDRESS = re.compile(r"^(?:(?:Mr|Mrs|Ms|Madam|Madame)\.?\s+(?:Speaker|Chairman|Chairwoman|Chair|President|Clerk)"
                     r"(?:\s+pro\s+tempore)?|(?:M\.|Mme|Monsieur|Madame)\s+(?:le|la)\s+(?:Pr\u00e9sidente?|"
                     r"Vice-Pr\u00e9sidente?))$", re.I)


def label_or_address(tok):
    """True for a subject that is a speaker label (followed by a colon) or a form of address followed by a comma."""
    # the colon or comma is often attached to the subject itself ("Le President:"), so look after its last word
    words = [t for t in tok.subtree if not (t.pos_ == "PUNCT" or t.dep_ == "punct")] or [tok]
    end = max(t.i for t in words)
    nxt = tok.doc[end + 1] if end + 1 < len(tok.doc) else None
    if nxt is None:
        return False
    if nxt.text == ":":
        return True
    text = " ".join(tok.doc[min(t.i for t in words):end + 1].text.split())
    return nxt.text == "," and bool(ADDRESS.match(text))


def is_pron(tok, text, lang):
    return tok.pos_ == "PRON" or tok.lower_ in PRON[lang] or text.lower() in PRON[lang]


def extract(sent, lang):
    root = sent.root
    if root.pos_ not in ("VERB", "AUX") or root.lemma_.lower() in EXCLUDE_ROOT[lang]:
        return None
    # PATCHED_CLAIM_SPANS_2026_10_07: a speaker label ("Le Vice-President:") or a form of address followed by a
    # comma ("Mr. Speaker, this legislation ...") is not the subject
    subj = next((c for c in root.children if c.dep_ in SUBJ and not label_or_address(c)), None)
    if subj is None:
        return None
    obj = next((c for c in root.children if c.dep_ in OBJ), None)
    if obj is None:
        for c in root.children:
            if c.i < root.i:          # an opening phrase ("In fact,", "At present,") is not the object
                continue
            if lang == "en" and c.dep_ == "prep":
                obj = next((g for g in c.children if g.dep_ == "pobj"), None)
            elif c.dep_ in OBL:
                obj = c
            elif c.dep_ == "xcomp":
                obj = next((g for g in c.children if g.dep_ in OBJ), None)
            if obj is not None:
                break
    if obj is None:
        return None
    s, o = span_text(subj), span_text(obj)
    if not s or not o or s.lower() == o.lower() or is_pron(subj, s, lang) or is_pron(obj, o, lang):
        return None
    words = {t.lemma_.lower() for t in sent} | {t.lower_ for t in sent}
    hedged = bool(words & HEDGE[lang])
    negated = any(c.dep_ == "neg" for c in root.children) or (
        lang == "fr" and any(c.lower_ in NEG_FR for c in root.children))
    return {"subject": s, "verb": root.text, "verb_lemma": root.lemma_.lower(), "object": o,
            "hedged": hedged, "negated": negated}


def run(j):
    import spacy
    sents = load_json(rp("data/dbpedia_pipeline", j, "sentences_v3.json")) or sys.exit(
        f"sentences_v3.json missing for {j}. Run build_sentences_v3.py first.")
    out_path = rp("data/dbpedia_pipeline", j, "predications_v3.json")
    ck_path = out_path + ".checkpoint"
    ck = load_json(ck_path, {"done": {}, "preds": []})
    preds = ck["preds"]
    stats = Counter()
    by_lang = {}
    for s in sents:
        by_lang.setdefault(s["lang"], []).append(s)
    for lang, group in sorted(by_lang.items()):
        if lang not in MODELS:
            continue
        start = ck["done"].get(lang, 0)
        if start >= len(group):
            continue
        print(f"{j} [{lang}] loading {MODELS[lang]} for {len(group):,} sentences (resuming at {start:,})", flush=True)
        nlp = spacy.load(MODELS[lang], disable=["ner"])
        t0 = time.time()
        texts = (x["text"] for x in group[start:])
        for i, doc in enumerate(nlp.pipe(texts, batch_size=256), start):
            src = group[i]
            p = None
            for sent in doc.sents:
                p = extract(sent, lang)
                if p:
                    break
            if p:
                p.update({"sentence_id": src["sentence_id"], "bill_key": src["bill_key"], "session": src["session"],
                          "date": src["date"], "language": lang, "full_text": src["text"]})
                preds.append(p)
                stats[f"{lang}_predications"] += 1
            if (i + 1) % 25000 == 0:
                ck["done"][lang] = i + 1
                save_json(ck, ck_path)
                rate = (i + 1 - start) / max(time.time() - t0, 1)
                print(f"   {i + 1:,}/{len(group):,} ({rate:.0f}/s), predications so far {len(preds):,}", flush=True)
        ck["done"][lang] = len(group)
        save_json(ck, ck_path)
    save_json(preds, out_path)
    if os.path.exists(ck_path):
        os.remove(ck_path)
    n = len(sents)
    print(f"{j}: {len(preds):,} predications from {n:,} sentences ({100.0 * len(preds) / max(n, 1):.1f}%)")
    print(f"   by language: {dict(Counter(p['language'] for p in preds))}")
    print(f"   hedged: {sum(p['hedged'] for p in preds):,}  negated: {sum(p['negated'] for p in preds):,}")
    print(f"   saved {out_path}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for j in (["ontario", "quebec", "us"] if which == "all" else [which]):
        run(j)
