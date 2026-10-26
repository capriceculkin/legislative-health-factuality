"""edu_collect.py [--more 20]   Discourse first, on this Mac, with the real parsers (design from the Oct 22 meeting).

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 scripts/v6/edu_collect.py --more 20

1. For the 220 sentences already parsed on Oct 19 (data/parity_oct19/parity_parses.json): each discourse unit is
   parsed again on its own by the constituency parser (Stanza for English, Berkeley benepar_fr2 for French), so each
   unit has its own tree instead of a piece of the sentence's tree.
2. With --more N: N new sentences from each legislature (US House, Ontario, Quebec), drawn at random (seed 20261026)
   from data/dbpedia_pipeline/*/sentences_v3.json, leaving out sentences already in the answer keys and quoted bill
   text ('(A) Employer coverage ...--In the case of'). Each one gets the
   discourse parse, the sentence's constituency tree, and a tree for every unit. These have no answer key; they are for
   looking at by hand and for the figures.

Writes outputs/edu/edu_trees.json (unit trees for every sentence) and outputs/edu/more_parses.json (the new sentences,
in the same shape as parity_parses.json). The dependency parsers are not run. About 15 to 30 minutes."""
import argparse, json, random, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
sys.path.insert(0, str(HERE))
import preds as P            # noqa: E402   the v6 rules, loaded first so parse_corpus_v5 uses them
import combine_lib as C      # noqa: E402
import edu_pipeline as E     # noqa: E402   only for is_bill_text, shared with the notebook so both draw the same sentences
sys.path.insert(1, str(PROJECT / "scripts" / "v4"))
import parse_corpus_v5 as V  # noqa: E402   the same models and settings as the full run
assert V.P is P, "parse_corpus_v5 picked up another copy of the rules"

ap = argparse.ArgumentParser()
ap.add_argument("--more", type=int, default=0)
ap.add_argument("--parses", default=str(PROJECT / "data" / "parity_oct19" / "parity_parses.json"))
A = ap.parse_args()
OUT = PROJECT / "outputs" / "edu"
OUT.mkdir(parents=True, exist_ok=True)
JUR = {"US": "us", "ON": "ontario", "QC": "quebec"}


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def tree_of(text, lang):
    """The constituency tree(s) of one piece of text, read the same way as the full run."""
    if lang == "en":
        doc = V.stanza_model("en")(text)
        return [P.from_stanza_tree(x.constituency) for x in doc.sentences if getattr(x, "constituency", None) is not None]
    bp = V.berkeley()
    if bp is None:
        return []
    trees, _ = V.berkeley_trees(bp, V.BEN["mod"], V.spacy_model("fr")(text))
    return trees


def unit_trees(row):
    d = row.get("disc_native") or {}
    edus = d.get("edus") or [{"text": row["text"], "start": 0, "end": len(row["text"])}]
    out = []
    for e in edus:
        t = (e.get("text") or row["text"][e["start"]:e["end"]]).strip()
        try:
            out.append(tree_of(t, row["lang"]) if t else [])
        except Exception as ex:                          # noqa: BLE001
            say(f"   unit could not be parsed ({type(ex).__name__}): {t[:60]}")
            out.append([])
    return out


def norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def more_sentences(n, taken):
    rnd = random.Random(20261026)
    out = []
    for code, j in JUR.items():
        p = PROJECT / "data" / "dbpedia_pipeline" / j / "sentences_v3.json"
        recs = [x for x in json.load(open(p, encoding="utf-8")) if x.get("sentence_id") and x.get("text")]
        recs = [x for x in recs if x["sentence_id"] not in taken and 8 <= len(x["text"].split()) <= 60 and not E.is_bill_text(x["text"])]
        rnd.shuffle(recs)
        lang = "fr" if j == "quebec" else "en"
        for k, x in enumerate(recs[:n], 1):
            out.append({"n": f"more|{code}|{k}", "set": "more", "lang": x.get("lang") if x.get("lang") in ("en", "fr") else lang,
                        "text": V.clean(x["text"]), "sentence_id": x["sentence_id"]})
        say(f"   {j}: {min(n, len(recs))} new sentences drawn from {len(recs)}")
    return out


def main():
    rows = json.load(open(A.parses, encoding="utf-8"))["rows"]
    say(f"== edu_collect: {len(rows)} saved sentences; rules {P.__file__}")
    trees, t0 = {}, time.time()
    for k, r in enumerate(rows, 1):
        trees[r["n"]] = unit_trees(r)
        if k % 20 == 0 or k == len(rows):
            say(f"   {k}/{len(rows)} sentences, every unit parsed ({(time.time() - t0) / k:.1f}s each)")
    more = []
    if A.more:
        taken = {r.get("sentence_id") for r in rows}
        for k, s in enumerate(more_sentences(A.more, taken), 1):
            d, st = V.rst_parse(s["text"], s["lang"])
            s["disc_native"], s["disc_native_status"] = d, st
            s["trees"] = tree_of(s["text"], s["lang"])
            trees[s["n"]] = unit_trees(s)
            more.append(s)
            if k % 10 == 0:
                say(f"   {k} new sentences parsed")
    json.dump(trees, open(OUT / "edu_trees.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"made": time.strftime("%Y-%m-%d %H:%M"), "rows": more}, open(OUT / "more_parses.json", "w", encoding="utf-8"), ensure_ascii=False)
    say(f"== wrote {OUT / 'edu_trees.json'} ({len(trees)} sentences) and {OUT / 'more_parses.json'} ({len(more)} new)")


if __name__ == "__main__":
    main()
