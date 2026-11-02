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
       "apposition_across": True,  # an apposition split over two units, read through their elaboration relation
       "questions": True,         # a unit that is a question is not a claim
       "neg_particles": True,     # ne ... plus / pas after the verb is part of the verb; ne ... que is not negation
       "adverbial_object": True,  # 'resigned before the report came out': the time clause is not the object
       "said_object": True,       # 'the HMO said,' | 'You need another opinion': the object is what the next unit says
       "reanchor": True,          # unit offsets checked against the sentence (the parser may have seen spaced dashes)
       "frame_context": True,     # a unit with no clause ('L'an dernier,') is attached as context to the lines it frames
       "time_subject": True,      # 'Last year the House passed': a time is not the subject
       "bare_lines": True,        # a unit with a verb the tree rules gave no line for ('said', 'prévoit') gets one to fill
       "better_object": True,     # an adverb is not the object ('is also a moral obligation'); 'mess that up' = mess up
       "r6_stranded": True,       # round 6: 'we heard from', 'agreed to by conferees': a lone preposition is not the object
       "r6_experiencer": True,    # round 6: 'it seems to me ... that': 'to me' is not the object; what seems is
       "r6_aux_carry": True,      # round 6: 'you cannot listen ... and believe': the second verb keeps 'cannot'
       "r6_object_after": True,   # round 6: 'nous avons adopté, des mesures', 'prévoit, | ... | une indemnité': the object after a comma or in a later unit
       "r6_procedural": True,
       "r6_split_verb": True,
       "r6b_adjunct": True,       # round 6b: 'said very well', 'have heard persistently', 'a vu la semaine dernière': not the object
       "r6b_vocative": True,      # round 6b: 'Mr. Speaker, we're doubling': the subject is 'we', not the person spoken to
       "r6b_copula": True,        # round 6b: 'they are infected', 'on est d'accord': what follows the copula is its complement
       "r6b_make_sure": True,     # round 6b: 'make sure that ...': the that-clause is the object, not 'sure'
       "r6b_passive_part": True,
       "r7_subject_pron": True,   # round 7: a line with no subject whose verb comes right after a pronoun ('I found that ...')
       "r7_expletive_inf": True,  # round 7: 'it is important to give credit': 'it' does not do the infinitive
       "r7_list_not_appos": True, # round 7: 'the Lung Association, the Heart and Stroke Foundation, ...' is a list, not an apposition
       "r7_bare_aux": True,       # round 7: 'A Police Services Act | can |', 'il | est |' (a false start): not claims  # round 6b: 'a group called X', 'child support paid for': a participle on a noun is passive     # round 6: 'getting it done for the people': the pronoun inside the verb is the object     # round 6: 'a motion to recommit': the name of a motion, not a claim
       "r6_purpose_np": False,    # round 6 (tested, see notes): 'a grants program | to help ...': the noun just before does it
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


CLAUSE = {"S", "SINV", "SQ", "SBAR", "SENT", "Ssub", "Srel", "Sint", "VPinf", "VPpart", "FRAG"}   # a unit parsed alone is often FRAG


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
                head = (leaves_of(["NP", nouns])[-1:] or [""])[0].lower() if nouns else ""
                if OPT["units_only"] and nouns and head not in COMPLEMENT_NOUNS and clause_inf_has_object(node):
                    return P.text(["NP", nouns]), "an infinitive with its own object on a noun: the noun does it ('measures to help us')"
                return "(unstated)", "an infinitive on a noun: who does it is not in the words"
            if nouns:
                return P.text(["NP", nouns]), "a clause on a noun: the noun does it"
        kids = node[1]
        if lab in CLAUSE or (lab == "COORD" and any(not isinstance(k, str) and k[0] == "VN" for k in kids)):
            below = path[depth + 1] if depth + 1 < len(path) else None
            i = next((j for j, k in enumerate(kids) if k is below), len(kids))
            vi = next((j for j, k in enumerate(kids) if not isinstance(k, str) and k[0].split("-")[0] in ("VP", "VN")), None)
            if vi is not None and vi <= i:
                subj = next((k for k in reversed(kids[:vi]) if not isinstance(k, str) and (k[0].split("-")[0] in ("NP", "CLS")
                             or (k[0].split("-")[0] == "S" and first_tag(k) == "VBG"))), None)   # 'Having a large number ... places'
                if subj is not None and subj[0].split("-")[0] == "S":
                    return P.text(subj), "the clause the verb sits in has a gerund clause as its subject"
                if subj is not None and not P.ADDRESS & {w.lower() for w in leaves_of(subj)}:
                    return np_text(subj), "the subject of the clause the verb sits in"
    return None


RELPRON = {"who", "which", "that", "whom", "qui", "que", "qu'", "lequel", "laquelle", "dont"}
DEMONSTR = {"that", "this", "cela", "ce", "c'", "ça", "ceci"}   # 'it' / 'il' stand for a noun, not for a stretch of discourse


TIME_HEADS = {"year", "years", "week", "weeks", "month", "months", "day", "days", "session", "sessions", "time", "night", "morning",
              "afternoon", "evening", "decade", "century", "spring", "summer", "fall", "autumn", "winter", "today", "yesterday",
              "tomorrow", "tonight", "january", "february", "march", "april", "may", "june", "july", "august", "september",
              "october", "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
              "an", "année", "années", "semaine", "semaines", "mois", "jour", "jours", "hier", "aujourd'hui", "demain", "soir",
              "matin", "printemps", "été", "automne", "hiver", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre", "lundi", "mardi", "mercredi", "jeudi", "vendredi"}
TIME_FIRST = {"last", "next", "this", "that", "every", "each", "earlier", "later", "yesterday", "today", "tomorrow", "tonight",
              "l'", "cette", "ce", "chaque", "hier", "aujourd'hui", "demain", "dernier", "dernière", "prochain", "prochaine"}


def is_time_phrase(text):
    "'Last year', 'This week', 'Yesterday', 'L'an dernier', 'Cette semaine': a time, which cannot be who does the verb."
    t = (text or "").lower().replace("’", "'").strip(" ,")
    ws = [w for w in re.split(r"\s+|(?<=')", t) if w]
    if not 1 <= len(ws) <= 4 or not any(w in TIME_HEADS for w in ws):
        return False
    if len(ws) == 1:                     # one word only when it cannot be a name ('May' can)
        return ws[0] in {"yesterday", "today", "tomorrow", "tonight", "hier", "aujourd'hui", "demain"}
    return ws[0] in TIME_FIRST


def time_subject(path):
    """'Last year the House passed ...' parsed alone can give (S (NP Last year) (NP the House) (VP passed ...)), and the
    tree rules take the first noun phrase. In the clause the verb sits in: when the first noun phrase before the verb is
    a time and another noun phrase follows it, the later one is the subject and the time is context."""
    for depth in range(len(path) - 2, -1, -1):
        node, child = path[depth], path[depth + 1]
        if node[0].split("-")[0] not in ("S", "SINV", "SQ", "SENT", "Sint", "Ssub"):
            continue
        idx = next((i for i, k in enumerate(node[1]) if k is child), None)
        if idx is None:
            return None
        nps = [k for k in node[1][:idx] if not isinstance(k, str) and k[0].split("-")[0] == "NP"]
        if len(nps) == 1:                       # both inside one noun phrase: (NP (NP Last year) (NP the House))
            inner = [k for k in nps[0][1] if not isinstance(k, str) and k[0].split("-")[0] == "NP"]
            nps = inner if inner and len(inner) == len(nps[0][1]) else nps
        if len(nps) >= 2 and is_time_phrase(P.text(nps[0])) and not is_time_phrase(P.text(nps[-1])):
            return np_text(nps[-1]), P.text(nps[0])
        return None
    return None


CONTRACT = {"m": "am", "'m": "am", "re": "are", "'re": "are", "ve": "have", "'ve": "have", "ll": "will", "'ll": "will",
            "d": "would", "'d": "would", "s": "is", "'s": "is"}


def expand_contractions(ln, unit_text=""):
    "'I'm sure' gives the verb 'm (or m once the apostrophe is split off): written out as 'am', the form as written kept."
    if re.search(r"\bcan not\b", ln["verb"]) and re.search(r"\bcannot\b", unit_text, re.I):
        ln["verb"] = re.sub(r"\bcan not\b", "cannot", ln["verb"])      # as written: 'cannot'
    ws = ln["verb"].replace("’", "'").split()
    if ws and ws[0].lower() in CONTRACT:
        ln["verb_as_written"] = ln["verb"]
        ln["verb"] = " ".join([CONTRACT[ws[0].lower()]] + ws[1:])


BILL_TEXT = re.compile(r"""^\W{0,2}\(\w{1,4}\)\s | \.--\S | ^\W{0,2}(SEC\.|SECTION\s+\d|Sec\.\s*\d|TITLE\s+[IVX]+\b)
                       | \bis\ amended\b | ^\W{0,2}(in\ )?(subparagraph|paragraph|subsection|section)\ \(\w{1,4}\)""", re.X)
# a member's motion that quotes a bill ('Mr Eves moves that subsection 19(4) of the bill be struck out ...') is kept:
# moving it is something said in the debate


def is_bill_text(text):
    """Quoted statute text in the debate record ('(A) Employer coverage at time of ...--In the case of'), which is not
    something a member said; left out when new sentences are drawn."""
    return bool(BILL_TEXT.search(text or ""))


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


VERB_LABELS = {"VB", "VBD", "VBG", "VBN", "VBP", "VBZ", "MD", "V", "VPP", "VINF", "VPR", "VS", "VIMP"}
ADDRESS_WORDS = {"mr", "mr.", "mrs", "mrs.", "ms", "ms.", "madam", "madame", "m.", "monsieur", "mme", "speaker", "président",
                 "présidente", "chair", "chairman", "chairwoman", "honourable", "hon.", "the", "le", "la", "member", "members"}


QUESTION_START = re.compile(r"""^\W*((and|but|so|then|et|mais|alors|donc|or)\W+)?(why|how|what|when|where|who|whom|which|whose|is|are|was|were|do|does|did|can|could|would|should|will|shall|has|have|had|isn't|aren't|doesn't|don't|didn't|won't|wouldn't|shouldn't|couldn't|pourquoi|comment|quand|où|combien|quel|quelle|quels|quelles|qui|que|qu'est-ce|est-ce|lequel|laquelle)\b""", re.I | re.X)


def is_question_sentence(text):
    "'Et pourquoi ... la municipalité paierait ... ?': the whole sentence is a question (a tag question like ', O.K.?' is not)."
    t = (text or "").strip().rstrip(" »”\"'")
    if not t.endswith("?") or re.search(r",\s*(o\.?\s?k\.?|okay|right|hein|n['’]est-ce pas|non|oui|eh)\s*\?$", t, re.I):
        return False
    return bool(QUESTION_START.match(t.replace("’", "'")))


def has_verb(pieces):
    "Whether the unit's tree has a verb anywhere in it."
    def walk(n):
        if isinstance(n, str):
            return False
        if len(n[1]) == 1 and isinstance(n[1][0], str):
            return n[0] in VERB_LABELS
        return any(walk(k) for k in n[1])
    return any(walk(t) for t, _ in pieces)


def has_clause(pieces):
    """Whether the unit's tree has a full clause: a subject (noun phrase or clitic) before a verb in the same clause.
    'and then after that we control you' has one and is not context; 'If passed,' and 'tel que demandé par ...' have a
    verb but no subject of their own, and are."""
    def walk(n):
        if isinstance(n, str):
            return False
        kids = [k for k in n[1] if not isinstance(k, str)]
        if n[0].split("-")[0] in ("S", "SINV", "SQ", "SENT", "Sint", "Ssub", "Srel", "VN"):
            labs = [k[0].split("-")[0] for k in kids]
            for i, lab in enumerate(labs):
                if lab in ("VP", "VN") and any(l2 in ("NP", "CLS") for l2 in labs[:i]):
                    return True
            if n[0] == "VN" and any(l2 == "CLS" for l2 in labs):
                return True
        return any(walk(k) for k in kids)
    return any(walk(t) for t, _ in pieces)


def is_address(text):
    "'Mr. Speaker,' 'M. le Président,': someone spoken to, not the time or place of anything."
    ws = re.findall(r"[\w.']+", (text or "").lower())
    core = {"speaker", "président", "présidente", "chair", "chairman", "chairwoman", "madam", "madame", "monsieur", "mr", "mr.",
            "mrs", "mrs.", "m.", "mme", "honourable"} | set(P.ADDRESS)
    return bool(ws) and all(w in ADDRESS_WORDS or w in P.ADDRESS for w in ws) and any(w in core for w in ws)


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
    # the rest of a unit split by an insertion comes first: the discourse parse says whose sentence it is
    for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
        if r["shared"] == "same-unit" and r["right"][0] == k:
            head = units[r["left"][0]]
            if not head["lines"] and pieces_all[head["unit"]]:
                np = top_np(pieces_all[head["unit"]][0][0])
                if np is not None:
                    return np_text(np), f"unit {head['unit']} (same-unit: the sentence goes on after an insertion)"
    tag = first_tag(pieces_all[k][0][0]) if pieces_all[k] else ""
    tags2 = [pth[-1][0] for _, _, pth in unit_leaves(pieces_all[k])[:2]] if pieces_all[k] else []
    prev_lines = units[k - 1]["lines"] if k > 0 else []
    no_comma = k > 0 and not re.search(r"[,;:]\s*$", units[k - 1]["text"])
    jr = joined_by(k, rels)
    if tag == "TO" and prev_lines and no_comma and \
            re.fullmatch(r"(is|was|are|were|be|been|being|'s|’s)", prev_lines[-1]["verb"].lower().split()[-1] if prev_lines[-1]["verb"] else "") and prev_lines[-1]["object"]:
        po = prev_lines[-1]["object"]
        adj = word_tag(pieces_all[k - 1], po.split()[0]).startswith(("JJ", "ADJ", "RB", "ADV"))
        if not adj and unit_inf_has_object(pieces_all[k]) and (re.findall(r"\w+", po.lower()) or [""])[-1] not in COMPLEMENT_NOUNS:
            return po, f"'{prev_lines[-1]['verb']} {po} | to ... <object>': the noun does it ('an adequate base of seniors | to offset the portion')"
        return "(unstated)", f"'{prev_lines[-1]['verb']} {po} | to ...': an infinitive on a noun or adjective; who does it is not in the words"
    if no_comma and tags2[:2] == ["IN", "VBG"] and jr and jr["shared"] == "elaboration":
        return "(unstated)", "a gerund after a preposition, on the noun before it ('the formula | for determining ...'): who does it is not in the words"
    if no_comma and prev_lines and prev_lines[-1]["object"] and re.match(r"^(d'|d’|de |à )", u["text"].lower()) and \
            any(pth and pth[-1][0] == "VINF" for _, _, pth in unit_leaves(pieces_all[k])) and \
            not any(w.startswith(st) for w in prev_lines[-1]["verb"].lower().split() for st in CONTROL_STEMS):
        return "(unstated)", "an infinitive on the noun before it ('la décision du gouvernement | d'aller'): who does it is not in the words"
    if no_comma and (tag in ("VBG", "VBN", "VPP", "VPR") or (tag == "VBD" and re.search(r"\bby\b", u["text"]))):
        a = antecedent_by_discourse(k, rels, pieces_all, no_pp=True)
        if a:
            return a[0], f"describes the last noun phrase of {a[1]} (no comma between them; discourse: {a[2]})"
    return None


REL_TAGS = {"PROREL", "WDT", "WP", "WP$"}
NOT_ANTECEDENT = {"ce", "-ce", "c'", "ça", "cela", "ceci", "celui", "celle", "ceux", "celles", "that", "this", "those", "what",
                  "it", "il", "elle", "qu'", "que", "qui", "who", "which"}


def word_tag(pieces, word):
    "The part-of-speech label the unit's tree gives the first occurrence of word ('' when it is not there)."
    w = word.lower().replace("’", "'")
    for t, _ in pieces:
        def walk(n):
            if isinstance(n, str):
                return None
            if len(n[1]) == 1 and isinstance(n[1][0], str):
                return n[0] if n[1][0].lower().replace("’", "'") == w else None
            for k in n[1]:
                got = walk(k)
                if got:
                    return got
            return None
        got = walk(t)
        if got:
            return got
    return ""


def resolve_relative(u, word, lp, rels, pieces_all):
    """who / which / qui / que at the start of a clause (units_only mode): first the noun phrase it hangs on inside the
    same unit's tree ('un dossier qui soit constitue'); when the unit starts with it, the last noun phrase of the unit
    before it, through the discourse parse. Only a word the unit's tree marks as a relative pronoun (PROREL, WDT, WP):
    the question word in 'qu'est-ce qui' is not one. And the antecedent must be a noun phrase, not another pronoun
    ('ce qui' = what)."""
    w = word.split()[0]
    if re.search(r"qu['’]est-ce|est-ce qu", u["text"].lower()) and w.lower().replace("’", "'") in ("qu'", "que", "qui"):
        return None                             # 'qu'est-ce qui' is a question word; a fragment parsed alone can tag
                                                # a relative as a question word or a demonstrative, so tags are not used
    ok = lambda a: a and a.lower().strip(" ,") not in NOT_ANTECEDENT and not a.strip().startswith("-")
    a = antecedent(lp) if lp else None
    if ok(a):
        return a, f"unit tree: '{w}' stands for the noun before it"
    if a:                                        # it hangs on a pronoun: what it stands for is not stated
        return None
    a = antecedent_by_discourse(u["unit"], rels, pieces_all)
    if a and ok(a[0]):
        return a[0], f"'{w}' stands for the last noun phrase of {a[1]} (discourse: {a[2]})"
    return None


def antecedent_by_discourse(k, rels, pieces_all, no_pp=False):
    """'which' / 'qui' opening unit k: the last noun phrase of the unit just before it, when the discourse parse joins
    the two (the smallest relation that has unit k on one side and the unit before it on the other). With no_pp, a noun
    phrase inside a prepositional phrase does not count ('to get back to work | putting America ...': not 'work')."""
    for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
        if r["right"][0] == k and r["left"][1] == k - 1:
            nps, pp_nps = [], []
            for t, _ in pieces_all[k - 1]:
                def walk(n, in_pp=False):
                    if isinstance(n, str):
                        return
                    lab = n[0].split("-")[0]
                    if lab == "NP":
                        nps.append(n)
                        if in_pp:
                            pp_nps.append(n)
                    for c in n[1]:
                        walk(c, lab == "PP")         # only a noun phrase that is the preposition's own object ('to work')
                walk(t)
            if no_pp:
                nps = [n for n in nps if not (any(n is q for q in pp_nps) and len(leaves_of(n)) == 1 and leaves_of(n)[0][:1].islower())]
            if nps:
                return np_text(nps[-1]) if not isinstance(nps[-1], str) else nps[-1], f"unit {k - 1}", r["shared"]
    return None


ADV_LABELS = {"ADVP", "RB", "ADV", "RBR", "RBS", "WHADVP"}
FLOATING = {"tous", "toutes", "tout", "all", "both", "each"}
OBJ_LABELS = ("NP", "ADJP", "AP", "PP", "S", "SBAR", "Ssub", "VPinf", "QP", "Sint")
PARTICLES = {"up", "down", "out", "off", "back", "over", "away", "through"}
IDIOMS = [(r"\bwhat have you\b", "have"), (r"\bso to speak\b", "speak"), (r"\bif you will\b", "will"), (r"\bas it were\b", "were"),
          (r"\bmind you\b", "mind"), (r"\bthank you\b", "thank"), (r"\bpeu importe\b", "importe"), (r"\bn'importe\b", "importe")]
POINT_C = {"explanation", "evaluation", "cause-result"}      # 'c'est pourquoi', 'c'est dommage': c' / ce point back only here


def _norm(x):
    return re.sub(r"[^\w]+", "", (x or "").lower())


def unit_leaves(pieces):
    "Every word of a unit's tree(s) in order: (global word number, word, chain of nodes from the root to its label)."
    out = []
    for t, idx in pieces:
        for i, (w, pth) in enumerate(zip(leaves_of(t), paths([t]))):
            out.append((idx[i] if i < len(idx) else None, w, pth))
    return out


def verb_paths(ln, ul):
    "The chains above the verb's own words, last word first (the main verb, then any auxiliary)."
    vws = [w.lower().replace("’", "'") for w in tokens(ln.get("verb_as_written") or ln["verb"]) if w]
    start = next((j for j, (g, _, _) in enumerate(ul) if g == ln.get("leaf")), None)
    if start is None:
        start = next((j for j, (_, w, _) in enumerate(ul) if vws and w.lower().replace("’", "'") == vws[0]), None)
    if start is None:
        return []
    got = [pth for g, w, pth in ul[max(0, start - 3):start + 8] if w.lower().replace("’", "'") in vws and pth and pth[-1][0] in VERB_LABELS]
    return list(reversed(got))


def better_object(ln, ul):
    """'it is also a moral obligation', 'we will lose slightly in excess of ...', 'Nous comprenons tous la raison': the
    tree rules took the adverb (or a floating 'tous') as the object. In the verb's clause, the phrase after it is the
    object; with nothing after it, there is no object."""
    if not ln["object"]:
        return
    for path in verb_paths(ln, ul):
        for depth in range(len(path) - 2, -1, -1):
            node, child = path[depth], path[depth + 1]
            i = next((j for j, k in enumerate(node[1]) if k is child), None)
            if i is None:
                break
            after = [k for k in node[1][i + 1:] if not isinstance(k, str) and k[0] not in (",", "PONCT", ".", ":")]
            if not after:
                continue
            first = after[0]
            if _norm(P.text(first)) != _norm(ln["object"]):
                return
            lab = first[0].split("-")[0]
            ft = P.text(first).lower().strip()
            if ft in ("pas", "plus", "jamais", "guère", "point") and re.search(r"(^|\s)(ne|n'|n’)", ln["verb"].lower()):
                nxt = next((k for k in after[1:] if k[0].split("-")[0] in OBJ_LABELS), None)
                ln["verb"], ln["negated"] = ln["verb"] + " " + ft, True       # 'ne reçoivent plus | ce service'
                ln["object"] = P.text(nxt) if nxt is not None else ""
                return
            if ft in ("so much", "much", "more", "less", "a lot", "plus", "moins", "beaucoup", "autant", "davantage"):
                return                              # 'practise so much', 'gagnent moins': the amount is what is done
            if lab in ADV_LABELS or (lab == "NP" and P.text(first).lower().strip() in FLOATING):
                nxt = next((k for k in after[1:] if k[0].split("-")[0] in OBJ_LABELS), None)
                if nxt is not None:                 # with nothing after it, the adverb stays ('gagnent | moins', 'went | underground')
                    ln["object"] = P.text(nxt)
                    ln["how"] = (ln["how"] + "; an adverb is not the object; the phrase after it is").strip("; ")
            return


def move_particle(ln, ul):
    "'mess that up': the particle belongs to the verb (mess up | that)."
    ws = ln["object"].split()
    if len(ws) >= 2 and ws[-1].lower() in PARTICLES and any(w.lower() == ws[-1].lower() and pth and pth[-1][0] in ("RP", "PRT") for _, w, pth in ul):
        ln["verb"] = ln["verb"] + " " + ws[-1]
        ln["object"] = " ".join(ws[:-1])
        ln["how"] = (ln["how"] + "; the particle goes with the verb").strip("; ")


def inf_vp_has_object(path):
    "Whether the infinitive's own verb phrase has a noun phrase object ('to offset the portion' yes; 'to do so' no)."
    if not path or len(path) < 2:
        return False
    vp = path[-2]
    return any(not isinstance(k, str) and k[0].split("-")[0] == "NP" for k in vp[1])


def unit_inf_has_object(pieces):
    "The same for a unit that is a to-infinitive: the verb phrase under 'to' has a noun phrase object."
    for t, _ in pieces:
        found = []
        def walk(n):
            if isinstance(n, str) or found:
                return
            kids = [k for k in n[1] if not isinstance(k, str)]
            if n[0].split("-")[0] == "VP" and kids and kids[0][0] == "TO":
                vp = next((k for k in kids[1:] if k[0].split("-")[0] == "VP"), None)
                found.append(vp is not None and any(not isinstance(k, str) and k[0].split("-")[0] == "NP" for k in vp[1]))
                return
            for k in kids:
                walk(k)
        walk(t)
        if found:
            return found[0]
    return False


SAID_START = re.compile(r"""^\W*(that|whether|if|que|qu'|qu’|si|s'|«|"|“|:)""", re.I)


def speaks(sp, units):
    "Whether a span has a verb of saying in one of its lines."
    return any(any(w in SPEECH_WORDS or w.rstrip("s") in SPEECH_WORDS for w in ln["verb"].lower().split())
               for v in units[sp[0]:sp[1] + 1] for ln in v["lines"])


def attribution_sides(r, units, lang):
    """(the side that does the saying, the side that is said), for an attribution relation. Read from the sentence: the
    side with a verb of saying, or the side that does not open the reported part ('that', 'que', 'whether', 'si', a
    quote mark, a colon before it). Only when the words do not tell, the parser's main part: the English model marks
    what is said as the main part, the French one the sayer."""
    L, R = r["left"], r["right"]
    sl, sr = speaks(L, units), speaks(R, units)
    if sl != sr:
        return (L, R) if sl else (R, L)
    if SAID_START.match(units[R[0]]["text"]) or units[L[1]]["text"].rstrip().endswith(":"):
        return L, R
    if SAID_START.match(units[L[0]]["text"]):
        return R, L
    main = r["main"] or R
    other = L if main == R else R
    return (other, main) if lang == "en" else (main, other)


def unit_appositions(pieces):
    "'Jean Martin, the health minister,' inside one unit's tree: (word number of the name, name, description, whole)."
    out = []
    for t, idx in pieces:
        for pos, name, desc, whole in appositions({"trees": [t]}, None):
            out.append((idx[pos] if pos < len(idx) else None, name, desc, whole))
    return out


def lone_np(pieces):
    "The noun phrase a unit consists of, when it is nothing else (punctuation aside); else None."
    for t, _ in pieces:
        n = t
        while not isinstance(n, str):
            kids = [k for k in n[1] if not isinstance(k, str) and k[0] not in (",", "PONCT", ".", ":", "``", "''")]
            if len(kids) != 1:
                return None
            if kids[0][0].split("-")[0] == "NP":
                return kids[0]
            n = kids[0]
    return None


def has_name(np):
    "Whether a noun phrase holds a proper name."
    def walk(n):
        if isinstance(n, str):
            return False
        if n[0] in ("NNP", "NNPS", "NPP") and len(n[1]) == 1:
            return True
        return any(walk(k) for k in n[1])
    return walk(np)


def main_units(span, rels, toward, units=None, lang="en"):
    """The units that carry the main part of a span: inside it, follow each relation to its main side ('SB-8 ... bars
    abortion | after a fetal heartbeat can be detected': unit 0, not the time clause); when both sides are equal,
    the side nearer to the unit asking."""
    a, b = span
    while a < b:
        r = next((r for r in rels if r["left"][0] == a and r["right"][1] == b), None)
        if r is None:
            break
        if r["shared"] == "attribution" and units is not None:
            side = attribution_sides(r, units, lang)[0]              # 'the proposal would ensure | that ...': the sayer
        elif r["shared"] == "attribution" and r["main"] is not None:
            side = r["left"] if r["main"] == r["right"] else r["right"]
        else:
            side = r["main"] if r["main"] is not None else (r["right"] if toward > b else r["left"])
        a, b = side
    return list(range(a, b + 1))


DUMMY_HEADS = {"time", "important", "necessary", "essential", "clear", "possible", "impossible", "hard", "easy", "difficult",
               "true", "good", "best", "right", "wrong", "unfortunate", "crucial", "vital", "likely", "unlikely", "obvious",
               "temps", "important", "nécessaire", "essentiel", "clair", "possible", "impossible", "difficile", "vrai", "dommage", "évident"}
CONTENT_NOUNS = {"fact", "idea", "notion", "claim", "belief", "hope", "news", "argument", "possibility", "assumption", "view",
                 "suggestion", "concern", "fear", "statement", "assurance", "promise", "sense", "feeling", "impression", "point",
                 "fait", "idée", "notion", "espoir", "argument", "possibilité", "crainte", "impression", "sentiment"}


COMPLEMENT_NOUNS = {"decision", "decisions", "plan", "plans", "right", "rights", "time", "way", "ways", "ability", "chance", "chances",
                    "effort", "efforts", "attempt", "attempts", "opportunity", "opportunities", "need", "desire", "intention",
                    "power", "authority", "responsibility", "obligation", "duty", "freedom", "choice", "permission",
                    "commitment", "goal", "aim", "purpose", "reason", "proposal", "promise", "request", "order", "motion",
                    "willingness", "refusal", "failure", "capacity", "means", "order", "bid", "move", "push", "pressure",
                    "décision", "plan", "droit", "temps", "moyen", "moyens", "façon", "capacité", "chance", "effort", "tentative",
                    "occasion", "besoin", "désir", "intention", "pouvoir", "responsabilité", "obligation", "devoir", "liberté",
                    "choix", "permission", "engagement", "objectif", "but", "raison", "proposition", "promesse", "demande"}


def clause_inf_has_object(node):
    "In an infinitive clause on a noun ('measures to help us'): whether the verb after 'to' has a noun phrase object."
    def find(n):
        if isinstance(n, str):
            return None
        kids = [k for k in n[1] if not isinstance(k, str)]
        if n[0].split("-")[0] == "VP" and kids and kids[0][0] == "TO":
            return next((k for k in kids[1:] if k[0].split("-")[0] == "VP"), None)
        for k in kids:
            got = find(k)
            if got is not None:
                return got
        return None
    vp = find(node)
    return vp is not None and any(not isinstance(k, str) and k[0].split("-")[0] == "NP" for k in vp[1])


def good_source(l2):
    """A line whose subject another unit can take: it has a real subject (its own, or one already found for it), not
    '(unstated)', not 'that' pointing to units, and not the empty 'it' of 'It is time' / 'Il est temps'."""
    s0 = l2["subject"].replace("(inh)", "").strip()
    if not s0 or s0 == "(unstated)" or l2.get("refers_to"):
        return False
    if s0.lower() in ("it", "il", "ce", "c'") and re.search(r"(^|\s)(is|was|'s|’s|est|était|sera)(\s|$)", l2["verb"].lower()) and \
            (not l2["object"] or set(re.findall(r"\w+", l2["object"].lower())[-1:]) & DUMMY_HEADS):
        return False                                # 'It is time', 'It is important': nobody; 'it is in front of the forum': the matter
    return True


def joined_by(k, rels):
    "The relation that joins unit k to the unit right before it (the smallest one), or None."
    for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
        if r["right"][0] == k and r["left"][1] == k - 1:
            return r
    return None


SUBORD_START = re.compile(r"^\W*(if|unless|when|whenever|while|although|though|once|until|because|as|since|before|after|si|s'|quand|lorsque|lorsqu'|bien que|tel que|telle que|tels que|comme|avant|après|pendant|dès)\b")


def bare_line(pieces, lang):
    """A unit whose tree has a verb but gave no line ('said', 'prévoit,', 'that answer to the people', 'are the people'):
    the tree rules drop a verb with neither subject nor object of its own. The line is built from the unit's tree with
    an empty subject, so the discourse parse can fill it."""
    for t, idx in pieces:
        leaves = leaves_of(t); ps = paths([t])
        for i, pth in enumerate(ps):
            if not pth or pth[-1][0] not in VERB_LABELS:
                continue
            parent = pth[-2] if len(pth) >= 2 else None
            if parent is None:
                return None
            if lang == "fr" and parent[0] == "VN":
                words = [" ".join(leaves_of(k)) for k in parent[1] if not isinstance(k, str) and k[0] not in ("CLS",)]
                joined = ""
                for w_ in words:                    # n' est -> n'est
                    joined = joined + w_ if joined.endswith(("'", "’")) else (joined + " " + w_ if joined else w_)
                words = [joined]
                subj = next((P.text(k) for k in parent[1] if not isinstance(k, str) and k[0] == "CLS"), "")
                holder, at = (pth[-3], next((j for j, k in enumerate(pth[-3][1]) if k is parent), 0)) if len(pth) >= 3 else (parent, 0)
            else:
                at = next(j for j, k in enumerate(parent[1]) if k is pth[-1])
                words, subj, j = [], "", at
                holder = parent
                while j < len(holder[1]):
                    k = holder[1][j]
                    if not isinstance(k, str) and (k[0] in VERB_LABELS or (k[0] == "RB" and P.text(k).lower() in ("not", "n't", "never"))):
                        words.append(P.text(k)); j += 1
                    elif not isinstance(k, str) and k[0].split("-")[0] == "VP" and words:
                        holder, j = k, 0
                    else:
                        break
                at = j - 1
                if len(pth) >= 3 and any(not isinstance(k, str) and k[0] == "TO" for k in pth[-3][1][:1]):
                    words = ["to"] + words          # (VP (TO to) (VP (VB ensure)))
            obj = next((P.text(k) for k in holder[1][at + 1:] if not isinstance(k, str) and k[0].split("-")[0] in OBJ_LABELS), "")
            if not obj and len(pth) >= 3:           # (SINV (VP (VBP are)) (NP the people)): the object sits beside the verb phrase
                gp = pth[-3]; pi = next((j for j, k in enumerate(gp[1]) if k is parent), None)
                if pi is not None:
                    obj = next((P.text(k) for k in gp[1][pi + 1:] if not isinstance(k, str) and k[0].split("-")[0] in OBJ_LABELS), "")
            return {"subject": subj, "verb": " ".join(words), "object": obj, "kind": "asserted", "negated": False, "hedged": False,
                    "how": "a verb the tree rules gave no line for; read from the unit's tree", "leaf": idx[i] if i < len(idx) else None}
    return None


STRANDED = {"to", "from", "of", "for", "with", "about", "on", "in", "at", "into", "upon", "by"}
EXPERIENCER = re.compile(r"^(to|for)\s+(me|us|him|her|them|you)$", re.I)
SEEM_VERBS = {"seems", "seem", "seemed", "appears", "appear", "appeared", "sounds", "looks", "semble", "paraît", "parait"}
MODALS = {"can", "cannot", "could", "will", "would", "shall", "should", "may", "might", "must", "do", "does", "did", "can't", "won't",
          "wouldn't", "shouldn't", "couldn't", "don't", "doesn't", "didn't"}
DETS_START = re.compile(r"^(the|a|an|this|these|those|our|their|its|his|her|all|some|any|des|les|le|la|l'|un|une|ces|cette|ce|cet|nos|notre|leurs|leur|ses|son|sa|plusieurs|certains|certaines)\b", re.I)


def _note(ln, text):
    ln["how"] = (ln["how"] + "; " + text).strip("; ")


def _after_verb(unit_text, verb, subject=""):
    "The text of the unit after the verb's last word (None when the word is not found); after 'subject verb' when that is there."
    w = verb.split()[-1:] if verb.split() else []
    if not w:
        return None
    sj = subject.replace("(inh)", "").strip()
    if sj:
        m = re.search(r"(?<![\w])" + re.escape(sj) + r"\s*(?:\S+\s+){0,3}?" + re.escape(w[0]) + r"(?![\w'’])", unit_text, re.I)
        if m:
            return unit_text[m.end():]
    m = None
    for m in re.finditer(r"(?<![\w'’])" + re.escape(w[0]) + r"(?![\w'’])", unit_text, re.I):
        break
    return unit_text[m.end():] if m else None


COPULAS = {"is", "are", "was", "were", "be", "been", "being", "am", "get", "gets", "got", "become", "becomes", "became", "remain", "remains",
           "est", "sont", "était", "étaient", "sera", "seront", "reste", "restent", "devient", "deviennent", "semble"}
ADJUNCT_WORDS = {"well", "very well", "today", "tonight", "now", "here", "there", "then", "again", "too", "also", "already", "still",
                 "over and over", "again and again", "always", "often", "sometimes", "the past", "in the past", "in our minds", "in my mind",
                 "with you", "with us", "toujours", "souvent", "parfois", "par année", "par mois",
                 "aujourd'hui", "maintenant", "hier", "demain", "ici", "là", "encore", "aussi", "déjà", "toujours", "bien", "très bien"}
ADJUNCT_START = re.compile(r"^(at the (time|outset|moment|end|beginning)|at this (time|point|moment)|in many ways|in a way|de façon|de manière|"
                           r"avec (justesse|raison|force|insistance)|comme (députée?|ministre|parlementaires?)|en cette chambre|la semaine (dernière|prochaine)|"
                           r"l'an (dernier|prochain)|cet après-midi|ce matin|ce soir|un bon jour)\b", re.I)
SAY_VERBS = {"said", "say", "says", "tell", "told", "stated", "state", "explain", "explained", "dire", "dit", "dis", "disait", "expliquer",
             "expliquées", "expliqué", "demande", "demander", "souligné", "rappelé", "affirmé"}


def round6_pre(row, units):
    """Round 6b, before 'what is said' is filled in: an adverb, a time, a manner phrase or the person spoken to is not
    the object ('The member said very well that ...', 'je vous dis que ...')."""
    if not OPT["r6b_adjunct"]:
        return
    for u in units:
        for ln in u["lines"]:
            o = ln["object"].strip().replace("’", "'")
            ol = o.lower()
            if not o:
                continue
            adverb = ol in ADJUNCT_WORDS or (len(ol.split()) == 1 and re.fullmatch(r"[a-zà-ÿ]+ly" if row["lang"] == "en" else r"[a-zà-ÿ]+ment", ol) and ol not in ("supply", "family", "assembly", "gouvernement", "parlement", "règlement", "logement", "département", "traitement", "financement", "établissement", "amendement", "paiement", "investissement", "environnement", "enseignement", "jugement", "document", "argument", "moment", "comment", "élément", "segment", "monument", "instrument", "ministry")) \
                or ADJUNCT_START.match(ol) or is_time_phrase(o)
            if ol in ("into place", "in place", "en place") and len(ln["verb"].split()) >= 1:
                ln["verb"], ln["object"] = ln["verb"] + " " + o, ""
                _note(ln, f"'{o}' goes with the verb")
                continue
            spoken_to = any(w in SAY_VERBS for w in ln["verb"].lower().split()) and \
                (re.match(r"^to\s+(my|the|our|all|you|him|her|them|us|me|members?|colleagues?)\b", ol) or ol in ("vous", "nous", "lui", "leur", "te", "me", "us", "you"))
            if adverb or spoken_to:
                ln["adjunct"] = o
                ln["object"] = ""
                _note(ln, f"'{o}' is " + ("who it is said to" if spoken_to else "how or when, not the object"))


def round6(row, units, rels, pieces_all, ULEAVES):
    """Round 6 (Nov 1), from the claims two readers marked wrong on the 60 new sentences. Each rule is switched by its
    OPT flag, and each one notes what it did in the line's 'how'."""
    lang = row["lang"]
    for u in units:
        k = u["unit"]
        for ln in u["lines"]:
            obj = ln["object"].strip()
            # A. a lone preposition left behind by a relative or a passive is not the object
            if OPT["r6_stranded"] and obj.lower() in STRANDED and lang == "en":
                by = re.search(r"(?<![\w])" + re.escape(ln["verb"].split()[-1]) + r"\s+" + re.escape(obj) + r"\s+by\s+(.+?)\s*[.,;:]?$", u["text"], re.I) \
                    if ln["verb"].split() else None
                if by and obj.lower() != "by":
                    # 'the statistical assumptions | agreed to by conferees': the conferees agreed to the assumptions
                    old = ln["subject"]
                    ln["subject"], ln["verb"], ln["object"] = by.group(1).strip(), ln["verb"] + " " + obj, old
                    ln["subject_from"] = f"unit tree: a passive participle; who does it is the phrase after 'by'"
                    ln["object_from"] = "what the participle hangs on (the noun before it)"
                    _note(ln, "a passive with 'by': the doer is after 'by', the thing done to is the noun it hangs on")
                    continue
                ln["verb"], ln["object"] = ln["verb"] + " " + obj, ""
                _note(ln, f"'{obj}' is a preposition left behind, part of the verb, not the object")
                # 'The people | we heard from': a clause on the noun phrase of the unit before it (no 'that')
                if OPT["r6b_copula"] and k > 0 and re.match(r"^\W*(that|which|whom)\b", u["text"], re.I) and \
                        not re.search(r"[,;:]\s*$", units[k - 1]["text"]):
                    # 'the people | that I have talked to': the relative's noun is what the preposition is about
                    jr = joined_by(k, rels)
                    if jr and jr["shared"] in ("elaboration", "same-unit"):
                        got = antecedent_by_discourse(k, rels, pieces_all)
                        if got and got[0].lower().strip() not in NOT_ANTECEDENT and _norm(got[0]) != _norm(ln["subject"]):
                            ln["object"], ln["object_from"] = got[0], f"object relative: '{u['text'].split()[0]}' stands for the last noun phrase of {got[1]} (discourse: {got[2]})"
                            continue
                if k > 0 and not re.match(r"^\W*(that|which|who|whom)\b", u["text"], re.I):
                    jr = joined_by(k, rels)
                    prev = units[k - 1]
                    if jr and jr["shared"] in ("elaboration", "same-unit") and not prev["lines"]:
                        a = lone_np(pieces_all[k - 1])
                        if a is not None:
                            ln["object"], ln["object_from"] = np_text(a), f"unit {k - 1}: the noun phrase this clause hangs on (no 'that')"
            # B. 'it seems to me': the experiencer is not the object; what seems is the that-clause it introduces
            elif OPT["r6_experiencer"] and EXPERIENCER.match(obj) and any(w in SEEM_VERBS for w in ln["verb"].lower().split()):
                ln["adjunct"] = obj
                ln["object"] = ""
                for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
                    if r["shared"] == "attribution" and r["left"][0] <= k <= r["left"][1] and r["right"][0] == r["left"][1] + 1:
                        R = r["right"]
                        ln["object"] = " ".join(v["text"] for v in units[R[0]:R[1] + 1]).strip(" .,;")
                        ln["object_from"] = f"discourse: what seems so, {span(R)}"
                        break
                _note(ln, f"'{obj}' says to whom it seems; it is not the object")
            # B2. 'from what I've seen of this': what was seen is 'what', not 'of this'
            elif OPT["r6_experiencer"] and lang == "en" and re.match(r"^of\s+(this|that|it|these|those)$", obj, re.I) and \
                    re.search(r"\bwhat\s+" + re.escape(ln["subject"].split()[0]) + r"\b", u["text"], re.I) if ln["subject"].split() else False:
                ln["adjunct"], ln["object"] = obj, "what"
                _note(ln, "'what' is what is seen (a free relative); the phrase after is not the object")
        # C. 'you cannot listen ... and believe': a bare verb joined by 'and' to a verb with a modal keeps the modal
        if OPT["r6_aux_carry"] and lang == "en":
            for ln in u["lines"]:
                m = re.match(r"^\W*(and|or|but)\s+(\w+)", u["text"], re.I)
                src = re.match(r"^unit (\d+)", ln.get("subject_from") or "")
                if not m or not src or len(ln["verb"].split()) != 1 or m.group(2).lower() != ln["verb"].lower():
                    continue
                if word_tag(pieces_all[k], ln["verb"]) not in ("VB", ""):
                    continue
                sl = next((l2 for l2 in units[int(src.group(1))]["lines"] if _norm(l2["subject"]) == _norm(ln["subject"])), None)
                if not sl:
                    continue
                aux = [w for w in sl["verb"].split()[:-1] if w.lower() in MODALS or w.lower() in ("not", "never", "n't")]
                if aux and aux[0].lower() in MODALS:
                    ln.setdefault("verb_as_written", ln["verb"])          # the words in this unit; the modal is carried from the other
                    ln["verb"] = " ".join(aux) + " " + ln["verb"]
                    ln["negated"] = ln.get("negated") or bool(sl.get("negated")) or any(a.lower() in ("cannot", "not", "never", "n't") or a.lower().endswith("n't") for a in aux)
                    _note(ln, f"joined by '{m.group(1).lower()}' to '{sl['verb']}' in unit {src.group(1)}: it keeps '{' '.join(aux)}'")
        # D. an object after a comma in the same unit ('nous avons adopté, des mesures'), or in a later unit that is only
        # a noun phrase ('prévoit, | lorsque ... | - c'est ... - | une indemnité de départ ...')
        if OPT["r6_object_after"]:
            for ln in u["lines"]:
                if ln["object"].strip() or not ln["verb"].strip() or ln.get("implied_verb"):
                    continue
                rest = _after_verb(u["text"], ln["verb"])
                if rest is None:
                    continue
                r1 = rest.strip()
                m = re.match(r"^,\s*(.+)$", r1)
                if m and DETS_START.match(m.group(1)) and not re.match(r"^(lorsque|quand|si|when|if|because|parce|que|qu'|that)\b", m.group(1), re.I):
                    np_ = re.split(r"\s*[,;:.](?:\s|$)", m.group(1))[0].strip()
                    if 1 <= len(np_.split()) <= 15:
                        ln["object"], ln["object_from"] = np_, "the same unit, after a comma"
                        _note(ln, "the object comes after a comma")
                        continue
                if r1.strip(" ,;:-–—") == "":
                    for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
                        if r["shared"] == "same-unit" and r["left"][0] <= k <= r["left"][1] and r["right"][0] == r["right"][1] > k:
                            j = r["right"][0]
                            only_np = (not units[j]["lines"] and lone_np(pieces_all[j]) is not None) or \
                                (DETS_START.match(units[j]["text"].strip()) and units[j]["lines"] and all("describes a noun" in l["how"] for l in units[j]["lines"]))
                            if only_np:
                                ln["object"], ln["object_from"] = units[j]["text"].strip(" .,;"), f"unit {j}: the sentence goes on after an insertion (same-unit)"
                                _note(ln, f"the object is unit {j}, after the insertion")
                            break
        # G. 'getting it done for the people of Ontario': a pronoun between the two verb words is the object
        if OPT["r6_split_verb"] and lang == "en":
            for ln in u["lines"]:
                vw = ln["verb"].split()
                if len(vw) != 2:
                    continue
                m = re.search(r"\b" + re.escape(vw[0]) + r"\s+(it|them|this|that|him|her|everything|something|nothing)\s+" + re.escape(vw[1]) + r"\b", u["text"], re.I)
                if m and (not ln["object"].strip() or re.match(r"^(for|to|with|in|on|at|by)\s", ln["object"], re.I)):
                    if ln["object"].strip():
                        ln["adjunct"] = ln["object"]
                    ln["object"], ln["object_from"] = m.group(1), "the pronoun between the verb's two words"
                    _note(ln, f"'{m.group(1)}' sits inside the verb ('{vw[0]} {m.group(1)} {vw[1]}'): it is the object")
        # E. 'a motion to recommit': the name of a procedure, not a claim
        if OPT["r6_procedural"] and lang == "en":
            u["lines"] = [l for l in u["lines"] if not (l["verb"].split() and re.search(r"\bmotion\s+to\s+" + re.escape(l["verb"].split()[-1].lower()) + r"\b",
                                                                                          row["text"].lower()) and len(l["verb"].split()) <= 2
                                                                    and re.search(r"\bto\s+" + re.escape(l["verb"].split()[-1].lower()) + r"\b", u["text"].lower()))]
        for ln in u["lines"]:
            vlow = ln["verb"].lower().replace("’", "'")
            # J. 'Mr. Speaker, we're doubling': the person spoken to is not the subject
            if OPT["r6b_vocative"] and is_address(ln["subject"]):
                m = re.search(re.escape(ln["subject"]) + r"\W*\s*(we|it|i|you|they|he|she|this|that|there|nous|je|j|il|elle|on|ils|elles|c|ce|ça|cela)(?=[\s'’,]|$)", u["text"], re.I)
                if m:
                    ln["subject"] = m.group(1) + ("'" if m.group(1).lower() in ("c", "j") else "")
                    ln["subject_from"] = "the person spoken to is not the subject; the pronoun after it is"
                    _note(ln, "someone spoken to is not the subject")
            # L. 'make sure that ...'
            if OPT["r6b_make_sure"] and re.search(r"\b(make|makes|making|made)$", vlow) and ln["object"].strip().lower() in ("sure", "certain"):
                rest = re.split(r"\b(?:sure|certain)\b", u["text"], maxsplit=1, flags=re.I)
                after = rest[1].strip(" ,.;:") if len(rest) > 1 else ""
                if after.lower() in ("that", "que", "qu'"):
                    after = ""
                j = k + 1
                while not after and j < len(units) and units[j]["text"].strip(" ,.;:").lower() in ("that", "que", "qu'"):
                    j += 1                                  # a lone 'that' cut off as its own unit
                if not after and j < len(units):
                    jr = joined_by(j, rels) or joined_by(k + 1, rels)
                    if jr and jr["shared"] in ("attribution", "elaboration", "same-unit", "purpose"):
                        after = units[j]["text"].strip(" ,.;:")
                        ln["object_from"] = f"unit {j}: what is made sure of"
                ln["verb"] = ln["verb"] + " " + ln["object"].strip()
                ln["object"] = re.sub(r"^that\s+", "", after, flags=re.I) if after else ""
                _note(ln, "'make sure': what follows is the object")
            # I. a copula with nothing after it in the claim: its complement is the words after it ('they are infected')
            if OPT["r6b_copula"] and not ln["object"].strip() and vlow.split() and vlow.split()[-1] in COPULAS:
                rest = _after_verb(u["text"], ln["verb"], ln["subject"])
                if rest is not None:
                    r1 = rest.strip()
                    m = re.match(r"^([^,.;:!?()«»\"“”\-–—]+)", r1)
                    if m and not re.match(r"^(that|if|when|because|qu|que|si|parce|lorsque|quand|to)\b", m.group(1).strip(), re.I) and 1 <= len(m.group(1).split()) <= 8:
                        ln["object"], ln["object_from"] = m.group(1).strip(), "the words after the copula in the same unit"
                        _note(ln, "the complement of the copula")
            # H. 'a community group called X', 'child support paid for a family': a past participle hanging on the noun
            # before it is passive: the noun is what is done to, not who does it
            if OPT["r6b_passive_part"] and lang == "en" and "describes the last noun phrase" in (ln.get("subject_from") or "") and \
                    len(ln["verb"].split()) == 1 and word_tag(pieces_all[k], ln["verb"]) == "VBN":
                ln.setdefault("verb_as_written", ln["verb"])
                ln["verb"] = "(is) " + ln["verb"]
                ln["passive"] = True
                _note(ln, "a past participle on the noun before it: passive (the noun is what is done to)")
        for ln in u["lines"]:
            # R7e. no subject, but a pronoun right before the verb in the same unit ('I found that ...', 'I said that ...')
            if OPT["r7_subject_pron"] and not ln["subject"].strip() and ln["verb"].split():
                v0 = (ln.get("verb_as_written") or ln["verb"]).split()[0]
                m = re.search(r"(?<![\w'’])(I|we|you|he|she|they|je|j'|nous|vous|il|elle|on|ils|elles)\s+(?:\w+\s+){0,2}?" + re.escape(v0) + r"\b", u["text"], re.I)
                if m:
                    ln["subject"], ln["subject_from"] = m.group(1), "the pronoun right before the verb in the same unit"
            # R7f. 'it is important to give credit': an expletive 'it' / 'il' / 'c'' does not do the infinitive
            sj7 = ln["subject"].replace("(inh)", "").strip().lower().replace("’", "'")
            expl_ok = sj7 in ("c'", "ce", "ça") or \
                (sj7 == "it" and re.search(r"\bit\s+(is|was|would be|will be|'s|seems|makes)\b", row["text"], re.I)) or \
                (sj7 == "il" and re.search(r"\bil\s+(faut|fallait|faudrait|est|était|serait)\s+(\w+\s+)?(de|d'|que)?", row["text"].replace("’", "'"), re.I) and
                 re.search(r"\bil\s+(faut|fallait|faudrait)\b|\bil\s+(est|était|serait)\s+\w+\s+(de|d')", row["text"].replace("’", "'"), re.I))
            if OPT["r7_expletive_inf"] and expl_ok and \
                    (ln["verb"].lower().startswith("to ") or word_tag(pieces_all[k], (ln.get("verb_as_written") or ln["verb"]).split()[-1]) in ("VINF", "VB")) and \
                    (("(inh)" in ln["subject"]) or "the subject of the clause" in (ln.get("subject_from") or "") or ln["verb"].lower().startswith("to ")) and \
                    not re.search(r"\b(it|il)\s+(\w+\s+){0,2}" + re.escape(ln["verb"].split()[-1]) + r"\b", u["text"], re.I):
                ln["subject"], ln["subject_from"] = "(unstated)", "an infinitive after 'it is ...' / 'il faut' / 'c'est ...': who does it is not in the words"
        # R7j. a modal or auxiliary alone, or 'il est' left hanging (a false start): not a claim
        if OPT["r7_bare_aux"]:
            keep = []
            for ln in u["lines"]:
                vw = ln["verb"].lower().replace("’", "'").split()
                bare_modal = len(vw) == 1 and vw[0] in ("can", "could", "will", "would", "shall", "should", "may", "might", "must", "pourra", "peut", "doit")
                bare_pass = vw in (["a", "été"], ["ont", "été"], ["avait", "été"], ["has", "been"], ["have", "been"])
                after = _after_verb(u["text"], ln["verb"], ln["subject"])
                hanging = len(vw) == 1 and vw[0] in COPULAS and after is not None and not after.strip(" ,.;:-–—…")
                if not ln["object"].strip() and (bare_modal or bare_pass or hanging) and not ln.get("implied_verb"):
                    continue
                keep.append(ln)
            u["lines"] = keep
        # F. (tested; off) 'a grants program | to help ...': the noun phrase at the end of the unit before does the to-verb
        if OPT["r6_purpose_np"] and lang == "en" and k > 0 and re.match(r"^\W*to\s+\w", u["text"], re.I):
            jr = joined_by(k, rels)
            prev_lines = units[k - 1]["lines"]
            if jr and jr["shared"] in ("elaboration", "purpose") and prev_lines:
                po = prev_lines[-1]["object"].strip()
                po = re.sub(r"^(on|with|about|upon)\s+", "", po, flags=re.I)
                if po and DETS_START.match(po) or (po and po[:1].isupper()):
                    for ln in u["lines"]:
                        if (ln.get("subject_from") or "").startswith(f"unit {k - 1}"):
                            ln["subject"], ln["subject_from"] = po, f"unit {k - 1}: the noun phrase just before the to-clause does it"


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
    if OPT["units_only"] and OPT["bare_lines"]:
        for u, ps in zip(units, pieces_all):
            if not u["lines"] and ps and has_verb(ps) and not SUBORD_START.match(u["text"].lower().replace("’", "'")):
                b = bare_line(ps, row["lang"])
                if b and b["verb"]:
                    u["lines"].append(b)
    ULEAVES = [unit_leaves(ps) for ps in pieces_all]
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
                expand_contractions(ln, u["text"])
            if OPT["units_only"] and OPT["better_object"]:
                better_object(ln, ULEAVES[u["unit"]])
                move_particle(ln, ULEAVES[u["unit"]])
            if is_address(ln["object"]):
                ln["object"], ln["how"] = "", (ln["how"] + "; someone spoken to is not the object").strip("; ")
            if row["lang"] == "fr":
                m = re.match(r"^(je|j'|tu|il|elle|on|nous|vous|ils|elles)\s+(?=\S)", ln["verb"].replace("’", "'"), re.I)
                if m and (not ln["subject"].strip() or ln["subject"].strip().lower() == m.group(1).lower()):
                    ln["subject"] = ln["subject"].strip() or ln["verb"][:len(m.group(1))]
                    ln["verb"] = ln["verb"][m.end():]
        u["lines"] = [l for l in u["lines"] if not any(re.search(rx, u["text"], re.I) and l["verb"].lower().split()[-1:] == [vb] for rx, vb in IDIOMS)]
        for ln in u["lines"]:
            if ln["object"].strip() in ("ce (que)", "ce (qu')") and re.search(r"(jusqu'|jusqu’|à|de|pour|parce) ce qu", u["text"].lower()):
                ln["object"], ln["how"] = "", (ln["how"] + "; 'ce que' is part of the conjunction").strip("; ")
    if OPT["units_only"] and OPT["apposition"]:
        for u in units:
            for leaf, name, desc, whole in unit_appositions(pieces_all[u["unit"]]):
                if OPT["r7_list_not_appos"] and desc[:1].isupper() and name[:1].isupper() and not re.match(r"^(the|a|an|le|la|les|l'|un|une)\s+[a-zà-ÿ]", desc, re.I) \
                        and re.search(re.escape(desc) + r"\s*,\s*(and\s+|et\s+)?[A-ZÀ-Ý]", u["text"]):
                    continue                            # 'the Lung Association, the Heart and Stroke Foundation, Cancer Care Ontario': a list
                if is_address(desc):                                        # 'Bill 87, Speaker,': someone spoken to
                    for ln in u["lines"]:
                        if re.search(r",\s*" + re.escape(desc) + r"\W*$", ln["object"]):
                            ln["object"] = re.sub(r",\s*" + re.escape(desc) + r"\W*$", "", ln["object"])
                            ln["how"] = (ln["how"] + "; the form of address after the comma is not part of the object").strip("; ")
                    continue
                for ln in u["lines"]:
                    if ln["subject"].replace("(inh)", "").strip().replace(" ,", ",").rstrip(",") in (whole, name + ", " + desc, name + " " + desc):
                        ln["subject"] = name
                u["lines"].append({"subject": name, "verb": "is (apposition)", "object": desc, "kind": "asserted", "negated": False, "hedged": False,
                                   "how": "apposition in the unit's tree: the phrase after the comma renames the name", "leaf": leaf, "subject_from": "", "implied_verb": True})
                u["lines"].sort(key=lambda l: l.get("leaf") if l.get("leaf") is not None else 10 ** 6)
    if OPT["units_only"] and OPT["bare_lines"]:
        for u in units:
            m = re.match(r"^\W*(by|en)\s+([\w'’-]+(?:ing|ant))\b\s*(.*)$", u["text"], re.I)
            if m and not u["lines"] and not has_verb(pieces_all[u["unit"]]):
                g = next((gi for gi, w, _ in ULEAVES[u["unit"]] if w.lower() == m.group(2).lower()), None)
                u["lines"].append({"subject": "", "verb": m.group(2), "object": m.group(3).strip(" .,;:"), "kind": "asserted", "negated": False,
                                   "hedged": False, "how": f"means ({m.group(1).lower()} + -ing / -ant): the parser read the verb as a noun", "leaf": g})
    # 'qu'est-ce qui justifie la difference' (what justifies the difference): the French tree rules read the question
    # word as a clause of its own (qu' | est | -ce) and give '-ce' as the subject; it is one word, qu'est-ce, = what
    if row["lang"] == "fr":
        for u in units:
            low = u["text"].lower().replace("’", "'")
            if "qu'est-ce" not in low and "qu'est -ce" not in low:
                continue
            u["lines"] = [l for l in u["lines"] if not (l["subject"].lower().replace("’", "'") in ("qu'", "que") and l["verb"].lower() == "est"
                                                         and l["object"].lower().strip() in ("-ce", "ce"))]
            for l in u["lines"]:
                if l["subject"].strip() in ("-ce", "ce"):
                    l["subject"] = "qu'est-ce"
                    l["how"] = (l["how"] + "; qu'est-ce qui = what (one question word)").strip("; ")
    # questions are not claims
    if OPT["questions"] and units and is_question_sentence(row["text"]):
        for u in units:
            u["question"] = True
            u["lines"] = []
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
                vw = ln["verb"].lower().replace("’", "'")
                last = vw.split()[-1] if vw.split() else ""
                m2 = re.search(r"(^|\s|')" + re.escape(last) + r"\s+(pas|plus|jamais|rien|guère|point)\b", low) if last else None
                if has_ne and m2 and not re.search(r"\b(pas|jamais|plus|guère|point|rien)\b", vw):
                    ln["verb"] = ln["verb"] + " " + m2.group(2); ln["negated"] = True
                    vw = ln["verb"].lower().replace("’", "'")
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
                               "hedged": False, "how": "apposition: the phrase after the comma renames the name", "leaf": pos, "subject_from": "", "implied_verb": True})
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
                              + (f"; {span(main)} {agree('frames', main)} {span(R if main == L else L)} (the setting is the main part)"
                                 if main and x["relation"] == "frame" else       # French 'frame': the main part is the setting ('L'an dernier')
                                 f"; {span(R if main == L else L)} {agree(MEANING.get(sh, 'is related to'), R if main == L else L)} {span(main)}" if main else "")})
    if OPT["units_only"] and OPT["apposition"] and OPT["apposition_across"]:
        for r in rels:
            k = r["right"][0]
            if r["shared"] == "elaboration" and r["left"] == [k - 1, k - 1] and r["right"] == [k, k] and not units[k]["lines"] and not units[k - 1]["lines"]:
                a, b = lone_np(pieces_all[k - 1]), lone_np(pieces_all[k])
                if a is not None and b is not None and has_name(a) and not has_name(b) and not is_address(units[k - 1]["text"]) \
                        and not units[k - 1]["text"].rstrip().endswith(":") and not is_address(P.text(b)):   # 'M. Brassard:' names who speaks
                    units[k]["lines"].append({"subject": np_text(a), "verb": "is (apposition)", "object": P.text(b), "kind": "asserted", "negated": False,
                                              "hedged": False, "how": f"apposition across units: unit {k} renames the name in unit {k - 1} (elaboration)",
                                              "leaf": None, "fixed_from": f"unit {k - 1} (apposition, elaboration)", "implied_verb": True})
    if OPT["units_only"]:
        round6_pre(row, units)
    if OPT["said_object"]:
        for u in units:
            for ln in u["lines"]:
                speech = any(w in SPEECH_WORDS or w.rstrip("s") in SPEECH_WORDS for w in ln["verb"].lower().split())
                if ln["object"] or not (speech or (OPT["units_only"] and ln is u["lines"][-1])):
                    continue
                for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
                    if r["shared"] != "attribution":
                        continue
                    sayer, said = attribution_sides(r, units, row["lang"]) if OPT["units_only"] else \
                        ((r["left"] if r["main"] == r["right"] else r["right"]), r["main"]) if r["main"] is not None else (None, None)
                    k_ = u["unit"]
                    aside = k_ > 0 and units[k_ - 1]["text"].rstrip().endswith(",") and u["text"].rstrip().endswith(",") and len(u["text"].split()) <= 4
                    if aside:                       # 'qui, je constate, a choisi': an aside between commas reports nothing
                        break
                    if sayer and sayer[0] <= u["unit"] <= sayer[1]:
                        ln["object"] = " ".join(v["text"] for v in units[said[0]:said[1] + 1]).strip(" “”\"«».")
                        ln["object_from"] = f"discourse: what is said, {span(said)}"
                        break
    # subjects across units: a line without a subject takes the subject of the main part of the smallest relation
    # that attaches its unit to another one
    for u in units:
        for ln in u["lines"]:
            ln["subject_from"] = ln.pop("fixed_from", "")              # set by a rule that already read it from another unit
            s0 = ln["subject"].replace("(inh)", "").strip()
            lp = leaf_paths[ln["leaf"]] if ln.get("leaf") is not None and ln["leaf"] < len(leaf_paths) else None
            first = re.split(r"[\s']", s0.lower())[0] if s0 else ""
            starts_rel = u["unit"] > 0 and u["text"].lower().startswith(first) and not re.search(r"[,.;:!?]\s*$", units[u["unit"] - 1]["text"]) if first else False
            is_rel = (s0.lower() in RELPRON and (s0.lower() not in DEMONSTR or starts_rel)) or (first in RELPRON and len(s0.split()) > 1 and first != "that")
            if OPT["time_subject"] and lp and is_time_phrase(s0):
                got = time_subject(lp)
                if got:
                    ln["subject"], ln["subject_from"] = got[0], f"unit tree: '{got[1]}' is when, not who; the subject is the noun phrase after it"
                    ln.setdefault("context", []).append(f"{got[1]} (time, unit {u['unit']})")
                    continue
            jr = joined_by(u["unit"], rels)
            w0 = s0.lower() or (re.split(r"\s+", u["text"].lower().strip(" ,"))[0] if ln is u["lines"][0] else "")
            if OPT["relpron"] and OPT["units_only"] and (w0 in ("which", "ce qui", "ce que", "ce qu'") or u["text"].lower().startswith(("ce qui", "ce que"))) and jr and \
                    (jr["shared"] in POINT_C or ln["object"].lower().startswith(("why", "the reason"))):
                L = jr["left"]
                ln["refers_to"] = f"{span(L)}: " + " ".join(v["text"] for v in units[L[0]:L[1] + 1])
                ln["subject"] = ln["subject"] or "which"
                ln["subject_from"] = f"'{ln['subject']}' stands for the whole of {span(L)} ({jr['shared']})"
                continue
            if OPT["relpron"] and OPT["units_only"] and is_rel:
                got = resolve_relative(u, s0, lp, rels, pieces_all)
                if got:
                    ln["subject"], ln["subject_from"] = got
                    continue
            if OPT["relpron"] and not OPT["units_only"] and (s0.lower() in RELPRON or (first in RELPRON and len(s0.split()) > 1 and first != "that")) and lp:
                a = antecedent(lp)
                if a:
                    ln["subject"], ln["subject_from"] = a, f"sentence tree: '{s0.split()[0]}' stands for the noun before it"
                    continue
            if OPT["demonstrative"] and s0.lower() in DEMONSTR:
                for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
                    L, R = r["left"], r["right"]
                    if s0.lower() in ("c'", "ce") and r["shared"] not in POINT_C:
                        continue
                    if R[0] <= u["unit"] <= R[1]:           # it points back, to what came before it
                        other = L
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
                g0 = got[0].lower().strip()
                if OPT["relpron"] and OPT["units_only"] and g0 in RELPRON and g0 not in DEMONSTR:
                    # the clause's subject is itself 'qui' / 'who': what it stands for, from the unit tree or the discourse parse
                    rel = resolve_relative(u, got[0], lp, rels, pieces_all)
                    if rel:
                        ln["subject"], ln["subject_from"] = rel
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
                core = main_units(other, rels, u["unit"], units, row["lang"])
                pool = [(v, l2) for i in core for v in [units[i]] for l2 in v["lines"] if good_source(l2)]
                if other[1] < u["unit"]:
                    pool = pool[::-1]                   # in the main part, the nearest clause before this one
                pool += [(v, l2) for v in units[other[0]:other[1] + 1] if v["unit"] not in core for l2 in v["lines"] if good_source(l2)]
                if pool:
                    v, l2 = pool[0]
                    ln["subject"], ln["subject_from"] = l2["subject"].replace("(inh)", "").strip(), f"unit {v['unit']} ({r['shared']})"
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
    if OPT["units_only"]:
        for u in units:
            ul = ULEAVES[u["unit"]]
            low = " " + u["text"].lower().replace("’", "'") + " "
            for ln in u["lines"]:
                # D1. 'the right thing to do', 'it makes economic sense to do so': an infinitive on the noun right before it,
                # with no object of its own, is not done by that noun
                if ln["verb"].lower().startswith("to ") and ln["subject"] not in ("", "(unstated)") and "(inh)" not in ln["subject"] and \
                        (not ln.get("subject_from") or "a clause on a noun" in ln.get("subject_from", "")):
                    sj = ln["subject"].lower().replace("’", "'")
                    vw = ln["verb"].lower().split()
                    at = low.find(" " + sj + " " + " ".join(vw[:2]) + " ") if len(vw) >= 2 else -1
                    if at < 0 and len(vw) >= 2:
                        at = low.find(" " + sj + " " + " ".join(vw[:2]))
                    before = low[:at].split()[-1:] if at >= 0 else []
                    if at >= 0 and not any(b.startswith(st) for b in before for st in CONTROL_STEMS) and \
                            not any(inf_vp_has_object(pth) for pth in verb_paths(ln, ul)):
                        ln["subject"], ln["subject_from"] = "(unstated)", "an infinitive on the noun before it with no object of its own ('the right thing to do'): who does it is not in the words"
                # R. object relatives: 'the resources | that they need', 'des dommages | que le ministre veut éviter'
                if not ln["object"] and ln["subject"] and ln["subject"].lower() not in RELPRON:
                    m = re.match(r"^\W*(that|which|whom|que|qu')\s*", u["text"].lower().replace("’", "'"))
                    a = None
                    if m and u["unit"] > 0 and not re.search(r"[,;:]\s*$", units[u["unit"] - 1]["text"]):
                        jr = joined_by(u["unit"], rels)
                        tg = word_tag(pieces_all[u["unit"]], m.group(1))
                        passive = bool(re.search(r"\b(be|been|being|is|are|was|were|am)\b(\s+\w+)*\s+\w+(ed|en)$", ln["verb"].lower()))
                        prev_head = (re.findall(r"\w+", units[u["unit"] - 1]["text"].lower()) or [""])[-1]
                        english_ok = tg in REL_TAGS or (tg in ("IN", "DT") and not passive and prev_head not in CONTENT_NOUNS)
                        if jr and jr["shared"] in ("elaboration", "same-unit") and (row["lang"] == "fr" or english_ok):
                            got = antecedent_by_discourse(u["unit"], rels, pieces_all)
                            a = (got[0], f"object relative: '{m.group(1)}' stands for the last noun phrase of {got[1]} (discourse: {got[2]})") if got else None
                    if a and a[0].lower().strip() not in NOT_ANTECEDENT and _norm(a[0]) != _norm(ln["subject"]):
                        ln["object"], ln["object_from"] = a
                # N. an infinitive or gerund with no subject anywhere: say so
                if not ln["subject"].strip():
                    vw0 = (ln.get("verb_as_written") or ln["verb"]).split()[:1]
                    t0 = word_tag(pieces_all[u["unit"]], vw0[0]) if vw0 else ""
                    if ln["verb"].lower().startswith("to ") or t0 in ("VINF", "VBG", "VPR"):
                        ln["subject"], ln["subject_from"] = "(unstated)", "an infinitive or gerund with no subject in the words"
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
    if OPT["units_only"]:
        round6(row, units, rels, pieces_all, ULEAVES)
    # a unit with no clause of its own ("L'an dernier,", "In 1994,") is context for the lines on the other side of its
    # relation: it is attached to them rather than lost
    if OPT["frame_context"]:
        for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
            if r["shared"] not in FRAMES:
                continue
            for side, other in ((r["left"], r["right"]), (r["right"], r["left"])):
                us = units[side[0]:side[1] + 1]
                if side[0] == side[1] and not us[0]["lines"] and not us[0].get("question") and not us[0].get("context_used") \
                        and not has_clause(pieces_all[side[0]]) and not is_address(us[0]["text"]):
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
        for ln in u["lines"]:
            if OPT["units_only"] and row["lang"] == "en" and re.match(r"^to\s+\S", ln["verb"], re.I):
                ln["verb"], ln["infinitive"] = ln["verb"][3:].strip(), True      # 'to accept' -> accept (infinitive)
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
