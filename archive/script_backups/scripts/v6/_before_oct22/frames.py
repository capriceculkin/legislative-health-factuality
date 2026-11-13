"""frames.py   PropBank-style frames from a UD tree, one mapping for English and French (design 2, step 4)."""
import lexicon as X
import os, re, html

PB_FRAMES = os.environ.get("PB_FRAMES", "/home/claude/jwijffels/propbank-frames/frames")      # English PropBank frame files
UP_FR_VERBS = os.environ.get("UP_FR_VERBS", "/home/claude/jwijffels/up1/UP_French/verbs")     # French lemma -> English roleset
_NO_ARG0 = {}


def no_arg0(lemma, lang):
    """True when none of the verb's PropBank rolesets has an ARG0 (unaccusative: "the program failed", "le programme a échoué"),
    so its active subject is ARG1. French lemmas are mapped to the English roleset Universal PropBank uses for them.
    Both languages are read from the same English frame files. None when the verb is not in the frames."""
    key = (lemma, lang)
    if key in _NO_ARG0:
        return _NO_ARG0[key]
    res = None
    en = lemma
    if lang == "fr":
        p = os.path.join(UP_FR_VERBS, lemma + ".html")
        en = None
        if os.path.exists(p):
            m = re.search(r'<div id="([a-z_\-]+)\.\d+">', open(p, encoding="utf-8", errors="replace").read())
            en = m.group(1) if m else None
    if en:
        p = os.path.join(PB_FRAMES, en + ".xml")
        if os.path.exists(p):
            x = open(p, encoding="utf-8", errors="replace").read()
            sets = re.findall(r"<roleset .*?</roleset>", x, re.S)
            if sets:
                res = all('n="0"' not in r_ for r_ in sets)    # unaccusative only when no sense of the verb has an ARG0
    _NO_ARG0[key] = res
    return res


def make(P):
    CORE = P.SUBJ | P.OBJ | {"iobj", "obl", "obl:arg", "obl:agent", "obl:mod", "obl:tmod", "ccomp", "xcomp", "agent"}
    TIME_ADV, TIME_NOUN = X.both(X.TIME_ADV), X.both(X.TIME_NOUN)
    TIME_MARK = X.both(X.TIME_FIRST) - {"if", "si", "s'", "s’", "unless", "moins", "as", "comme"}
    TIME_CASE = {"during", "since", "after", "before", "until", "pendant", "depuis", "après", "avant", "jusqu'", "jusqu’", "lors"}
    MODAL = {"can", "could", "may", "might", "must", "shall", "should", "will", "would", "pouvoir", "devoir", "falloir", "vouloir", "aller"}


    def frame(toks, t, line):
        """PropBank-style roles from the UD tree. Active subject = ARG0, passive subject = ARG1, object = ARG1, indirect
        object = ARG2, the 'by / par' agent of a passive = ARG0, clausal complement = ARG1; copula clause: subject = ARG1,
        complement = ARG2; obliques = ARGM-TMP for time words, else ARGM-<preposition>; negation = ARGM-NEG; modal = ARGM-MOD."""
        roles = []
        passive = any(c.dep in ("nsubj:pass", "nsubjpass", "aux:pass", "auxpass") for c in t.kids)
        copula = any(c.dep == "cop" for c in t.kids)
        for c in sorted(t.kids, key=lambda x: x.i):
            d = c.dep
            xs = [k for k in t.kids if k.dep == "xcomp"]
            controlled = bool(xs) and any(k.dep in (P.OBJ | {"iobj"}) and k.i < xs[0].i for k in t.kids) and t.lemma not in X.both(X.RAISING)
            if d in P.SUBJ:
                r = "ARG1" if (passive or copula or no_arg0(t.lemma, line.get("lang", "en"))) else "ARG0"
            elif d in P.OBJ or d == "iobj":
                r = "ARG2" if (controlled or d == "iobj") else "ARG1"     # urge [the doctors]ARG2 [to accept]ARG1
            elif d in ("obl:agent", "agent"):
                r = "ARG0"
            elif d in ("ccomp", "xcomp") and not P.adverbial_marks(c):
                r = "ARG1"
            elif d in ("advcl",) and {g.text.lower() for g in c.kids if g.dep == "mark"} & TIME_MARK:
                r = "ARGM-TMP"                                   # when / quand ... clause
            elif d in ("advmod", "advmod:tmod", "obl:tmod", "nmod:tmod", "obl:npmod", "npadvmod") and (c.text.lower() in TIME_ADV or c.text.lower() in TIME_NOUN or d.endswith("tmod")):
                r = "ARGM-TMP"
            elif d == "advmod" and not (c.text.lower() in P.NEG_EN | P.STRONG_NEG_FR | P.NE_NEG_FR | {"ne", "n'", "n’"}):
                r = "ARGM-ADV"
            elif d.startswith("obl") and c.text.lower() in TIME_NOUN:
                r = "ARGM-TMP"
            elif d.startswith("obl") or d == "prep":
                case = next((g.text.lower() for g in c.kids if g.dep in ("case", "fixed")), c.text.lower() if d == "prep" else "")
                if case in ("by", "par") and passive:
                    r = "ARG0"
                elif d == "obl:tmod" or case in TIME_CASE:
                    r = "ARGM-TMP"
                else:
                    r = f"ARGM-{case or 'OBL'}"
            else:
                continue
            roles.append((r, P.span(toks, c), c.i))
        if copula:
            roles.append(("ARG2", P.span_without(toks, t, P.SUBJ | {"cop", "aux", "aux:tense", "aux:pass", "mark", "cc", "advmod", "punct"}), t.i))
        if line.get("negated"):
            ng = next((c for c in t.kids if c.dep in ("advmod", "advmod:neg", "neg") and (c.text.lower() in P.NEG_EN | P.STRONG_NEG_FR | P.NE_NEG_FR | {"ne", "n'", "n’"})), None)
            roles.append(("ARGM-NEG", ng.text if ng is not None else "yes", ng.i if ng is not None else None))
        modt = [c for c in t.kids if c.dep in P.AUX and (c.lemma in MODAL or c.text.lower() in MODAL)]
        mods = [c.text for c in modt]
        if t.lemma in MODAL:
            mods.append(t.text)
        cnd = [x for x in [t] + [c for c in t.kids if c.dep in P.AUX] if "Mood=Cnd" in x.feats and x.lemma not in ("devoir", "falloir")]
        if cnd and not mods:
            mods.append(f"{cnd[0].text} (conditional)")      # French has no separate word for English "would"
        if mods:
            roles.append(("ARGM-MOD", " ".join(mods), modt[0].i if modt else None))
        return {"predicate": line["verb"], "lemma": t.lemma, "roles": roles, "kind": line.get("kind"), "hedged": line.get("hedged")}


    return frame, CORE
