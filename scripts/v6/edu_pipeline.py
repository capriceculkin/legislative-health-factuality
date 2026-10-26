"""edu_pipeline.py RULES PARSES.json OUT.json [--edu-trees EDU_TREES.json] [--rows sample|1,test|A8|fr]

Discourse first (design agreed Oct 22): the discourse parse cuts each sentence into elementary discourse units (EDUs);
the constituency tree of each unit gives the subject | verb | object lines inside it; the discourse relations connect
the units. No vote and no dependency parses.

Where each unit's tree comes from:
  projected  (default) the sentence's saved constituency tree, cut down to the unit's words. Same parser output, no
             new parsing, so it runs anywhere.
  reparsed   (--edu-trees, from edu_collect.py on the Mac) the constituency parser run on the unit's text alone, as
             proposed in the meeting.

Across units: a line with no subject of its own takes the subject of the unit it is attached to by the discourse
parse (the nucleus of the relation), and is marked with where the subject came from.

Writes one record per sentence: the units (text, character span, tree, lines) and the relations between units, with
every step kept so the output can be checked by hand. Plain python3, no packages."""
import sys, os, json, re, argparse

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("rules"); ap.add_argument("parses"); ap.add_argument("out")
    ap.add_argument("--edu-trees", default="")
    ap.add_argument("--rows", default="")
    ap.add_argument("--with-sentence-tree", action="store_true",
                    help="also let the whole sentence's tree fill gaps (not part of the Oct 22 design; for comparison)")
    A = ap.parse_args()
    sys.path.insert(0, os.path.abspath(A.rules))
else:                      # imported (the test notebook): the rules are the copy next to this file unless already loaded
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preds as P          # noqa: E402

# Every rule can be switched off, so its effect can be measured (the test notebook does this one rule at a time).
OPT = {"collapse": True,          # merge a verb phrase that holds only another verb phrase after cutting
       "drop_address": True,      # 'Mr. Speaker,' is not the subject
       "unwrap_coord": True,      # French: a clause inside COORD read as a clause
       "object_fill": True,       # an empty object taken from the sentence's tree
       "backfill": True,          # a line from the sentence's tree when the unit alone gives none
       "participles": True,       # French: participle phrases on a noun
       "fix_verb": True,          # the verb as written, with its negation
       "relpron": True,           # who / qui = the noun before it
       "demonstrative": True,     # 'that' pointing back to units, through the discourse parse
       "tree_subject": True,      # a missing subject found in the sentence's tree
       "discourse_subject": True, # a missing subject taken through the discourse relation
       "verb_join": True,         # 'refused to act' as one verb
       "control_list": True,      # 'X to do' takes X as subject only after verbs like urge, require (not purpose: cut taxes to help)
       "apposition": True,        # 'Jean Martin, the health minister,': its own line, and the name as the subject
       "questions": True,         # a unit that is a question is not a claim
       "neg_particles": True,     # ne ... plus / pas after the verb is part of the verb; ne ... que is not negation
       "adverbial_object": True,  # 'resigned before the report came out': the time clause is not the object
       "said_object": True,       # 'the HMO said,' | 'You need another opinion': the object is what the next unit says
       "reanchor": True,          # unit offsets checked against the sentence (the parser may have seen spaced dashes)
       "frame_context": True,     # a unit with no clause ('L'an dernier,') is attached as context to the lines it frames
       "units_only": False}       # the Oct 22 design exactly: only each unit's own tree and the discourse parse are used;
                                  # nothing is read from the whole sentence's tree (switches off object_fill, backfill,
                                  # participles, apposition, tree_subject, and finds 'which'/'qui' through the discourse parse)
SENTENCE_TREE_RULES = ("object_fill", "backfill", "participles", "apposition")
# tree_subject stays on in units_only mode, but reads the unit's own tree instead of the sentence's


def on(rule):
    "A rule is used when it is switched on, and, in units_only mode, when it does not read the whole sentence's tree."
    return OPT[rule] and not (OPT["units_only"] and rule in SENTENCE_TREE_RULES)
import lexicon as X        # noqa: E402
CONTROL_STEMS = {w for w in X.both(X.CONTROL) if " " not in w}
SPEECH_WORDS = {w.lower() for w in X.both(X.SPEECH)}
ADVERBIAL = ("before ", "after ", "because ", "when ", "while ", "unless ", "until ", "although ", "though ", "since ", "once ",
             "as soon as ", "so that ", "avant que ", "avant qu'", "après que ", "parce que ", "parce qu'", "quand ", "lorsque ",
             "lorsqu'", "à moins que ", "à moins qu'", "jusqu'à ce que ", "jusqu'à ce qu'", "bien que ", "bien qu'", "puisque ",
             "puisqu'", "pendant que ", "dès que ", "afin que ", "pour que ")

SHARED = {"elaboration": "elaboration", "elab": "elaboration", "adversative": "contrast", "contrast": "contrast",
          "attribution": "attribution", "attr": "attribution", "explanation": "explanation", "causal": "cause-result",
          "cause": "cause-result", "result": "cause-result", "cause-result": "cause-result", "condition": "condition",
          "contingency": "condition", "purpose": "purpose", "goal": "purpose", "background": "background",
          "frame": "background", "context": "background", "circumstance": "background", "temporal": "time-sequence",
          "temporal-sequence": "time-sequence", "time-sequence": "time-sequence", "joint": "joint", "list": "joint",
          "sequence": "time-sequence", "same-unit": "same-unit", "evaluation": "evaluation", "comment": "evaluation",
          "manner-means": "manner-means", "manner": "manner-means", "means": "manner-means", "comparison": "comparison",
          "restatement": "elaboration", "summary": "elaboration", "topic": "elaboration", "enablement": "purpose",
          "evidence": "explanation", "justify": "explanation", "motivation": "explanation", "concession": "contrast",
          "antithesis": "contrast", "alternation": "joint", "conjunction": "joint", "disjunction": "joint",
          "continuation": "joint", "e-elaboration": "elaboration", "topic-comment": "evaluation"}
MEANING = {"elaboration": "adds detail to", "background": "gives background or context for", "attribution": "says who says",
           "purpose": "gives the purpose of", "explanation": "gives the reason for", "cause-result": "is the cause or result of",
           "condition": "is a condition for", "evaluation": "comments on", "time-sequence": "is ordered in time with",
           "manner-means": "says how", "comparison": "is compared with", "contrast": "contrasts with",
           "joint": "is listed with", "same-unit": "is one unit with (split by an insertion)"}
# a unit with no subject of its own takes one from the unit it hangs on, for these relations only
INHERIT = {"elaboration", "purpose", "manner-means", "background", "joint", "same-unit", "time-sequence", "cause-result", "condition", "contrast", "explanation"}

PTB = {"-LRB-": "(", "-RRB-": ")", "-LSB-": "[", "-RSB-": "]", "-LCB-": "{", "-RCB-": "}", "``": '"', "''": '"'}
QUOTES = '"“”«»\'’‘`'


def shared(rel):
    r = rel.lower().replace("_", "-")
    return SHARED.get(r, SHARED.get(r.split("-")[0], r))


def leaves_of(t):
    return [t] if isinstance(t, str) else [w for k in t[1] for w in leaves_of(k)]


def align(text, words):
    """Character start of each tree leaf in the sentence, found left to right. A leaf that cannot be found keeps the
    current position, so a missed quote mark cannot shift the rest."""
    pos, out = 0, []
    low = text
    for w in words:
        w2 = PTB.get(w, w)
        i = low.find(w2, pos)
        if i < 0 and w2 in ('"',):
            m = re.compile(r"[\"“”«»]").search(low, pos)
            i = m.start() if m else -1
        if i < 0 or i - pos > 40:
            out.append(pos); continue
        out.append(i); pos = i + len(w2)
    return out


def prune(t, keep, counter):
    """The tree with only the leaves whose sentence index is in keep; empty phrases dropped."""
    if isinstance(t, str):
        i = counter[0]; counter[0] += 1
        return t if i in keep else None
    kids = [x for x in (prune(k, keep, counter) for k in t[1]) if x is not None]
    if not kids:
        return None
    return [t[0], kids]


def bracket(t):
    return t if isinstance(t, str) else "(" + t[0] + " " + " ".join(bracket(k) for k in t[1]) + ")"


def wrap(t, lang):
    """Rules expect a root label; a cut tree keeps the sentence's own root when it survives."""
    if lang == "fr":
        return t if t[0] in ("SENT", "TOP") else ["SENT", [t]]
    return t if t[0] in ("ROOT", "TOP") else ["ROOT", [t]]


def unwrap_coord(t):
    """French: a unit that is one side of a coordination ("mais le Senat a refuse d'agir") comes out of the French
    tree as a COORD node holding a whole clause. Inside its own unit, that clause is lifted out of the COORD (the
    linking word kept as the unit's first word) so the clause rules read it as a clause."""
    if isinstance(t, str):
        return t
    kids = []
    for k in t[1]:
        k = unwrap_coord(k)
        if not isinstance(k, str) and k[0] == "COORD" and any(not isinstance(x, str) and x[0] == "VN" for x in k[1]):
            kids += k[1]
        else:
            kids.append(k)
    return [t[0], kids]


VERB_TAGS = {"MD", "VB", "VBD", "VBG", "VBN", "VBP", "VBZ", "TO"}


def collapse(t):
    """Cutting a tree can leave a verb phrase holding only another verb phrase ("thank ... and rise" cut down to
    "and rise"). The outer one is merged into the inner one, so the rules find the verb."""
    if isinstance(t, str):
        return t
    kids = [collapse(k) for k in t[1]]
    if t[0].split("-")[0] == "VP":
        sub = [k for k in kids if not isinstance(k, str) and k[0].split("-")[0] == "VP"]
        verbish = any(not isinstance(k, str) and k[0] in VERB_TAGS for k in kids)
        if len(sub) == 1 and not verbish:
            i = kids.index(sub[0])
            return [sub[0][0], kids[:i] + sub[0][1] + kids[i + 1:]]
    return [t[0], kids]


def drop_address(t):
    """'Mr. Speaker, I thank ...': the form of address and its comma are not the subject."""
    if isinstance(t, str):
        return t
    kids = [drop_address(k) for k in t[1]]
    if t[0].split("-")[0] in ("S", "SENT") and len(kids) > 2 and not isinstance(kids[0], str) and kids[0][0].startswith("NP"):
        words = {w.lower().strip(".") for w in leaves_of(kids[0])}
        if words & {w.strip(".") for w in P.ADDRESS} and not isinstance(kids[1], str) and kids[1][0] in (",", "PONCT"):
            kids = kids[2:]
    return [t[0], kids]


def paths(trees):
    """For each leaf of the sentence, in order: the chain of nodes above it, root first."""
    out = []
    def walk(n, chain):
        if isinstance(n, str):
            out.append(chain); return
        for k in n[1]:
            walk(k, chain + [n])
    for t in trees:
        walk(t, [])
    return out


CLAUSE = {"S", "SINV", "SQ", "SBAR", "SENT", "Ssub", "Srel", "Sint", "VPinf", "VPpart"}


def np_text(n):
    """A noun phrase without the clauses and verb phrases hanging on it (the core that a subject names)."""
    if isinstance(n, str):
        return n
    keep = [k for k in n[1] if isinstance(k, str) or k[0].split("-")[0] not in CLAUSE | {"VP", "PP", ",", "PONCT"}]
    return P.text(["NP", keep]) if keep else P.text(n)


def subject_from_tree(path, lang):
    """Who the verb's clause is about, read from the sentence's whole tree, for a line whose own unit has no subject.
    Walking up from the verb: the first clause that has its own subject gives it; a participle clause hanging on a
    noun ("women donating fetal tissue") takes that noun; an infinitive hanging on a noun ("the decision to have an
    abortion") has no subject in the words. Returns (subject, how) or None."""
    tag = path[-1][0] if path else ""
    for depth in range(len(path) - 1, 0, -1):
        node, parent = path[depth], path[depth - 1]
        lab, plab = node[0].split("-")[0], parent[0].split("-")[0]
        if plab in ("ADJP", "AP") and lab in ("S", "VPinf"):
            return "(unstated)", "an infinitive on an adjective: who does it is not in the words"
        if plab == "VP" and lab == "S" and not any(not isinstance(k, str) and k[0].split("-")[0] == "NP" for k in node[1]) \
                and any(not isinstance(k, str) and k[0] == "TO" for k in P_iter(node)[:3]):
            i = parent[1].index(node)
            prev = parent[1][i - 1] if i > 0 else None          # the object right before the to-clause, no comma between
            obj = prev if prev is not None and not isinstance(prev, str) and prev[0].split("-")[0] == "NP" else None
            gov = next((P.text(k).lower() for k in reversed(parent[1][:i]) if not isinstance(k, str) and k[0] in VERB_TAGS), "")
            if obj is not None and (not OPT["control_list"] or any(gov.startswith(st) for st in CONTROL_STEMS)):
                return np_text(obj), "the object of the verb before it does it (urge X to, require X to)"
        if lang == "fr" and lab == "VPinf" and plab == "PP" and depth >= 2 and OPT["control_list"]:
            gp = path[depth - 2]; i = gp[1].index(parent)
            prev = gp[1][i - 1] if i > 0 else None
            vn = next((k for k in reversed(gp[1][:i]) if not isinstance(k, str) and k[0] == "VN"), None)
            gov = P.text(vn).lower() if vn is not None else ""
            if prev is not None and not isinstance(prev, str) and prev[0].startswith("NP") and any(w.startswith(st) for w in gov.split() for st in CONTROL_STEMS):
                return np_text(prev), "the object of the verb before it does it (exhorter X à)"
        if plab == "NP" and lab in ("VP", "S", "VPpart", "VPinf", "SBAR", "Srel"):
            nouns = [k for k in parent[1][:parent[1].index(node)] if not isinstance(k, str) and k[0].split("-")[0] in ("NP", "NN", "NNS", "NNP", "NNPS", "NC", "NPP", "DET", "DT", "JJ", "ADJ", "AP", "PRP$")]
            if lab == "VPinf" or (lab in ("S", "VP") and any(not isinstance(k, str) and k[0] == "TO" for k in P_iter(node))):
                return "(unstated)", "an infinitive on a noun: who does it is not in the words"
            if nouns:
                return P.text(["NP", nouns]), "a clause on a noun: the noun does it"
        kids = node[1]
        if lab in CLAUSE or (lab == "COORD" and any(not isinstance(k, str) and k[0] == "VN" for k in kids)):
            below = path[depth + 1] if depth + 1 < len(path) else None
            i = next((j for j, k in enumerate(kids) if k is below), len(kids))
            vi = next((j for j, k in enumerate(kids) if not isinstance(k, str) and k[0].split("-")[0] in ("VP", "VN")), None)
            if vi is not None and vi <= i:
                subj = next((k for k in reversed(kids[:vi]) if not isinstance(k, str) and k[0].split("-")[0] in ("NP", "CLS")), None)
                if subj is not None and not P.ADDRESS & {w.lower() for w in leaves_of(subj)}:
                    return np_text(subj), "the subject of the clause the verb sits in"
    return None


RELPRON = {"who", "which", "that", "whom", "qui", "que", "qu'", "lequel", "laquelle", "dont"}
DEMONSTR = {"that", "this", "it", "cela", "ce", "c'", "ça", "ceci"}


def antecedent(path):
    """For a relative clause: the noun phrase it hangs on (who / qui = that noun)."""
    for depth in range(len(path) - 1, 0, -1):
        node, parent = path[depth], path[depth - 1]
        if node[0].split("-")[0] in ("SBAR", "Srel") and parent[0].split("-")[0] == "NP":
            i = parent[1].index(node)
            return np_text(["NP", parent[1][:i]]) if i else None
    return None


def P_iter(n):
    """Every node under n, depth first, top down (the first TO found is the infinitive marker of the clause)."""
    if isinstance(n, str):
        return []
    out = []
    for k in n[1]:
        if not isinstance(k, str):
            out.append(k)
            if k[0] not in ("NP",):
                out += P_iter(k)
    return out


def unit_trees(row, edus):
    """For each unit: the pieces of the sentence's trees that fall inside it, and for each piece the sentence index
    of every leaf it kept."""
    trees = row.get("trees") or []
    words, owner = [], []
    for ti, t in enumerate(trees):
        lv = leaves_of(t)
        words += lv; owner += [ti] * len(lv)
    starts = align(row["text"], words)
    out = []
    for e in edus:
        keep = {i for i, s in enumerate(starts) if e["start"] <= s < e["end"]}
        pieces = []
        base = 0
        for ti, t in enumerate(trees):
            n = len(leaves_of(t))
            local = {i - base for i in keep if base <= i < base + n}
            if local:
                p = prune(t, local, [0])
                if p is not None:
                    p = collapse(p) if OPT["collapse"] else p
                    p = drop_address(p) if OPT["drop_address"] else p
                    if row["lang"] == "fr" and OPT["unwrap_coord"]:
                        p = unwrap_coord(p)
                    pieces.append((wrap(p, row["lang"]), sorted(base + i for i in local)))
            base += n
        out.append(pieces)
    return out


def lines_from(pieces, lang):
    out = []
    for p, idx in pieces:
        try:
            got = P.from_constituency(p, lang)
        except Exception as e:      # noqa: BLE001
            got = []
        for x in got:
            at = x.get("at")
            out.append({"subject": (x.get("subject") or "").strip(), "verb": x.get("verb") or "", "object": x.get("object") or "",
                        "kind": x.get("kind"), "negated": bool(x.get("negated")), "hedged": bool(x.get("hedged")),
                        "how": x.get("how") or "", "leaf": idx[at] if idx and isinstance(at, int) and at < len(idx) else None})
    return out


NEG = {"not", "n't", "never", "no", "longer", "pas", "jamais", "plus", "ne", "n'", "point", "guère"}


def tokens(text):
    return [w.strip(",.;:!?«»\"“”()") for w in re.findall(r"[\w’'-]+'?|\S", text.replace("n’t", " n't").replace("n't", " n't"))]


def fix_verb(ln, unit_text):
    """The verb as the words are written in the unit, from its first to its last word, so a negation the tree put
    outside the verb group (ne pourra pas congedier; no longer go) is kept with it."""
    tk = [w for w in tokens(unit_text) if w]
    low = [w.lower().replace("’", "'") for w in tk]
    vw = [w.lower().replace("’", "'") for w in tokens(ln["verb"]) if w]
    if not vw or vw[0] not in low:
        return
    i = low.index(vw[0])
    j = next((k for k in range(i, min(len(low), i + 8)) if low[k] == vw[-1]), None)
    if j is None:
        return
    words = tk[i:j + 1]
    if len(words) > len(vw) and all(w.lower().replace("’", "'") in NEG | set(vw) or w.lower() in ("y", "se", "s'", "en", "l'", "le", "la", "les", "lui", "leur") for w in words):
        ln["verb"] = " ".join(words).replace("' ", "'")
    pre = low[max(0, i - 2):i]
    if pre[-2:] == ["no", "longer"] or (pre and pre[-1] in ("never", "not")):
        k = 2 if pre[-2:] == ["no", "longer"] else 1
        ln["verb"] = " ".join(tk[i - k:i]) + " " + ln["verb"]
    if any(w.lower().replace("’", "'") in {"not", "n't", "never", "pas", "jamais", "no", "ne", "n'"} for w in tokens(ln["verb"])) \
            or re.search(r"(^|\s)n['’]", ln["verb"].lower()):
        ln["negated"] = True


def add_participles(row, units, starts, have):
    """French: a participle or infinitive phrase hanging on a noun ("une entente negociee par le gouvernement",
    "les personnes ayant une deficience") is a claim about that noun; the French tree rules skip it, so it is read
    here from the sentence's tree: the noun | the participle | what follows."""
    base = 0
    for t in row.get("trees") or []:
        def walk(n, pos):
            if isinstance(n, str):
                return
            p = pos
            for i, k in enumerate(n[1]):
                if not isinstance(k, str) and k[0] in ("VPpart",) and n[0].startswith("NP") and i > 0:
                    vn = next((x for x in k[1] if not isinstance(x, str) and x[0] in ("VN", "VPP", "VPR")), None)
                    if vn is not None and p not in have and p < len(starts):
                        noun = np_text(["NP", n[1][:i]])
                        rest = [x for x in k[1] if x is not vn]
                        u = next((v for v in units if v["start"] <= starts[p] < v["end"] + 1), None)
                        if u is not None:
                            u["lines"].append({"subject": noun, "verb": P.text(vn), "object": P.text(["X", rest]) if rest else "",
                                               "kind": "embedded", "negated": False, "hedged": False,
                                               "how": "describes a noun (participle); from the sentence tree", "leaf": p, "subject_from": ""})
                walk(k, p)
                p += len(leaves_of(k))
        walk(t, base)
        base += len(leaves_of(t))
    for u in units:
        u["lines"].sort(key=lambda l: l.get("leaf") if l.get("leaf") is not None else 10 ** 6)


def add_participles_units(units, pieces_all):
    """The same participle rule read from each unit's own tree (units_only mode): 'une entente negociee par le
    gouvernement' inside one unit gives une entente | negociee | par le gouvernement."""
    for u, ps in zip(units, pieces_all):
        have = {l.get("leaf") for l in u["lines"]}
        for t, idx in ps:
            def walk(n, pos):
                if isinstance(n, str):
                    return
                p = pos
                for i, k in enumerate(n[1]):
                    if not isinstance(k, str) and k[0] == "VPpart" and n[0].startswith("NP") and i > 0:
                        vn = next((x for x in k[1] if not isinstance(x, str) and x[0] in ("VN", "VPP", "VPR")), None)
                        leaf = idx[p] if p < len(idx) else None
                        if vn is not None and leaf not in have:
                            rest = [x for x in k[1] if x is not vn]
                            u["lines"].append({"subject": np_text(["NP", n[1][:i]]), "verb": P.text(vn), "object": P.text(["X", rest]) if rest else "",
                                               "kind": "embedded", "negated": False, "hedged": False,
                                               "how": "describes a noun (participle); from the unit's tree", "leaf": leaf, "subject_from": ""})
                    walk(k, p)
                    p += len(leaves_of(k))
            walk(t, 0)
        u["lines"].sort(key=lambda l: l.get("leaf") if l.get("leaf") is not None else 10 ** 6)


def K_norm(x):
    return re.sub(r"[^\w']+", " ", (x or "").replace("(inh)", "").lower()).strip()


def span(u):
    "Units named one by one, as agreed on Oct 22: 'unit 0', 'unit 0 and unit 1', 'unit 0, unit 1 and unit 2'."
    names = [f"unit {i}" for i in range(u[0], u[1] + 1)]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def reanchor(edus, text):
    """Unit offsets found again in the sentence itself. The discourse parser may have read a slightly different text
    (dashes with spaces added around them), which shifts every offset after the change."""
    out, pos = [], 0
    for e in edus:
        t = re.sub(r"\s+", " ", (e.get("text") or "").strip())
        pat = r"\s*".join(re.escape(ch) for ch in t.replace(" ", ""))
        m = re.compile(pat).search(text, pos) if t else None
        if m:
            out.append(dict(e, start=m.start(), end=m.end(), text=text[m.start():m.end()])); pos = m.end()
        else:
            out.append(dict(e))
    return out


def appositions(row, starts):
    """'Jean Martin, the health minister, tabled the bill': in the tree, a name, a comma and a noun phrase inside one
    noun phrase. Gives (sentence position of the name, name text, description text, whole phrase text)."""
    out = []
    base = 0
    for t in row.get("trees") or []:
        def walk(n, pos):
            if isinstance(n, str):
                return
            ks = n[1]
            if n[0].split("-")[0] == "NP" and len(ks) >= 3:
                labs = [k[0] if not isinstance(k, str) else "" for k in ks]
                if labs[0].startswith("NP") and labs[1] in (",", "PONCT") and labs[2].startswith("NP") \
                        and any(not isinstance(x, str) and x[0] in ("NNP", "NNPS", "NPP") for x in ks[0][1]) \
                        and not any(lab in ("CC",) for lab in labs) \
                        and not ({w.lower().strip(".") for w in leaves_of(ks[0])} & {w.strip(".") for w in P.ADDRESS}):   # 'Mr. Speaker,' is someone addressed
                    out.append((pos, P.text(ks[0]), np_text(ks[2]), P.text(["NP", [k for k in ks if not (not isinstance(k, str) and k[0] in (",", "PONCT"))]])))
            p = pos
            for k in ks:
                walk(k, p); p += len(leaves_of(k))
        walk(t, base)
        base += len(leaves_of(t))
    return out


FRAMES = {"background", "circumstance", "condition", "time-sequence", "temporal", "manner-means"}


def agree(phrase, sp):
    "'unit 0 and unit 1 give the reason', not 'gives'."
    if sp[0] == sp[1]:
        return phrase
    w, _, rest = phrase.partition(" ")
    w = {"is": "are", "says": "say", "gives": "give", "adds": "add"}.get(w, w[:-1] if w.endswith("s") else w)
    return (w + " " + rest).strip()


def first_tag(t):
    "The part-of-speech label of the first word of a tree."
    while not isinstance(t, str):
        if len(t[1]) == 1 and isinstance(t[1][0], str):
            return t[0]
        t = t[1][0]
    return ""


def top_np(t):
    "The first noun phrase that is a direct part of the clause (the would-be subject of a unit with no verb)."
    level = [t]
    while level:                                   # the shallowest noun phrase, left to right
        nxt = []
        for n in level:
            if isinstance(n, str):
                continue
            if n is not t and n[0].split("-")[0] == "NP":
                return n
            nxt += [k for k in n[1] if not isinstance(k, str)]
        level = nxt
    return None


def strict_subject(u, units, rels, pieces_all):
    """A unit with no subject in its own tree, read through the discourse parse (units_only mode):
    1. it opens with who / which / that / qui / que: the last noun phrase of the unit before it ('miners | who went underground')
    2. it opens with a participle or 'to' and is not set off by a comma: it describes the last noun before it
       ('women | donating fetal tissue'); with a comma it is about the subject before it ('a store ..., | sending')
    3. it is the rest of a unit split by an insertion (same-unit): the noun phrase the first part stands on
       ('miners | who went underground | were exposed')"""
    k = u["unit"]
    first = re.split(r"[\s']", u["text"].lower().lstrip(" “\"«"))[0] if u["text"] else ""
    if k > 0 and (first in RELPRON or u["text"].lower().startswith(("qu'", "qu’"))):
        a = antecedent_by_discourse(k, rels, pieces_all)
        if a:
            return a[0], f"'{first}' stands for the last noun phrase of {a[1]} (discourse: {a[2]})"
    tag = first_tag(pieces_all[k][0][0]) if pieces_all[k] else ""
    if k > 0 and tag in ("VBG", "VBN", "VPP", "VPR") and not re.search(r"[,;:]\s*$", units[k - 1]["text"]):
        a = antecedent_by_discourse(k, rels, pieces_all)
        if a:
            return a[0], f"describes the last noun phrase of {a[1]} (no comma between them; discourse: {a[2]})"
    for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
        if r["shared"] == "same-unit" and r["right"][0] <= k <= r["right"][1]:
            head = units[r["left"][0]]
            if not head["lines"] and pieces_all[head["unit"]]:
                np = top_np(pieces_all[head["unit"]][0][0])
                if np is not None:
                    return np_text(np), f"unit {head['unit']} (same-unit: the sentence goes on after an insertion)"
    return None


def antecedent_by_discourse(k, rels, pieces_all):
    """'which' / 'qui' opening unit k: the last noun phrase of the unit just before it, when the discourse parse joins
    the two (the smallest relation that has unit k on one side and the unit before it on the other)."""
    for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
        if r["right"][0] == k and r["left"][1] == k - 1:
            nps = []
            for t, _ in pieces_all[k - 1]:
                def walk(n):
                    if isinstance(n, str):
                        return
                    if n[0].split("-")[0] == "NP":
                        nps.append(n)
                    for c in n[1]:
                        walk(c)
                walk(t)
            if nps:
                return np_text(nps[-1]) if not isinstance(nps[-1], str) else nps[-1], f"unit {k - 1}", r["shared"]
    return None


def process(row, edu_trees=None):
    d = row.get("disc_native") or {}
    edus = d.get("edus") or [{"text": row["text"], "start": 0, "end": len(row["text"])}]
    if OPT["reanchor"]:
        edus = reanchor(edus, row["text"])
    strict_rep = edu_trees is not None and OPT["units_only"]
    if strict_rep:
        # the Oct 22 design: the words are numbered from the units' own trees; the sentence's tree is not read at all
        words, starts = [], []
        for e, ts in zip(edus, edu_trees):
            u_text = row["text"][e["start"]:e["end"]]
            for t in ts:
                lv = leaves_of(t)
                words += lv; starts += [e["start"] + c for c in align(u_text, lv)]
        row = dict(row, trees=[])
    else:
        words = [w for t in row.get("trees") or [] for w in leaves_of(t)]
        starts = align(row["text"], words)
    if edu_trees is not None:
        # each unit parsed on its own: its leaves are matched to the sentence's words by where they start in the text
        at_char = {}
        for i, c in enumerate(starts):
            at_char.setdefault(c, i)
        pieces_all = []
        for e, ts in zip(edus, edu_trees):
            u_text = row["text"][e["start"]:e["end"]]
            ps = []
            for t in ts:
                cs = [e["start"] + c for c in align(u_text, leaves_of(t))]
                t2 = collapse(t) if OPT["collapse"] else t
                t2 = drop_address(t2) if OPT["drop_address"] else t2
                if row["lang"] == "fr" and OPT["unwrap_coord"]:
                    t2 = unwrap_coord(t2)
                ps.append((wrap(t2, row["lang"]), [at_char.get(c) for c in cs]))
            pieces_all.append(ps)
        source = "reparsed"
    else:
        pieces_all, source = unit_trees(row, edus), "projected"
    leaf_paths = paths(row.get("trees") or [])
    if OPT["units_only"]:
        # each word's chain of nodes in its own unit's tree, not the sentence's
        unit_paths = {}
        for ps in pieces_all:
            for t, idx in ps:
                for i, pth in zip(idx, paths([t])):
                    if i is not None:
                        unit_paths[i] = pth
        leaf_paths = [unit_paths.get(i, []) for i in range(len(words))]
    full, base = {}, 0                             # the sentence's own tree read whole, by the verb's position
    for t in row.get("trees") or []:
        for x in P.from_constituency(t, row["lang"]):
            if isinstance(x.get("at"), int):
                full[base + x["at"]] = x
        base += len(leaves_of(t))
    units = []
    for i, (e, pieces) in enumerate(zip(edus, pieces_all)):
        txt = e.get("text") or row["text"][e["start"]:e["end"]]
        units.append({"unit": i, "text": txt.strip(), "start": e["start"], "end": e["end"],
                      "tree": [bracket(p) for p, _ in pieces], "tree_nodes": [p for p, _ in pieces],
                      "lines": lines_from(pieces, row["lang"])})
    # where a unit is too short to read on its own ("explicitly ensuring"), or its object sits in the next unit
    # ("the HMO said," | "You need another opinion"), the line comes from the sentence's whole tree
    have = {l["leaf"] for u in units for l in u["lines"] if l.get("leaf") is not None}
    for u in units:
        for ln in u["lines"]:
            ft = full.get(ln.get("leaf"))
            if on("object_fill") and ft is not None and not ln["object"] and ft.get("object"):
                ln["object"], ln["object_from"] = ft["object"], "sentence tree: the object runs into the next unit"
    if source == "projected" and on("backfill"):
        for leaf, ft in sorted(full.items()):
            if leaf in have or leaf >= len(starts):
                continue
            u = next((v for v in units if v["start"] <= starts[leaf] < v["end"] + 1), None)
            if u is None:
                continue
            u["lines"].append({"subject": (ft.get("subject") or "").strip(), "verb": ft.get("verb") or "", "object": ft.get("object") or "",
                               "kind": ft.get("kind"), "negated": bool(ft.get("negated")), "hedged": bool(ft.get("hedged")),
                               "how": (ft.get("how") or "") + "; from the sentence tree (the unit alone gave no line)", "leaf": leaf})
            u["lines"].sort(key=lambda l: l.get("leaf") if l.get("leaf") is not None else 10 ** 6)
    if row["lang"] == "fr" and OPT["units_only"] and OPT["participles"]:
        add_participles_units(units, pieces_all)
    if row["lang"] == "fr" and source == "projected" and on("participles"):
        add_participles(row, units, starts, {l["leaf"] for u in units for l in u["lines"] if l.get("leaf") is not None})
    for u in units:
        for ln in u["lines"]:
            if OPT["fix_verb"]:
                fix_verb(ln, u["text"])
    # questions are not claims
    if OPT["questions"]:
        for u in units:
            t = u["text"].rstrip(" »”\"'")
            tag = re.search(r",\s*(o\.?\s?k\.?|okay|right|hein|n['’]est-ce pas|non|oui|eh)\s*\?$", t, re.I)   # a tag question asks for agreement, the claim stands
            if t.endswith("?") and not tag:
                u["question"] = True
                u["lines"] = []
    if OPT["neg_particles"]:
        for u in units:
            for ln in u["lines"]:
                vw = ln["verb"].lower().replace("’", "'")
                has_ne = bool(re.search(r"(^|\s)(ne|n')", vw))
                m = re.match(r"^(plus|pas|jamais|guère|point)\b\s*", ln["object"], re.I)
                if has_ne and m:
                    ln["verb"] = ln["verb"] + " " + m.group(1); ln["object"] = ln["object"][m.end():]; ln["negated"] = True
                low = " " + u["text"].lower().replace("’", "'") + " "
                last = vw.split()[-1] if vw.split() else ""
                if has_ne and not re.search(r"\b(pas|jamais|plus|guère|point|aucun|aucune|personne|rien|nul)\b", vw + " " + ln["object"].lower()) \
                        and re.search(re.escape(last) + r"\s+qu", low):
                    ln["verb"] = re.sub(r"(^|\s)(ne|n')\s*", r"\1", ln["verb"], flags=re.I).strip()
                    ln["negated"] = False; ln["how"] = (ln["how"] + "; ne ... que (only) is not negation").strip("; ")
    if OPT["adverbial_object"]:
        for u in units:
            for ln in u["lines"]:
                o = ln["object"].lower().replace("’", "'") + " "
                if o.startswith(ADVERBIAL):
                    ln["adjunct"] = ln["object"]; ln["object"] = ""
                    ln["how"] = (ln["how"] + "; an adverbial clause is an adjunct, not the object").strip("; ")
    if on("apposition") and source == "projected":
        for pos, name, desc, whole in appositions(row, starts):
            if pos >= len(starts):
                continue
            u = next((v for v in units if v["start"] <= starts[pos] < v["end"] + 1), None)
            if u is None:
                continue
            for v in units:
                for ln in v["lines"]:
                    if ln["subject"].replace("(inh)", "").strip().replace(" ,", ",") in (whole, name + ", " + desc, name + " " + desc):
                        ln["subject"] = name
            u["lines"].append({"subject": name, "verb": "is (apposition)", "object": desc, "kind": "asserted", "negated": False,
                               "hedged": False, "how": "apposition: the phrase after the comma renames the name", "leaf": pos, "subject_from": ""})
            u["lines"].sort(key=lambda l: l.get("leaf") if l.get("leaf") is not None else 10 ** 6)
    rels = []
    for x in d.get("relations", []):
        sh = shared(x["relation"])
        nuc = x.get("nuclearity") or ""
        L, R = tuple(x["left"]), tuple(x["right"])
        main = L if nuc == "NS" else R if nuc == "SN" else None
        rels.append({"left": list(L), "right": list(R), "relation": x["relation"], "shared": sh, "nuclearity": nuc,
                     "main": list(main) if main else None,
                     "reads": f"{span(L)} to {span(R)}: {sh}; " + (f"main part {span(main)}" if main else "both equally important")
                              + (f"; {span(R if main == L else L)} {agree(MEANING.get(sh, 'is related to'), R if main == L else L)} {span(main)}" if main else "")})
    if OPT["said_object"]:
        for u in units:
            for ln in u["lines"]:
                speech = any(w in SPEECH_WORDS or w.rstrip("s") in SPEECH_WORDS for w in ln["verb"].lower().split())
                if ln["object"] or not (speech or (OPT["units_only"] and ln is u["lines"][-1])):
                    continue
                for r in rels:
                    if r["shared"] == "attribution" and r["main"] is not None:
                        side = r["left"] if r["main"] == r["right"] else r["right"]
                        if side[0] <= u["unit"] <= side[1]:
                            m = r["main"]
                            ln["object"] = " ".join(v["text"] for v in units[m[0]:m[1] + 1]).strip(" “”\"«»")
                            ln["object_from"] = f"discourse: what is said, {span(m)}"
                            break
    # subjects across units: a line without a subject takes the subject of the main part of the smallest relation
    # that attaches its unit to another one
    for u in units:
        for ln in u["lines"]:
            ln["subject_from"] = ""
            s0 = ln["subject"].replace("(inh)", "").strip()
            lp = leaf_paths[ln["leaf"]] if ln.get("leaf") is not None and ln["leaf"] < len(leaf_paths) else None
            first = re.split(r"[\s']", s0.lower())[0] if s0 else ""
            starts_rel = u["unit"] > 0 and u["text"].lower().startswith(first) and not re.search(r"[,.;:!?]\s*$", units[u["unit"] - 1]["text"]) if first else False
            is_rel = (s0.lower() in RELPRON and (s0.lower() not in DEMONSTR or starts_rel)) or (first in RELPRON and len(s0.split()) > 1 and first != "that")
            if OPT["relpron"] and OPT["units_only"] and is_rel:
                a = antecedent_by_discourse(u["unit"], rels, pieces_all)
                if a:
                    ln["subject"], ln["subject_from"] = a[0], f"'{s0.split()[0]}' stands for the last noun phrase of {a[1]} (discourse: {a[2]})"
                    continue
            if OPT["relpron"] and not OPT["units_only"] and (s0.lower() in RELPRON or (first in RELPRON and len(s0.split()) > 1 and first != "that")) and lp:
                a = antecedent(lp)
                if a:
                    ln["subject"], ln["subject_from"] = a, f"sentence tree: '{s0.split()[0]}' stands for the noun before it"
                    continue
            if OPT["demonstrative"] and s0.lower() in DEMONSTR:
                for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
                    L, R = r["left"], r["right"]
                    if L[0] <= u["unit"] <= L[1] or R[0] <= u["unit"] <= R[1]:
                        other = R if L[0] <= u["unit"] <= L[1] else L
                        ln["refers_to"] = f"{span(other)}: " + " ".join(v["text"] for v in units[other[0]:other[1] + 1])
                        ln["subject_from"] = f"'{s0}' points to {span(other)} ({r['shared']})"
                        break
                continue
            if s0 and s0 != "(unstated)" and "(inh)" not in ln["subject"]:
                continue
            # first the sentence's own tree: which clause the verb sits in
            got = subject_from_tree(leaf_paths[ln["leaf"]], row["lang"]) if on("tree_subject") and ln.get("leaf") is not None and ln["leaf"] < len(leaf_paths) else None
            if got:
                ln["subject"], ln["subject_from"] = got[0], ("unit tree: " if OPT["units_only"] else "sentence tree: ") + got[1]
                continue
            if OPT["units_only"] and OPT["discourse_subject"] and (not s0 or "(inh)" in ln["subject"]):
                got = strict_subject(u, units, rels, pieces_all)
                if got:
                    ln["subject"], ln["subject_from"] = got
                    continue
            if s0 or not OPT["discourse_subject"]:
                continue
            cands = []
            for r in rels:
                if r["main"] is None and r["shared"] not in ("joint", "same-unit", "contrast", "time-sequence"):
                    continue
                inside = lambda s: s[0] <= u["unit"] <= s[1]
                L, R = r["left"], r["right"]
                mine, other = (L, R) if inside(L) else (R, L) if inside(R) else (None, None)
                if mine is None or r["shared"] not in INHERIT:
                    continue
                if r["main"] is not None and r["main"] == mine:
                    continue                                    # this unit is the main part: nothing to inherit from
                cands.append((other[1] - other[0] + mine[1] - mine[0], other, r))
            for _, other, r in sorted(cands, key=lambda c: c[0]):
                src = next((v for v in units[other[0]:other[1] + 1] for l2 in v["lines"] if l2["subject"] and not l2.get("subject_from")), None)
                if src:
                    subj = next(l2["subject"] for l2 in src["lines"] if l2["subject"] and not l2.get("subject_from"))
                    ln["subject"], ln["subject_from"] = subj, f"unit {src['unit']} ({r['shared']})"
                    break
    # purpose, not control: "cut taxes to help families" -- the tree rules give "taxes" as the subject of "to help";
    # only after verbs like urge, require, ask is the object the one who does the next verb
    if OPT["control_list"]:
        allv = [l for u in units for l in u["lines"]]
        if True:
            for prev, ln in zip(allv, allv[1:]):
                if re.match(r"^(to|pour|afin de|à|de|d')\s", ln["verb"].lower()) and prev["object"] and \
                        K_norm(ln["subject"]) == K_norm(prev["object"]) and not any(w.startswith(st) for w in prev["verb"].lower().split() for st in CONTROL_STEMS) and \
                        not re.search(r"\b(is|are|was|were|be|been|need\w*|want\w*|use\w*|est|sont|faut|besoin|veu\w*)\b", prev["verb"].lower()):
                    ln["subject"], ln["subject_from"] = prev["subject"], "purpose: the subject of the verb before it (not urge X to)"
    # a verb chained with to / de ("refused to act", "a refuse d'agir") is one action, as in the dependency
    # convention: when a line's object is just the to-clause of the next line, with the same subject, they are one line
    for u in units:
        keep = []
        for ln in u["lines"]:
            prev = keep[-1] if keep else None
            if prev is not None and OPT["verb_join"]:
                o = prev["object"].lower().replace("’", "'")
                v = ln["verb"].lower()
                bare = re.sub(r"^(to|de|d'|à)\s*", "", v)
                same_subj = prev["subject"].replace("(inh)", "").strip().lower() == ln["subject"].replace("(inh)", "").strip().lower()
                if same_subj and bare and re.match(r"^(to |de |d'|à )", o) and re.sub(r"^(to|de|d'|à)\s*", "", o).startswith(bare):
                    marker = re.match(r"^(to |de |d'|à )", o).group(1)
                    prev["verb"] = prev["verb"] + " " + prev["object"][:len(marker)] + bare
                    prev["object"] = ln["object"]
                    prev["how"] = (prev["how"] + "; joined with its to-clause").strip("; ")
                    continue
            keep.append(ln)
        u["lines"] = keep
    # a unit with no clause of its own ("L'an dernier,", "In 1994,") is context for the lines on the other side of its
    # relation: it is attached to them rather than lost
    if OPT["frame_context"]:
        for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
            if r["shared"] not in FRAMES:
                continue
            for side, other in ((r["left"], r["right"]), (r["right"], r["left"])):
                us = units[side[0]:side[1] + 1]
                if side[0] == side[1] and not us[0]["lines"] and not us[0].get("question") and not us[0].get("context_used"):
                    us[0]["context_used"] = True
                    for v in units[other[0]:other[1] + 1]:
                        for ln in v["lines"]:
                            ln.setdefault("context", []).append(f"{us[0]['text'].strip(' ,;')} ({r['shared']}, unit {side[0]})")
    # connections between units, from the discourse parse: one per relation, with the text of each side, so the
    # whole of unit 0 and unit 1 can be what unit 2 explains (the 'that is why' case)
    conns = []
    for r in rels:
        L, R = r["left"], r["right"]
        txt = lambda sp: " ".join(v["text"] for v in units[sp[0]:sp[1] + 1]).strip()
        conns.append({"from": span(L), "to": span(R), "relation": r["shared"], "parser_label": r["relation"], "main": span(r["main"]) if r["main"] else "both",
                      "from_units": list(range(L[0], L[1] + 1)), "to_units": list(range(R[0], R[1] + 1)),
                      "from_text": txt(L), "to_text": txt(R), "reads": r["reads"]})
    for u in units:
        u.pop("context_used", None)
    return {"n": row["n"], "set": row.get("set"), "lang": row["lang"], "text": row["text"], "tree_source": source,
            "design": "units only (Oct 22)" if OPT["units_only"] else "units, with help from the sentence's tree",
            "discourse_status": row.get("disc_native_status"), "units": units, "relations": rels, "connections": conns,
            "lines": [dict(l, unit=u["unit"]) for u in units for l in u["lines"]]}


def main():
    OPT["units_only"] = not A.with_sentence_tree
    rows = json.load(open(A.parses, encoding="utf-8"))["rows"]
    want = set(A.rows.split(",")) if A.rows else None
    et = json.load(open(A.edu_trees, encoding="utf-8")) if A.edu_trees else {}
    out = []
    for r in rows:
        if want and r["n"] not in want:
            continue
        reparsed = et.get(r["n"])
        out.append(process(r, [[t for t in u] for u in reparsed] if reparsed else None))
    json.dump({"design": "discourse first, then constituency per unit (Oct 22)" + ("" if OPT["units_only"] else ", with the sentence's tree filling gaps"), "rows": out}, open(A.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {A.out}: {len(out)} sentences, {sum(len(x['units']) for x in out)} units, {sum(len(x['lines']) for x in out)} lines")


if __name__ == "__main__":
    main()
