#!/usr/bin/env python3
"""fr_const_run.py   French constituency trees for the French sentences (the 50 in the sample and the held-out ones),
with the Berkeley Neural Parser's French model (benepar_fr2, trained on the French Treebank). Stanza has no French
constituency model, which is why this parser is used. Words come from spaCy's French model, so the trees line up
with the dependency parses. Writes ~/Desktop/next_steps/oct15/fr_trees.json."""
import json, os, signal, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = Path(os.environ.get("OCT15_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct15"))); OUT.mkdir(parents=True, exist_ok=True)
LIMIT = int(os.environ.get("FRCONST_LIMIT_MIN", "40"))


def give_up(*_):
    sys.exit(f"The French parser took longer than {LIMIT} minutes (probably stuck downloading). Nothing was written; "
             "run the bundle again, or send this message to the chat.")


signal.signal(signal.SIGALRM, give_up); signal.alarm(LIMIT * 60)

import benepar_fix
try:
    benepar = benepar_fix.prepare()
except Exception as e:
    sys.exit(f"The Berkeley parser (benepar) would not load: {type(e).__name__}: {str(e)[:300]}\nSend this message to the chat.")
import spacy

print("== French constituency: loading spaCy French and the Berkeley parser's French model", flush=True)
nlp = spacy.load("fr_core_news_lg")
try:
    parser = benepar_fix.get_parser(benepar, lambda m: print(m, flush=True))
    test = benepar_fix.self_test(benepar, parser)
    print("   test sentence parsed:", " ".join(str(test).split())[:200], flush=True)
except Exception as e:
    import traceback
    tb = traceback.extract_tb(e.__traceback__)[-3:]
    print(f"The French model would not load or parse: {type(e).__name__}: {str(e)[:400]}", flush=True)
    for f in tb:
        print(f"      at {Path(f.filename).name} line {f.lineno}: {f.line}", flush=True)
    if benepar_fix.NOTES:
        print("   fixes used before it stopped:", "; ".join(benepar_fix.NOTES), flush=True)
    sys.exit(3)
if benepar_fix.NOTES:
    print("   fixes used:", "; ".join(benepar_fix.NOTES), flush=True)


def to_lists(t):
    """nltk Tree -> [label, [children]], leaves as plain strings (so brackets inside words cannot break anything)."""
    if isinstance(t, str):
        return t
    return [t.label(), [to_lists(k) for k in t]]


rows = json.loads((HERE / "pc.json").read_text(encoding="utf-8"))["rows"]
held = json.loads((HERE / "heldout.json").read_text(encoding="utf-8"))
held = held["rows"] if isinstance(held, dict) else held
todo = [(str(r["n"]), r["text"]) for r in rows if r["lang"] == "fr"] + [("h" + str(h["h"]), h["text"]) for h in held if h["lang"] == "fr"]
out, labels, t0, fails = {}, {}, time.time(), []
for key, text in todo:
    doc = nlp(text)
    trees = []
    for sent in doc.sents:
        words = [t.text for t in sent if not t.is_space]
        if not words:
            continue
        try:
            tree = parser.parse(benepar.InputSentence(words=words))
        except Exception as e:
            fails.append((key, f"{type(e).__name__}: {str(e)[:120]}")); continue
        L = to_lists(tree)
        trees.append(L)
        stack = [L]
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                labels[n[0]] = labels.get(n[0], 0) + 1; stack.extend(n[1])
    out[key] = trees
if todo and len(fails) > len(todo) / 2:
    for k, e in fails[:3]:
        print("   failed:", k, e)
    print(f"More than half the French sentences failed to parse ({len(fails)}), so no trees were saved.", flush=True)
    sys.exit(3)
print(f"   parsed {len(out)} French sentences in {time.time() - t0:.0f}s; {len(fails)} sentence parts failed", flush=True)
for k, e in fails[:5]:
    print("   failed:", k, e)
(OUT / "fr_trees.json").write_text(json.dumps({"parser": "benepar_fr2", "benepar": getattr(benepar, "__version__", "?"),
                                               "fixes": benepar_fix.NOTES, "labels": labels, "trees": out}, ensure_ascii=False), encoding="utf-8")
print("   labels seen:", ", ".join(f"{k} {v}" for k, v in sorted(labels.items(), key=lambda x: -x[1])[:30]))
print("== wrote", OUT / "fr_trees.json")
