"""strict.py   A strict score next to the loose one, for the three-slot lines and for the full predications.

Loose (as before): the verb shares a word or its first four letters, and subject and object each share one content word.
Strict, on the same pairing of key line to output line:
  exact      subject, verb and object each equal to the key after folding case, accents of quotes, punctuation and notes
  word F1    per slot, the overlap of words (precision and recall over the words of key and output), averaged over key lines
For the full predications the object is the object plus every argument the line now carries (to whom, for what ...),
except when / modal / how, because the answer key puts those in no slot.

    python3 strict.py RULES PARSES.json"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv, ARGS = sys.argv[:1] + sys.argv[1:3], sys.argv[1:]
import full as F                    # noqa: E402
S, P, C = F.S, F.P, F.C
import gold_heldout as GH, parallel_tests as PT   # noqa: E402


def words(s):
    return [w for w in P.fold(P._no_note((s or "").replace("(inh)", " "))) if w not in (",", ".", ";", ":")]


def f1(gold, out):
    g, o = collections.Counter(words(gold)), collections.Counter(words(out))
    if not g and not o:
        return 1.0
    common = sum((g & o).values())
    if not common:
        return 0.0
    p, r = common / sum(o.values()), common / sum(g.values())
    return 2 * p * r / (p + r)


def full_lines(fr):
    out = []
    for r in fr["lines"]:
        extra = [q["text"] for q in r["parts"] if q["role"] not in ("ARGM-TMP", "ARGM-MOD", "ARGM-ADV", "ARGM-NEG", "OPENING") and q.get("ref") is None]
        if r.get("recipient"):
            extra = [r["recipient"]] + extra                # the same object the comparison script scores (compare3.as_lines)
        obj = (r.get("object_words") or "") if (r["object"] or "").startswith("[what is said") else (r["object"] or "")
        out.append(dict(subject=r["subject"], verb=r["verb"], object=obj, object_full=" ".join([obj] + extra).strip(),
                        kind=r["kind"], negated=r.get("negated"), hedged=r.get("hedged")))
    return out


def score(gold, lines, objkey):
    al = P.align(gold, lines) if gold else []
    c = collections.Counter(key=len(gold), produced=len(lines))
    used = {a for a in al if a is not None}
    c["extra"] = len(lines) - len(used)
    for g, a in zip(gold, al):
        if a is None:
            continue
        p = lines[a]
        c["found"] += 1
        fs, fv, fo = f1(g[0], p["subject"]), f1(g[1], p["verb"]), f1(g[2], p[objkey])
        c["f1_subj"] += fs; c["f1_verb"] += fv; c["f1_obj"] += fo
        c["exact"] += (fs == 1.0 and fv == 1.0 and fo == 1.0)
        c["obj_exact"] += fo == 1.0
        c["label"] += p["kind"] == g[3]
        gw = set(words(g[2])) - P.STOP
        if gw:
            c["obj_words"] += len(gw)
            c["obj_words_core"] += len(gw & set(words(p["object"])))
            c["obj_words_all"] += len(gw & set(words(p[objkey])))
    return c


def main():
    rows = json.load(open(ARGS[1], encoding="utf-8"))["rows"]
    tests = {t["id"]: t for t in PT.T}
    tot = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    for r in rows:
        if r["set"] == "test":
            gold = tests[r["key_n"]][r["lang"]]["lines"]
        else:
            gold = (C.KEY if r["set"] == "sample" else GH.GH).get(r["key_n"]) or []
        res = S.analyze(P, C, r, "native", "prod", "multi")
        old = [dict(p, object_full=p["object"]) for p in res["final"]]
        fr = F.full_row(r)
        new = full_lines(fr)
        for name, L, ok in (("lines (now)", old, "object"), ("full predication", new, "object_full")):
            c = score(gold, L, ok)
            tot[(r["set"], r["lang"], name)].update(c)
        # key lines whose object the old line got loosely but not exactly, and the full line fixed
        for g, a, b in zip(gold, P.align(gold, old) if gold else [], P.align(gold, new) if gold else []):
            if a is not None and b is not None and f1(g[2], old[a]["object"]) < 1.0 and f1(g[2], new[b]["object_full"]) > f1(g[2], old[a]["object"]):
                examples[r["set"]].append((r["n"], g[2], old[a]["object"], new[b]["object_full"]))
    print("set       lang  output             key  found  exact(all 3 slots)  object exact  word F1 subj / verb / obj   right label  extra")
    for (st, lang, name), c in sorted(tot.items()):
        n = c["found"] or 1
        print(f"{st:9s} {lang:4s}  {name:18s} {c['key']:4d}  {c['found']:5d}  {c['exact']:5d} ({100*c['exact']/max(c['key'],1):3.0f}% of key)"
              f"   {c['obj_exact']:5d}      {c['f1_subj']/n:.2f} / {c['f1_verb']/n:.2f} / {c['f1_obj']/n:.2f}      {c['label']:5d}   {c['extra']:4d}"
              f"   key object words covered {c['obj_words_all']}/{c['obj_words']} ({100*c['obj_words_all']/max(c['obj_words'],1):.0f}%)")
    print("\nobjects the full predication completes (key | three-slot line | full predication), first 12 of the sample:")
    for e in examples["sample"][:12]:
        print("  ", e)
    print("count:", {k: len(v) for k, v in examples.items()})


main()
