"""keydiff.py RULES_A RULES_B PARSES.json   Answer-key lines found by A but not by B (and the reverse), and lines whose
label changed, at every stage, on the held-out key and the 100-sentence key.
    python3 scripts/v6/keydiff.py scripts/v4 scripts/v6 data/parity_oct19/parity_parses.json"""
import sys, os, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))


def run(d, parses):
    code = f'''
import sys, json, os
sys.path.insert(0, os.path.abspath({d!r})); sys.path.insert(1, {HERE!r})
import parity_score as S, gold_heldout as GH
P, C = S.load_rules({d!r})
out = []
for r in json.load(open({parses!r}, encoding="utf-8"))["rows"]:
    if r["set"] == "test":
        continue
    g = (C.KEY if r["set"] == "sample" else GH.GH)[r["key_n"]]
    res = S.analyze(P, C, r, "native", "prod", "multi")
    for st in ("spacy", "stanza", "const", "final"):
        al = P.align(g, res[st])
        for gi, a in enumerate(al):
            if a is not None:
                out.append([r["n"], st, gi, res[st][a]["kind"] == g[gi][3]])
print(json.dumps(out))
'''
    o = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if o.returncode:
        sys.exit(o.stderr[-2000:])
    return {(a, b, c): k for a, b, c, k in json.loads(o.stdout)}


A, B = run(sys.argv[1], sys.argv[3]), run(sys.argv[2], sys.argv[3])
sys.path.insert(0, HERE)
import gold, gold2, gold_heldout as GH
K = {**gold.G, **gold2.G2}


def g(n, i):
    s, k = n.split("|")
    return (K if s == "sample" else GH.GH)[int(k)][i][:4]


for x in sorted(set(A) - set(B)): print("lost  ", x, g(x[0], x[2]))
for x in sorted(set(B) - set(A)): print("gained", x, g(x[0], x[2]))
for x in sorted(set(A) & set(B)):
    if A[x] != B[x]: print("label ", "right->wrong" if A[x] else "wrong->right", x, g(x[0], x[2]))
