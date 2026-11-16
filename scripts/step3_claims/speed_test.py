"""speed_test.py   Where the time goes in the full parse, and which speedups give exactly the same parses.

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 scripts/step3_claims/speed_test.py              150 of the 900 CLAY sentences, 50 per legislature
  python3 scripts/step3_claims/speed_test.py --n 300

Reads only. Nothing in outputs/full is touched, so it can run while the full run is going (the times will be a bit
slower than usual because the two share the processor, but the comparisons are made inside this one test).

1. Times each part of one sentence: the discourse parse, the sentence's constituency tree, and the trees for each
   discourse unit. Also checks this test reproduces the saved Nov 1 parses, so the comparisons below mean something.
2. English: the Stanza pipeline also runs lemmas and the dependency parse, which the claims never use. Parses every
   English sentence and unit with and without them and checks the constituency trees are the same.
3. French: spaCy is only there to split sentences and words for the Berkeley parser. Checks that leaving out its
   named entities and lemmas gives the same words and the same Berkeley trees.
4. A sentence with one discourse unit gets its tree twice (once as the sentence, once as the unit). Checks the two
   are the same and how much time the second parse costs.
5. Threads: the discourse and Stanza time at a few thread counts, and whether the parses stay the same. If fewer
   threads cost little, several copies can run side by side without slowing each other down.

Writes outputs/speed_test.json."""
import argparse, json, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
sys.path.insert(0, str(HERE))
import preds as P            # noqa: E402   loaded first so parse_corpus_v5 uses the same rules, as in run_full_corpus.py
sys.path.insert(1, str(PROJECT / "scripts" / "step2_parsers"))

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=150, help="sentences to test, split evenly across the three legislatures")
ap.add_argument("--thread-sample", type=int, default=30, help="sentences used for the thread test")
A = ap.parse_args()
sys.argv = [sys.argv[0]]                 # edu_collect reads its own arguments when imported
import parse_corpus_v5 as V              # noqa: E402
import edu_collect as C                  # noqa: E402


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def clock(f, *a):
    t = time.perf_counter()
    out = f(*a)
    return out, time.perf_counter() - t


# the sample: the first n/3 sentences of each legislature in the saved CLAY file
saved = json.load(open(PROJECT / "outputs" / "edu" / "more_parses.json", encoding="utf-8"))["rows"]
saved_units = json.load(open(PROJECT / "outputs" / "edu" / "edu_trees.json", encoding="utf-8"))
per = max(1, A.n // 3)
rows = []
for code in ("US", "ON", "QC"):
    rows += [r for r in saved if r["n"].split("|")[1] == code][:per]
say(f"{len(rows)} sentences ({sum(r['lang'] == 'en' for r in rows)} English, {sum(r['lang'] == 'fr' for r in rows)} French)")

# load every model before timing anything
for lang in ("en", "fr"):
    r = next(x for x in rows if x["lang"] == lang)
    V.rst_parse(r["text"], lang)
    C.tree_of(r["text"], lang)
report = {"sentences": len(rows)}


# 1. where the time goes, and whether this test reproduces the saved parses
say("1. timing each part")
t_rst = t_sent = t_units = 0.0
t_single = 0.0
n_units = n_single = 0
match = {"discourse": 0, "sentence_tree": 0, "unit_trees": 0}
fresh = []
for r in rows:
    text = V.clean(r["text"])
    (d, st), a = clock(V.rst_parse, text, r["lang"])
    tree, b = clock(C.tree_of, text, r["lang"])
    s = {"text": text, "lang": r["lang"], "disc_native": d, "trees": tree}
    units, c = clock(C.unit_trees, s)
    t_rst += a; t_sent += b; t_units += c
    edus = (d or {}).get("edus") or []
    n_units += max(1, len(edus))
    if len(edus) <= 1:
        n_single += 1
        t_single += c
    match["discourse"] += same(d, r.get("disc_native"))
    match["sentence_tree"] += same(tree, r.get("trees"))
    match["unit_trees"] += same(units, saved_units.get(r["n"]))
    fresh.append((r, s, units))
n = len(rows)
total = t_rst + t_sent + t_units
report["seconds_per_sentence"] = {"discourse": round(t_rst / n, 3), "sentence_tree": round(t_sent / n, 3),
                                  "unit_trees": round(t_units / n, 3), "all": round(total / n, 3)}
report["share_of_time"] = {"discourse": round(t_rst / total, 3), "sentence_tree": round(t_sent / total, 3),
                           "unit_trees": round(t_units / total, 3)}
report["reproduces_saved"] = {k: f"{v}/{n}" for k, v in match.items()}
say(f"   per sentence: discourse {t_rst / n:.2f}s, sentence tree {t_sent / n:.2f}s, unit trees {t_units / n:.2f}s "
    f"({n_units / n:.1f} units each); total {total / n:.2f}s")
say(f"   same as the saved Nov 1 parses: discourse {match['discourse']}/{n}, sentence tree {match['sentence_tree']}/{n}, "
    f"unit trees {match['unit_trees']}/{n}")


# 2. English Stanza without lemmas and the dependency parse
say("2. English Stanza without lemmas and dependencies")
import stanza                            # noqa: E402
full_en = V.stanza_model("en")
kept = [p for p in full_en.processors if p not in ("lemma", "depparse")]
light_en = stanza.Pipeline("en", processors=",".join(kept), tokenize_no_ssplit=True, verbose=False, download_method=None)
texts_en = []
for r, s, units in fresh:
    if r["lang"] == "en":
        texts_en.append(s["text"])
        for e in ((s["disc_native"] or {}).get("edus") or []):
            t = (e.get("text") or s["text"][e["start"]:e["end"]]).strip()
            if t:
                texts_en.append(t)


def const(nlp, t):
    return [P.from_stanza_tree(x.constituency) for x in nlp(t).sentences if getattr(x, "constituency", None) is not None]


t_full = t_light = 0.0
eq = 0
for t in texts_en:
    a, x = clock(const, full_en, t)
    b, y = clock(const, light_en, t)
    t_full += x; t_light += y
    eq += same(a, b)
report["english_light_stanza"] = {"processors_now": list(full_en.processors), "processors_light": kept,
                                  "texts": len(texts_en), "same_trees": f"{eq}/{len(texts_en)}",
                                  "seconds_now": round(t_full, 1), "seconds_light": round(t_light, 1)}
say(f"   {len(texts_en)} English texts: same trees {eq}/{len(texts_en)}; {t_full:.1f}s now, {t_light:.1f}s without "
    f"({1 - t_light / max(t_full, 1e-9):.0%} less)")


# 3. French spaCy without named entities and lemmas
say("3. French spaCy without named entities and lemmas")
import spacy                             # noqa: E402
full_fr = V.spacy_model("fr")
drop = [p for p in ("ner", "lemmatizer") if p in full_fr.pipe_names]
light_fr = spacy.load("fr_core_news_lg", exclude=drop)
bp = V.berkeley()
texts_fr = []
for r, s, units in fresh:
    if r["lang"] == "fr":
        texts_fr.append(s["text"])
        for e in ((s["disc_native"] or {}).get("edus") or []):
            t = (e.get("text") or s["text"][e["start"]:e["end"]]).strip()
            if t:
                texts_fr.append(t)


def words(doc):
    return [[w.text for w in sent if not w.is_space] for sent in doc.sents]


t_full = t_light = 0.0
eq_words = eq_trees = 0
for t in texts_fr:
    a, x = clock(full_fr, t)
    b, y = clock(light_fr, t)
    t_full += x; t_light += y
    eq_words += words(a) == words(b)
    if bp is not None:
        eq_trees += same(V.berkeley_trees(bp, V.BEN["mod"], a)[0], V.berkeley_trees(bp, V.BEN["mod"], b)[0])
report["french_light_spacy"] = {"pipes_now": list(full_fr.pipe_names), "left_out": drop, "texts": len(texts_fr),
                                "same_words": f"{eq_words}/{len(texts_fr)}", "same_trees": f"{eq_trees}/{len(texts_fr)}",
                                "spacy_seconds_now": round(t_full, 1), "spacy_seconds_light": round(t_light, 1)}
say(f"   {len(texts_fr)} French texts: same words {eq_words}/{len(texts_fr)}, same Berkeley trees {eq_trees}/{len(texts_fr)}; "
    f"spaCy {t_full:.1f}s now, {t_light:.1f}s without")


# 4. one-unit sentences: the unit tree is the sentence tree parsed a second time
say("4. one-unit sentences")
one = [(r, s, units) for r, s, units in fresh if len((s["disc_native"] or {}).get("edus") or []) <= 1]
eq = sum(len(units) == 1 and same(units[0], s["trees"]) for r, s, units in one)
report["one_unit_sentences"] = {"count": len(one), "unit_tree_same_as_sentence_tree": f"{eq}/{len(one)}",
                                "seconds_per_sentence_saved_overall": round(t_single / n, 3)}
say(f"   {len(one)} of {n} sentences have one unit; unit tree same as sentence tree {eq}/{len(one)}; "
    f"reusing it saves {t_single / n:.2f}s per sentence on average")


# 5. thread counts
say("5. threads")
import torch                             # noqa: E402
start = torch.get_num_threads()
sub = fresh[:: max(1, len(fresh) // A.thread_sample)][:A.thread_sample]
base = None
report["threads"] = {}
for k in sorted({start, max(1, start // 2), max(1, start // 3), 2}, reverse=True):
    torch.set_num_threads(k)
    t0 = time.perf_counter()
    out = []
    for r, s, units in sub:
        d, st = V.rst_parse(s["text"], r["lang"])
        out.append((d, C.tree_of(s["text"], r["lang"])))
    secs = (time.perf_counter() - t0) / len(sub)
    if base is None:
        base = out
    eq = sum(same(a, b) for a, b in zip(out, base))
    report["threads"][k] = {"seconds_per_sentence": round(secs, 3), "same_as_default": f"{eq}/{len(sub)}"}
    say(f"   {k} threads: {secs:.2f}s per sentence (discourse and sentence tree only); same as {start} threads {eq}/{len(sub)}")
torch.set_num_threads(start)

out = PROJECT / "outputs" / "speed_test.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
say(f"written to {out}")
