"""design2_full.py RULES PARSES UDPIPE [--json OUT]   The proposal, built end to end, on the same saved parses as design 1.

  1. One parse: Stanza dependency (UD labels in English and French). Every line and every frame comes from it.
  2. Check by structure: UDPipe 1.4 (UD 2.5 models, English EWT / French GSD), run on the backbone's own words, so the
     two parses are compared word by word. A line is "confirmed" when UDPipe gives the predicate and each of its core
     arguments (subject, object, indirect object, oblique, clausal complement) the same head and the same relation.
  3. Constituency as a boundary check only: an object span is "confirmed" when it is exactly a phrase of the
     constituency tree (Stanza for English, Berkeley for French). It never changes a line.
  4. Rules: the same v6b rules give each line; each line also gets a PropBank-style frame (ARG0, ARG1, ARG2, ARGM-NEG,
     ARGM-MOD, ARGM-TMP, ARGM-<preposition>) read from the same UD tree, with one mapping for both languages.
  5. Discourse: the same re-read as design 1.
Variants scored:  2a every backbone line   2c only lines the structure check confirms (the rest go to review)
Design 1 (three parsers, two-of-three vote) is scored beside them on the same input."""
import sys, os, json, collections, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parity_score as S
import parallel_tests as PT, gold_heldout as GH

ap = argparse.ArgumentParser()
ap.add_argument("rules"); ap.add_argument("parses"); ap.add_argument("udpipe"); ap.add_argument("--json")
a = ap.parse_args()
P, C = S.load_rules(a.rules)
X = P.X
rows = json.load(open(a.parses, encoding="utf-8"))["rows"]
UDP = json.load(open(a.udpipe, encoding="utf-8"))["rows"]

import frames as FR
frame, CORE = FR.make(P)


def base(d):
    return (d or "").split(":")[0]


def toks_of(sent):
    t = [P.T(*x) for x in sent]
    return P.link_kids(t)


def structure_check(st, ud, t):
    """Same head and same relation in both UD parses, for the predicate and each core argument."""
    arcs = [t] + [c for c in t.kids if c.dep in CORE]
    same = [(base(st[x.i].dep) == base(ud[x.i][4]) and st[x.i].head == ud[x.i][5]) for x in arcs]
    return all(same), sum(same), len(same)


def phrase_spans(tree):
    """Every phrase of a constituency tree as its text (the same text function the rules use)."""
    out = set()
    def go(n):
        if isinstance(n, str):
            return
        out.add(tuple(P.fold(" ".join(P.leaves(n)))))      # compared as word lists, so spacing and elision do not matter
        for k in n[1]:
            go(k)
    root = P.parse_tree(tree) if isinstance(tree, str) else P._tuples(tree)
    go(root)
    return out


def design2(row):
    text, lang = row["text"], row["lang"]
    if text.endswith("?") or len(text.split()) < 3:
        return {"2a": [], "2c": [], "d1": [], "info": collections.Counter(), "frames": []}
    info = collections.Counter()
    spans = set()
    for tr in row.get("trees", []):
        spans |= phrase_spans(tr)
    back, off = [], 0
    for si, sent in enumerate(row["deps_stanza"]):
        toks = toks_of(sent)
        ud = UDP[row["n"]][si]
        for p in P.from_dependencies(toks):
            t = toks[p["at"]]
            ok, k, n = structure_check(toks, ud, t)
            obj_ok = (not p["object"]) or (tuple(P.fold(p["object"])) in spans) if spans else None
            info["lines"] += 1; info["confirmed"] += ok; info["arcs"] += n; info["arcs_same"] += k
            if obj_ok is not None and p["object"]:
                info["objects"] += 1; info["objects_in_tree"] += bool(obj_ok)
            back.append(dict(p, at=p["at"] + off, found_by=["stanza"] + (["udpipe"] if ok else []), at_by={"stanza": p["at"] + off},
                             confirmed=ok, object_phrase=obj_ok, frame=frame(toks, t, dict(p, lang=lang))))
        off += len(toks)
    r = {"n": row["n"], "lang": lang, "text": text, "deps_spacy": row["deps_spacy"], "deps_stanza": row["deps_stanza"], "trees": row.get("trees", [])}
    d = row.get("disc_native")
    if not S.needs_rst("multi", text, [b for b in back if b["confirmed"]], S.speech_words(P, C)):
        d = None
    S.apply_rst(P, C, back, [], r, d)
    for b in back:
        b["frame"]["kind"] = b["kind_rst"]
    apps = []
    for sent in row["deps_stanza"]:
        apps += [dict(x, kind="asserted", hedged=False, negated=False, confirmed=True) for x in P.appositions(toks_of(sent))]
    fin = lambda L: [dict(q, kind=q["kind_rst"]) for q in L] + apps
    d1 = S.analyze(P, C, row, "native", "prod", "multi")["final"]
    return {"2a": fin(back), "2c": fin([b for b in back if b["confirmed"]]), "d1": d1, "info": info,
            "frames": [b["frame"] for b in back], "back": back}


tests = {t["id"]: t for t in PT.T}
tot = collections.defaultdict(collections.Counter)
passes = collections.defaultdict(collections.Counter)
info = collections.defaultdict(collections.Counter)
wrong_by_check = collections.defaultdict(collections.Counter)
examples = []
for row in rows:
    res = design2(row)
    L = row["lang"]
    info[L].update(res["info"])
    if row["set"] == "test":
        t = tests[row["key_n"]]; gold = t[L]["lines"]
        for k in ("d1", "2a", "2c"):
            c = S.score(P, gold, res[k], t["hedge_check"])
            ok = (not res[k]) if not gold else (c.get("all_right", 0) == len(gold) and c.get("extra", 0) == 0)
            passes[L][k] += ok
        if row["key_n"] in ("A2", "D1", "C1", "F4") and res["frames"]:
            examples.append((row["n"], row["text"], res["frames"]))
        continue
    gold = (C.KEY if row["set"] == "sample" else GH.GH)[row["key_n"]]
    for k in ("d1", "2a", "2c"):
        tot[(row["set"], L, k)].update(S.score(P, gold, res[k]))
    # is the structure check informative? lines it confirms vs lines it does not, against the key
    al = P.align(gold, res["2a"])
    hit = {i for i in al if i is not None}
    for i, q in enumerate(res["2a"]):
        if "confirmed" not in q or q.get("source") == "apposition":
            continue
        key = "confirmed" if q["confirmed"] else "not confirmed"
        wrong_by_check[(L, key)]["lines"] += 1; wrong_by_check[(L, key)]["in_key"] += i in hit
        if q.get("object") and q.get("object_phrase") is not None:
            k2 = "object is a phrase" if q["object_phrase"] else "object is not a phrase"
            wrong_by_check[(L, k2)]["lines"] += 1; wrong_by_check[(L, k2)]["in_key"] += i in hit

print("== test pairs passed, of 45")
for k, name in (("d1", "design 1 (vote)"), ("2a", "design 2a (backbone, all lines)"), ("2c", "design 2c (backbone, structure-confirmed)")):
    print(f"  {name:42s} EN {passes['en'][k]:2d}   FR {passes['fr'][k]:2d}")
for st in ("heldout", "sample"):
    print(f"\n== {st}: found/key   produced   share in key   right label")
    for L in ("en", "fr"):
        for k in ("d1", "2a", "2c"):
            c = tot[(st, L, k)]
            print(f"  {L} {k}: {c['found']:3d}/{c['key']:<3d}  p{c['produced']:<4d} {c['found'] / max(1, c['produced']):4.0%}   label {c['label']}/{c['found']}")
print("\n== the checks themselves (all 220 sentences)")
for L in ("en", "fr"):
    i = info[L]
    print(f"  {L}: {i['lines']} backbone lines; UDPipe confirms {i['confirmed']} ({i['confirmed'] / max(1, i['lines']):.0%}); "
          f"core arcs the same {i['arcs_same']}/{i['arcs']} ({i['arcs_same'] / max(1, i['arcs']):.0%}); "
          f"objects that are exactly a phrase of the tree {i['objects_in_tree']}/{i['objects']} ({i['objects_in_tree'] / max(1, i['objects']):.0%})")
print("\n== is each check informative? share of lines that are in the key (held-out + sample)")
for L in ("en", "fr"):
    for k in ("confirmed", "not confirmed", "object is a phrase", "object is not a phrase"):
        c = wrong_by_check[(L, k)]
        print(f"  {L} {k:24s} {c['in_key']}/{c['lines']}  {c['in_key'] / max(1, c['lines']):.0%}")
print("\n== example frames")
for n, txt, frs in examples:
    print(" ", n, txt)
    for f in frs:
        print("     ", f["predicate"], "|", f["kind"], "| hedged" if f["hedged"] else "", "|", "; ".join(f"{r[0]}: {r[1]}" for r in f["roles"]))
if a.json:
    json.dump({"passes": passes, "scores": {"|".join(k): v for k, v in tot.items()}, "checks": info,
               "check_informative": {"|".join(k): v for k, v in wrong_by_check.items()}}, open(a.json, "w"), indent=1, default=dict)
