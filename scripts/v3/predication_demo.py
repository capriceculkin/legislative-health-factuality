#!/usr/bin/env python3
"""
predication_demo.py   (reads the data, changes nothing)

For the meeting with David. For each sentence it prints what three approaches get out of it:

  A  CURRENT     what the pipeline stored in predications_v3.json for this exact sentence
                 (one subject / main verb / object per sentence)
  B  LINGUISTIC  every clause in the sentence with its full arguments: subject, predicate
                 (following "tried to", "have to" through to the content verb), object or
                 complement, prepositional phrases, negation and modality (would / could /
                 may / might / should, and tried / hoped / planned to). This is the
                 predicate-argument ("linguistic") task.
  C  ENTITIES    the named entities spaCy finds and, for each pair, the words that connect
                 them in the parse. This is the IE / NER task: what could be looked up as a
                 fact in DBpedia.
It ends with the dependency parse, so the structure can be read directly.

Run from the project folder:
  python3 scripts/v3/predication_demo.py                      David's two sentences + 3 real Ontario sentences
  python3 scripts/v3/predication_demo.py --sample us 5        5 US sentences from the data
  python3 scripts/v3/predication_demo.py "Any sentence you want to test."
English only (the French model uses a different set of grammar labels).
Also saves the output to outputs/audit/predication_demo.txt
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REPORT = os.path.join(ROOT, "outputs", "audit", "predication_demo.txt")
LINES = []

DAVID = [
    ("David's example 1, ON 33-2-Bill113, 1986-11-19",
     "The ministry has tried to set up a separate entity."),
    ("David's example 2, ON 33-2-Bill113, 1986-11-19",
     "Members of my own family entered a home for the aged because, despite the presence of a central intake "
     "and so-called planning service in the city of Hamilton, there were no services for the frail elderly."),
]
# three real Ontario sentences from the data, fixed so the demo shows the same ones every time
REAL = [
    ("Ontario, 41-1-Bill9, 2014-12-02",
     "Even international agencies such as the WHO, the IMF and the UN are also asking all governments to take "
     "action in this regard."),
    ("Ontario, 41-1-Bill54, 2015-03-05",
     "How many of our homeless youth in Ontario have been denied access to care as a result of the timing of "
     "their 16th birthday?"),
    ("Ontario, 42-1-Bill277, 2021-05-13",
     "She talked about how under the ADP program\u2014first of all, they could change the ADP program if they liked."),
]
# entity types a knowledge base like DBpedia can link; dates, numbers and ordinals ("16th") are not things
LINKABLE = {"PERSON", "NORP", "FAC", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE"}
HEDGE_AUX = {"would", "could", "may", "might", "should"}
# verbs whose real content is in the verb after "to": tried TO SET UP, have TO PAY, seem TO BE
CONTROL = {"try", "attempt", "want", "need", "begin", "start", "continue", "fail", "seek", "plan", "intend",
           "hope", "refuse", "decide", "manage", "go", "have", "promise", "choose", "expect", "seem", "appear",
           "continue", "wish", "struggle", "propose", "agree"}
HEDGE_VERB = {"seem", "appear", "try", "attempt", "hope", "want", "plan", "intend", "expect", "propose"}
CLAUSE_DEPS = {"ROOT", "conj", "advcl", "ccomp", "xcomp", "relcl", "parataxis", "csubj"}
KIND = {"ROOT": "main clause", "conj": "joined clause", "advcl": "adverbial clause", "ccomp": "reported clause",
        "xcomp": "infinitive clause", "relcl": "relative clause", "parataxis": "side clause", "csubj": "subject clause"}


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def span(t):
    return t.doc[t.left_edge.i: t.right_edge.i + 1].text


def kids(t, *deps):
    return [c for c in t.children if c.dep_ in deps]


def particle(t):
    p = kids(t, "prt")
    return t.lemma_ + (" " + p[0].text if p else "")


def subject_of(t):
    s = kids(t, "nsubj", "nsubjpass", "csubj", "csubjpass")
    if s:
        if s[0].lower_ in ("that", "which", "who", "whom") and t.dep_ == "relcl":
            h = t.head
            return t.doc[h.left_edge.i: h.i + 1].text
        return span(s[0])
    if t.dep_ in ("conj", "xcomp", "advcl") and t.head is not t:
        if t.dep_ == "xcomp":
            o = kids(t.head, "dobj")
            if o:
                return span(o[0])
        return subject_of(t.head) if t.head.pos_ in ("VERB", "AUX") else ""
    if t.dep_ == "relcl":
        h = t.head
        return t.doc[h.left_edge.i: h.i + 1].text
    return ""


def negated(tokens, arg_heads):
    if any(kids(t, "neg") for t in tokens):
        return True
    for h in arg_heads:
        if h is None:
            continue
        if h.lower_ in ("nothing", "nobody", "none", "no-one", "neither") or \
                any(c.dep_ == "det" and c.lower_ in ("no", "neither") for c in h.children):
            return True
    return False


def clauses(doc):
    out, absorbed = [], set()
    for t in doc:
        if t.pos_ not in ("VERB", "AUX") or t.dep_ not in CLAUSE_DEPS or t.i in absorbed:
            continue
        verbs = [t]
        x = kids(t, "xcomp")
        if t.lemma_ in CONTROL and x and x[0].pos_ in ("VERB", "AUX"):
            verbs.append(x[0])
            absorbed.add(x[0].i)
            pred = f"{t.lemma_} to {particle(x[0])}"
        else:
            pred = particle(t)
        content = verbs[-1]
        subj = subject_of(t)
        obj_tokens = [c for v in verbs for c in kids(v, "dobj", "attr", "acomp", "oprd", "dative")]
        existential = bool(kids(t, "expl")) and t.lemma_ == "be"
        subj_head = next(iter(kids(t, "nsubj", "nsubjpass")), None)
        if existential:
            att = kids(t, "attr") or kids(t, "nsubj")
            subj, subj_head, pred = (span(att[0]), att[0], "exist (there is/are)") if att else (subj, subj_head, pred)
            obj_tokens = []
        obj = "; ".join(span(o) for o in obj_tokens)
        preps = []
        for v in verbs:
            for p in kids(v, "prep", "agent"):
                po = kids(p, "pobj", "pcomp")
                preps.append(f"{p.text} {span(po[0])}" if po else span(p))
        comp = [span(c) for v in verbs for c in kids(v, "ccomp")]
        hedge = sorted({a.lower_ for v in verbs for a in kids(v, "aux") if a.lower_ in HEDGE_AUX}
                       | ({t.lemma_} if len(verbs) > 1 and t.lemma_ in HEDGE_VERB else set()))
        neg = negated(verbs, [subj_head] + obj_tokens)
        mark = next((m.text for m in kids(t, "mark")), "")
        out.append({"kind": KIND.get(t.dep_, t.dep_) + (f" ({mark}...)" if mark else ""), "subject": subj,
                    "predicate": pred, "object": obj, "preps": preps, "complement": comp,
                    "negated": neg, "hedge": hedge, "tokens": {v.i for v in verbs} | {o.i for o in obj_tokens},
                    "arg_tokens": [subj_head] + obj_tokens})
    return out


def ent_in(text_span, ents):
    return [e for e in ents if re.search(r"(?<!\w)" + re.escape(e.text) + r"(?!\w)", text_span)]


def dep_path(a, b):
    up = [a] + list(a.ancestors)
    down = [b] + list(b.ancestors)
    ids = [t.i for t in down]
    lca = next((t for t in up if t.i in ids), None)
    if lca is None:
        return []
    left = up[: [t.i for t in up].index(lca.i) + 1]
    right = down[: ids.index(lca.i)]
    return left + list(reversed(right))


def stored(text, store):
    key = re.sub(r"\s+", " ", text).strip()
    return store.get(key, [])


def load_store():
    """full_text -> predication records, from all three jurisdictions' predications_v3.json."""
    store = {}
    for j in ("ontario", "us", "quebec"):
        p = os.path.join(ROOT, "data", "dbpedia_pipeline", j, "predications_v3.json")
        try:
            with open(p, encoding="utf-8") as f:
                for r in json.load(f):
                    store.setdefault(re.sub(r"\s+", " ", str(r.get("full_text", ""))).strip(), []).append(r)
        except (OSError, ValueError):
            say(f"(could not read {p}; section A will be empty for {j})")
    return store


def show(nlp, label, text, store, parse=True):
    doc = nlp(text)
    say("\n" + "=" * 90)
    say(f"[{label}]")
    say(f"\"{text}\"")
    recs = stored(text, store)
    question = text.rstrip().endswith("?")
    say("\nA. CURRENT PIPELINE (stored in predications_v3.json for this sentence)")
    if recs:
        for r in recs:
            say(f"   subject '{r.get('subject')}' | verb '{r.get('verb')}' ({r.get('verb_lemma')}) | "
                f"object '{r.get('object')}' | hedged {r.get('hedged')} | negated {r.get('negated')}")
        say(f"   -> {len(recs)} claim(s) kept from this sentence")
        if question:
            say("   !! the sentence is a QUESTION, yet it was stored as a claim")
    else:
        say("   nothing stored for this sentence (no subject+object on the main verb, or not in the data)")
    cl = clauses(doc)
    say(f"\nB. LINGUISTIC TASK: every clause, full arguments ({len(cl)} clause(s))"
        + ("  [the sentence is a QUESTION: nothing in it is asserted]" if question else ""))
    ents = [e for e in doc.ents if e.label_ in LINKABLE]
    skipped = [e for e in doc.ents if e.label_ not in LINKABLE]
    for n, c in enumerate(cl, 1):
        flags = ", ".join(x for x in (("NEGATED" if c["negated"] else ""),
                                      ("modality: " + "/".join(c["hedge"]) if c["hedge"] else "")) if x)
        say(f"   {n}. {c['kind']}{'  [' + flags + ']' if flags else ''}")
        say(f"      subject:   {c['subject'] or '(none)'}")
        say(f"      predicate: {c['predicate']}")
        if c["object"]:
            say(f"      object:    {c['object']}")
        for p in c["preps"]:
            say(f"      + {p}")
        for x in c["complement"]:
            say(f"      + that-clause: {x}")
        linked = sorted({f"{e.text} ({e.label_})" for e in ent_in(" ".join([c['subject'], c['object']] + c['preps']), ents)})
        say(f"      entities in its arguments: {', '.join(linked) if linked else 'none (nothing DBpedia could look up)'}")
    say("\nC. IE / NER TASK: named entities and what connects each pair")
    if skipped:
        say("   (not linkable, left out: " + ", ".join(f"{e.text} ({e.label_})" for e in skipped) + ")")
    if not ents:
        say("   no named entities: nothing an entity-relation step could look up as a fact")
    else:
        say("   entities: " + ", ".join(dict.fromkeys(f"{e.text} ({e.label_})" for e in ents)))
        pairs = [(a, b) for i, a in enumerate(ents) for b in ents[i + 1:] if a.text != b.text]
        if not pairs:
            say("   only one distinct entity: no entity-entity relation to check")
        for a, b in pairs:
            path = dep_path(a.root, b.root)
            words = [t.text for t in path[1:-1] if t.pos_ in ("VERB", "AUX", "ADP", "NOUN", "ADJ")]
            say(f"   {a.text}  ~  {b.text}:  " + (f"connected through [{' '.join(words)}]" if words
                                                  else "only listed together; nothing in the sentence relates them"))
    if parse:
        say("\nparse (word/grammar label -> the word it depends on):")
        row = []
        for t in doc:
            row.append(f"{t.text}/{t.dep_}->{t.head.text}")
        for k in range(0, len(row), 6):
            say("   " + "   ".join(row[k:k + 6]))


def sample(nlp, j, n):
    p = os.path.join(ROOT, "data", "dbpedia_pipeline", j, "sentences_v3.json")
    try:
        with open(p, encoding="utf-8") as f:
            sents = [s for s in json.load(f) if s.get("lang") == "en" and 12 <= len(s.get("text", "").split()) <= 45]
    except (OSError, ValueError):
        say(f"(could not read {p}; no {j} sample)")
        return []
    rng = random.Random(29)
    pool = rng.sample(sents, min(3000, len(sents)))
    picked = []
    for s, doc in zip(pool, nlp.pipe([s["text"] for s in pool], batch_size=64)):
        if len(doc.ents) >= 2:
            picked.append((f"{j} sample, {s.get('bill_key')} {s.get('date')}", s["text"]))
            if len(picked) >= n:
                break
    return picked


def main():
    try:
        import spacy
    except ImportError:
        sys.exit("spaCy is not installed in this environment (activate the project venv first).")
    try:
        nlp = spacy.load("en_core_web_lg")
    except OSError:
        nlp = spacy.load("en_core_web_sm")
        say("(en_core_web_lg not found; using en_core_web_sm, parses may differ from the pipeline's)")
    args = sys.argv[1:]
    items = []
    if args and args[0] == "--sample":
        j = args[1] if len(args) > 1 else "ontario"
        n = int(args[2]) if len(args) > 2 else 5
        if j not in ("ontario", "us"):
            sys.exit("--sample works for ontario or us (English)")
        items = sample(nlp, j, n)
    elif args:
        items = [("your sentence", " ".join(args))]
    else:
        items = list(DAVID) + list(REAL)
    store = load_store()
    for label, text in items:
        show(nlp, label, text, store)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    print(f"\nSaved {REPORT}")


if __name__ == "__main__":
    main()
