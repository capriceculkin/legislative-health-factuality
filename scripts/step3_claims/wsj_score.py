"""wsj_score.py RULES WSJ_PARSES.json TREEBANK_DIR [--json OUT]

Scores every method (each parser alone, the 2-of-3 vote, the tree-first designs) against the Penn Treebank's own
human annotation, turned into gold lines by ptb_gold.py. WSJ_PARSES.json comes from wsj_collect.py, which parses the
treebank's sentences with the same parsers the pipeline uses.

What is scored, per gold line (one per clause):
  found     the vote's loose match test (same as the debate key)
  heads     found, and the subject and the object each have the gold head word and no word from outside the gold
            phrase (fair to rules that keep the core noun phrase where the treebank keeps the whole phrase)
  exact     subject, verb and object all equal to the gold, word for word
  subj+verb the subject and the verb are right, whatever the object
  recipient for the lines where the annotators marked a recipient (-DTV or the first of two objects): is it in the
            recipient slot, not lost and not in the object slot
  adjunct   for the lines where the verb has no object, only adjuncts (-LOC, -DIR, -MNR ...): is the object slot empty
Plain python3, no packages."""
import sys, os, json, argparse, collections, re, random
ap = argparse.ArgumentParser()
ap.add_argument("rules"); ap.add_argument("parses"); ap.add_argument("treebank")
ap.add_argument("--json", default="")
ap.add_argument("--methods", default="spacy,stanza,const,tree_fixed,tree_plus,vote")
A = ap.parse_args()
sys.argv = [sys.argv[0], A.rules, A.parses]
sys.path.insert(0, A.rules)
import full as F             # noqa: E402
import ptb_gold as G         # noqa: E402
import compare3 as K         # noqa: E402
P = F.P
NAMES = {"spacy": "spaCy alone", "stanza": "Stanza alone", "const": "tree alone", "tree_fixed": "tree, fixed by deps",
         "tree_plus": "tree + deps add", "vote": "2-of-3 vote"}
METHODS = A.methods.split(",")

gold = {(f, k): G.gold_lines(root) for f, k, root in G.treebank_sentences(A.treebank)}
rows = json.load(open(A.parses, encoding="utf-8"))["rows"]
content = lambda s: {w for w in P.fold(s or "") if w not in P.STOP and len(w) > 1}

tot = {m: collections.defaultdict(collections.Counter) for m in METHODS}
per_sent = collections.defaultdict(dict)
crash = collections.Counter()
for r in rows:
    gl = gold.get((r["file"], r["k"]))
    if not gl:
        continue
    key = [G.key_line(g) for g in gl]
    for m in METHODS:
        try:
            L = K.as_lines(F.full_row(r, method=m))
            fr_lines = F.full_row(r, method=m)["lines"]
        except Exception as e:          # noqa: BLE001
            crash[(m, type(e).__name__)] += 1
            L, fr_lines = [], []
        al = P.align(key, L) if key else []
        exact = {(G.norm(x["subject"]), G.norm(x["verb"]), G.norm(x["object"])) for x in L}
        flags = []
        for g, kl, a in zip(gl, key, al):
            kinds = ["all"]
            if g["subject_understood"]:
                kinds.append("subject understood (trace)")
            if g["object_kind"] == "predicative complement":
                kinds.append("predicative complement")
            if g["recipient"]:
                kinds.append("recipient or indirect object")
            if g["object_kind"] and g["object_kind"].startswith("clause"):
                kinds.append("clause as object")
            if g["object_kind"] and g["object_kind"].startswith("prepositional complement"):
                kinds.append("prepositional complement (CLR)")
            if not g["object"] and g.get("adjuncts"):
                kinds.append("no object, adjunct only")
            if g["negated"]:
                kinds.append("negated")
            if g["passive"] or g["passive_doer"]:
                kinds.append("passive")
            hit = a is not None
            ex = (G.norm(kl[0]), G.norm(kl[1]), G.norm(kl[2])) in exact
            hd = hit and bool(G.head_ok(g["subject"], g["subject_head"], L[a]["subject"])) and bool(G.head_ok(g["object"], g["object_head"], L[a]["object"]))
            # subject and verb right, found without the aligner: any line with the gold verb's last word and a shared subject word
            gv = P.fold(g["verb"])[-1:]
            cand = [j for j, o in enumerate(L) if gv and gv[0] in P.fold(o["verb"] or "")
                    and (content(g["subject"]) & content(o["subject"]) or (not content(g["subject"]) and P.fold(g["subject"])[:1] == P.fold(o["subject"])[:1]))]
            sv = bool(cand) if g["subject"] else None
            rec = adj = None
            if g["recipient"] and cand:
                o = fr_lines[cand[0]] if cand[0] < len(fr_lines) else {}
                rec = bool(content(g["recipient"]) & content(o.get("recipient") or "")) and not (content(g["recipient"]) & content(o.get("object") or ""))
            if not g["object"] and g.get("adjuncts") and cand:
                adj = not content(L[cand[0]]["object"])
            for kd in kinds:
                c = tot[m][kd]
                c["n"] += 1; c["found"] += hit; c["exact"] += ex; c["head"] += hd
                if sv is not None:
                    c["sv_n"] += 1; c["sv"] += sv
                if rec is not None:
                    c["rec_n"] += 1; c["rec"] += rec
                if adj is not None:
                    c["adj_n"] += 1; c["adj"] += adj
            flags.append((hit, ex))
        tot[m]["_"]["extra"] += len(L) - len({a for a in al if a is not None})
        tot[m]["_"]["produced"] += len(L)
        per_sent[(r["file"], r["k"])][m] = flags

pc = lambda a, b: f"{100 * a / b:5.1f}%" if b else "    - "
print(f"Penn Treebank: {len(per_sent)} sentences scored against the annotators' marks (ptb_gold.py)")
print(f"Gold: Marcus et al. 1993/1994, hand-annotated; free NLTK sample, WSJ sections 00-01 (the usual training split is 02-21; whether Stanza and spaCy saw 00-01 in training is not confirmed).")
kinds = ["all", "subject understood (trace)", "predicative complement", "recipient or indirect object", "clause as object",
         "prepositional complement (CLR)", "no object, adjunct only", "negated", "passive"]
for kd in kinds:
    print(f"\n== {kd}")
    print(f"   {'method':20s} {'lines':>6s} {'found':>7s} {'heads':>7s} {'exact':>7s} {'subj+verb':>10s} {'recipient right':>16s} {'object left empty':>18s}")
    for m in METHODS:
        c = tot[m][kd]
        if not c["n"]:
            continue
        print(f"   {NAMES[m]:20s} {c['n']:6d} {pc(c['found'], c['n'])} {pc(c['head'], c['n'])} {pc(c['exact'], c['n'])} {pc(c['sv'], c['sv_n']):>10s} "
              f"{pc(c['rec'], c['rec_n']):>16s} {pc(c['adj'], c['adj_n']):>18s}")
print("\n== lines produced that match no gold line")
for m in METHODS:
    print(f"   {NAMES[m]:20s} {tot[m]['_']['extra']:6d} of {tot[m]['_']['produced']}")

# paired test, vote against each, with a sentence-level bootstrap
rnd = random.Random(20261019)
print("\n== the vote against each method, same gold lines (exact)")
keys = list(per_sent)
for m in METHODS:
    if m == "vote" or "vote" not in METHODS:
        continue
    b = c_ = 0
    for s in keys:
        for (h1, e1), (h2, e2) in zip(per_sent[s].get("vote", []), per_sent[s].get(m, [])):
            b += e1 and not e2; c_ += e2 and not e1
    diffs = []
    for _ in range(2000):
        d = n = 0
        for s in (keys[rnd.randrange(len(keys))] for _ in keys):
            for (h1, e1), (h2, e2) in zip(per_sent[s].get("vote", []), per_sent[s].get(m, [])):
                d += e1 - e2; n += 1
        diffs.append(100 * d / max(n, 1))
    diffs.sort()
    print(f"   vote vs {NAMES[m]:20s} only vote {b:5d}, only {m} {c_:5d}   McNemar p = {K.mcnemar(b, c_):.3f}   "
          f"difference {diffs[50]:+5.1f} to {diffs[1949]:+5.1f} points")
if crash:
    print("\ncrashes:", dict(crash))
if A.json:
    json.dump({m: {kd: dict(v) for kd, v in tot[m].items()} for m in METHODS}, open(A.json, "w", encoding="utf-8"), indent=1)
