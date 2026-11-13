"""edu_keydiff.py BEFORE.json AFTER.json [PARSES.json]   Every answer-key line whose result changed between two runs of
edu_pipeline.py (found or exact, on the 100-sentence key, the held-out key and the simple test pairs), with the output
line before and after, and a count of how many got better and how many got worse.
    python3 scripts/step3_claims/edu_keydiff.py outputs/edu/edu_reparsed_before.json outputs/edu/edu_reparsed.json
A line marked '(only the to)' changed only because a to-infinitive is now written as the bare verb ('accept', marked
to-infinitive), which is how the answer keys write it."""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
before_path, after_path = sys.argv[1], sys.argv[2]
parses = sys.argv[3] if len(sys.argv) > 3 else "data/parity_oct19/parity_parses.json"
sys.argv = [sys.argv[0], HERE, parses]          # full.py reads the rules folder and the parses from argv
sys.path.insert(0, HERE)
import full as F            # noqa: E402
import compare3 as K        # noqa: E402
import combine_lib as C     # noqa: E402
import gold_heldout as GH   # noqa: E402
import parallel_tests as PT  # noqa: E402

P, norm = F.P, K.norm
A = {r["n"]: r for r in json.load(open(before_path))["rows"]}
B = {r["n"]: r for r in json.load(open(after_path))["rows"]}
tests = {}
for t in PT.T:
    for lang in ("en", "fr"):
        k = t[lang]["lines"]
        tests[f"test|{t['id']}|{lang}"] = ast.literal_eval(k) if isinstance(k, str) else k


def marks(rec, key):
    lines = rec["lines"]
    al = P.align(key, lines)
    exact = {(norm(x["subject"]), norm(x["verb"]), norm(x["object"])) for x in lines}
    return ([a is not None for a in al], [(norm(k[0]), norm(k[1]), norm(P._no_note(k[2]))) in exact for k in key], lines, al)


better = worse = only_to = 0
for r in json.load(open(parses))["rows"]:
    key = (C.KEY.get(r["key_n"]) if r["set"] == "sample" else GH.GH.get(r["key_n"]) if r["set"] == "heldout" else tests.get(r["n"])) or []
    if not key or r["n"] not in A or r["n"] not in B:
        continue
    fa, ea, la, ala = marks(A[r["n"]], key)
    fb, eb, lb, alb = marks(B[r["n"]], key)
    for i, k in enumerate(key):
        if (fa[i], ea[i]) == (fb[i], eb[i]):
            continue
        got_worse = fb[i] < fa[i] or eb[i] < ea[i]
        worse += got_worse
        better += not got_worse
        xa = la[ala[i]] if ala[i] is not None else None
        xb = lb[alb[i]] if alb[i] is not None else None
        to = bool(xa and xb and xa["verb"].lower().startswith("to ") and xa["verb"][3:] == xb["verb"]
                  and (xa["subject"], xa["object"]) == (xb["subject"], xb["object"]))
        only_to += to
        print("WORSE " if got_worse else "better", "(only the to)" if to else "", r["n"], "| key:", " | ".join(map(str, k[:3]))[:90])
        for label, x in (("   before", xa), ("   after ", xb)):
            print(label, (x["subject"], x["verb"], x["object"][:50], (x.get("subject_from") or "")[:45], (x.get("object_from") or "")[:30]) if x else None)
print(f"{better} better ({only_to} of them only from writing the verb without 'to'), {worse} worse")
