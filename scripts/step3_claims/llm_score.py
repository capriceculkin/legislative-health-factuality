"""llm_score.py   Scores LLM-written claim lines against the Penn Treebank's human annotation, next to the parser
methods on the same sentences, the same way wsj_score.py scores the parsers (found, heads, exact, subject and verb).

  python3 scripts/step3_claims/llm_score.py scripts/step3_claims outputs/wsj/wsj_parses.json data/ptb_sample/combined \
      outputs/llm_pilot/sample.json outputs/llm_pilot/lines_raw.txt

lines_raw.txt: '#i' starts sentence i of sample.json, then one 'subject | verb | object | recipient' per line."""
import sys, json, collections, random

RULES, PARSES, TREEBANK, SAMPLE, LINES = sys.argv[1:6]
LABEL = sys.argv[6] if len(sys.argv) > 6 else "LLM (pilot)"
sys.argv = [sys.argv[0], RULES, PARSES]
sys.path.insert(0, RULES)
import full as F             # noqa: E402
import ptb_gold as G         # noqa: E402
import compare3 as K         # noqa: E402
P = F.P

# reading the LLM lines
sample = json.load(open(SAMPLE, encoding="utf-8"))
llm, cur = {}, None
for raw in open(LINES, encoding="utf-8"):
    raw = raw.rstrip("\n")
    if raw.startswith("#"):
        cur = int(raw[1:]); llm[cur] = []
    elif raw.strip():
        parts = [x.strip() for x in raw.split(" | ")] + ["", "", "", ""]
        s, v, o, rcp = parts[0], parts[1].rstrip(" |").strip(), parts[2], parts[3]
        if v.endswith("|"):
            v = v[:-1].strip()
        llm[cur].append({"subject": s, "verb": v, "object": o, "recipient": rcp, "kind": "asserted"})
llm = {(sample[i]["file"], sample[i]["k"]): L for i, L in llm.items()}

gold = {(f, k): G.gold_lines(root) for f, k, root in G.treebank_sentences(TREEBANK)}
rows = {(r["file"], r["k"]): r for r in json.load(open(PARSES, encoding="utf-8"))["rows"]}
content = lambda s: {w for w in P.fold(s or "") if w not in P.STOP and len(w) > 1}
METHODS = ["spacy", "stanza", "const", "tree_plus", "vote", "llm"]
NAMES = {"spacy": "spaCy alone", "stanza": "Stanza alone", "const": "tree alone", "tree_plus": "tree + deps add",
         "vote": "2-of-3 vote", "llm": LABEL}

tot = {m: collections.defaultdict(collections.Counter) for m in METHODS}
per = collections.defaultdict(dict)
for key in llm:
    gl, r = gold.get(key), rows.get(key)
    if not gl or not r:
        continue
    kl_all = [G.key_line(g) for g in gl]
    for m in METHODS:
        if m == "llm":
            L = fr_lines = llm[key]
        else:
            try:
                L = K.as_lines(F.full_row(r, method=m)); fr_lines = F.full_row(r, method=m)["lines"]
            except Exception:                    # noqa: BLE001
                L, fr_lines = [], []
        al = P.align(kl_all, L) if kl_all else []
        exact = {(G.norm(x["subject"]), G.norm(x["verb"]), G.norm(x["object"])) for x in L}
        flags = []
        for g, kl, a in zip(gl, kl_all, al):
            hit = a is not None
            ex = (G.norm(kl[0]), G.norm(kl[1]), G.norm(kl[2])) in exact
            hd = hit and bool(G.head_ok(g["subject"], g["subject_head"], L[a]["subject"])) and bool(G.head_ok(g["object"], g["object_head"], L[a]["object"]))
            gv = P.fold(g["verb"])[-1:]
            cand = [j for j, o in enumerate(L) if gv and gv[0] in P.fold(o["verb"] or "")
                    and (content(g["subject"]) & content(o["subject"]) or (not content(g["subject"]) and P.fold(g["subject"])[:1] == P.fold(o["subject"])[:1]))]
            c = tot[m]["all"]
            c["n"] += 1; c["found"] += hit; c["exact"] += ex; c["head"] += hd
            if g["subject"]:
                c["sv_n"] += 1; c["sv"] += bool(cand)
            flags.append(ex)
        tot[m]["_"]["extra"] += len(L) - len({a for a in al if a is not None})
        tot[m]["_"]["produced"] += len(L)
        per[key][m] = flags

pc = lambda a, b: f"{100 * a / b:5.1f}%" if b else "    - "
print(f"Penn Treebank pilot: {len(per)} sentences, the same sentences for every method")
print(f"   {'method':18s} {'gold lines':>10s} {'found':>7s} {'heads':>7s} {'exact':>7s} {'subj+verb':>10s} {'lines made':>11s} {'match no gold':>14s}")
for m in METHODS:
    c = tot[m]["all"]; x = tot[m]["_"]
    print(f"   {NAMES[m]:18s} {c['n']:10d} {pc(c['found'], c['n'])} {pc(c['head'], c['n'])} {pc(c['exact'], c['n'])} {pc(c['sv'], c['sv_n']):>10s} {x['produced']:11d} {x['extra']:14d}")

# paired comparison on exact, LLM against the best parser method, with a sentence bootstrap
rnd = random.Random(20261116)
keys = list(per)
for m in ["tree_plus", "vote"]:
    b = c_ = 0
    for s in keys:
        for e1, e2 in zip(per[s]["llm"], per[s][m]):
            b += e1 and not e2; c_ += e2 and not e1
    diffs = []
    for _ in range(2000):
        d = n = 0
        for s in (keys[rnd.randrange(len(keys))] for _ in keys):
            for e1, e2 in zip(per[s]["llm"], per[s][m]):
                d += e1 - e2; n += 1
        diffs.append(100 * d / max(n, 1))
    diffs.sort()
    print(f"   LLM vs {NAMES[m]:16s} exact only LLM {b:4d}, only {m} {c_:4d}   McNemar p = {K.mcnemar(b, c_):.3f}   "
          f"difference {diffs[50]:+5.1f} to {diffs[1949]:+5.1f} points (95% bootstrap)")
