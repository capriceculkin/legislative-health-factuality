"""All three parses together (proposed in the Oct 8 meeting): keep a predication when at least two of the syntactic parses produce it
(spaCy dependency, Stanza dependency, constituency), then use the discourse (RST) parse to decide how each one is
used in the sentence: stated, embedded (condition, time, purpose, relative clause) or reported (attribution)."""
import json, sys, collections, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preds as P
import lexicon as X   # PARITY_V6
import gold as g1, gold2 as g2
KEY = {**g1.G, **g2.G2}
DISC = {d['n']: d for d in json.load(open(os.path.join(HERE, 'discourse.json'), encoding='utf-8'))['rows']}
FR_CONST = None                                   # filled in when the French constituency trees arrive (French Treebank)
SUBORD = tuple(sorted(X.both(X.TIME_FIRST)))
REL = tuple(sorted(X.both(X.REL)))


def run(r, PP=P):
    """All three methods on one saved row (same as load.run)."""
    out = {}
    tk = [PP.T(*x) for x in r["deps_spacy"]]; PP.link_kids(tk)
    out["spacy"] = PP.from_dependencies(tk)
    st, words = [], []
    for sent in r["deps_stanza"]:
        tk = [PP.T(*x) for x in sent]; PP.link_kids(tk); off = len(words)
        for p in PP.from_dependencies(tk):
            p["at"] += off; st.append(p)
        words += [t.text for t in tk]
    out["stanza"] = st
    co, n_words = [], 0
    for tree in r.get("trees", []):
        root = PP.parse_tree(tree) if isinstance(tree, str) else tree
        for p in PP.from_constituency(tree, r["lang"]):
            p["at"] += n_words; co.append(p)
        n_words += len(PP.leaves(PP._tuples(root) if not isinstance(root, tuple) else root))
    out["const"] = co
    return out


def as_key(p):
    return (p["subject"], p["verb"], p["object"], p["kind"], "negated" if p["negated"] else "")


def same(p, q):
    return P.matches(as_key(p), q) or P.matches(as_key(q), p)


def vote(outs, methods, need=2):
    agreed, review, used = [], [], {m: set() for m in methods}
    for i, m in enumerate(methods):
        for a, p in enumerate(outs[m]):
            if a in used[m]:
                continue
            group = [(m, a)]
            for m2 in methods[i + 1:]:
                b = next((b for b, q in enumerate(outs[m2]) if b not in used[m2] and same(p, q)), None)
                if b is not None:
                    group.append((m2, b))
            for mm, x in group:
                used[mm].add(x)
            rec = dict(p, found_by=[mm for mm, _ in group], at_by={mm: outs[mm][x]["at"] for mm, x in group})
            if len(group) >= 3:                         # V6B: the label and the hedge are the majority's, not the first parser's
                mem = [outs[mm][x] for mm, x in group]
                for f in ("kind", "hedged"):
                    vals = [q[f] for q in mem]
                    top = max(set(vals), key=vals.count)
                    if vals.count(top) >= 2 and top != rec[f]:
                        rec[f] = top
                        if f == "kind":
                            rec["how"] = next(q["how"] for q in mem if q["kind"] == top) + " (majority of the parsers)"
            (agreed if len(group) >= need else review).append(rec)
    return agreed, review


def offsets(rows_of_tokens):
    """Character offset of every token, from the saved token text and trailing space."""
    s, offs = "", []
    for t in rows_of_tokens:
        offs.append(len(s)); s += t[1] + t[7]
    return offs, s


def edu_of(off, edus):
    for i, e in enumerate(edus):
        if e["start"] <= off < e["end"] or (i == len(edus) - 1 and off >= e["start"]):
            return i
    return None


SELF = tuple(sorted(X.both(X.SELF)))
SOURCE_WORDS = tuple(sorted(X.both(X.SPEECH) | X.both(X.SOURCE_EXTRA)))


def edu_roles(d):
    """For every EDU: the RST relations in which it sits on the satellite side, and the attribution nuclei.
    An attribution counts as 'reported' only when someone else is the source (my friends say, research tells us,
    the report recommends); 'vous savez', 'I think', 'we know' are the speaker's own framing; 'ensuring that'
    is a complement, not a source."""
    sat, attributed = collections.defaultdict(list), {}
    for rel in d["relations"]:
        (a, b), (c, e) = rel["left"], rel["right"]
        nuc = rel["nuclearity"]
        left, right = range(a, b + 1), range(c, e + 1)
        if nuc == "NS":
            for i in right: sat[i].append(rel["relation"])
        elif nuc == "SN":
            for i in left: sat[i].append(rel["relation"])
        if rel["relation"] == "attribution":
            # V6B: the source side is found by its words (said / dit, according to / selon, I / je), not by nuclearity.
            # English RST-DT gives "The minister said | that ..." as SN; the French data gives "Le ministre a dit | que ..."
            # as NS, so reading the satellite as the source turned the French speech verb itself into the claim.
            def side(rng):
                words = [w.strip(",.;:\"“”«»()") for w in " ".join(d["edus"][i]["text"] for i in rng).lower().split()]
                own = bool(words) and (words[0] in SELF or words[0][:2] in ("j'", "j’"))
                src = any(w in SOURCE_WORDS or w in P.SOURCE_PREP for w in words)
                return own, src
            (lo, ls), (ro, rs) = side(left), side(right)
            if (ls or lo) and not (rs or ro):
                src, content, own = left, right, lo
            elif (rs or ro) and not (ls or lo):
                src, content, own = right, left, ro
            else:
                continue                                     # no clear source, or both sides: the syntax decides
            if own:
                continue                                     # the speaker's own framing: keep the parser's reading
            for i in content:
                attributed[i] = "reported"
    return sat, attributed


def rst_kind(p, i, d, sat, attributed):
    """The discourse parse's reading of how predication p (in EDU i) is used."""
    if i is None:
        return p["kind"], "no unit"
    edu = d["edus"][i]["text"].strip().lstrip("“\"«(").lower()
    first = edu.split(" ")[0] if edu else ""
    rels = sat.get(i, [])
    if p["kind"] != "asserted":
        return p["kind"], "parser's reading kept (only a stated line can be re-read)"
    if i in attributed:
        return attributed[i], ("attribution (someone else is the source)" if attributed[i] == "reported" else "complement of an attribution verb")
    for r in rels:
        if r == "condition":
            return "embedded", "condition"
        if r in ("temporal", "background", "frame", "circumstance") and (first in SUBORD or first.startswith(("lorsqu", "quand"))):
            return "embedded", f"{r} ({first})"
        if r in ("purpose", "enablement") and first in X.both(X.PURPOSE):
            return "embedded", f"{r} ({first})"
        if r in ("elaboration", "e-elaboration") and (first in REL or edu.startswith(("in which", "of which", "for which"))):
            return "embedded", "relative clause (elaboration)"
    return p["kind"], "parser's reading kept"


def combine(r, need=2):
    if r["lang"] == "fr" and FR_CONST and str(r["n"]) in FR_CONST:
        r = dict(r, trees=FR_CONST[str(r["n"])])
    out = run(r, P)
    ms = ["spacy", "stanza"] + (["const"] if r["lang"] == "en" or r.get("trees") else [])
    agreed, review = vote(out, ms, need=need)
    d = DISC.get(r["n"])
    so, _ = offsets(r["deps_spacy"])
    st = [t for sent in r["deps_stanza"] for t in sent]
    sto, _ = offsets(st)
    sat, attributed = edu_roles(d) if d else ({}, set())
    for p in agreed + review:
        off = None
        if "spacy" in p["at_by"] and p["at_by"]["spacy"] < len(so):
            off = so[p["at_by"]["spacy"]]
        elif "stanza" in p["at_by"] and p["at_by"]["stanza"] < len(sto):
            off = sto[p["at_by"]["stanza"]]
        first = p["verb"].split(" ")[0] if p["verb"] else ""
        hits = [k for k in range(len(r["text"])) if r["text"].startswith(first, k)] if first else []
        if hits:
            before = [k for k in hits if off is None or k <= off]
            off = max(before) if before else min(hits)       # "say repeal": place it at "say", not at "repeal"
        i = edu_of(off, d["edus"]) if (d and off is not None) else None
        p["edu"] = i
        p["edu_text"] = d["edus"][i]["text"] if i is not None else ""
        p["kind_parser"] = p["kind"]
        p["kind_rst"], p["rst_why"] = rst_kind(p, i, d, sat, attributed) if d else (p["kind"], "no discourse parse")
    return ms, agreed, review


def load_rows():
    return json.load(open(os.path.join(HERE, 'pc.json'), encoding='utf-8'))['rows']


def evaluate(need=2):
    rows = load_rows()
    res = collections.defaultdict(collections.Counter)
    detail = []
    for r in rows:
        n = r["n"]
        if n not in KEY:
            continue
        ms, agreed, review = combine(r, need)
        gold = KEY[n]
        al = P.align(gold, agreed)
        L = r["lang"]
        res[L]["key"] += len(gold); res[L]["found"] += sum(a is not None for a in al)
        res[L]["produced"] += len(agreed); res[L]["produced_in_key"] += len({a for a in al if a is not None})
        for g, a in zip(gold, al):
            if a is None:
                continue
            p = agreed[a]
            gk = "asserted" if g[3] == "asserted" else "not asserted"
            pk = "asserted" if p["kind_parser"] == "asserted" else "not asserted"
            rk = "asserted" if p["kind_rst"] == "asserted" else "not asserted"
            res[L]["kind_pairs"] += 1; res[L]["kind_parser_ok"] += pk == gk; res[L]["kind_rst_ok"] += rk == gk
            res[L]["kind3_parser_ok"] += p["kind_parser"] == g[3]; res[L]["kind3_rst_ok"] += p["kind_rst"] == g[3]
            if p["kind_parser"] != p["kind_rst"]:
                detail.append((n, L, g[:4], p["kind_parser"], p["kind_rst"], p["rst_why"], p["edu_text"]))
        res[L]["methods"] = len(ms)
    return res, detail


if __name__ == "__main__":
    for need in (2, 1):
        res, detail = evaluate(need)
        print(f"== keep a predication found by at least {need} parse(s)")
        for L in ("en", "fr"):
            c = res[L]
            print(f"  {L}: key lines found {c['found']}/{c['key']}, produced {c['produced']} of which in key {c['produced_in_key']}; "
                  f"asserted-or-not right: parser {c['kind_parser_ok']}/{c['kind_pairs']}, with discourse {c['kind_rst_ok']}/{c['kind_pairs']}; "
                  f"exact kind: parser {c['kind3_parser_ok']}, with discourse {c['kind3_rst_ok']}")
        if need == 2:
            for x in detail:
                print("   changed by discourse:", x[0], x[1], "|", " | ".join(x[2][:3]), "| key:", x[2][3], "| parser:", x[3], "-> rst:", x[4], "(", x[5], ")")
