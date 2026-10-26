"""edu_score.py RULES PARSES.json EDU_OUT.json

The discourse-first lines (edu_pipeline.py) against the same answer keys as the earlier designs, scored the same way
for every method: found = the vote's loose match test (preds.py align); exact = subject, verb and object word for word
(case and punctuation ignored). Keys: the 100-sentence sample and the held-out set (drafted with AI assistance, not a
gold standard) and the 45 simple test pairs. Plain python3."""
import sys, os, json, ast, collections
rules, parses, edu = sys.argv[1:4]
sys.argv = [sys.argv[0], rules, parses]
sys.path.insert(0, os.path.abspath(rules))
import full as F                 # noqa: E402
import compare3 as K             # noqa: E402
import combine_lib as C          # noqa: E402
import gold_heldout as GH        # noqa: E402
import parallel_tests as PT      # noqa: E402
P = F.P

rows = {r["n"]: r for r in json.load(open(parses, encoding="utf-8"))["rows"]}
E = {r["n"]: r for r in json.load(open(edu, encoding="utf-8"))["rows"]}
tests = {}
for t in PT.T:
    for L in ("en", "fr"):
        k = t[L]["lines"]
        tests[f"test|{t['id']}|{L}"] = ast.literal_eval(k) if isinstance(k, str) else k


def key_of(r):
    if r["set"] == "sample":
        return C.KEY.get(r["key_n"]) or []
    if r["set"] == "heldout":
        return GH.GH.get(r["key_n"]) or []
    return tests.get(r["n"]) or []


def lines(n, m):
    if m == "edu":
        return [dict(subject=l["subject"], verb=l["verb"], object=l["object"], negated=l["negated"], kind=l["kind"]) for l in E[n]["lines"]]
    return [dict(x, object=x["object"]) for x in K.as_lines(F.full_row(rows[n], method=m))]


nm = K.norm
METHODS = ("vote", "tree_plus", "edu")
NAMES = {"vote": "2-of-3 vote", "tree_plus": "tree + deps add", "edu": "discourse first"}
tot = collections.defaultdict(collections.Counter)
per = collections.defaultdict(lambda: collections.defaultdict(list))
for n, r in rows.items():
    key = key_of(r)
    if not key or n not in E:
        continue
    grp = ("simple tests" if r["set"] == "test" else r["set"]) + " " + r["lang"]
    for m in METHODS:
        L = lines(n, m)
        al = P.align(key, L)
        ex = {(nm(x["subject"]), nm(x["verb"]), nm(x["object"])) for x in L}
        c = tot[(grp, m)]
        c["key"] += len(key); c["found"] += sum(a is not None for a in al)
        e = [(nm(k[0]), nm(k[1]), nm(P._no_note(k[2]))) in ex for k in key]
        c["exact"] += sum(e); c["produced"] += len(L)
        c["extra"] += len(L) - len({a for a in al if a is not None})
        per[grp][m].append(e)

print("Discourse-first design against the earlier two, same keys, same scoring (subject, verb, object).")
print("Keys for sample and held-out were drafted with AI assistance; they are working keys, not a gold standard.\n")
print(f"{'set':18s} {'method':18s} {'found':>12s} {'exact':>12s} {'extra lines':>12s}")
for grp in sorted({g for g, _ in tot}):
    for m in METHODS:
        c = tot[(grp, m)]
        print(f"{grp:18s} {NAMES[m]:18s} {c['found']:4d}/{c['key']:<4d} {100*c['found']/c['key']:3.0f}% {c['exact']:4d}/{c['key']:<4d} {100*c['exact']/c['key']:3.0f}% {c['extra']:6d} of {c['produced']}")
    for m in ("vote", "tree_plus"):
        b = sum(x and not y for a, bb in zip(per[grp]["edu"], per[grp][m]) for x, y in zip(a, bb))
        cc = sum(y and not x for a, bb in zip(per[grp]["edu"], per[grp][m]) for x, y in zip(a, bb))
        print(f"{'':18s} exact, discourse first vs {NAMES[m]}: only discourse first {b}, only {NAMES[m]} {cc}, McNemar p = {K.mcnemar(b, cc):.2f}")
    print()
