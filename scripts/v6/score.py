"""score.py DIR  Scores the rule files in DIR on the 100-sentence key, per language: each parser alone, the vote,
what the vote leaves for review, the stated/embedded/reported label, negation and hedging. Prints JSON."""
import sys, os, json, collections
D = os.path.abspath(sys.argv[1]); sys.path.insert(0, D)
os.chdir(D)
import combine_lib as C, preds as P
C.FR_CONST = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fr_trees.json")))["trees"]
R = collections.defaultdict(collections.Counter)
for r in C.load_rows():
    if r["n"] not in C.KEY:
        continue
    L, gold = r["lang"], C.KEY[r["n"]]
    rr = dict(r, trees=C.FR_CONST.get(str(r["n"]), [])) if L == "fr" else r
    out = C.run(rr, P)
    ms = ["spacy", "stanza"] + (["const"] if rr.get("trees") else [])
    for m in ms:
        al = P.align(gold, out[m]); k = f"{L}.{m}"
        R[k]["key"] += len(gold); R[k]["found"] += sum(a is not None for a in al); R[k]["produced"] += len(out[m])
        for g, a in zip(gold, al):
            if a is not None:
                R[k]["kind_ok"] += out[m][a]["kind"] == g[3]
    ms2, agreed, review = C.combine(rr)
    al = P.align(gold, agreed); k = f"{L}.vote"
    R[k]["key"] += len(gold); R[k]["found"] += sum(a is not None for a in al); R[k]["produced"] += len(agreed)
    for g, a in zip(gold, al):
        if a is None:
            continue
        p = agreed[a]; note = (g[4] if len(g) > 4 else "") or ""
        R[k]["kind_ok"] += p["kind_rst"] == g[3]; R[k]["kind_parser_ok"] += p["kind_parser"] == g[3]
        gh = "hedged" in note and "not hedged" not in note
        R[k]["hedge_ok"] += bool(p["hedged"]) == gh; R[k]["hedge_key"] += gh; R[k]["hedge_out"] += bool(p["hedged"])
        R[k]["kind_key_" + g[3]] += 1; R[k]["kind_hit_" + g[3]] += p["kind_rst"] == g[3]
    have = {a for a in al if a is not None}
    al1 = P.align(gold, agreed + review)
    R[f"{L}.review"]["produced"] += len(review)
    R[f"{L}.review"]["new_key_lines"] += sum(1 for a, b in zip(al, al1) if a is None and b is not None)
print(json.dumps(R, indent=0, sort_keys=True))
