"""wsj_collect.py TREEBANK_DIR [--n N]   Parses the Penn Treebank sample's sentences with the pipeline's own parsers
(spaCy en_core_web_lg, Stanza English with its constituency parser), in the same row format as parity_parses.json, so
wsj_score.py can score every method against the treebank's human annotation.

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 scripts/step3_claims/wsj_collect.py data/ptb_sample/combined

The parsers see plain text rebuilt from the treebank's words (understood elements and annotation removed), not the
treebank's trees. No discourse parse (not needed for this score). Writes outputs/wsj/wsj_parses.json. Reads only.
About 0.2 to 0.5 seconds a sentence on a laptop CPU: 15 to 30 minutes for all 3,914."""
import json, sys, time, argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
V4 = PROJECT / "scripts" / "step2_parsers"
sys.path.insert(0, str(HERE))
import preds as P            # noqa: E402
import combine_lib as C      # noqa: E402
import ptb_gold as G         # noqa: E402
sys.path.insert(1, str(V4))
import parse_corpus_v5 as V  # noqa: E402   the same model loading and parse calls as the debate run
assert V.P is P and V.C is C, "parse_corpus_v5 picked up another copy of the rules"

ap = argparse.ArgumentParser()
ap.add_argument("treebank")
ap.add_argument("--n", type=int, default=0, help="only the first N sentences (default: all)")
ap.add_argument("--out", default=str(PROJECT / "outputs" / "wsj" / "wsj_parses.json"))
A = ap.parse_args()


def plain_text(root):
    ws = [w.replace("-LRB-", "(").replace("-RRB-", ")").replace("-LCB-", "{").replace("-RCB-", "}") for w in G.words(root)]
    t = P.text(("X", ws))
    return t.replace("``", '"').replace("''", '"').replace(" ,", ",").strip()


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def main():
    sents = [(f, k, root) for f, k, root in G.treebank_sentences(A.treebank)]
    if A.n:
        sents = sents[:A.n]
    say(f"== wsj_collect: {len(sents)} treebank sentences, rules {P.__file__}")
    rows, t0 = [], time.time()
    nlp_sp, nlp_st = V.spacy_model("en"), V.stanza_model("en")
    for j, (f, k, root) in enumerate(sents, 1):
        text = V.clean(plain_text(root))
        if not text:
            continue
        doc = nlp_sp(text)
        sdoc = nlp_st(text)
        row = dict(n=f"wsj|{f}|{k}", set="wsj", key_n=None, lang="en", file=f, k=k, text=text,
                   deps_spacy=V.tuples(P.from_spacy(doc)), deps_stanza=[V.tuples(P.from_stanza(x)) for x in sdoc.sentences], trees=[])
        for x in sdoc.sentences:
            if getattr(x, "constituency", None) is not None:
                row["trees"].append(P.from_stanza_tree(x.constituency))
        rows.append(row)
        if j in (25, 100) or j % 250 == 0 or j == len(sents):
            each = (time.time() - t0) / j
            say(f"   {j}/{len(sents)} parsed ({each:.2f}s each, about {each * (len(sents) - j) / 60:.0f} min left)")
    import importlib.metadata as md
    versions = {}
    for pkg in ("spacy", "stanza", "torch"):
        try:
            versions[pkg] = md.version(pkg)
        except Exception:                               # noqa: BLE001
            versions[pkg] = None
    out = Path(A.out); out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"meta": {"versions": versions, "made": time.strftime("%Y-%m-%d %H:%M"), "treebank": "NLTK Penn Treebank sample, wsj_0001-0199"},
               "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    say(f"== wrote {out} ({len(rows)} sentences)")


if __name__ == "__main__":
    main()
