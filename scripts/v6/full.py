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
        if len(mem) >= 2:                                  # the wording most of the parsers agree on, not just the first parser's
            for f in ("subject", "verb", "object"):
                vals = [q[f] for q in mem]
                top = max(set(vals), key=vals.count)
                if vals.count(top) >= 2 and top != rec[f]:
                    rec["notes"] = rec.get("notes", []) + [f"{f}: majority wording ({rec[f]!r} was the first parser's)"]
                    rec[f] = top
        rec.update(parts=[], links=[], notes=rec.get("notes", []), edu=p.get("edu"), source=None, head=None)
        if "apposition" in (p.get("verb") or ""):
            rec["source"] = "apposition"; lines.append(rec); continue
        at = p.get("at_by", {})
        if "stanza" in at and at["stanza"] in Swhere and method in ("vote", "stanza"):
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
            lines.append(rec); continue
        P._TOKS["toks"] = toks
        t = toks[wi]
        rec["head"] = (rec["source"], si, wi)
        chained = chain_tokens(t)
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
                part = {"role": role, "label": lab, "text": text, "tok": ti}
                if ft.split(" ")[0] in NEGW:
                    part["negated"] = True
                if not any(fold(q["text"]) == ft for q in rec["parts"]):
                    rec["parts"].append(part)
        lines.append(rec)
    own = {}
    for rec in lines:
        if rec["head"]:
            own.setdefault(rec["head"][:2], set()).add(rec["head"][2])
    for rec in lines:
        if rec["head"]:
            src, si, wi = rec["head"]
            toks = (SP if src == "stanza" else DP)[si]
            heads_here = own.get((src, si), set()) - {wi}
            rec["parts"] = [q for q in rec["parts"] if q.get("tok") not in heads_here]

    # links between lines: the nearest line above in the tree
    heads = {rec["head"]: i for i, rec in enumerate(lines) if rec["head"]}
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
            if j is not None:
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
        for q in r["parts"]:
            print(f"        {q['label']}: {q['text']}" + (" (inherited)" if q.get("inherited") else "") + (" [negated part]" if q.get("negated") else ""))
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
