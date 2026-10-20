"""compare3.py   How each of the three parsers does alone, against the vote, on the same sentences and the same keys.

For spaCy alone, Stanza alone, the constituency tree alone, and the two-of-three vote, each turned into full predications
by full.py (the tree's arguments are read from its phrases), against the 100-sentence sample and the held-out key:
  loose found        the old test (verb shares a word or 4 letters; subject and object share one content word)
  exact              subject, verb and object equal to the key after folding case and punctuation
  object words       share of the key object's content words the output carries (object plus its parts)
  extra              output lines that match no key line
Then paired comparisons on the same key lines (each key line found or not by two methods):
  McNemar exact test on the lines where the two disagree, and a 95% interval for the difference from 10,000 bootstrap
  draws that resample whole sentences (key lines of one sentence move together).
And how often two parsers produce the same line (loose), which says how independent the three voters are.

    python3 compare3.py RULES PARSES.json"""
import sys, os, json, re, math, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import full as F                                 # noqa: E402
S, P, C = F.S, F.P, F.C
import gold_heldout as GH                        # noqa: E402

METHODS = ("spacy", "stanza", "const", "vote", "vote_sw")
NAMES = {"spacy": "spaCy alone", "stanza": "Stanza alone", "const": "tree alone", "vote": "vote", "vote_sw": "vote, Stanza words"}


def norm(x):
    x = (x or "").replace("(inh)", " ").replace("’", "'")
    x = re.sub(r"\((?!inh)[^)]*\)", " ", x)
    x = re.sub(r"[^\w' ]", " ", x.lower())
    return " ".join(x.replace("'", " ' ").split())


def as_lines(fr):
    out = []
    for r in fr["lines"]:
        extra = [q["text"] for q in r["parts"] if q["role"] not in ("ARGM-TMP", "ARGM-MOD", "ARGM-ADV", "ARGM-NEG", "OPENING")]
        out.append(dict(subject=r["subject"], verb=r["verb"], object=r["object"] or "", full=" ".join([r["object"] or ""] + extra).strip(),
                        kind=r["kind"], negated=r.get("negated"), hedged=r.get("hedged")))
    return out


def mcnemar(b, c):
    """Exact two-sided McNemar p-value: b = lines only method A finds, c = lines only method B finds."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def wilson(k, n, z=1.96):
    if not n:
        return (0, 0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - h), 100 * (c + h))


def main():
    rows = json.load(open(sys.argv[2], encoding="utf-8"))["rows"]
    per = collections.defaultdict(list)          # (set, lang) -> list of sentences: {method: [found flags], exact flags}
    tot = collections.defaultdict(collections.Counter)
    agree = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["set"] not in ("sample", "heldout"):
            continue
        gold = (C.KEY if r["set"] == "sample" else GH.GH).get(r["key_n"]) or []
        sent = {}
        outs = {}
        for m in METHODS:
            L = as_lines(F.full_row(r, method="vote", wording="stanza") if m == "vote_sw" else F.full_row(r, method=m))
            outs[m] = L
            al = P.align(gold, L) if gold else []
            exact_set = {(norm(x["subject"]), norm(x["verb"]), norm(x["full"])) for x in L}
            found = [a is not None for a in al]
            exact = [(norm(g[0]), norm(g[1]), norm(g[2])) in exact_set for g in gold]
            c = tot[(r["set"], r["lang"], m)]
            c["key"] += len(gold); c["found"] += sum(found); c["exact"] += sum(exact); c["produced"] += len(L)
            c["extra"] += len(L) - len({a for a in al if a is not None})
            for g, a in zip(gold, al):
                if a is not None:
                    c["label"] += L[a]["kind"] == g[3]
                gw = set(P.fold(P._no_note(g[2]))) - P.STOP
                gw = {w for w in gw if len(w) > 1}
                c["objw"] += len(gw)
                if a is not None:
                    c["objw_hit"] += len(gw & set(P.fold(L[a]["full"])))
            sent[m] = (found, exact)
        per[(r["set"], r["lang"])].append(sent)
        for i, a in enumerate(METHODS[:3]):
            for b in METHODS[i + 1:3]:
                for x in outs[a]:
                    agree[(r["lang"], a, b)]["lines"] += 1
                    agree[(r["lang"], a, b)]["same"] += any(C.same(dict(x, negated=bool(x["negated"])), dict(y, negated=bool(y["negated"]))) for y in outs[b])

    print("== each method alone and the vote (full predications)")
    print("set      lang  method          loose found        exact (95% interval)        object words   extra  right label")
    for st in ("sample", "heldout"):
        for lang in ("en", "fr"):
            for m in METHODS:
                c = tot[(st, lang, m)]
                lo, hi = wilson(c["exact"], c["key"])
                flo, fhi = wilson(c["found"], c["key"])
                print(f"{st:8s} {lang:4s}  {NAMES[m]:14s} {c['found']:3d}/{c['key']:3d} ({flo:3.0f}-{fhi:3.0f})   {c['exact']:3d}/{c['key']:3d} = {100*c['exact']/c['key']:3.0f}% ({lo:3.0f}-{hi:3.0f})"
                      f"     {100*c['objw_hit']/max(c['objw'],1):3.0f}%      {c['extra']:4d}   {c['label']:4d}")
    print("\n== the vote against each parser alone, on the same key lines")
    rnd = random.Random(20261019)
    for st in ("sample", "heldout"):
        for lang in ("en", "fr"):
            sents = per[(st, lang)]
            for m in ("spacy", "stanza", "const", "vote_sw"):
                for which, idx in (("loose found", 0), ("exact", 1)):
                    b = c_ = 0
                    for s in sents:
                        for v, o in zip(s["vote"][idx], s[m][idx]):
                            b += v and not o; c_ += o and not v
                    diffs = []
                    for _ in range(10000):
                        smp = [sents[rnd.randrange(len(sents))] for _ in sents]
                        n = sum(len(s["vote"][idx]) for s in smp)
                        if n:
                            diffs.append(100 * (sum(sum(s["vote"][idx]) for s in smp) - sum(sum(s[m][idx]) for s in smp)) / n)
                    diffs.sort()
                    lo, hi = diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs))]
                    print(f"{st:8s} {lang}  vote vs {NAMES[m]:18s} {which:12s} only vote {b:2d}, only {m} {c_:2d}   McNemar p = {mcnemar(b, c_):.2f}   difference {lo:+5.1f} to {hi:+5.1f} points")
    print("\n== how often two parsers produce the same line (loose), all 130 key sentences")
    for (lang, a, b), c in sorted(agree.items()):
        print(f"  {lang}  {a:6s} lines also found by {b:6s}: {c['same']}/{c['lines']} = {100*c['same']/c['lines']:.0f}%")


if __name__ == "__main__":
    main()
