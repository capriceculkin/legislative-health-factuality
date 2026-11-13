"""design2.py RULES PARSES   Scores the one-backbone design on the same saved parses as the current design.

Design 1 (now): three parsers make lines; a line is kept when two of the three agree (combine_lib.vote).
Design 2 (proposal): every line comes from one parse (Stanza dependency, UD labels in both languages). The other
two parses do not vote; each Stanza line gets a confidence: how many of the two checks have the same line.
  2a  all backbone lines kept (confidence reported, nothing dropped)
  2b  backbone lines kept when at least one check agrees (the others go to review)
Both get the same discourse re-read and appositions as design 1. Scored per language on the test pairs,
the held-out key and the 100-sentence key: found, produced, label right, precision."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parity_score as S
import parallel_tests as PT, gold_heldout as GH
P, C = S.load_rules(sys.argv[1])
rows = json.load(open(sys.argv[2], encoding="utf-8"))["rows"]


def design2(row):
    text, lang = row["text"], row["lang"]
    if text.endswith("?") or len(text.split()) < 3:
        return {"2a": [], "2b": [], "d1": []}
    r = {"n": row["n"], "lang": lang, "text": text, "deps_spacy": row["deps_spacy"], "deps_stanza": row["deps_stanza"], "trees": row.get("trees", [])}
    out = C.run(r, P)
    checks = [m for m in ("spacy", "const") if m != "const" or r["trees"]]
    back = []
    for p in out["stanza"]:
        conf = [m for m in checks if any(C.same(p, q) for q in out[m])]
        back.append(dict(p, found_by=["stanza"] + conf, at_by={"stanza": p["at"]}, confidence=len(conf)))
    d = row.get("disc_native")
    if not S.needs_rst("multi", text, [b for b in back if b["confidence"]], S.speech_words(P, C)):
        d = None
    S.apply_rst(P, C, back, [], r, d)
    apps = []
    for sent in row["deps_stanza"]:
        toks = [P.T(*x) for x in sent]; P.link_kids(toks)
        apps += [dict(a, kind="asserted", hedged=False, negated=False) for a in P.appositions(toks)]
    fin = lambda L: [dict(p, kind=p["kind_rst"]) for p in L] + apps
    d1 = S.analyze(P, C, row, "native", "prod", "multi")["final"]
    return {"2a": fin(back), "2b": fin([b for b in back if b["confidence"] >= 1]), "d1": d1}


tot = collections.defaultdict(collections.Counter)
tests = {t["id"]: t for t in PT.T}
passes = collections.defaultdict(collections.Counter)
for row in rows:
    res = design2(row)
    if row["set"] == "test":
        t = tests[row["key_n"]]; gold = t[row["lang"]]["lines"]
        for k, L in res.items():
            c = S.score(P, gold, L, t["hedge_check"])
            ok = (not L) if not gold else (c.get("all_right", 0) == len(gold) and c.get("extra", 0) == 0)
            passes[row["lang"]][k] += ok
        continue
    gold = (C.KEY if row["set"] == "sample" else GH.GH)[row["key_n"]]
    for k, L in res.items():
        tot[(row["set"], row["lang"], k)].update(S.score(P, gold, L))
print("design   test pairs passed (of 45)")
for k in ("d1", "2a", "2b"):
    print(f"  {k}:  EN {passes['en'][k]}  FR {passes['fr'][k]}")
for st in ("heldout", "sample"):
    print(f"\n{st}: found/key  produced  precision  label right")
    for L in ("en", "fr"):
        for k in ("d1", "2a", "2b"):
            c = tot[(st, L, k)]
            print(f"  {L} {k}: {c['found']}/{c['key']}  p{c['produced']}  {c['found'] / max(1, c['produced']):.0%}  label {c['label']}/{c['found']}")
