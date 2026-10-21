"""dep_disagree.py [UD_EVAL_DIR]   Question from the Oct 20 meeting: "Are the differences between the two dependency parses useful?"

Uses the files ud_eval.py wrote (outputs/ud_eval/gold_<tb>.conllu, spacy_<tb>.conllu, stanza_<tb>.conllu: the same
words, the treebank's gold arcs and each parser's arcs). For every word, the two parsers either agree on its arc
(head and main label) or not. If agreement is almost always right and disagreement often wrong, then the differences
are useful: a disagreement marks where to look for an error, before any rule runs.

French only for the main table: spaCy English uses ClearNLP labels and draws some arcs the other way (preposition and
copula heads), so English disagreements are mostly convention, not error. The English rows are printed for subject and
object arcs only, where both schemes agree on direction, and marked as such.
Plain python3, no packages."""
import sys, collections
from pathlib import Path

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/ud_eval")
FAMILY = {"nsubj": "subject", "csubj": "subject", "obj": "object", "iobj": "indirect object", "obl": "oblique (complement or adjunct)",
          "ccomp": "clause as object", "xcomp": "open clause (to act)", "advcl": "adverbial clause", "acl": "relative or noun clause",
          "conj": "coordination", "cop": "copula", "nmod": "noun modifier", "appos": "apposition", "dobj": "object", "pobj": "object"}


def read(p):
    out, s = [], []
    for line in open(p, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            if s:
                out.append(s); s = []
            continue
        if line.startswith("#"):
            continue
        f = line.split("\t")
        if "-" in f[0] or "." in f[0]:
            continue
        s.append((f[1], int(f[6]) if f[6] not in ("_", "") else -1, f[7].split(":")[0]))
    if s:
        out.append(s)
    return out


CLEAR_TO_UD = {"dobj": "obj", "nsubjpass": "nsubj", "csubjpass": "csubj", "dative": "iobj"}   # spaCy English label names


def table(tb, only=None):
    g, a, b = (read(D / f"{x}_{tb}.conllu") for x in ("gold", "spacy", "stanza"))
    if tb.startswith("en"):
        a = [[(w, h, CLEAR_TO_UD.get(r, r)) for (w, h, r) in s] for s in a]
    assert len(g) == len(a) == len(b), (tb, len(g), len(a), len(b))
    c = collections.defaultdict(collections.Counter)
    for sg, sa, sb in zip(g, a, b):
        assert len(sg) == len(sa) == len(sb)
        for (w, gh, gr), (_, ah, ar), (_, bh, br) in zip(sg, sa, sb):
            if gr == "punct":
                continue
            fam = FAMILY.get(gr, "other")
            if only and fam not in only:
                continue
            ok_a, ok_b = (ah, ar) == (gh, gr), (bh, br) == (gh, gr)
            same = (ah, ar) == (bh, br)
            for k in ("all words", fam):
                x = c[k]
                x["n"] += 1
                if same:
                    x["agree"] += 1; x["agree_right"] += ok_a
                else:
                    x["disagree"] += 1; x["dis_spacy"] += ok_a; x["dis_stanza"] += ok_b; x["dis_neither"] += not (ok_a or ok_b)
    return c


pc = lambda a, b: f"{100 * a / b:5.1f}%" if b else "   -  "
for tb, only in (("fr_gsd", None), ("fr_sequoia", None), ("fr_rhapsodie", None), ("en_ewt", {"subject", "object"}), ("en_gum", {"subject", "object"})):
    if not all((D / f"{x}_{tb}.conllu").exists() for x in ("gold", "spacy", "stanza")):
        print(f"== {tb}: files missing in {D} (run ud_eval.py first)")
        continue
    c = table(tb, only)
    print(f"\n== {tb}" + ("   (English: subject and object arcs only, where both label schemes point the same way; labels compared loosely)" if only else ""))
    print(f"   {'arc (gold label)':34s} {'words':>6s} {'parsers agree':>14s} {'right when agree':>17s} {'disagree':>9s} {'spaCy right':>12s} {'Stanza right':>13s} {'neither':>8s}")
    order = ["all words", "subject", "object", "indirect object", "oblique (complement or adjunct)", "clause as object",
             "open clause (to act)", "adverbial clause", "relative or noun clause", "coordination", "apposition"]
    for k in order:
        x = c.get(k)
        if not x or not x["n"]:
            continue
        print(f"   {k:34s} {x['n']:6d} {pc(x['agree'], x['n']):>14s} {pc(x['agree_right'], x['agree']):>17s} {pc(x['disagree'], x['n']):>9s} "
              f"{pc(x['dis_spacy'], x['disagree']):>12s} {pc(x['dis_stanza'], x['disagree']):>13s} {pc(x['dis_neither'], x['disagree']):>8s}")
print("\nRead: 'right when agree' is how often the shared arc is correct. The last three columns split the disagreements:"
      " which parser had the gold arc, or neither. Right and wrong mean head and main label both equal to the treebank.")
