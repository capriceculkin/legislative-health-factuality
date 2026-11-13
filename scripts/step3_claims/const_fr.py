"""Predications from a French Treebank (FTB) constituency tree, as produced by the Berkeley parser's French model
(benepar_fr2). FTB differs from Penn trees in the places that matter here:
  - the verb group is its own node, VN, and holds the clitics: subject (CLS il, ça, c'), object (CLO le, la, t'),
    reflexive (CLR se, s'), the negation (ADV ne ... pas) and the auxiliaries;
  - clauses: SENT (sentence), Sint (inserted or coordinated), Ssub (subordinate, starts with CS), Srel (relative),
    VPinf (infinitive, often with P de / à / pour), VPpart (participle);
  - relative clauses sit inside the noun phrase they describe, and French puts the subject after the verb after
    que / où / dont ("où sont situés les quartiers généraux", "qu'introduit le projet de loi").
Function tags (NP-SUJ, NP-OBJ) are used when the parser keeps them and ignored otherwise."""
import re
import lexicon as X   # PARITY_V6

CLAUSE = {"SENT", "Sint", "Ssub", "Srel", "VPinf", "VPpart"}
MODAL = {"doit", "doivent", "devait", "devaient", "devra", "devront", "devrait", "devraient", "dois", "devons", "devez",
         "peut", "peuvent", "pouvait", "pouvaient", "pourra", "pourront", "pourrait", "pourraient", "pourrais", "pourrions",
         "peux", "pouvons", "pouvez", "veut", "veulent", "voulait", "voudrait", "voudraient", "veux", "voulons", "voulez",
         "va", "vont", "allait", "allaient", "vais", "allons", "allez", "faut", "fallait", "faudra", "faudrait",
         "sait", "savent", "semble", "semblent", "vient", "viennent"}
HEDGE = X.fr(X.HEDGE_AUX) | X.fr(X.HEDGE_ADV)        # PARITY_V6: no devrait (should) and no semble, as in English
NEG = {"ne", "n'", "n’", "pas", "jamais", "aucun", "aucune", "plus", "nullement", "guère", "rien", "personne"}
STRONG_NEG = {"pas", "jamais", "aucun", "aucune", "nullement"}
ASSERTED_CS = X.fr(X.CAUSE)
NOT_ASSERTED_CS = X.fr(X.NOT_STATED) | X.fr(X.NOT_STATED_AS) | {"afin", "pour"}
SPEECH_FR = X.fr(X.SPEECH) | (X.fr(X.SOURCE_EXTRA) - X.fr(X.SOURCE_PREP))   # V6B: recommande que, montre que
FRAMING_FR = X.fr(X.FRAMING)
FIRST_FR = X.fr(X.FIRST_PERSON)
CONTROL_FR = tuple(sorted(X.fr(X.CONTROL)))
REL_OBJ = {"que", "qu'", "qu’", "où", "dont", "lequel", "laquelle", "lesquels", "lesquelles"}


def lab(n):
    return "" if isinstance(n, str) else n[0].split("-")[0].split("=")[0]


def func(n):
    return "" if isinstance(n, str) or "-" not in n[0] else n[0].split("-", 1)[1]


def leaves(n):
    return [n] if isinstance(n, str) else [w for k in n[1] for w in leaves(k)]


def text(n):
    s = " ".join(leaves(n)) if not isinstance(n, str) else n
    s = re.sub(r"\s+([,.;:!?)%])", r"\1", s)
    s = re.sub(r"(\b(?:[lLdDjJnNsScCmMtT]|[qQ]u|[jJ]usqu|[lL]orsqu|[pP]uisqu)['’])\s+", r"\1", s)
    s = re.sub(r"\(\s+", "(", s).replace("_", " ")
    return s.strip(" ,;:\"“”«»`")


def kids_with_offsets(n, pos):
    out, p = [], pos
    for k in n[1]:
        out.append((k, p)); p += len(leaves(k))
    return out


def vn_parts(vn):
    """Split a verb group into (subject clitic, verb text, object clitic, negated, hedged)."""
    subj, obj, words = "", "", []
    ls = [(lab(k), text(k)) for k in vn[1]]
    low = [w.lower() for _, w in ls]
    has_ne = any(w in ("ne", "n'", "n’") for w in low)
    neg = any(w in STRONG_NEG for w in low) or (has_ne and any(w in NEG for w in low if w not in ("ne", "n'", "n’")))
    if has_ne and any(w == "que" for w in low):
        neg = False                                     # ne ... que = only
    for i, (L, w) in enumerate(ls):
        if L == "CLS" and not subj:
            subj = w
        elif L == "CLO" and w.lower() not in ("en", "y"):
            obj = obj or w
        elif L == "ADV" and w.lower() not in NEG:
            continue                                    # sûrement, également: not part of the verb
        else:
            words.append(w)
    verb = " ".join(words)
    verb = re.sub(r"(\b(?:[nNsSmMtTlLjJ]|[qQ]u)['’])\s+", r"\1", verb)
    hedged = any(w.lower() in HEDGE or _conditional(w) for w in leaves(vn))
    return subj, verb, obj, neg, hedged


_CND = ("erait", "eraient", "erais", "irait", "iraient", "irais", "drait", "draient", "drais", "urait", "uraient", "urais",
        "rrait", "rraient", "rrais", "vrait", "vraient", "tirait")


def _conditional(w):
    """PARITY_V6: a conditional verb form (réduirait, serait, pourrait, prendrait), the French for English "would" + verb.
    devoir and falloir are obligation, as English should and must; the imperfect (déclarait, montrait) is not matched."""
    low = w.lower()
    return low.endswith(_CND) and not low.startswith(("devr", "faudr")) and low != "tirait"


def inf_parts(n):
    """An infinitive phrase: (marker word, its VN, what follows the VN)."""
    kids = n[1]
    mark = text(kids[0]) if kids and lab(kids[0]) == "P" else ""
    vn = next((k for k in kids if lab(k) == "VN"), None)
    rest = kids[kids.index(vn) + 1:] if vn is not None else []
    return mark, vn, rest


def obj_text(ks, i0):
    """The object after the verb: the first NP / PP / AP / Ssub / VPinf / AdP, with an AP joined to a following
    VPinf ('important de le mentionner'). Relative clauses inside it are left out (they are their own predications)."""
    for j in range(i0, len(ks)):
        k = ks[j]
        if lab(k) == "ADV" and text(k).lower() in X.fr(X.QUANT_ADV):
            return text(k)                              # V6B: "gagnent moins", as English trees keep ADVP
        if lab(k) in ("NP", "PP", "AP", "Ssub", "VPinf", "AdP", "VPpart"):
            t = core(k)
            if lab(k) == "AP" and j + 1 < len(ks) and lab(ks[j + 1]) == "VPinf":
                t = t + " " + text(ks[j + 1])
            return t
    return ""


def core(n):
    """A noun phrase without its relative clauses and participle clauses."""
    if isinstance(n, str) or lab(n) not in ("NP", "PP", "AP"):
        return text(n)
    keep = [k for k in n[1] if lab(k) not in ("Srel", "VPpart") and not (lab(k) == "PONCT" and text(k) == ",")]
    while keep and lab(keep[-1]) in ("PONCT", "CC"):
        keep.pop()
    return text((n[0], [core(k) if lab(k) in ("NP", "PP") else k for k in keep])) if keep else text(n)


def from_ftb(root):
    out = []

    def add(subj, inh, verb, obj, kind, how, neg, hedged, at):
        if verb and (subj or obj):
            out.append(dict(subject=subj + (" (inh)" if inh and subj else ""), verb=verb, object=obj, kind=kind, how=how,
                            negated=neg, hedged=hedged, at=at))

    def clause(n, subj, inh, kind, how, pos, head_np=None, rel_word=None):
        """A clause node (SENT, Sint, Ssub, Srel, VPinf, VPpart) whose verb group is a direct child."""
        ko = kids_with_offsets(n, pos)
        ks = [k for k, _ in ko]
        L = lab(n)
        vn = next((k for k in ks if lab(k) == "VN"), None)
        if vn is None:
            for k, o in ko:
                walk(k, subj, inh, kind, how, o)
            return
        i_vn = ks.index(vn)
        csubj, verb, cobj, neg, hed = vn_parts(vn)
        k2, h2 = kind, how
        first = text(ks[0]).lower().split(" ")[0] if ks else ""
        two = " ".join(text(k).lower() for k in ks[:2])
        if L == "Ssub" and how.startswith(("what is said", "the speaker's own framing")):
            k2, h2 = kind, how                          # PARITY_V6: the words of a speech verb, as in the English rules
        elif L == "Ssub":
            if two.startswith("comme quoi"):
                k2, h2 = "embedded", "what is said (comme quoi)"
            elif first in ASSERTED_CS or (first == "parce"):
                k2, h2 = kind, f"cause ({first})"
            elif first in NOT_ASSERTED_CS:
                k2, h2 = "embedded", f"condition or time ({first})"
            else:
                k2, h2 = "embedded", f"subordinate ({first})"
        elif L == "Srel":
            k2, h2 = "embedded", "relative clause"
        elif L in ("VPinf", "VPpart") and how == "main clause":
            k2, h2 = "embedded", "infinitive or participle"
        # subject: an NP before the verb group, else the clitic inside it, else (relative) the noun, else inherited
        np_before = [k for k in ks[:i_vn] if lab(k) == "NP" and func(k) != "OBJ"
                     and not all(lab(x) == "PROREL" for x in k[1] if not isinstance(x, str))]
        s, i2 = subj, True
        inverted = None
        if np_before and not (L == "Srel" and any(w.lower() in ("qui",) for w in leaves(np_before[0]))):
            s, i2 = core(np_before[-1]), False
        elif csubj:
            s, i2 = csubj, False
        if L == "Srel" and head_np is not None:
            if rel_word in ("qui",):
                s, i2 = head_np, False
            elif rel_word in REL_OBJ:
                inverted = next((k for k in ks[i_vn + 1:] if lab(k) == "NP"), None)
                if not np_before and not csubj and inverted is not None:
                    s, i2 = core(inverted), False       # où sont situés les quartiers généraux: inverted subject
        # verb chain: modal or control verb + infinitive ("doit résider", "s'est permis d'ouvrir")
        rest_i = i_vn + 1
        while rest_i < len(ks) and lab(ks[rest_i]) in ("PONCT", "PP") and lab(ks[rest_i]) == "PONCT":
            rest_i += 1
        nxt = next((j for j in range(i_vn + 1, len(ks)) if lab(ks[j]) not in ("PONCT", "ADV", "PP")), None)
        inf = ks[nxt] if nxt is not None and lab(ks[nxt]) == "VPinf" else None
        no_obj_between = inf is not None and not any(lab(ks[j]) in ("NP",) for j in range(i_vn + 1, nxt))
        merged_from = None
        inf_mark = text(inf[1][0]).lower() if inf is not None and inf[1] and lab(inf[1][0]) == "P" else ""
        if inf is not None and no_obj_between and inf_mark not in ("pour", "afin", "sans", "avant", "après", "par"):
            mark, ivn, rest = inf_parts(inf)
            if ivn is not None:
                _, iverb, iobj, ineg, ihed = vn_parts(ivn)
                verb = (verb + " " + (mark + " " if mark else "") + iverb).replace("' ", "'")
                verb = re.sub(r"\b([dD])['’]\s+", r"\1'", verb)
                neg, hed = neg or ineg, hed or ihed
                obj = obj_text(rest, 0) or iobj
                merged_from = inf
        if merged_from is None:
            obj = obj_text(ks, i_vn + 1)
            if inverted is not None and s == core(inverted):
                obj = obj_text([k for k in ks[i_vn + 1:] if k is not inverted], 0)
            obj = obj or cobj
        if L == "Srel" and head_np is not None and rel_word in ("que", "qu'", "qu’"):
            obj = f"{head_np} ({rel_word})"
        elif L == "Srel" and head_np is not None and rel_word == "où" and not obj:
            obj = f"{head_np} (où)"
        if any(lab(k) == "PP" and text(k).lower().startswith(("selon", "d'après", "d’après")) for k in ks):
            k2, h2 = "reported", "according to / selon"          # V6B
        add(s, i2, verb, obj, k2, h2, neg, hed, ko[i_vn][1])
        joined = {id(ks[j + 1]) for j in range(len(ks) - 1) if lab(ks[j]) == "AP" and lab(ks[j + 1]) == "VPinf"}
        last_verb = verb.split(" ")[-1].lower() if verb else ""
        for j, (k, o) in enumerate(ko):
            if j > i_vn and k is not merged_from and lab(k) == "Ssub" and last_verb in FRAMING_FR and \
                    (s or "").lower().split(" ")[0] in FIRST_FR and text(k).lower().split(" ")[0] in ("que", "qu'", "qu’"):
                clause(k, s, True, "asserted", f"the speaker's own framing ({verb})", o)    # V6B: je pense que
                continue
            if j > i_vn and k is not merged_from and lab(k) == "Ssub" and last_verb in SPEECH_FR and \
                    text(k).lower().split(" ")[0] in ("que", "qu'", "qu’"):
                clause(k, s, True, "reported", f"what is said ({verb})", o)      # PARITY_V6: il a dit que ...
                continue
            if j > i_vn and k is not merged_from and lab(k) == "VPinf" and last_verb.startswith(CONTROL_FR):
                ctrl = next((x for x in reversed(ks[i_vn + 1:j]) if lab(x) in ("NP", "PP")), None)
                if ctrl is not None:
                    c_txt = core(ctrl)
                    if lab(ctrl) == "PP":
                        c_txt = re.sub(r"^(?:à|aux|au)\s+", "", c_txt)
                    clause(k, c_txt, True, "embedded", f"complement of {verb}", o)   # PARITY_V6: encourager les citoyens à collaborer
                    continue
            if k is vn or (np_before and k is np_before[-1] and not has_clause(k)) or id(k) in joined:
                continue
            if k is merged_from:
                mark, ivn, rest = inf_parts(k)
                for k3, o3 in kids_with_offsets(k, o):
                    if k3 in rest:
                        walk(k3, s, True, k2, h2, o3)
                continue
            walk(k, s, True, k2, h2, o)

    def has_clause(n):
        return not isinstance(n, str) and any(lab(k) in CLAUSE or has_clause(k) for k in n[1])

    def walk(n, subj, inh, kind, how, pos):
        if isinstance(n, str):
            return
        L = lab(n)
        if L in CLAUSE:
            clause(n, subj, inh, kind, how, pos)
            return
        ko = kids_with_offsets(n, pos)
        if L == "NP":
            head = core(n)
            for k, o in ko:
                if lab(k) == "Srel":
                    rel = next((w.lower() for w in leaves(k)[:2] if w.lower() in REL_OBJ | {"qui"}), None)
                    clause(k, head, False, "embedded", "relative clause", o, head_np=head, rel_word=rel)
                elif lab(k) == "VPpart":
                    clause(k, head, False, "embedded", "describes a noun", o)
                else:
                    walk(k, subj, inh, kind, how, o)
            return
        if L == "COORD":
            for k, o in ko:
                walk(k, subj, True, kind, "joined (coordination)" if how == "main clause" else "joined: " + how, o)
            return
        if L == "PP":
            prep = text(n[1][0]).lower() if n[1] else ""
            for k, o in ko:
                if lab(k) in ("VPpart", "VPinf"):
                    if prep in X.fr(X.MEANS):
                        clause(k, subj, True, kind, f"means ({prep})", o)          # PARITY_V6: en / par, as English "by"
                    elif prep in X.fr(X.EXAMPLE):
                        clause(k, subj, True, kind, "example (such as / including)", o)
                    else:
                        clause(k, subj, True, "embedded", f"after '{prep}'", o)
                else:
                    walk(k, subj, inh, kind, how, o)
            return
        for k, o in ko:
            walk(k, subj, inh, kind, how, o)

    walk(root, "", True, "asserted", "main clause", 0)
    out.sort(key=lambda p: p["at"])
    return out
