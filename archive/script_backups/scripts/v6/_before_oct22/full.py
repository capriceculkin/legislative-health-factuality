"""full.py   Full predications from the kept lines of the two-of-three vote (design 1), the same way in English and French.

For each kept line it adds, from the Universal Dependencies parse (Stanza, or spaCy when Stanza was not in the vote):
  parts    every other argument of the verb and of its chained verbs ("refused to act"): to whom, for what, when, how,
           modal, with the negation that sits inside an argument kept in place ("not to themselves but off to others")
  time     a time phrase at the very start of a sentence is carried to the clauses joined to it, marked (inherited)
  unstated a line with no object and no other argument is marked "object not stated"; when it is joined by a contrast
           (but / mais) to a clause that has an object, that object is given as a candidate, marked (inferred)
  links    which line each line depends on, and how: the linking word in the sentence (because, but, if, that is why ...)
           and the relation the discourse parse puts between the two units (explanation, contrast, condition ...)
"That is why X" / "c'est pourquoi X" is read as a link (X is the result of the clause before it), not as its own line.

    python3 full.py RULES PARSES.json [--rows n1,n2,...] [--json OUT]
Nothing here loads a parser; it reads the saved parses like parity_score.py."""
import sys, os, json, argparse, re

ap = argparse.ArgumentParser()
ap.add_argument("rules"); ap.add_argument("parses"); ap.add_argument("--rows"); ap.add_argument("--json")
A = ap.parse_args() if __name__ == "__main__" else None
RULES = A.rules if A else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(RULES)); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parity_score as S                      # noqa: E402
P, C = S.load_rules(RULES)
import frames as FR                           # noqa: E402
frame, CORE = FR.make(P)

# Linking words, paired English / French, each with the relation it signals. Multiword ones are matched on the words
# before the clause's verb.
LINKS = [
    ("result",     ["that is why", "this is why", "which is why", "that's why", "therefore", "thus", "so"],
                   ["c'est pourquoi", "c'est pour cela que", "c'est pour ça que", "voilà pourquoi", "donc", "par conséquent"]),
    ("cause",      ["because", "since", "given that", "as"], ["parce que", "parce qu'", "puisque", "puisqu'", "car", "vu que", "étant donné que", "comme"]),
    ("contrast",   ["but", "yet", "however", "whereas", "while"], ["mais", "cependant", "pourtant", "tandis que", "alors que", "toutefois"]),
    ("concession", ["although", "though", "even though", "even if"], ["bien que", "bien qu'", "quoique", "même si"]),
    ("condition",  ["if", "unless"], ["si", "s'", "à moins que", "à moins qu'"]),
    ("time",       ["when", "while", "until", "after", "before", "once", "then"], ["quand", "lorsque", "lorsqu'", "jusqu'à ce que", "après", "avant", "puis", "ensuite", "une fois"]),
    ("purpose",    ["to", "so that", "in order to"], ["pour", "afin de", "afin que", "pour que", "afin d'"]),
    ("addition",   ["and", "also"], ["et", "aussi"]),
    ("alternative", ["or"], ["ou"]),
]
for _rel, en, fr in LINKS:
    assert en and fr, _rel                    # every relation has both sides
REASON_COPULA = {"why", "pourquoi"}           # "that is why", "c'est pourquoi" as a copula clause
DEMONSTR = {"that", "this", "which", "c'", "ce", "cela", "ça", "voilà"}
LABEL = {"OPENING": "opening phrase", "ARGM-TMP": "when", "ARGM-MOD": "modal", "ARGM-NEG": "negation", "ARGM-ADV": "how / extra", "ARG2": "second object"}
NEGW = {"not", "never", "no", "ne", "n'", "n’", "pas", "jamais", "non"}
# Words that are never an argument of their own: relative pronouns (they stand for the noun the clause describes),
# reflexive and adverbial clitics, paired English / French.
NOT_ARG = {"that", "which", "who", "whom", "whose", "que", "qu'", "qu’", "qui", "dont", "lequel", "laquelle", "se", "s'", "s’", "y", "en"}
MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
          "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"}
STANCE = {"in short", "in my opinion", "in fact", "of course", "for instance", "for example", "on average", "in his usual wisdom",
          "en somme", "à mon avis", "en fait", "bien sûr", "par exemple", "en moyenne", "d'autre part", "d’autre part", "par ailleurs", "en effet"}


X_TIME = ["last year", "this year", "today", "yesterday", "now", "then", "recently", "aujourd'hui", "hier", "maintenant", "récemment", "l'an dernier", "l'année dernière", "cette année"]


def is_time(text):
    w = P.fold(text)
    return any(x in MONTHS for x in w) or any(re.fullmatch(r"(1[89]|20)\d\d", x) for x in w)


def fold(s):
    return " ".join(P.fold(s or ""))


def sentences(row, which):
    """Token lists (one per sentence) and a map from the vote's word positions to (sentence, word)."""
    sents = [row["deps_spacy"]] if which == "spacy" else row["deps_stanza"]
    out, where = [], {}
    for si, s in enumerate(sents):
        t = [P.T(*x) for x in s]; P.link_kids(t)
        base = sum(len(x) for x in out)
        for w in t:
            where[base + w.i] = (si, w.i)
        out.append(t)
    return out, where


def chain_tokens(t):
    """The verb and the verbs chained to it by xcomp ("refused to act"), as preds.chain() joins them."""
    _, last = P.chain(t)
    path, x = [last], last
    while x is not t and x.head is not None:
        x = P._TOKS["toks"][x.head] if False else None
        break
    out, y = [t], t
    while y is not last:
        y = next((c for c in y.kids if c.dep == "xcomp" and P.is_verbal(c) and not P.has_subj(c)), None)
        if y is None:
            break
        out.append(y)
    return out


def link_word(toks, h, lang):
    """The linking word of the clause headed by h, and its relation. spaCy's English labels hang "and / but" on the first
    clause instead of the second, so for a joined clause the words between the two clauses count too."""
    before = [c for c in sorted(h.kids, key=lambda x: x.i) if c.i < h.i and c.dep in ("mark", "cc", "advmod", "case", "fixed")]
    if h.dep == "conj" and h.head is not None:
        g = toks[h.head]
        before = sorted(before + [c for c in g.kids if c.dep == "cc" and g.i < c.i < h.i], key=lambda x: x.i)
    words = [c.text.lower() for c in before]
    phrase = " ".join(words)
    side = 1 if lang == "en" else 2
    best = None
    for rel, *sides in LINKS:
        for w in sorted(sides[side - 1], key=len, reverse=True):
            if re.search(r"(^| )" + re.escape(w) + r"( |$)", phrase) and (best is None or len(w) > len(best[1])):
                best = (rel, w)
    return best


def disc_relation(d, ea, eb):
    """The discourse relation joining the units ea and eb: the smallest relation with one unit on each side."""
    if not d or ea is None or eb is None or ea == eb:
        return None
    best = None
    for r in d["relations"]:
        L, R = r["left"], r["right"]
        inL = lambda e: L[0] <= e <= L[1]
        inR = lambda e: R[0] <= e <= R[1]
        if (inL(ea) and inR(eb)) or (inL(eb) and inR(ea)):
            size = (L[1] - L[0]) + (R[1] - R[0])
            if best is None or size < best[0]:
                best = (size, r["relation"])
    return best[1] if best else None


def tree_parts(row, at, obj):
    """Arguments from the constituency tree: the phrases beside the verb (English: inside its VP; French: beside its VN)."""
    lang = row["lang"]
    trees = [P.parse_tree(t) if isinstance(t, str) else P._tuples(t) for t in row.get("trees", [])]
    off, found = 0, None
    def walk(n, start, parents):
        nonlocal found
        if isinstance(n, str):
            return start + 1
        pos = start
        for k in n[1]:
            end = walk(k, pos, parents + [n])
            if found is None and pos <= at < end and isinstance(k, str):
                found = parents + [n]
            pos = end
        return pos
    chain_ = None
    for t in trees:
        found = None
        n_leaves = len(P.leaves(t))
        if off <= at < off + n_leaves:
            walk(t, off, [])
            chain_ = found
            break
        off += n_leaves
    if not chain_:
        return []
    node = None
    if lang == "en":
        node = next((n for n in reversed(chain_) if P.lab(n) == "VP"), None)
    else:
        vn = next((i for i in range(len(chain_) - 1, -1, -1) if P.lab(chain_[i]) == "VN"), None)
        node = chain_[vn - 1] if vn else None
    if node is None:
        return []
    out, of = [], fold(obj)
    for k in node[1]:
        if isinstance(k, str) or P.lab(k) not in ("PP", "ADVP", "AdP", "NP"):
            continue
        txt = P.text(k)
        ft = fold(txt)
        if not ft or (of and (ft in of or of in ft)) or ft in {fold(w) for w in NOT_ARG}:
            continue
        if P.lab(k) == "NP" and not is_time(txt) and fold(txt).split(" ")[0] not in {fold(w) for w in X_TIME}:
            continue                                   # a bare noun phrase beside the verb is the object, not a part
        w = [x for x in ft.split(" ") if x not in NEGW]
        role = "ARGM-TMP" if (is_time(txt) or (w and w[0] in {fold(x) for x in X_TIME})) else ("ARGM-" + (w[0] if w else "ADV"))
        if P.lab(k) in ("ADVP", "AdP") and role != "ARGM-TMP":
            role = "ARGM-ADV"
        if ft in {fold(x) for x in STANCE}:
            role = "OPENING"
        part = {"role": role, "label": LABEL.get(role, role.replace("ARGM-", "")), "text": txt, "tok": None}
        if ft.split(" ")[0] in NEGW:
            part["negated"] = True
        out.append(part)
    return out



# Complements and adjuncts (Huddleston and Pullum, ch. 4): a complement is licensed by the verb (the object, the person
# something is given or said to, what is said), an adjunct can go with almost any verb (time, place, manner, reason).
# Verbs that take a recipient, paired English / French (lemmas):
RECIP_VERBS = [
    (["give", "send", "offer", "provide", "grant", "pay", "sell", "transfer", "deliver", "lend", "owe", "award", "allocate", "assign", "submit", "present", "return"],
     ["donner", "envoyer", "offrir", "fournir", "accorder", "payer", "verser", "vendre", "transférer", "remettre", "prêter", "devoir", "attribuer", "allouer", "soumettre", "présenter", "rendre"]),
    (["say", "tell", "explain", "write", "show", "report", "announce", "ask", "promise", "propose", "recommend", "suggest", "declare", "repeat", "mention"],
     ["dire", "expliquer", "écrire", "montrer", "rapporter", "annoncer", "demander", "promettre", "proposer", "recommander", "suggérer", "déclarer", "répéter", "mentionner"]),
]
# Verbs whose direct object is the person told and whose clause is what is told
TELL_PERSON = [(["tell", "inform", "notify", "remind", "assure", "warn", "advise", "convince", "persuade"],
                ["informer", "aviser", "avertir", "prévenir", "assurer", "convaincre", "persuader"])]
RECIP_PREP = [(["to"], ["à", "au", "aux"])]
# Prepositions that usually start an adjunct when they hang on a verb (a guess where UD does not say: English obl)
ADJUNCT_PREP = [(["in", "at", "during", "under", "after", "before", "since", "despite", "throughout", "within", "across", "until", "because", "as"],
                 ["dans", "en", "pendant", "sous", "après", "avant", "depuis", "malgré", "lors", "durant", "parmi", "comme"])]
for _en, _fr in RECIP_VERBS + TELL_PERSON + RECIP_PREP + ADJUNCT_PREP:
    assert _en and _fr
_both = lambda L: {w for en, fr in L for w in en + fr}
RV, TP, RP, AP = _both(RECIP_VERBS), _both(TELL_PERSON), _both(RECIP_PREP), _both(ADJUNCT_PREP)


def complements(rec, content=None, content_words=""):
    """Recipient, complements and adjuncts for one line (changes rec in place). content: the number of the line that
    is this verb's clause ("what is said / told"), when that clause is its own predication."""
    lem = (rec.get("lemma") or "").lower()
    first = lambda x: fold(x).split(" ")[0] if x else ""
    parts = rec["parts"]
    clause = next((q for q in parts if q["role"] == "ARG1" and q.get("dep") in ("ccomp", "xcomp", "")), None)
    if clause is None and content is not None and (not rec["object"] or lem in TP | {"tell"} or first(rec["object"]) in RP):
        clause = {"role": "ARG1", "label": "what is said", "text": f"[what is said: predication {content + 1}]", "dep": "ccomp", "ref": content, "words": content_words}
        parts.append(clause)
    io = next((q for q in parts if q.get("dep") == "iobj"), None)
    if io is not None:                                    # the parse itself marks the indirect object
        rec["recipient"] = io["text"]; parts.remove(io)
    is_clause = bool(content_words) and fold(rec["object"]) in (fold(content_words), fold("that " + content_words), fold("que " + content_words))
    # the object slot holds "to X" / "au X" for a giving or saying verb: X is the recipient
    if "recipient" in rec:
        pass
    elif rec["object"] and first(rec["object"]) in RP and lem in RV:
        rec["recipient"] = rec["object"]; rec["object"] = ""
        rec["notes"].append("recipient moved out of the object slot")
    # tell X that ...: X is the person told, the clause is what is told
    elif rec["object"] and lem in TP | {"tell"} and clause is not None and not is_clause and first(rec["object"]) not in ("that", "que", "qu'"):
        rec["recipient"] = rec["object"]; rec["object"] = clause["text"]; rec["object_words"] = clause.get("words", ""); parts.remove(clause)
        rec["notes"].append("the person told is the recipient; what is told is the object")
    if not rec["object"] and clause is not None and lem in RV:
        rec["object"] = clause["text"]; rec["object_words"] = clause.get("words", ""); parts.remove(clause)
    for q in list(parts):
        dep, w = q.get("dep", ""), first(q["text"])
        if w in {"not", "ne", "pas"}:
            w = next((x for x in fold(q["text"]).split(" ") if x not in NEGW), w)
        if "recipient" not in rec and (dep == "iobj" or (w in RP and lem in RV)):
            rec["recipient"] = q["text"]; parts.remove(q); continue
        if q["role"] in ("ARGM-TMP", "ARGM-ADV", "OPENING", "ARGM-MOD"):
            q["kind"], q["why"] = ("adjunct", "time, manner or scene") if q["role"] != "ARGM-MOD" else ("modal", "helper verb")
        elif dep == "obl:arg":
            q["kind"], q["why"] = "complement", "UD label obl:arg (required by the verb)"
        elif dep in ("obl:mod", "advmod", "advcl", "obl:tmod", "nmod:tmod", "npadvmod"):
            q["kind"], q["why"] = "adjunct", f"UD label {dep}"
        elif q["role"] in ("ARG0", "ARG1", "ARG2"):
            q["kind"], q["why"] = "complement", "core argument"
        elif w in AP:
            q["kind"], q["why"] = "adjunct", f"starts with '{w}' (word-list guess)"
        else:
            q["kind"], q["why"] = "complement", f"starts with '{w}' (word-list guess)"
    rec["parts"] = [q for q in parts if not (q.get("ref") is not None and rec["object"])]     # an unused "what is said" pointer
    rec["triple"] = [(rec["subject"] or "").replace(" (inh)", ""), rec["verb"], rec.get("object_words") or rec["object"] or rec.get("candidate", "")]


def tree_backbone(out3, plus=False):
    """David's proposal (Oct 20): the constituency tree is the backbone; the two dependency parses only find its errors.
    Every tree line is kept, in the tree's own wording. For each one, the dependency lines with the same verb are found
    (one per parse, first unused match, the vote's order). When both dependency parses agree with each other on that
    verb's subject or object and the tree differs, the tree's subject or object is corrected to theirs and marked.
    Tree lines no dependency parse has at all are kept but marked unconfirmed. With plus=True, lines that both dependency
    parses produce and the tree does not are added, marked as missed by the tree."""
    used = {"spacy": set(), "stanza": set()}
    out = []
    for t in out3.get("const", []):
        rec = dict(t, found_by=["const"], at_by={"const": t["at"]}, notes=[])
        cand = {}
        for m in ("spacy", "stanza"):
            j = next((j for j, q in enumerate(out3[m]) if j not in used[m] and P.verb_match(t["verb"], q["verb"])
                      and bool(q["negated"]) == bool(t["negated"])), None)
            if j is not None:
                cand[m] = j
        for m, j in cand.items():
            used[m].add(j)
            rec["at_by"][m] = out3[m][j]["at"]
            if C.same(t, out3[m][j]):
                rec["found_by"].append(m)
        if len(cand) == 2:
            a, b = out3["spacy"][cand["spacy"]], out3["stanza"][cand["stanza"]]
            for f in ("subject", "object"):
                fa, fb, ft = fold(a[f]), fold(b[f]), fold(t[f])
                if fa and fa == fb and fa != ft:
                    rec["notes"].append(f"{f} corrected by both dependency parses (tree had {t[f]!r})")
                    rec[f] = a[f]
        if len(rec["found_by"]) == 1:
            rec["notes"].append("no dependency parse has this line (unconfirmed)")
        out.append(rec)
    if plus:
        for i, a in enumerate(out3["spacy"]):
            if i in used["spacy"]:
                continue
            j = next((j for j, q in enumerate(out3["stanza"]) if j not in used["stanza"] and C.same(a, q)), None)
            if j is not None:
                used["stanza"].add(j)
                out.append(dict(a, found_by=["spacy", "stanza"], at_by={"spacy": a["at"], "stanza": out3["stanza"][j]["at"]},
                                notes=["missed by the tree; both dependency parses have it"]))
    return out


def full_row(row, policy="multi", method="vote", wording="majority"):
    """method: "vote" (the kept lines of the two-of-three vote) or one parser alone: "spacy", "stanza", "const"."""
    res = S.analyze(P, C, row, "native", "prod", policy)
    lang = row["lang"]
    if res["skipped"]:
        return {"n": row["n"], "text": row["text"], "skipped": res["skipped"], "lines": []}
    d = row.get("disc_native")
    SP, Swhere = sentences(row, "stanza")
    DP, Dwhere = sentences(row, "spacy")
    out3 = C.run(row, P)
    if method == "vote":
        base = res["final"]
    elif method in ("tree_fixed", "tree_plus"):
        base = tree_backbone(out3, plus=(method == "tree_plus"))
        r_ = {"n": row["n"], "lang": lang, "text": row["text"], "deps_spacy": row["deps_spacy"], "deps_stanza": row["deps_stanza"], "trees": row.get("trees", [])}
        S.apply_rst(P, C, base, [], r_, d)
        base = [dict(p, kind=p.get("kind_rst", p["kind"])) for p in base]
    else:
        base = [dict(p, found_by=[method], at_by={method: p["at"]}) for p in out3[method]]
        r_ = {"n": row["n"], "lang": lang, "text": row["text"], "deps_spacy": row["deps_spacy"], "deps_stanza": row["deps_stanza"], "trees": row.get("trees", [])}
        S.apply_rst(P, C, base, [], r_, d)
        base = [dict(p, kind=p.get("kind_rst", p["kind"])) for p in base]
    lines = []
    for p in base:
        rec = {k: p.get(k) for k in ("subject", "verb", "object", "kind", "negated", "hedged", "found_by", "how")}
        mem = [next((q for q in out3.get(m, []) if q["at"] == p["at_by"][m]), None) for m in (p.get("found_by") or []) if m in p.get("at_by", {})]
        mem = [q for q in mem if q]
        if wording == "stanza" and "stanza" in (p.get("found_by") or []):
            q = next((q for q in out3["stanza"] if q["at"] == p["at_by"]["stanza"]), None)
            if q:                                          # variant: the vote decides which lines to keep, Stanza gives the words
                for f in ("subject", "verb", "object"):
                    rec[f] = q[f]
                mem = []
        if method.startswith("tree"):
            mem = []                                       # the backbone keeps the tree's own wording
        if len(mem) >= 2:                                  # the wording most of the parsers agree on, not just the first parser's
            for f in ("subject", "verb", "object"):
                vals = [q[f] for q in mem]
                top = max(set(vals), key=vals.count)
                if vals.count(top) >= 2 and top != rec[f]:
                    rec["notes"] = rec.get("notes", []) + [f"{f}: majority wording ({rec[f]!r} was the first parser's)"]
                    rec[f] = top
        rec.update(parts=[], links=[], notes=rec.get("notes", []) + list(p.get("notes") or []), edu=p.get("edu"), source=None, head=None,
                   at_by=dict(p.get("at_by") or {}))
        if "apposition" in (p.get("verb") or ""):
            rec["source"] = "apposition"; lines.append(rec); continue
        at = p.get("at_by", {})
        tree_m = method.startswith("tree")
        if "stanza" in at and at["stanza"] in Swhere and (method in ("vote", "stanza") or (tree_m and "const" not in at)):
            si, wi = Swhere[at["stanza"]]; toks = SP[si]; rec["source"] = "stanza"
        elif "spacy" in at and at["spacy"] in Dwhere and method in ("vote", "spacy"):
            si, wi = Dwhere[at["spacy"]]; toks = DP[si]; rec["source"] = "spacy"
        else:
            rec["source"] = "tree only"
            if "const" in at:
                rec["parts"] = tree_parts(row, at["const"], rec["object"] or "")
                if not rec["object"]:
                    core_ = [q for q in rec["parts"] if not q["role"] in ("ARGM-TMP", "ARGM-ADV", "OPENING")]
                    if core_:
                        rec["object"] = core_[0]["text"]; rec["parts"].remove(core_[0])
            if tree_m and "stanza" in at and at["stanza"] in Swhere:
                si, wi = Swhere[at["stanza"]]
                rec["head"] = ("stanza", si, wi)            # ties between clauses read from the dependency parse
                rec["source"] = "tree (ties from Stanza)"
            lines.append(rec); continue
        P._TOKS["toks"] = toks
        t = toks[wi]
        rec["head"] = (rec["source"], si, wi)
        chained = chain_tokens(t)
        rec["lemma"] = chained[-1].lemma if chained else t.lemma
        cids = {x.i for x in chained}
        obj_f = fold(rec["object"])
        for x in chained:
            f = frame(toks, x, dict(p, lang=lang))
            for role, text, ti in f["roles"]:
                if ti is not None and (ti in cids or toks[ti].dep in P.SUBJ):
                    continue
                if role == "ARGM-NEG" and rec["negated"]:
                    continue                                  # the line already says negated
                ft = fold(text)
                if ft in NOT_ARG or ft in {fold(w) for w in NOT_ARG} or ft in REASON_COPULA:
                    continue
                if role.startswith("ARGM-") and role not in ("ARGM-TMP", "ARGM-MOD", "ARGM-NEG") and is_time(text):
                    role = "ARGM-TMP"
                if ft in {fold(w) for w in STANCE} or (role.startswith("ARGM-") and role not in ("ARGM-TMP", "ARGM-MOD", "ARGM-NEG")
                                                         and ti is not None and ti < x.i and any(c.dep in P.SUBJ and c.i > ti for c in x.kids)):
                    role = "OPENING"                          # a phrase before the subject sets the scene; it is not an argument
                if not ft or (obj_f and (ft in obj_f or obj_f in ft and role in ("ARG1",))):
                    continue
                if role in ("ARG1",) and not rec["object"]:
                    rec["object"] = text; obj_f = ft; continue
                lab = LABEL.get(role, role.replace("ARGM-", "") if role.startswith("ARGM-") else role)
                part = {"role": role, "label": lab, "text": text, "tok": ti, "dep": toks[ti].dep if ti is not None else ""}
                if ft.split(" ")[0] in NEGW:
                    part["negated"] = True
                if not any(fold(q["text"]) == ft for q in rec["parts"]):
                    rec["parts"].append(part)
        lines.append(rec)
    so_, _x = C.offsets(row["deps_spacy"])
    sto_, _y = C.offsets([t_ for sent in row["deps_stanza"] for t_ in sent])
    by_off = {"spacy": {o: k for k, o in enumerate(so_)}, "stanza": {o: k for k, o in enumerate(sto_)}}
    pos_off = {"spacy": so_, "stanza": sto_}

    def spots(rec):
        """Every position of this line's verb, in each dependency parse that has it (so lines kept from different parses
        can still be tied to each other)."""
        out = [rec["head"]] if rec["head"] else []
        at_ = dict(rec.get("at_by", {}))
        for m, o in (("stanza", "spacy"), ("spacy", "stanza")):    # the same word in the other parse, by its place in the text
            if m not in at_ and o in at_ and at_[o] < len(pos_off[o]):
                k = by_off[m].get(pos_off[o][at_[o]])
                if k is not None:
                    at_[m] = k
        for m, where in (("stanza", Swhere), ("spacy", Dwhere)):
            k = at_.get(m)
            if k is not None and k in where:
                out.append((m,) + where[k])
        return out
    own = {}
    for rec in lines:
        for sp_ in spots(rec):
            own.setdefault(sp_[:2], set()).add(sp_[2])
    for rec in lines:
        if rec["head"]:
            src, si, wi = rec["head"]
            toks = (SP if src == "stanza" else DP)[si]
            heads_here = own.get((src, si), set()) - {wi}
            rec["parts"] = [q for q in rec["parts"] if q.get("tok") not in heads_here]

    # links between lines: the nearest line above in the tree
    heads = {}
    for i, rec in enumerate(lines):
        for sp_ in spots(rec):
            heads.setdefault(sp_, i)
    for i, rec in enumerate(lines):
        if not rec["head"]:
            continue
        src, si, wi = rec["head"]
        toks = (SP if src == "stanza" else DP)[si]
        t = toks[wi]
        x, gov = t, None
        while x.head is not None:
            x = toks[x.head]
            j = heads.get((src, si, x.i))
            if j is not None and j != i:
                gov = j; break
        if gov is None:
            continue
        lw = link_word(toks, t, lang)
        rel = lw[0] if lw else {"conj": "addition (joined)", "advcl": "adverbial", "ccomp": "content", "xcomp": "complement",
                                "acl:relcl": "describes", "relcl": "describes", "acl": "describes", "parataxis": "side clause"}.get(t.dep, t.dep)
        rec["links"].append({"to": gov, "relation": rel, "word": lw[1] if lw else "", "discourse": disc_relation(d, lines[gov]["edu"], rec["edu"])})

    # "that is why X" / "c'est pourquoi X": the copula line becomes a link; X is the result of the clause before it
    drop = set()
    for i, rec in enumerate(lines):
        if not rec["head"] or fold(rec["subject"]) not in {fold(w) for w in DEMONSTR}:
            continue
        o = fold(rec["object"]).split(" ")
        if not o or o[0] not in REASON_COPULA:
            continue
        inner = next((j for j, q in enumerate(lines) if j != i and any(l["to"] == i for l in q["links"])), None)
        before = rec["links"][0]["to"] if rec["links"] else None
        if inner is None:
            continue
        drop.add(i)
        q = lines[inner]
        q["links"] = [l for l in q["links"] if l["to"] != i]
        if before is not None:
            q["links"].append({"to": before, "relation": "result", "word": " ".join(rec["subject"].split() + rec["verb"].split() + [o[0]]),
                               "discourse": disc_relation(d, lines[before]["edu"], q["edu"])})
        if q["kind"] == "embedded":
            q["kind"] = "asserted"; q["notes"].append("stated: it is what the speaker concludes (that is why ...)")
    # a time phrase opening the sentence carries to the clauses joined to it
    for i, rec in enumerate(lines):
        for l in rec["links"]:
            g = lines[l["to"]]
            if l["relation"].startswith(("addition", "contrast", "time")) and not any(q["role"] == "ARGM-TMP" for q in rec["parts"]):
                tm = [q for q in g["parts"] if q["role"] == "ARGM-TMP"]
                if tm and g["head"]:
                    src, si, wi = g["head"]
                    toks = (SP if src == "stanza" else DP)[si]
                    first = min((c.i for c in toks if c.dep != "punct"), default=0)
                    tm_tok = next((c for c in toks[wi].kids if fold(P.span(toks, c)) == fold(tm[0]["text"])), None)
                    if tm_tok is not None and min(x.i for x in [tm_tok] + _sub(tm_tok)) == first:
                        rec["parts"].append({"role": "ARGM-TMP", "label": "when", "text": tm[0]["text"], "inherited": True})
                        rec["notes"].append("time phrase opens the sentence; it may cover this clause too")
    # an object that is not stated
    for i, rec in enumerate(lines):
        if rec["source"] in ("apposition", "tree only") or i in drop:
            continue
        real = [q for q in rec["parts"] if q["role"] not in ("ARGM-TMP", "ARGM-MOD", "ARGM-NEG", "ARGM-ADV")]
        if not rec["object"] and not real:
            rec["unstated"] = "object not stated"
            for l in rec["links"]:
                g = lines[l["to"]]
                if l["relation"] == "contrast" and g["object"]:
                    rec["candidate"] = g["object"]
                    rec["notes"].append(f"refers back to: {g['object']} (inferred, not in the words)")
    for k, r in enumerate(lines):
        if r["source"] != "apposition":
            cont = next((j for j, q in enumerate(lines) if j not in drop and any(l["to"] == k and l["relation"] == "content" for l in q["links"])), None)
            words = ""
            if cont is not None and lines[cont]["head"]:
                src_, si_, wi_ = lines[cont]["head"]
                tk_ = (SP if src_ == "stanza" else DP)[si_]
                words = P.span(tk_, tk_[wi_], drop_clauses=False, limit=60)
            complements(r, cont, words)
    out = [r for i, r in enumerate(lines) if i not in drop]
    remap = {old: new for new, old in enumerate(i for i in range(len(lines)) if i not in drop)}
    for r in out:
        for l in r["links"]:
            l["to"] = remap.get(l["to"], l["to"])
    return {"n": row["n"], "text": row["text"], "lang": lang, "lines": out, "dropped": [lines[i]["verb"] for i in drop]}


def _sub(t):
    out, st = [], list(t.kids)
    while st:
        x = st.pop(); out.append(x); st += x.kids
    return out


def show(fr):
    print("==", fr["n"], fr["text"])
    for i, r in enumerate(fr["lines"]):
        neg = " NEGATED" if r.get("negated") else ""
        hed = " HEDGED" if r.get("hedged") else ""
        print(f"  [{i}] {r['subject']} | {r['verb']} | {r['object'] or '(' + r.get('unstated', 'no object') + ')'}   {r['kind']}{neg}{hed}  found by {len(r.get('found_by') or [])}")
        if r.get("recipient"):
            print(f"        recipient: {r['recipient']}")
        for q in r["parts"]:
            print(f"        {q.get('kind', '')} {q['label']}: {q['text']}" + (" (inherited)" if q.get("inherited") else "") + (" [negated part]" if q.get("negated") else ""))
        for l in r["links"]:
            print(f"        link -> [{l['to']}] {l['relation']}" + (f" ('{l['word']}')" if l["word"] else "") + (f"; discourse: {l['discourse']}" if l["discourse"] else ""))
        for nt in r["notes"]:
            print("        note:", nt)
    if fr.get("dropped"):
        print("  folded into a link:", fr["dropped"])


if __name__ == "__main__":
    rows = json.load(open(A.parses, encoding="utf-8"))["rows"]
    want = set(A.rows.split(",")) if A.rows else None
    allf = []
    for r in rows:
        if want and r["n"] not in want:
            continue
        fr = full_row(r)
        allf.append(fr)
        if want:
            show(fr)
    if A.json:
        json.dump(allf, open(A.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(len(allf), "sentences")
