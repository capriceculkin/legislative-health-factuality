"""parity_collect.py   Runs every parser on three sets of sentences and saves the raw parses, so English and French can
be scored side by side with any version of the rules (parity_score.py), without parsing again.

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 ~/.parity_v6/parity_collect.py

The sets:
  test     the parallel test sentences (parallel_tests.py): one construction at a time, English and French
  heldout  the 30 held-out sentences (heldout.json), never used while the rules were written
  sample   the 100-sentence sample, parsed again: checks that this Mac still gives the saved parses (pc.json)

For each sentence it saves: spaCy and Stanza dependency parses, the production constituency trees (Stanza English,
Berkeley benepar_fr2 French), the Berkeley English trees (benepar_en3) so both languages can also be run with the
same constituency parser, and the discourse parse twice for French: with the ANNODIS relation set it uses now, and
with the RST-DT set English uses, so both languages can be run with the same relations.

Writes ~/Desktop/next_steps/oct20/parity_parses.json, then prints the v6 scores. Reads only; data/ is not touched.
Takes about 10 to 20 minutes, most of it the discourse parser."""
import json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
V4 = PROJECT / "scripts" / "step2_parsers"
OUT = Path.home() / "Desktop" / "next_steps" / "oct20"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(HERE))
import preds as P            # noqa: E402   the v6 rules, loaded first so parse_corpus_v5 uses them
import combine_lib as C      # noqa: E402
assert "PARITY_V6" in open(P.__file__, encoding="utf-8").read(), f"wrong preds.py loaded: {P.__file__}"
sys.path.insert(1, str(V4))
import parse_corpus_v5 as V  # noqa: E402   model loading and the parse calls, unchanged from the full run
assert V.P is P and V.C is C, "parse_corpus_v5 picked up another copy of the rules"
import parallel_tests as PT  # noqa: E402


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def sentences():
    out = []
    for t in PT.T:
        for L in ("en", "fr"):
            out.append(dict(n=f"test|{t['id']}|{L}", set="test", key_n=t["id"], lang=L, text=t[L]["text"]))
    for h in json.load(open(HERE / "heldout.json", encoding="utf-8")):
        out.append(dict(n=f"heldout|{h['h']}", set="heldout", key_n=h["h"], lang=h["lang"], text=h["text"], sentence_id=h.get("sentence_id")))
    import gold, gold2
    key = {**gold.G, **gold2.G2}
    for r in json.load(open(HERE / "pc.json", encoding="utf-8"))["rows"]:
        if r["n"] in key:
            out.append(dict(n=f"sample|{r['n']}", set="sample", key_n=r["n"], lang=r["lang"], text=r["text"], sentence_id=r.get("sentence_id")))
    return out


def en3_parser():
    """The Berkeley parser's English model, through the same fixes as the French one. None if it will not load."""
    try:
        V.berkeley()                                    # applies benepar_fix.prepare()
        benepar = V.BEN.get("mod")
        if benepar is None:
            import benepar_fix
            benepar = benepar_fix.prepare()
        try:
            return benepar.Parser("benepar_en3"), benepar
        except LookupError:
            say("   downloading benepar_en3 (once, about 100 MB)")
            benepar.download("benepar_en3", quiet=True, raise_on_error=True)
            return benepar.Parser("benepar_en3"), benepar
    except Exception as e:                              # noqa: BLE001
        say(f"   benepar_en3 would not load ({type(e).__name__}: {str(e)[:200]}); the same-parser comparison is skipped")
        return None, None


def main():
    say(f"== parity_collect: rules {P.__file__}")
    sents = sentences()
    say(f"   {len(sents)} sentences: " + ", ".join(f"{s} {sum(x['set'] == s for x in sents)}" for s in ("test", "heldout", "sample")))
    en3, ben = en3_parser()
    rows, t0 = [], time.time()
    for k, s in enumerate(sents, 1):
        lang, text = s["lang"], V.clean(s["text"])
        doc = V.spacy_model(lang)(text)
        sdoc = V.stanza_model(lang)(text)
        toks = P.from_spacy(doc)
        row = dict(s, text=text, deps_spacy=V.tuples(toks), deps_stanza=[V.tuples(P.from_stanza(x)) for x in sdoc.sentences], trees=[])
        if lang == "en":
            for x in sdoc.sentences:
                if V.CONST.get("en") and getattr(x, "constituency", None) is not None:
                    row["trees"].append(P.from_stanza_tree(x.constituency))
            if en3 is not None:
                tr, fails = V.berkeley_trees(en3, ben, doc)
                row["trees_en3"], row["trees_en3_failed"] = tr, fails
        else:
            bp = V.berkeley()
            if bp is not None:
                row["trees"], row["tree_parts_failed"] = V.berkeley_trees(bp, V.BEN["mod"], doc)
        d, st = V.rst_parse(text, lang)
        row["disc_native"], row["disc_native_status"] = d, st
        if lang == "fr":
            keep = V.INV["fr"]
            V.INV["fr"] = "eng.rst.rstdt"
            try:
                d2, st2 = V.rst_parse(text, "fr")
            finally:
                V.INV["fr"] = keep
            row["disc_rstdt"], row["disc_rstdt_status"] = d2, st2
        rows.append(row)
        if k % 20 == 0 or k == len(sents):
            say(f"   {k}/{len(sents)} parsed ({(time.time() - t0) / k:.1f}s each)")

    # does this Mac still give the saved parses for the sample?
    saved = {f"sample|{r['n']}": r for r in json.load(open(HERE / "pc.json", encoding="utf-8"))["rows"]}
    same = {"spacy": 0, "stanza": 0, "n": 0}
    for r in rows:
        o = saved.get(r["n"])
        if o is None:
            continue
        same["n"] += 1
        same["spacy"] += [tuple(x[:6]) for x in r["deps_spacy"]] == [tuple(x[:6]) for x in o["deps_spacy"]]
        same["stanza"] += [[tuple(x[:6]) for x in s_] for s_ in r["deps_stanza"]] == [[tuple(x[:6]) for x in s_] for s_ in o["deps_stanza"]]
    import importlib.metadata as md
    versions = {}
    for pkg in ("spacy", "stanza", "benepar", "isanlp_rst", "torch", "transformers"):
        try:
            versions[pkg] = md.version(pkg)
        except Exception:                               # noqa: BLE001
            versions[pkg] = None
    meta = {"versions": versions, "saved_parses_reproduced": same, "en3_loaded": en3 is not None,
            "made": time.strftime("%Y-%m-%d %H:%M")}
    path = OUT / "parity_parses.json"
    json.dump({"meta": meta, "rows": rows}, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    say(f"== wrote {path}")
    say(f"   saved parses reproduced on this Mac: spaCy {same['spacy']}/{same['n']}, Stanza {same['stanza']}/{same['n']}")

    import subprocess
    for extra in ([], ["--disc", "rstdt"], ["--const", "en3"]):
        if extra == ["--const", "en3"] and en3 is None:
            continue
        r = subprocess.run([sys.executable, str(HERE / "parity_score.py"), str(HERE), str(path)] + extra
                           + ["--json", str(OUT / ("parity_scores" + "".join("_" + x.strip("-") for x in extra) + ".json"))],
                           capture_output=True, text=True)
        print(r.stdout[-6000:], r.stderr[-2000:])
    say("== done. Send parity_parses.json (and the printout) to the chat.")


if __name__ == "__main__":
    main()
