"""preds.py   Every predication in a sentence, from a dependency parse (spaCy or Stanza) or a constituency tree (Stanza).
Each predication: subject | verb | object, with kind = asserted (the speaker states it), embedded (inside a condition,
time clause, relative clause or description) or reported (what someone else said), plus negated, hedged and how the
clause hangs on the rest of the sentence. Written for the FACTUALITY parser comparison, Oct 2026."""
import re
import unicodedata

# ---------------------------------------------------------------- one token model for both parsers
class T:
    __slots__ = ("i", "text", "lemma", "upos", "dep", "head", "kids", "feats", "ws", "disp")
    def __init__(s, i, text, lemma, upos, dep, head, feats="", ws=" ", disp=None):
        s.i, s.text, s.lemma, s.upos, s.dep, s.head, s.feats, s.kids, s.ws = i, text, (lemma or text).lower(), upos, dep, head, feats or "", [], ws
        s.disp = text if disp is None else disp      # how the word is shown (French "du" for de + le)


def link_kids(toks):
    for t in toks:
        if t.head is not None and t.head != t.i:
            toks[t.head].kids.append(t)
    return toks


def from_spacy(doc):
    toks = [T(t.i, t.text, t.lemma_, t.pos_, t.dep_.lower(), None if t.dep_ == "ROOT" or t.head.i == t.i else t.head.i, str(t.morph), t.whitespace_) for t in doc]
    return link_kids(toks)


def _ws_after(w):
    """Space after a Stanza word: inside a multi-word token (du = de + le) none; otherwise the token's spaces_after
    (newer Stanza), or SpaceAfter=No in its misc field (older Stanza)."""
    try:
        tok = w.parent
        if tok is not None and len(tok.words) > 1 and w is not tok.words[-1]:
            return ""
        sa = getattr(tok, "spaces_after", None)
        if isinstance(sa, str):
            return " " if sa else ""
        return "" if "SpaceAfter=No" in (tok.misc or "") else " "
    except Exception:
        return " "


def _disp(w):
    """A multi-word token is shown as written (du, au, des): its first word carries the text, the rest show nothing."""
    try:
        tok = w.parent
        if tok is not None and len(tok.words) > 1:
            return tok.text if w is tok.words[0] else ""
    except Exception:
        pass
    return w.text


def from_stanza(sent):
    """Stanza words are numbered from 1 and head 0 is the root. Multi-word tokens (French du = de + le) come out as words."""
    ws = list(sent.words)
    toks = [T(k, w.text, w.lemma, w.upos, (w.deprel or "dep").lower(), None if w.head == 0 else w.head - 1, w.feats or "", _ws_after(w), _disp(w)) for k, w in enumerate(ws)]
    return link_kids(toks)


# ---------------------------------------------------------------- label groups (spaCy English labels and Universal Dependencies)
SUBJ = {"nsubj", "nsubjpass", "nsubj:pass", "csubj", "csubjpass", "csubj:pass", "expl:subj"}
OBJ = {"dobj", "obj"}
PRED_COMP = {"attr", "acomp", "oprd"}
OBL = {"obl", "obl:arg", "obl:mod", "obl:agent", "agent", "obl:npmod", "npadvmod", "obl:tmod"}
AUX = {"aux", "auxpass", "aux:pass", "aux:tense", "aux:caus", "cop"}
CLAUSE = {"acl", "acl:relcl", "relcl", "advcl", "ccomp", "parataxis", "csubj", "xcomp"}
CUT = {"acl", "acl:relcl", "relcl", "advcl", "ccomp", "parataxis", "appos", "dep", "punct", "mark"}
NEG_EN = {"not", "n't", "n’t", "never", "no"}
NEG_FR = {"ne", "n'", "pas", "jamais", "aucun", "aucune", "plus", "nullement", "guère"}
# Hedges are epistemic: the speaker is less than certain (would, could, might, may; the French conditional).
# Obligation and permission are not hedges: should, must, shall, can, doit, peut, pourra (left out on purpose).
HEDGE_AUX = {"may", "might", "could", "would", "'d", "pourrait", "pourraient", "pourrais", "pourrions", "pourriez",
             "devrait", "devraient", "devrais", "devrions", "aurait", "auraient", "aurais", "serait", "seraient", "serais"}
HEDGE_ADV = {"perhaps", "possibly", "probably", "likely", "maybe", "peut-être", "probablement", "vraisemblablement", "sans doute"}
SPEECH = {"say", "tell", "state", "claim", "argue", "ask", "add", "write", "suggest", "insist", "announce", "declare", "note",
          "dire", "déclarer", "affirmer", "souligner", "indiquer", "demander", "ajouter", "prétendre", "écrire", "annoncer"}
NOT_ASSERTED_MARK = {"if", "unless", "when", "whenever", "as", "after", "before", "while", "until", "once", "whether", "though",
                     "although", "si", "s'", "quand", "lorsque", "lorsqu'", "lorsqu’", "avant", "après", "pendant", "tandis", "alors", "bien", "dès"}
ASSERTED_MARK = {"because", "since", "parce", "puisque", "car"}
EXAMPLE_PREP = {"including", "notamment", "comme"}
REL_PRON = {"who", "which", "that", "whom", "qui", "que", "qu", "qu'", "qu’", "lequel", "laquelle", "dont", "où"}
PRONOUNS = {"it", "they", "he", "she", "we", "i", "you", "il", "ils", "elle", "elles", "on", "nous", "vous", "je", "ça", "cela", "ce"}


def is_verbal(t):
    return t.upos in ("VERB", "AUX")


def has_subj(t):
    return any(c.dep in SUBJ for c in t.kids)


def join_plain(ts):
    out = ""
    for k, t in enumerate(ts):
        out += t.disp
        if k + 1 < len(ts):
            out += t.ws if ts[k + 1].i == t.i + 1 else " "
    return out.strip()


def join(ts):
    """Words with the spacing they had in the sentence (a gap where words were left out)."""
    out = ""
    for k, t in enumerate(ts):
        out += t.disp
        if k + 1 < len(ts):
            out += t.ws if ts[k + 1].i == t.i + 1 else " "
    out = re.sub(r"\s{2,}", " ", out).strip(" ,;:-\"“”«»`")
    if re.fullmatch(r"['’]+|.*\s['’]+|['’]+\s.*", out):
        out = out.strip(" '’")             # a stray quote mark, not the c' of c'est
    return out


def span(toks, head, drop_clauses=True, limit=25):
    """Words of a phrase: the head and what hangs on it, without the clauses that are their own predications."""
    keep, stack = [], [head]
    while stack:
        t = stack.pop(); keep.append(t)
        for c in t.kids:
            if drop_clauses and c is not head and c.dep in CUT and not (c.dep == "punct" and c.text in "-'’") \
                    and not (c.dep == "appos" and t.text.lower() in TITLES):
                continue
            if drop_clauses and c.dep in ("prep", "case", "mark") and any(is_verbal(g) and g.dep in ("pcomp", "acl", "advcl") for g in c.kids):
                continue
            if drop_clauses and c.dep == "conj" and (has_subj(c) or (is_verbal(c) and is_verbal(t) is False)):
                continue
            stack.append(c)
    keep.sort(key=lambda t: t.i)
    ids = {t.i for t in keep}
    keep += [toks[i] for i in range(1, len(toks) - 1) if toks[i].text == "," and i not in ids and i - 1 in ids and i + 1 in ids]
    keep.sort(key=lambda t: t.i)
    return join(keep[:limit])


CHAIN_DEPS = {"aux", "aux:pass", "auxpass", "aux:tense", "aux:caus", "cop", "neg", "prt", "compound:prt", "expl:pv"}


def chain(t):
    """Verb words: modals, negation, the verb itself, particles, and a following infinitive (chosen to call, vise à intégrer).
    The infinitive is not joined when the verb has its own object (urge my colleagues to reject): that is a new predication."""
    def bits(x):
        has_ne = any(c.text.lower() in ("ne", "n'", "n’") and not _nimporte(c) for c in x.kids)
        out = []
        for c in x.kids:
            if _nimporte(c):
                continue
            low = c.text.lower()
            if c.dep in CHAIN_DEPS or (c.dep in ("advmod", "advmod:neg") and (low in NEG_EN or low in STRONG_NEG_FR or low in ("ne", "n'", "n’") or (low in NE_NEG_FR and has_ne))):
                out.append(c)
            elif c.dep == "advmod" and low == "longer" and any(g.text.lower() == "no" for g in c.kids):
                out += [g for g in c.kids if g.text.lower() == "no"] + [c]
        return out
    words = bits(t) + ([] if any(c.dep == "cop" for c in t.kids) else [t])
    x = next((c for c in t.kids if c.dep == "xcomp" and is_verbal(c) and not has_subj(c)), None) if not object_control(t) else None
    if x is not None and any(c.dep in PRED_COMP for c in t.kids):
        x = None                        # "is separate and independent of that to donate": the verb is "is", its complement "separate"
    while x is not None:
        words += [c for c in x.kids if c.dep in ("aux", "mark") and c.text.lower() in ("to", "à", "de", "d'", "d’")] + bits(x) + [x]
        t = x
        x = next((c for c in t.kids if c.dep == "xcomp" and is_verbal(c) and not has_subj(c)), None) if not object_control(t) else None
    words = sorted(set(words), key=lambda w: w.i)
    return join_plain(words), t


def object_control(v):
    """urge my colleagues to reject, encourager les citoyens à collaborer: the object is the subject of the infinitive."""
    if v.lemma in ("pouvoir", "devoir", "vouloir", "aller", "falloir", "savoir", "venir", "sembler", "paraître",
                   "can", "must", "will", "shall", "seem", "appear", "want", "need", "have", "try", "be"):
        return False                    # modal and raising verbs: "je pourrais vous citer" keeps je as the subject
    xs = [c for c in v.kids if c.dep == "xcomp" and is_verbal(c) and not has_subj(c)]
    return any(c.dep in OBJ and xs and c.i < xs[0].i for c in v.kids)


def noun_span(toks, head):
    return span_without(toks, head, {"case", "prep"})


def span_without(toks, head, skip):
    """The phrase under head, leaving out the children of head whose label is in skip, and any clause below."""
    keep, stack = [], [head]
    while stack:
        t = stack.pop(); keep.append(t)
        for c in t.kids:
            if (t is head and c.dep in skip) or (c.dep in CUT and not (c.dep == "punct" and c.text in "-'’")):
                continue
            stack.append(c)
    keep.sort(key=lambda t: t.i)
    return join(keep[:25])


def said_after_colon(toks, v):
    """The words a speech verb introduces after a colon or opening quote: "elle a dit : Je veux collaborer"."""
    if not (v.lemma in SPEECH or v.text.lower() in SPEECH_FORMS):
        return None
    colon = next((p for p in toks if p.i > v.i and p.text in (":", "«", "“", '"', "``") and (p.head == v.i or p.i == v.i + 1 or
                  all(x.dep in ("punct", "obl", "obl:mod", "advmod", "iobj", "dep") or x.text.startswith("-") for x in toks[v.i + 1:p.i]))), None)
    if colon is None:
        return None
    return next((c for c in v.kids if c.i > colon.i and c.dep != "punct"), None)


REFLEXIVE = {"se", "s'", "s’", "me", "m'", "m’", "te", "t'", "t’", "nous", "vous"}


def _reflexive(toks, v, c):
    """French pronominal verbs: "vous vous doutiez", "il s'en va": the clitic is part of the verb, not its object."""
    if c.text.lower() not in REFLEXIVE or c.i > v.i:
        return False
    if c.text.lower() in ("nous", "vous"):
        return any(s_.dep in SUBJ and s_.text.lower() == c.text.lower() for s_ in v.kids)
    return True


def object_of(toks, v, pred_head):
    """The first core complement: direct object, predicate noun or adjective, then a prepositional phrase, then a clause.
    A speech verb whose words follow a colon ("elle a dit : Je veux collaborer") takes them as its object."""
    q = said_after_colon(toks, v)
    if q is not None:
        return span(toks, q, drop_clauses=False)
    for c in v.kids:
        if c.dep in OBJ and not _reflexive(toks, v, c):
            return span(toks, c)
    for c in v.kids:
        if c.dep in PRED_COMP:
            return span(toks, c)
    if pred_head is v and any(c.dep == "cop" for c in v.kids):     # UD: "X est cynique" has the adjective as the head
        return span_without(toks, v, SUBJ | {"cop", "aux", "aux:tense", "aux:pass", "mark", "cc", "advmod"})
    TIME = {"npadvmod", "obl:tmod", "nmod:tmod", "obl:npmod"}
    cands = [c for c in v.kids if (c.dep == "prep" and any(g.dep in ("pobj", "pcomp") for g in c.kids) and not _in_example_prep(toks, c))
             or c.dep in OBL]
    cands.sort(key=lambda c: (c.dep in TIME, c.i < v.i, c.i))
    if cands:
        return span(toks, cands[0])
    for c in v.kids:
        if c.dep == "ccomp":
            return span(toks, c, drop_clauses=False)
    for c in v.kids:
        if c.dep == "advmod" and c.text.lower() in LOC_ADV:
            return span(toks, c)        # went underground, got elected here, aller stationner plus loin
    return ""


LOC_ADV = {"here", "there", "underground", "abroad", "home", "away", "overseas", "ici", "là-bas", "loin", "ailleurs", "dehors"}


def _in_example_prep(toks, c):
    return c.text.lower() in EXAMPLE_PREP or (c.text.lower() == "as" and any(k.text.lower() == "such" for k in c.kids))


STRONG_NEG_FR = {"pas", "jamais", "aucun", "aucune", "nullement"}
NE_NEG_FR = {"plus", "rien", "personne", "guère", "ni"}       # negative only with ne / n'


def _nimporte(c):
    """n' of "n'importe quoi / qui / où" (anything): not a negation."""
    toks = _TOKS.get("toks")
    return c.text.lower() in ("n'", "n’") and toks is not None and c.i + 1 < len(toks) and toks[c.i + 1].text.lower() == "importe"


def negated(t):
    words = [c for c in list(t.kids) + [c for a in t.kids if a.dep in AUX for c in a.kids] if not _nimporte(c)]
    low = {c.text.lower() for c in words}
    has_ne = bool(low & {"ne", "n'", "n’"})
    if has_ne and low & (STRONG_NEG_FR | NE_NEG_FR):
        return True                     # ne ... pas / plus / jamais / personne / rien
    if has_ne and any(g.text.lower() in ("que", "qu'", "qu’") and t.i < g.i <= t.i + 6 for g in _sub_all(t)):
        return False                    # "ne s'adressent qu'aux personnes", "n'a identifié que 60 %" = only
    if any(c.dep in ("neg", "advmod:neg") or (c.dep == "advmod" and (c.text.lower() in NEG_EN or c.lemma == "not")) for c in words):
        return True
    if any(c.text.lower() == "longer" and any(g.text.lower() == "no" for g in c.kids) for c in words):
        return True                     # no longer
    if low & STRONG_NEG_FR or has_ne:
        return True
    for c in t.kids:                    # "envisions no such thing", "receive no money", "will do nothing"
        if c.dep in OBJ | PRED_COMP | {"nsubj", "expl"} and c.i > t.i and (c.text.lower() in ("nothing", "none", "rien") or
                (any(g.dep == "det" and g.text.lower() in ("no", "aucun", "aucune", "nul", "nulle") for g in c.kids) and
                 sum(g.dep == "det" for g in c.kids) == 1)):    # but not "a no vote"
            return True
    return "Polarity=Neg" in t.feats


def _sub_all(t):
    out, st = [], list(t.kids)
    while st:
        x = st.pop(); out.append(x); st.extend(x.kids)
    return out


def hedged(t):
    return any((c.dep in AUX and (c.text.lower() in HEDGE_AUX or ("Mood=Cnd" in c.feats and c.lemma in ("pouvoir", "devoir", "avoir", "être"))))
               or (c.dep == "advmod" and c.text.lower() in HEDGE_ADV) for c in t.kids) \
        or t.text.lower() in HEDGE_AUX


def carry_hedges(preds):
    """A clause that only continues a hedged one is hedged too: "would have addressed ..., first by protecting ... and
    second by addressing", "would be joining an association, sending their premiums"."""
    for k, p in enumerate(preds):
        if p["hedged"] or p["kind"] != "asserted" or not p["subject"].endswith("(inh)"):
            continue
        if not any(w in p["how"] for w in ("means", "joined", "added clause", "example")):
            continue
        base = p["subject"][:-len("(inh)")].strip()
        prev = next((q for q in reversed(preds[:k]) if q["kind"] == "asserted" and q["subject"].replace("(inh)", "").strip() == base), None)
        if prev is not None and prev["hedged"]:
            p["hedged"] = True
            p["how"] += "; hedge carried over"
    return preds


_TOKS = {}


def object_control_parent(t):
    h = _TOKS.get("toks")
    return h is not None and t.head is not None and object_control(h[t.head])


def is_pred_head(t):
    if t.dep in AUX or t.dep in ("aux", "auxpass"):
        return False
    if any(c.dep == "cop" for c in t.kids):
        return True
    if not is_verbal(t):
        return False
    if t.upos == "AUX" and not has_subj(t) and t.dep not in ("root", "conj"):
        return False
    if t.dep == "xcomp" and not has_subj(t) and t.head is not None and not object_control_parent(t):
        return False                  # part of the verb chain of the verb it hangs on
    return t.dep in ("root", "conj", "advcl", "acl", "acl:relcl", "relcl", "ccomp", "parataxis", "pcomp", "csubj", "xcomp") or has_subj(t)


def owning_pred(toks, t):
    """The nearest predicate above t."""
    x = toks[t.head] if t.head is not None else None
    while x is not None:
        if is_pred_head(x):
            return x
        x = toks[x.head] if x.head is not None else None
    return None


ADDRESS = {"speaker", "president", "chair", "chairman", "chairwoman", "chairperson", "présidente", "président", "colleagues", "collègues"}


TITLES = {"mr", "mr.", "mrs", "mrs.", "ms", "ms.", "madam", "madame", "m.", "mme", "monsieur", "dr", "dr."}


def vocative(toks, c):
    """'Mr. Speaker,' or 'M. le Président,' read as a subject: it is someone being addressed."""
    sub = sorted(_sub_all(c) + [c], key=lambda x: x.i)
    words = {x.text.lower() for x in sub}
    end = sub[-1].i
    if c.text.lower() in ADDRESS and c.i + 1 < len(toks) and toks[c.i + 1].text == ",":
        return True
    return c.text.lower() in ADDRESS | TITLES and bool(words & ADDRESS) and bool(words & TITLES) and end + 1 < len(toks) and toks[end + 1].text == ","


def subject_of(toks, t, memo):
    if t.i in memo:
        return memo[t.i]
    subs = [c for c in t.kids if c.dep in SUBJ]
    if not subs and t.dep == "xcomp" and t.head is not None and object_control(toks[t.head]):
        o_ = next(c for c in toks[t.head].kids if c.dep in OBJ)
        memo[t.i] = (span(toks, o_), True)                # urge [my colleagues] to reject
        return memo[t.i]
    s = next((c for c in subs if not vocative(toks, c)), None)
    if s is None and subs:
        ap = next((c for c in subs[0].kids if c.dep == "appos" and c.text.lower() not in ADDRESS | TITLES), None)   # "Mr. Speaker, the Pelosi plan creates": the plan
        s = ap if ap is not None else subs[0]
    if s is not None:
        txt = span(toks, s)
        if s.text.lower() in REL_PRON and t.dep in ("acl:relcl", "relcl", "acl") and t.head is not None:
            txt = noun_span(toks, toks[t.head])    # who/qui stands for the noun the clause describes
        elif s.text.lower() in PRONOUNS:
            d_ = next((c for c in t.kids if c.dep.startswith("dislocated") and c.upos in ("NOUN", "PROPN")), None)
            if d_ is not None:
                txt = f"{txt} ({noun_span(toks, d_)})"   # "le ministre, là, il va nommer": il = le ministre
        memo[t.i] = (txt, False)
        return memo[t.i]
    if t.dep in ("acl", "acl:relcl", "relcl") and t.head is not None and not is_verbal(toks[t.head]):
        memo[t.i] = (noun_span(toks, toks[t.head]), False)   # "women donating": the noun is the subject
        if _in_example(toks, t):
            o = owning_pred(toks, t)
            memo[t.i] = (subject_of(toks, o, memo)[0], True) if o is not None else memo[t.i]
        return memo[t.i]
    o = toks[t.head] if t.head is not None else None
    if t.dep == "conj" and o is not None:
        memo[t.i] = (subject_of(toks, o, memo)[0], True)
        return memo[t.i]
    o = owning_pred(toks, t)
    memo[t.i] = (subject_of(toks, o, memo)[0], True) if o is not None else ("", True)
    return memo[t.i]


def _in_example(toks, t):
    """'such as requiring', 'including', 'notamment', 'comme': the clause is an example of what the predicate says."""
    x = toks[t.head] if t.head is not None else None
    if x is not None and x.dep in ("prep", "case", "mark") and (x.text.lower() in EXAMPLE_PREP or (x.text.lower() == "as" and any(c.text.lower() == "such" for c in x.kids + ([toks[x.head]] if x.head is not None else []) ))):
        return True
    return any(c.dep in ("mark", "case") and c.text.lower() in EXAMPLE_PREP for c in t.kids)


def kind_of(toks, t, quoted):
    if quoted:
        return "reported", "inside a quote"
    if t.head is not None and said_after_colon(toks, toks[t.head]) is t:
        return "reported", f"what is said ({toks[t.head].text}:)"
    d = t.dep
    marks = {c.text.lower() for c in t.kids if c.dep in ("mark", "case", "advmod") and c.i < t.i}
    if d == "root" or d == "parataxis":
        return "asserted", "main clause"
    if d == "conj":
        k, why = kind_of(toks, toks[t.head], quoted)
        return k, "joined to: " + why
    if d == "ccomp":
        h = toks[t.head]
        if h.lemma in SPEECH:
            return "reported", f"what is said ({h.text})"
        return "embedded", f"complement of {h.text}"
    if d in ("acl:relcl", "relcl"):
        return "embedded", "relative clause"
    if d in ("acl", "pcomp"):
        if _in_example(toks, t):
            return "asserted", "example (such as / including)"
        if d == "pcomp" and t.head is not None and toks[t.head].text.lower() in ("by", "en", "par"):
            return "asserted", f"means ({toks[t.head].text})"
        return "embedded", "describes a noun"
    if d == "advcl":
        if marks & ASSERTED_MARK:
            return "asserted", "cause (" + "/".join(sorted(marks & ASSERTED_MARK)) + ")"
        if marks & NOT_ASSERTED_MARK:
            return "embedded", "condition or time (" + "/".join(sorted(marks & NOT_ASSERTED_MARK)) + ")"
        if any(c.text.lower() in ("to", "pour", "afin") for c in t.kids if c.dep in ("aux", "mark")):
            return "embedded", "purpose (to)"
        if marks & {"by", "en", "par"}:
            return "asserted", "means (by)"
        return "asserted", "added clause, no linking word"
    if d == "xcomp":
        return "embedded", "complement"
    if d == "csubj":
        return "embedded", "clause as subject"
    return "asserted", f"other ({d})"


QUOTE_OPEN = {"``", "“", "«", '"'}


def quoted_spans(toks):
    inside, out, opened = set(), False, None
    for t in toks:
        if t.text in QUOTE_OPEN or t.text in ("''", "”", "»"):
            if t.text in ("''", "”", "»") or (t.text == '"' and out):
                out = False
            else:
                out = True
            continue
        if out:
            inside.add(t.i)
    return inside


def from_dependencies(toks):
    """All predications in one parsed sentence."""


    q = quoted_spans(toks)
    _TOKS["toks"] = toks
    memo, out = {}, []
    for t in toks:
        if not is_pred_head(t):
            continue
        if (t.i == 0 and t.dep == "advcl" and "VerbForm=Inf" in (t.feats or "") and not has_subj(t)
                and not any(c.dep in ("aux", "mark") or c.dep in OBJ or c.dep in PRED_COMP or c.dep in ("ccomp", "xcomp") for c in t.kids)):
            continue                    # "Way back in the day": a word tagged as a verb, with no object, subject or "to"
        verb, last = chain(t)
        obj = object_of(toks, last, t)
        if obj and any(c.dep in PRED_COMP for c in last.kids):
            xc = next((c for c in last.kids if c.dep == "xcomp" and is_verbal(c) and not has_subj(c) and c.i > last.i), None)
            if xc is not None:          # "it is important to fight illegal drugs": the infinitive belongs with the complement
                tail = span(toks, xc, drop_clauses=False)
                if tail and tail not in obj:
                    obj = obj + " " + tail
        first = obj.split(" ")[0].lower() if obj else ""
        if first in REL_PRON and t.dep in ("acl:relcl", "relcl") and t.head is not None:
            obj = (noun_span(toks, toks[t.head]) + " " + obj[len(first):].strip(" '’")).strip()   # "which" = the noun it stands for
        subj, inh = subject_of(toks, t, memo)
        kind, why = kind_of(toks, t, t.i in q)
        if not obj and not subj:
            continue
        out.append({"subject": subj + (" (inh)" if inh and subj else ""), "verb": verb, "object": obj, "kind": kind,
                    "how": why, "negated": negated(t), "hedged": hedged(t), "at": t.i})
    out.sort(key=lambda p: p["at"])
    return carry_hedges(out)


# ---------------------------------------------------------------- constituency trees (Penn style for English, French Treebank style for French)
def parse_tree(s):
    tokens = re.findall(r"\(|\)|[^\s()]+", s)
    pos = 0
    def node():
        nonlocal pos
        assert tokens[pos] == "("; pos += 1
        label = tokens[pos]; pos += 1
        kids = []
        while tokens[pos] != ")":
            if tokens[pos] == "(":
                kids.append(node())
            else:
                kids.append(tokens[pos]); pos += 1
        pos += 1
        return (label, kids)
    return node()


def leaves(n):
    if isinstance(n, str):
        return [n]
    return [w for k in n[1] for w in leaves(k)]


def text(n):
    s = " ".join(leaves(n)) if not isinstance(n, str) else n
    s = re.sub(r"\s+([,.;:!?)’'])", r"\1", s)
    s = re.sub(r"([$€£(])\s+", r"\1", s)
    s = re.sub(r"(\d)\s+%", r"\1%", s)
    s = re.sub(r"(\w) - (\w)", r"\1-\2", s).replace(" n't", "n't").replace(" 's", "'s").replace("-LRB- ", "(").replace(" -RRB-", ")")
    return s.strip(" ,;:\"“”«»`'")


def has_clause(n):
    if isinstance(n, str):
        return False
    return any(lab(k) in ("S", "SBAR", "VP", "Ssub", "Srel", "VPinf", "VPpart") or has_clause(k) for k in n[1])


def core(n):
    """A phrase without the clauses hanging on it (those are their own predications): NP minus relative clauses,
    reduced relatives and prepositional phrases that hold a clause."""
    if isinstance(n, str) or lab(n) not in ("NP", "PP", "ADJP"):
        return text(n)
    keep = [k for k in n[1] if not (lab(k) in ("SBAR", "VP", "S", "Srel", "VPpart") or
                                     (lab(k) == "PP" and any(lab(x) in ("S", "VP", "SBAR", "VPinf", "VPpart") for x in k[1])))]
    while keep and lab(keep[-1]) in (",", ":", "CC"):
        keep.pop()
    return text((n[0], [core(k) if not isinstance(k, str) and lab(k) in ("NP", "PP") else k for k in keep])) if keep else text(n)


def lab(n):
    return "" if isinstance(n, str) else n[0].split("-")[0].split("=")[0]


CLAUSE_EN = {"S", "SINV", "SQ"}
SPEECH_FORMS = {"said", "says", "say", "told", "tell", "tells", "stated", "states", "claimed", "claims", "argued", "argues",
                "asked", "asks", "added", "wrote", "writes", "insisted", "announced", "declared", "noted"}
CLAUSE_FR = {"SENT", "Sint", "Ssub", "Srel", "VPinf", "VPpart"}
VERB_TAGS = {"MD", "VB", "VBD", "VBG", "VBN", "VBP", "VBZ", "TO"}


def from_stanza_tree(t):
    """Stanza's tree object to (label, kids) directly, so a "(" in the sentence cannot break the reading."""
    kids = list(getattr(t, "children", []) or [])
    if not kids:
        return str(t.label)
    return (str(t.label), [from_stanza_tree(k) for k in kids])


def _flatten_neg_advp(n):
    """Stanza sometimes puts the negation and the rest of the verb phrase in an ADVP: (VBP are) (ADVP (RB n’t) (VP paying ...)).
    Lift the ADVP's children into the verb phrase so the verb chain reads are n’t paying."""
    if isinstance(n, str):
        return n
    kids = []
    for k in n[1]:
        k = _flatten_neg_advp(k)
        if lab(k) == "ADVP" and any(lab(x) == "VP" for x in k[1]) and any(lab(x) == "RB" and text(x).lower() in NEG_EN for x in k[1]):
            kids.extend(k[1])
        else:
            kids.append(k)
    return (n[0], kids)


# verbs whose object is the subject of the following "to" clause; any other verb + object + "to" is a purpose clause
CONTROL_STEMS = ("urg", "requir", "ask", "allow", "encourag", "forc", "tell", "told", "enabl", "permit", "persuad", "want",
                 "expect", "invit", "order", "compel", "oblig", "advis", "remind", "instruct", "authoriz", "help", "caus",
                 "call", "direct", "mandat", "empower", "entitl")


def _tuples(n):
    """Trees saved as JSON lists come back as [label, [kids]]; the walkers want (label, kids)."""
    if isinstance(n, str):
        return n
    return (n[0], [_tuples(k) for k in n[1]])


def from_constituency(tree_str, lang="en"):
    root = parse_tree(tree_str) if isinstance(tree_str, str) else _tuples(tree_str)
    if lang == "fr":                    # French Treebank trees (Berkeley parser, benepar_fr2): their own rules
        import const_fr
        return carry_hedges([p for p in const_fr.from_ftb(root) if p["verb"] and (p["subject"] or p["object"])])
    root = _flatten_neg_advp(root)
    out = []
    GAP = []
    counter = [0]

    def word_index(n):
        return counter[0]

    def walk(n, subj, inh, kind, how, pos):
        """pos = index of the first leaf of n in the sentence."""
        if isinstance(n, str):
            return
        L = lab(n)
        kids = n[1]
        offs, p = [], pos
        for k in kids:
            offs.append(p); p += len(leaves(k))
        if lang == "en" and L in CLAUSE_EN:
            np_ = next((k for k in kids if lab(k) == "NP"), None)
            vps = [k for k in kids if lab(k) == "VP"]
            if vps:
                s, i2 = (core(np_), False) if np_ is not None and kids.index(np_) < kids.index(vps[0]) else (subj, True)
                for k, o in zip(kids, offs):
                    if k is np_ and has_clause(k):
                        walk(k, s, False, kind, how, o)
                    if lab(k) == "VP":
                        vp(k, s, i2, kind, how, o)
                    elif lab(k) in CLAUSE_EN | {"SBAR", "PP"}:
                        walk(k, s, True, kind if lab(k) == "S" else kind, how, o)
                return
        if lang == "en" and L == "SBAR":
            first = next((x for x in kids if not isinstance(x, str)), None)
            w = text(first).lower() if first is not None else ""
            if lab(first) in ("WHNP", "WHADVP", "WHPP"):
                k2, h2 = "embedded", "relative clause"
            elif w in ASSERTED_MARK:
                k2, h2 = kind, f"cause ({w})"
            elif w in NOT_ASSERTED_MARK:
                k2, h2 = "embedded", f"condition or time ({w})"
            else:
                k2, h2 = "embedded", "complement clause" if kind == "asserted" else how
            for k, o in zip(kids, offs):
                walk(k, subj, True, k2, h2, o)
            return
        if lang == "en" and L == "NP":
            for k, o in zip(kids, offs):
                if lab(k) == "VP":      # "women donating fetal tissue": a verb phrase describing the noun
                    head_np = next((x for x in kids if lab(x) == "NP"), None)
                    vp(k, text(head_np) if head_np is not None else subj, False, "embedded", "describes a noun", o)
                elif lab(k) == "SBAR":
                    head_np = next((x for x in kids if lab(x) == "NP"), None)
                    wh = next((x for x in k[1] if lab(x) == "WHNP"), None)
                    s_in = next((x for x in k[1] if lab(x) == "S"), None)
                    obj_gap = wh is not None and text(wh).lower() in ("that", "which", "whom") and s_in is not None and any(lab(x) == "NP" for x in s_in[1])
                    GAP.append(core(head_np) if obj_gap and head_np is not None else "")
                    walk(k, text(head_np) if head_np is not None else subj, False, "embedded", "relative clause", o)
                    GAP.pop()
                else:
                    walk(k, subj, inh, kind, how, o)
            return
        if lang == "en" and L == "PP":
            prep = next((text(k).lower() for k in kids if lab(k) in ("IN", "TO", "VBG")), "")
            for k, o in zip(kids, offs):
                if lab(k) == "S":
                    if prep in ("by",):
                        walk(k, subj, True, kind, "means (by)", o)
                    elif prep in ("as", "including", "like"):
                        walk(k, subj, True, kind, "example (such as / including)", o)
                    else:
                        walk(k, subj, True, "embedded", f"after '{prep}'", o)
                else:
                    walk(k, subj, inh, kind, how, o)
            return
        if lang == "fr" and L in CLAUSE_FR:
            vn = next((k for k in kids if lab(k) == "VN"), None)
            if vn is not None:
                i_vn = kids.index(vn)
                np_ = next((k for k in kids[:i_vn] if lab(k) in ("NP", "CLS") or lab(k).startswith("NP")), None)
                s, i2 = (text(np_), False) if np_ is not None else (subj, True)
                k2, h2 = kind, how
                if L == "Srel":
                    k2, h2 = "embedded", "relative clause"
                elif L == "Ssub":
                    w = text(kids[0]).lower() if kids else ""
                    k2, h2 = (kind, f"cause ({w})") if w.split(" ")[0] in ASSERTED_MARK else ("embedded", f"subordinate ({w})")
                elif L in ("VPinf", "VPpart") and kind == "asserted" and how == "main clause":
                    k2, h2 = "embedded", "infinitive or participle"
                obj = next((text(k) for k in kids[i_vn + 1:] if lab(k) in ("NP", "PP", "AP", "VPinf", "Ssub", "ADV")), "")
                out.append(dict(subject=s + (" (inh)" if i2 and s else ""), verb=text(vn), object=obj, kind=k2, how=h2,
                                negated=any(w.lower() in ("pas", "jamais", "ne", "n'") for w in leaves(vn)), hedged=any(w.lower() in HEDGE_AUX for w in leaves(vn)), at=offs[i_vn]))
                for k, o in zip(kids, offs):
                    if k is not vn and k is not np_:
                        walk(k, s, True, k2, h2, o)
                return
        if lang == "fr" and L == "COORD":
            for k, o in zip(kids, offs):
                walk(k, subj, True, kind, "joined (coordination)", o)
            return
        for k, o in zip(kids, offs):
            walk(k, subj, inh, kind, how, o)

    def vp(n, subj, inh, kind, how, pos):
        gap = [GAP[-1] if GAP else ""]
        kids = n[1]
        offs, p = [], pos
        for k in kids:
            offs.append(p); p += len(leaves(k))
        sub_vps = [k for k in kids if lab(k) == "VP"]
        verbs = [k for k in kids if lab(k) in VERB_TAGS or (lab(k) == "RB" and text(k).lower() in NEG_EN)]
        if len(sub_vps) >= 2 and not any(lab(k) in VERB_TAGS for k in kids):
            for k, o in zip(kids, offs):          # coordinated verb phrases share the subject
                if lab(k) == "VP":
                    vp(k, subj, inh if k is sub_vps[0] else True, kind, how if k is sub_vps[0] else "joined: " + how, o)
                else:
                    walk(k, subj, True, kind, how, o)
            return
        words, cur, cur_off = [], n, pos
        while True:
            ks = cur[1]
            ko, pp = [], cur_off
            for k in ks:
                ko.append(pp); pp += len(leaves(k))
            vwords = [k for k in ks if lab(k) in VERB_TAGS or (lab(k) == "RB" and text(k).lower() in NEG_EN)]
            words += [text(k) for k in vwords]
            nxt = [k for k in ks if lab(k) == "VP"]
            if len(nxt) == 1 and vwords:
                cur_off = ko[ks.index(nxt[0])]; cur = nxt[0]
                continue
            break
        ks = cur[1]
        ko, pp = [], cur_off
        for k in ks:
            ko.append(pp); pp += len(leaves(k))
        if len([k for k in ks if lab(k) == "VP"]) >= 2:
            for k, o in zip(ks, ko):
                if lab(k) == "VP":
                    vp(k, subj, True, kind, "joined: " + how, o)
            return
        last_v = max((i for i, k in enumerate(ks) if lab(k) in VERB_TAGS), default=-1)
        prt = [k for k in ks[last_v + 1:] if lab(k) == "PRT"]
        words += [text(k) for k in prt]           # read out, make up, bringing together
        obj = next((core(k) for k in ks[last_v + 1:] if lab(k) in ("NP", "PP", "ADJP", "SBAR", "S", "ADVP")), "")
        if gap[0] and not any(lab(k) == "NP" for k in ks[last_v + 1:]):
            obj = gap[0]                  # "the shortfalls that this government has made": made the shortfalls
        at = ko[last_v] if last_v >= 0 else cur_off
        verb = " ".join(words)
        neg = any(w.lower() in NEG_EN for w in words)
        out.append(dict(subject=subj + (" (inh)" if inh and subj else ""), verb=verb, object=obj, kind=kind, how=how,
                        negated=neg, hedged=any(w.lower() in HEDGE_AUX for w in words), at=at))
        GAP.append("")                    # clauses further down do not inherit this relative clause's gap
        after = ks[last_v + 1:]
        for k, o in zip(after, ko[last_v + 1:]):
            before = after[:after.index(k)]
            obj_np = next((x for x in reversed(before) if lab(x) == "NP"), None)
            if (lab(k) == "S" and obj_np is not None and not any(lab(x) == "NP" for x in k[1])
                    and any(lab(x) == "VP" and any(lab(y) == "TO" for y in x[1]) for x in k[1])
                    and verb.split(" ")[-1].lower().startswith(CONTROL_STEMS)):
                ctrl = next((x for x in obj_np[1] if lab(x) == "NP"), obj_np) if any(lab(x) == "VP" for x in obj_np[1]) else obj_np
                walk(k, core(ctrl), True, "embedded", f"complement of {verb}", o)   # urge my colleagues to reject; requiring women to sign
                continue
            if lab(k) in ("SBAR", "S") and verb.split(" ")[-1].lower() in SPEECH_FORMS:
                walk(k, subj, True, "reported", f"what is said ({verb})", o)
            elif lab(k) == "S" and any(lab(x) == "NP" for x in k[1]) and any(lab(x) == "VP" for x in k[1]):
                walk(k, subj, True, "embedded", f"complement of {verb}", o)
            else:
                walk(k, subj, True, kind, how, o)
        GAP.pop()

    walk(root, "", True, "asserted", "main clause", 0)
    out.sort(key=lambda p: p["at"])
    return carry_hedges([p for p in out if p["verb"] and (p["subject"] or p["object"])])


# ---------------------------------------------------------------- discourse links between clauses, from the linking words
CONNECTIVES = [
    ("but", "contrast"), ("however", "contrast"), ("although", "concession"), ("though", "concession"), ("whereas", "contrast"),
    ("while", "contrast or time"), ("because", "cause"), ("since", "cause or time"), ("so", "result"), ("therefore", "result"),
    ("thus", "result"), ("if", "condition"), ("unless", "condition"), ("when", "time"), ("after", "time"), ("before", "time"),
    ("as well as", "addition"), ("and", "addition"), ("or", "alternative"), ("by", "means"), ("such as", "example"),
    ("including", "example"), ("for example", "example"), ("in order to", "purpose"),
    ("mais", "contraste"), ("cependant", "contraste"), ("pourtant", "contraste"), ("toutefois", "contraste"), ("bien que", "concession"),
    ("alors que", "contraste ou temps"), ("tandis que", "contraste"), ("parce que", "cause"), ("parce qu'", "cause"), ("car", "cause"),
    ("puisque", "cause"), ("donc", "résultat"), ("ainsi", "résultat"), ("si", "condition"), ("quand", "temps"), ("lorsque", "temps"),
    ("lorsqu'", "temps"), ("puis", "suite"), ("et", "ajout"), ("ou", "alternative"), ("pour", "but"), ("afin de", "but"),
    ("notamment", "exemple"), ("par exemple", "exemple"), ("en", "moyen"),
]


def connective_slots_dep(toks):
    """Word positions that can be a linking word between clauses in a dependency parse: a cc, mark, advmod or
    preposition that hangs on a predicate, or a preposition whose own child is a predicate ("by protecting").
    This keeps out "rights and protections" (joins two nouns) and French "s'en vont" (en is a pronoun there)."""
    ok = set()
    def pred_or_aux_of_pred(x):
        return is_pred_head(x) or (x.dep in AUX and x.head is not None and is_pred_head(toks[x.head]))
    for t in toks:
        if t.head is None:
            continue
        h = toks[t.head]
        hh = toks[h.head] if h.head is not None else None
        if t.dep in ("cc", "cc:preconj"):
            # spaCy hangs "and" on the first conjunct, UD on the second: a clause link if either side is a predicate
            if pred_or_aux_of_pred(h) or any(c.dep == "conj" and is_pred_head(c) for c in h.kids):
                ok.add(t.i)
        elif t.dep in ("mark", "advmod", "discourse", "advmod:neg"):
            if pred_or_aux_of_pred(h) or (h.upos in ("VERB", "AUX")):
                ok.add(t.i)
        elif t.dep in ("prep", "case"):
            def verb_below(x, depth):
                return depth > 0 and any((c.upos == "VERB" and c.dep in ("pcomp", "advcl", "acl", "xcomp")) or
                                         (c.dep == "pobj" and c.text.lower().endswith("ing")) or verb_below(c, depth - 1) for c in x.kids)
            if any(is_pred_head(c) or c.upos == "VERB" for c in t.kids) or (t.dep == "case" and h.upos == "VERB") or verb_below(t, 3):
                ok.add(t.i)          # "by protecting", "en plein été" stays out, "en attendant" stays in
        elif t.dep in ("fixed", "amod", "advmod") and hh is not None:
            if h.dep in ("prep", "case", "mark") and (any(c.upos == "VERB" for c in h.kids) or h.head is not None and toks[h.head].upos == "VERB"):
                ok.add(t.i)          # "such as requiring"
    return ok


def connective_slots_tree(root):
    """Word positions that can be a linking word in a tree: a word whose later sisters include a verb phrase or clause."""
    ok, pos = set(), [0]
    def has_verb(n):
        return not isinstance(n, str) and (lab(n) in VERB_TAGS | {"VN", "V", "VINF", "VPP", "VPR", "VS"} or any(has_verb(k) for k in n[1]))
    def go(n):
        if isinstance(n, str):
            pos[0] += 1
            return
        for j, k in enumerate(n[1]):
            later_verb = any(has_verb(x) for x in n[1][j + 1:])
            if not isinstance(k, str) and len(k[1]) == 1 and isinstance(k[1][0], str) and later_verb:
                ok.add(pos[0])
            elif not isinstance(k, str) and later_verb and all(not isinstance(x, str) and len(x[1]) == 1 and isinstance(x[1][0], str) for x in k[1]) \
                    and lab(k) in ("CONJP", "ADVP", "WHADVP", "MWC", "MWADV", "MWP"):
                ok.update(range(pos[0], pos[0] + len(k[1])))     # (CONJP as well as) (S meeting ...)
            go(k)
    go(root)
    return ok


def discourse(words, preds, allowed=None):
    """Which predications a linking word joins: the nearest predication before it and the nearest after it.
    allowed = word positions that may be a linking word (from connective_slots_dep or connective_slots_tree)."""
    low = [w.lower() for w in words]
    links, used = [], set()
    for phrase, rel in sorted(CONNECTIVES, key=lambda x: -len(x[0].split())):
        ph = phrase.split()
        for i in range(len(low) - len(ph) + 1):
            if low[i:i + len(ph)] == ph and not any(j in used for j in range(i, i + len(ph))) and \
               (allowed is None or any(j in allowed for j in range(i, i + len(ph)))):
                before = [k for k, p in enumerate(preds) if p["at"] < i]
                after = [k for k, p in enumerate(preds) if p["at"] > i + len(ph) - 1]
                if before and after:
                    links.append((before[-1] + 1, phrase, rel, after[0] + 1, i))
                    used.update(range(i, i + len(ph)))
    links.sort(key=lambda x: x[4])
    out = []
    for a, ph, rel, b, _ in links:
        s_ = f"[{a}] —{ph} ({rel})→ [{b}]"
        if s_ not in out:
            out.append(s_)
    return out


# ---------------------------------------------------------------- matching against the answer key
STOP = {"towards", "toward", "vers", "into", "from", "by", "at", "as", "par", "pour", "dans", "sur", "the", "a", "an", "of", "to", "in", "on", "for", "and", "with", "that", "this", "these", "their", "his", "her", "its", "our",
        "le", "la", "les", "l'", "un", "une", "des", "de", "du", "d'", "à", "au", "aux", "en", "et", "que", "qu'", "ce", "cette", "ses", "leur", "leurs",
        "(inh)", "inh", "would", "will", "have", "has", "had", "be", "is", "are", "was", "were", "been", "not", "ne", "pas", "a", "ont", "sont", "est"}


def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"([$%])\s+(?=\d)", r"\1", s)
    s = re.sub(r"(\d)\s+%", r"\1%", s)
    return re.findall(r"[a-z0-9$%]+", s)


def content(s):
    return {w for w in fold(s) if w not in STOP and len(w) > 1}


def verb_match(g, p):
    gw = [w for w in fold(g) if w not in STOP] or fold(g)
    pw = [w for w in fold(p) if w not in STOP] or fold(p)
    return any(a == b or (len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]) for a in gw for b in pw)


def _no_note(s):
    return re.sub(r"\((?!inh\))[^)]*\)", " ", s or "")      # "you (the patient)" -> "you"; "(inh)" stays


def gold_negated(g):
    """The answer key marks negation in its note ("negated"; "not negated" means no) or writes it in the verb."""
    note = (g[4] if len(g) > 4 else "") or ""
    if "not negated" in note:
        return False
    return "negated" in note or any(w in ("not", "never", "ne", "pas", "jamais", "nt") for w in fold(g[1].replace("’", "'").replace("n't", " nt")))


def matches(gold, pred):
    """Same verb, same polarity, and subject and object sharing a content word with the key line.
    A passive with 'by / par' counts as the active line it restates (une entente négociée par le gouvernement)."""
    if gold_negated(gold) != bool(pred.get("negated")):
        return False
    if _matches((gold[0], gold[1], _no_note(gold[2])), pred):
        return True
    o = fold(pred["object"])
    if o and o[0] in ("by", "par"):
        swapped = {"subject": " ".join(o[1:]), "verb": pred["verb"], "object": pred["subject"]}
        return _matches((gold[0], gold[1], _no_note(gold[2])), swapped)
    return False


PRON_OBJ = {"l", "le", "la", "les", "lui", "leur", "him", "her", "it", "them", "me", "nous", "vous", "en", "y"}


def _matches(gold, pred):
    gs, gv, go = gold[0], gold[1], gold[2]
    po, gof = fold(pred["object"]), fold(go)
    if po and len(po) == 1 and po[0] in PRON_OBJ and gof and gof[0] == po[0]:
        pred = dict(pred, object=go)              # the pronoun the key spells out
    if not verb_match(gv, pred["verb"]):
        return False
    ok_obj = (not go and not pred["object"]) or bool(content(go) & content(pred["object"])) or (not content(go) and not content(pred["object"]))
    gsub = content(gs.replace("(inh)", ""))
    psub = content(pred["subject"].replace("(inh)", ""))
    gf, pf = set(fold(gs.replace("(inh)", ""))), set(fold(pred["subject"].replace("(inh)", "")))
    if gsub & psub or "unstated" in gs.lower() or not gf:
        ok_subj = True
    elif gf & SUBJ_PRON:
        ok_subj = not pf or bool(pf & SUBJ_PRON)      # "It" in the key: the method wrote nothing, or a pronoun too
    else:
        ok_subj = False
    return ok_obj and ok_subj


SUBJ_PRON = PRONOUNS | {"c", "j", "moi", "toi", "lui", "eux", "us", "them", "i"}


def overlap(gold, pred):
    """How closely a predication matches one answer-key line (used to pair each line with at most one predication)."""
    sc = len(content(gold[0].replace("(inh)", "")) & content(pred["subject"])) + len(content(gold[2]) & content(pred["object"]))
    return sc


def align(gold_list, preds):
    """Pair answer-key lines with predications one to one: best overlap first. Returns, for each line, the index of its predication or None."""
    pairs = sorted(((overlap(g, p), gi, pi) for gi, g in enumerate(gold_list) for pi, p in enumerate(preds) if matches(g, p)), reverse=True)
    got, used = [None] * len(gold_list), set()
    for _, gi, pi in pairs:
        if got[gi] is None and pi not in used:
            got[gi] = pi; used.add(pi)
    return got


# ---------------------------------------------------------------- noun phrases that continue past a comma
def appositions(toks):
    """'Brian Smith, the much-admired Ottawa sportscaster,' and "L'AQDR, l'association québécoise des droits des retraités,":
    the phrase after the comma renames the one before it. The predicate extractor keeps only the first name (it is what a
    knowledge base would link), so each apposition is listed as its own statement: X | is | Y."""
    out = []
    for t in toks:
        if t.dep != "appos" or t.head is None:
            continue
        h = toks[t.head]
        if h.text.lower() in TITLES | ADDRESS or t.text.lower() in TITLES | ADDRESS:
            continue                    # Mr. Speaker, M. le Président: forms of address, not claims
        if t.upos not in ("NOUN", "PROPN") or h.upos not in ("NOUN", "PROPN", "PRON"):
            continue
        between = toks[min(h.i, t.i) + 1:max(h.i, t.i)]
        if not (t.i > h.i and between and between[0].text == "," and all(x.text not in ("(", ")") for x in between)):
            continue                    # only "X, Y": not "Ohio (Mr. Brown)" or "Johnson (TX)"
        sub = sorted(_sub_all(t) + [t], key=lambda x: x.i)
        if any(x.dep in ("conj", "cc") for x in sub) or any(x.dep == "conj" for x in h.kids):
            continue                    # a list ("a mandate, a mission, and a moral obligation"), not a renaming
        if sub[0].upos in ("ADV", "CCONJ", "ADP", "PUNCT") or len(t.text) < 3 or t.text.isupper() and len(t.text) < 5:
            continue                    # "plus particulièrement les articles", "(A)", "MD"
        out.append({"subject": noun_span(toks, h), "verb": "is (apposition)", "object": noun_span(toks, t), "at": t.i})
    return out
