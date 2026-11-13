"""wsj_diff.py OLD_RULES NEW_RULES WSJ_PARSES TREEBANK [--method tree_fixed]

Which Penn Treebank gold lines changed from exactly right to not (and the reverse) between two versions of the
rules, for one method. Each version runs in its own python process (the two versions have modules with the same
names), dumps its lines, and the lines are then compared against the same gold. Prints every changed line: the
sentence, the gold line, the old output and the new output. Reads only. Plain python3, no packages."""
import sys, os, json, subprocess, argparse, tempfile

ap = argparse.ArgumentParser()
ap.add_argument("old"); ap.add_argument("new"); ap.add_argument("parses"); ap.add_argument("treebank")
ap.add_argument("--method", default="tree_fixed")
ap.add_argument("--dump", default="")          # internal: RULES_DIR OUT.json
A = ap.parse_args()

DUMP = r'''
import sys, json
rules, parses, method, out = sys.argv[1:5]
sys.argv = [sys.argv[0], rules, parses]
sys.path.insert(0, rules)
import full as F, compare3 as K
res = {}
for r in json.load(open(parses, encoding="utf-8"))["rows"]:
    try:
        res[r["file"] + "|" + str(r["k"])] = [{x: L[x] for x in ("subject", "verb", "object")} for L in K.as_lines(F.full_row(r, method=method))]
    except Exception as e:
        res[r["file"] + "|" + str(r["k"])] = {"error": type(e).__name__}
json.dump(res, open(out, "w", encoding="utf-8"))
'''

tmp = tempfile.mkdtemp()
# the old version: the new folder (with its data files) and the old .py files laid on top, since the backup folder
# keeps only code
import shutil, glob
oldrules = os.path.join(tmp, "old_rules")
shutil.copytree(os.path.abspath(A.new), oldrules, ignore=shutil.ignore_patterns("__pycache__", "_before*"))
for f in glob.glob(os.path.join(A.old, "*.py")):
    shutil.copy(f, oldrules)
outs = {}
for tag, rules in (("old", oldrules), ("new", A.new)):
    path = os.path.join(tmp, tag + ".json")
    p = subprocess.run([sys.executable, "-c", DUMP, os.path.abspath(rules), A.parses, A.method, path], capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"{tag} rules failed:\n{p.stderr[-3000:]}")
    outs[tag] = json.load(open(path, encoding="utf-8"))

sys.path.insert(0, os.path.abspath(A.new))
import ptb_gold as G      # noqa: E402
P = G.P
gold = {f"{f}|{k}": (root, G.gold_lines(root)) for f, k, root in G.treebank_sentences(A.treebank)}
lost, gained = [], []
for key, (root, gl) in gold.items():
    if key not in outs["old"] or key not in outs["new"] or not gl:
        continue
    o, n = outs["old"][key], outs["new"][key]
    if isinstance(o, dict) or isinstance(n, dict):
        continue
    eo = {(G.norm(x["subject"]), G.norm(x["verb"]), G.norm(x["object"])) for x in o}
    en = {(G.norm(x["subject"]), G.norm(x["verb"]), G.norm(x["object"])) for x in n}
    for g in gl:
        kl = G.key_line(g)
        k = (G.norm(kl[0]), G.norm(kl[1]), G.norm(kl[2]))
        if (k in eo) != (k in en):
            verb = P.fold(g["verb"])[-1:]
            pick = lambda L: next((x for x in L if verb and verb[0] in P.fold(x["verb"] or "")), None)
            (lost if k in eo else gained).append((key, G.txt(root), kl, pick(o), pick(n), g))

def show(title, items):
    print(f"\n== {title}: {len(items)}")
    for key, text, kl, o, n, g in items:
        print(f"-- {key}: {text}")
        print(f"   gold: {kl[0]} | {kl[1]} | {kl[2]}" + (f"   [recipient: {g['recipient']}]" if g["recipient"] else ""))
        print(f"   old:  " + (f"{o['subject']} | {o['verb']} | {o['object']}" if o else "(no line with that verb)"))
        print(f"   new:  " + (f"{n['subject']} | {n['verb']} | {n['object']}" if n else "(no line with that verb)"))

print(f"method {A.method}: gold lines that changed between {A.old} and {A.new}")
show("exactly right before, not now", lost)
show("exactly right now, not before", gained)
