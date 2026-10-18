#!/usr/bin/env python3
"""parse_corpus_v5.py   Every predication from every sentence of a jurisdiction, the way the 100-sentence sample was
done on Oct 15: two dependency parses (spaCy, Stanza) and a constituency parse (Stanza for English, the Berkeley
parser's French Treebank model for French), a predication kept when at least two of the three produce it, and the
discourse parse (IsaNLP UniRST: RST-DT relations for English, ANNODIS for French) re-reading each stated line.

Two ways to run it (from the project folder, with the venv active):

  python3 scripts/v3/parse_corpus_v5.py us --sample 300
      300 random US sentences (seed 20261019): runs everything, prints seconds per sentence for each tool, the
      projected hours for the whole corpus, and the claim yield. Writes ~/Desktop/next_steps/oct19/sample_us.jsonl
      and timing_us.json. Nothing in data/ changes.

  python3 scripts/v3/parse_corpus_v5.py us
      the whole corpus: data/dbpedia_pipeline/us/sentences_v3.json -> data/dbpedia_pipeline/us/statements_v5.jsonl,
      one line per sentence, written as it goes. Stopping it (Ctrl-C, sleep, crash) loses nothing: run the same
      command again and it continues from the last line written.

Options:  --rst multi (default: discourse parse only where the vote found two or more predications, or the sentence
          has a speech verb; the parse changes nothing elsewhere)  --rst all  --rst none
          --batch 32 (sentences per Stanza batch)   --seed 20261019   --limit N (stop after N new sentences)
Reads only sentences_v3.json; never touches predications_v3.json or anything else."""
import argparse, json, os, random, signal, sys, time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("HF_HUB_OFFLINE", "1")           # the discourse model is already on this Mac; never wait on the network
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import preds as P
import combine_lib as C

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
DESK = Path(os.environ.get("OCT19_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct19")))
DEFAULT_LANG = {"ontario": "en", "quebec": "fr", "us": "en"}
INV = {"en": "eng.rst.rstdt", "fr": "fra.sdrt.annodis"}
SPEECH_WORDS = set(P.SPEECH) | set(C.SOURCE_WORDS)
VERSION = "v5 (Oct 19): three parses, two-of-three vote, discourse re-read; same rules as the Oct 15 sample"


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def clean(t):
    return " ".join(str(t).replace("``", "“").replace("''", "”").split())


# ---------------------------------------------------------------- models, loaded only when a language needs them
SP, ST, CONST = {}, {}, {}
BEN = {}
RST = {}
TIMES = Counter()
LOAD_SECS = {}


def spacy_model(lang):
    if lang not in SP:
        import spacy
        t = time.perf_counter()
        SP[lang] = spacy.load({"en": "en_core_web_lg", "fr": "fr_core_news_lg"}[lang])
        LOAD_SECS[f"spacy_{lang}"] = round(time.perf_counter() - t, 1)
        meta = getattr(SP[lang], "meta", {}) or {}
        say(f"   loaded spaCy {lang} ({meta.get('name', '?')} {meta.get('version', '?')}) in {LOAD_SECS[f'spacy_{lang}']}s")
    return SP[lang]


def stanza_model(lang):
    """Stanza dependency parse, plus the constituency parse for English (Stanza has no French constituency model)."""
    if lang not in ST:
        import stanza
        t = time.perf_counter()
        base = "tokenize,mwt,pos,lemma,depparse"
        tries = [base + ",constituency", base] if lang == "en" else [base, "tokenize,pos,lemma,depparse"]
        err = None
        for procs in tries:
            for how in ("local", "download"):           # the models are already on this Mac; download only if one is missing
                try:
                    if how == "local":
                        ST[lang] = stanza.Pipeline(lang, processors=procs, tokenize_no_ssplit=True, verbose=False, download_method=None)
                    else:
                        stanza.download(lang, processors=procs, verbose=False)
                        ST[lang] = stanza.Pipeline(lang, processors=procs, tokenize_no_ssplit=True, verbose=False)
                    CONST[lang] = "constituency" in procs
                    break
                except Exception as e:                  # noqa: BLE001
                    err = e
            if lang in ST:
                break
        if lang not in ST:
            sys.exit(f"Stanza {lang} would not load: {type(err).__name__}: {err}. Send this to the chat. Nothing changed.")
        LOAD_SECS[f"stanza_{lang}"] = round(time.perf_counter() - t, 1)
        say(f"   loaded Stanza {lang} {stanza.__version__} (constituency: {'yes' if CONST[lang] else 'no'}) in {LOAD_SECS[f'stanza_{lang}']}s")
    return ST[lang]


def berkeley():
    """The Berkeley parser's French model, through the same patches as the Oct 15 run."""
    if "parser" not in BEN:
        import benepar_fix
        t = time.perf_counter()
        try:
            benepar = benepar_fix.prepare()
            parser = benepar_fix.get_parser(benepar, lambda m: say(m))
            benepar_fix.self_test(benepar, parser)
        except Exception as e:                          # noqa: BLE001
            say(f"   the Berkeley parser would not load ({type(e).__name__}: {str(e)[:200]}); French sentences use the two dependency parses only")
            BEN["parser"] = None; BEN["mod"] = None
            return None
        BEN["parser"], BEN["mod"] = parser, benepar
        LOAD_SECS["berkeley"] = round(time.perf_counter() - t, 1)
        say(f"   loaded the Berkeley parser (benepar_fr2) in {LOAD_SECS['berkeley']}s" + (f"; fixes: {'; '.join(benepar_fix.NOTES)}" if benepar_fix.NOTES else ""))
    return BEN["parser"]


def discourse_model():
    if "parser" not in RST:
        t = time.perf_counter()
        try:
            from isanlp_rst.parser import Parser
            RST["parser"] = Parser(hf_model_name="tchewik/isanlp_rst_v3", hf_model_version="unirst", relinventory="eng.rst.rstdt", cuda_device=-1)
            RST["pred"] = RST["parser"].predictor
        except Exception as e:                          # noqa: BLE001
            say(f"   the discourse parser would not load ({type(e).__name__}: {str(e)[:200]}); stated/embedded comes from the syntax alone")
            RST["parser"] = None
            return None
        LOAD_SECS["discourse"] = round(time.perf_counter() - t, 1)
        say(f"   loaded the discourse parser (UniRST) in {LOAD_SECS['discourse']}s")
    return RST["parser"]


# ---------------------------------------------------------------- the parses
def to_lists(t):
    if isinstance(t, str):
        return t
    return [t.label(), [to_lists(k) for k in t]]


def rst_walk(node, edus, rels):
    if node.left is None or node.relation == "elementary":
        edus.append({"text": node.text, "start": node.start, "end": node.end})
        return [len(edus) - 1]
    a = rst_walk(node.left, edus, rels)
    b = rst_walk(node.right, edus, rels)
    rels.append({"left": [a[0], a[-1]], "right": [b[0], b[-1]], "relation": node.relation, "nuclearity": node.nuclearity})
    return a + b


def rst_parse(text, lang):
    parser = discourse_model()
    if parser is None:
        return None, "no discourse parser"
    RST["pred"].relinventory_idx = RST["pred"].dataset_names.index(INV[lang])

    def once(t):
        res = parser(t)
        edus, rels = [], []
        rst_walk(res["rst"][0], edus, rels)
        return {"edus": edus, "relations": rels, "inventory": INV[lang]}
    try:
        return once(text), "ok"
    except Exception as e:                              # noqa: BLE001
        try:                                            # a dash glued to words can break the parser's alignment
            return once(text.replace("—", " — ").replace("–", " – ")), "ok (dashes spaced)"
        except Exception:                               # noqa: BLE001
            return None, f"error: {type(e).__name__}: {str(e)[:80]}"


def stanza_bulk(nlp, texts):
    """One Stanza call for a batch of sentences (much faster than one at a time); falls back to one at a time."""
    try:
        from stanza.models.common.doc import Document
        docs = nlp.bulk_process([Document([], text=t) for t in texts])
        if len(docs) == len(texts):
            return docs
    except Exception:                                   # noqa: BLE001
        pass
    return [nlp(t) for t in texts]


def berkeley_trees(parser, benepar, spacy_doc):
    trees, fails = [], 0
    for sent in spacy_doc.sents:
        words = [w.text for w in sent if not w.is_space]
        if not words:
            continue
        try:
            trees.append(to_lists(parser.parse(benepar.InputSentence(words=words))))
        except Exception:                               # noqa: BLE001
            fails += 1
    return trees, fails


def needs_rst(policy, text, agreed):
    if policy == "none":
        return False
    if policy == "all":
        return True
    if len(agreed) >= 2:
        return True
    words = {w.strip(",.;:\"“”«»()").lower() for w in text.split()}
    return bool(words & SPEECH_WORDS)


def apply_rst(agreed, review, r, d):
    """The discourse parse's reading of each predication (the same steps as combine_lib.combine)."""
    so, _ = C.offsets(r["deps_spacy"])
    st = [t for sent in r["deps_stanza"] for t in sent]
    sto, _ = C.offsets(st)
    sat, attributed = C.edu_roles(d) if d else ({}, set())
    for p in agreed + review:
        off = None
        if "spacy" in p["at_by"] and p["at_by"]["spacy"] < len(so):
            off = so[p["at_by"]["spacy"]]
        elif "stanza" in p["at_by"] and p["at_by"]["stanza"] < len(sto):
            off = sto[p["at_by"]["stanza"]]
        first = p["verb"].split(" ")[0] if p["verb"] else ""
        hits = [k for k in range(len(r["text"])) if r["text"].startswith(first, k)] if first else []
        if hits:
            before = [k for k in hits if off is None or k <= off]
            off = max(before) if before else min(hits)
        i = C.edu_of(off, d["edus"]) if (d and off is not None) else None
        p["edu"] = i
        p["edu_text"] = d["edus"][i]["text"] if i is not None else ""
        p["kind_parser"] = p["kind"]
        p["kind_rst"], p["rst_why"] = C.rst_kind(p, i, d, sat, attributed) if d else (p["kind"], "no discourse parse")


def tuples(toks):
    return [(t.i, t.text, t.lemma, t.upos, t.dep, t.head, t.feats, t.ws, t.disp) for t in toks]


def process_batch(batch, lang, rst_policy, keep_secs):
    """A batch of sentence records of one language -> one output row per record."""
    texts = [clean(x["text"]) for x in batch]
    t = time.perf_counter()
    docs = list(spacy_model(lang).pipe(texts, batch_size=64))
    TIMES["spacy"] += time.perf_counter() - t
    t = time.perf_counter()
    sdocs = stanza_bulk(stanza_model(lang), texts)
    TIMES["stanza"] += time.perf_counter() - t
    bparser = berkeley() if lang == "fr" else None
    rows = []
    for rec, text, doc, sdoc in zip(batch, texts, docs, sdocs):
        secs = {}
        t = time.perf_counter()
        toks = P.from_spacy(doc)
        deps_spacy = tuples(toks)
        deps_stanza = []
        trees, tree_fail = [], 0
        for s in sdoc.sentences:
            deps_stanza.append(tuples(P.from_stanza(s)))
            if lang == "en" and CONST.get("en") and getattr(s, "constituency", None) is not None:
                trees.append(P.from_stanza_tree(s.constituency))     # read from the tree object, so a "(" in the text cannot break it
        if lang == "fr" and bparser is not None:
            t2 = time.perf_counter()
            trees, tree_fail = berkeley_trees(bparser, BEN["mod"], doc)
            secs["berkeley"] = time.perf_counter() - t2
            TIMES["berkeley"] += secs["berkeley"]
        r = {"n": rec["sentence_id"], "lang": lang, "text": text, "deps_spacy": deps_spacy, "deps_stanza": deps_stanza, "trees": trees}
        row = {"sentence_id": rec["sentence_id"], "bill_key": rec.get("bill_key"), "session": rec.get("session"), "date": rec.get("date"),
               "lang": lang, "text": text}
        if text.endswith("?") or len(text.split()) < 3:
            row.update(methods=[], statements=[], for_review=[], note="question" if text.endswith("?") else "too short", rst="skipped")
            rows.append(row)
            continue
        try:
            out = C.run(r, P)
        except Exception as e:                          # noqa: BLE001
            row.update(methods=[], statements=[], for_review=[], note=f"rules failed: {type(e).__name__}: {str(e)[:80]}", rst="skipped")
            rows.append(row)
            continue
        methods = ["spacy", "stanza"] + (["const"] if trees else [])
        agreed, review = C.vote(out, methods, need=2)
        secs["rules"] = time.perf_counter() - t
        TIMES["rules"] += secs["rules"]
        d, status = None, "not needed"
        row["rst_multi"] = needs_rst("multi", text, agreed)    # what the default policy would do with this sentence
        if needs_rst(rst_policy, text, agreed):
            t = time.perf_counter()
            d, status = rst_parse(text, lang)
            secs["discourse"] = time.perf_counter() - t
            TIMES["discourse"] += secs["discourse"]
            TIMES["discourse_n"] += 1
        apply_rst(agreed, review, r, d)
        apps = [dict(a, kind="asserted", how="apposition (renames the noun before the comma)", found_by=["spacy"], source="apposition")
                for a in P.appositions(toks)]
        st = [dict(subject=p["subject"], verb=p["verb"], object=p["object"], kind=p["kind_rst"], kind_parser=p["kind_parser"], how=p["how"],
                   rst=p["rst_why"], negated=p["negated"], hedged=p["hedged"], found_by=p["found_by"], source="agreed") for p in agreed]
        row.update(methods=methods, statements=st + [{k: a[k] for k in ("subject", "verb", "object", "kind", "how", "found_by", "source")}
                                                     | {"kind_parser": "asserted", "rst": "apposition", "negated": False, "hedged": False} for a in apps],
                   for_review=[dict(subject=p["subject"], verb=p["verb"], object=p["object"], kind=p["kind"], found_by=p["found_by"]) for p in review],
                   rst=status, tree_parts_failed=tree_fail)
        if keep_secs:
            row["secs"] = {k: round(v, 4) for k, v in secs.items()}
        rows.append(row)
    return rows


# ---------------------------------------------------------------- files
def load_sentences(j):
    p = ROOT / "data" / "dbpedia_pipeline" / j / "sentences_v3.json"
    if not p.exists():
        sys.exit(f"{p} is not there. Run from the project folder. Nothing changed.")
    recs = json.load(open(p, encoding="utf-8"))
    for x in recs:
        x["lang"] = x.get("lang") if x.get("lang") in ("en", "fr") else DEFAULT_LANG[j]
    return recs, p


def done_ids(path):
    ids = set()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                k = line.find('"sentence_id": "')
                if k >= 0:
                    e = line.find('"', k + 16)
                    ids.add(line[k + 16:e])
    return ids


class Writer:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "a", encoding="utf-8")
        self.n = 0

    def write(self, row):
        self.f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.n += 1
        if self.n % 50 == 0:
            self.f.flush()

    def close(self):
        self.f.flush(); self.f.close()


# ---------------------------------------------------------------- reports
def yield_report(rows, old_claims=None):
    n = len(rows)
    st = [s for r in rows for s in r["statements"]]
    kinds = Counter(s["kind"] for s in st)
    with_stated = sum(1 for r in rows if any(s["kind"] == "asserted" for s in r["statements"]))
    with_any = sum(1 for r in rows if r["statements"])
    review = sum(len(r["for_review"]) for r in rows)
    changed = sum(1 for s in st if s.get("source") == "agreed" and s["kind"] != s["kind_parser"])
    rst_run = sum(1 for r in rows if r.get("rst", "").startswith("ok"))
    rep = {"sentences": n, "predications": len(st), "per_sentence": round(len(st) / max(1, n), 2),
           "stated": kinds.get("asserted", 0), "embedded": kinds.get("embedded", 0), "reported": kinds.get("reported", 0),
           "appositions": sum(1 for s in st if s.get("source") == "apposition"),
           "sentences_with_a_stated_predication": with_stated, "sentences_with_any_predication": with_any,
           "lines_sent_to_review (one parser only)": review, "questions_or_too_short": sum(1 for r in rows if r.get("note") in ("question", "too short")),
           "discourse_parsed": rst_run, "stated_lines_re_read_by_discourse": changed, "negated": sum(1 for s in st if s.get("negated")),
           "hedged": sum(1 for s in st if s.get("hedged")), "tree_parts_failed": sum(r.get("tree_parts_failed", 0) for r in rows)}
    if old_claims is not None:
        had = sum(1 for r in rows if r["sentence_id"] in old_claims)
        rep["old_extractor_had_a_claim"] = had
    return rep


def timing_report(j, n_done, n_total, rows):
    per = {k: TIMES[k] / max(1, n_done) for k in ("spacy", "stanza", "berkeley", "rules")}
    rst_n = TIMES["discourse_n"]
    per["discourse (per sentence it ran on)"] = TIMES["discourse"] / max(1, rst_n)
    share_multi = sum(1 for r in rows if r.get("rst_multi")) / max(1, n_done)
    parse_h = n_total * (per["spacy"] + per["stanza"] + per["berkeley"] + per["rules"]) / 3600
    rst_all_h = n_total * per["discourse (per sentence it ran on)"] / 3600
    rst_multi_h = rst_all_h * share_multi
    return {"jurisdiction": j, "sample": n_done, "corpus": n_total, "seconds_per_sentence": {k: round(v, 4) for k, v in per.items()},
            "model_load_seconds": LOAD_SECS, "share_of_sentences_the_discourse_parse_would_run_on (multi policy)": round(share_multi, 3),
            "projected_hours": {"syntax (spaCy, Stanza, Berkeley, rules)": round(parse_h, 1), "discourse on every sentence": round(rst_all_h, 1),
                                "discourse on multi-predication sentences only": round(rst_multi_h, 1),
                                "total with --rst multi": round(parse_h + rst_multi_h, 1), "total with --rst all": round(parse_h + rst_all_h, 1)},
            "threads": os.environ.get("PARSE_THREADS", "default")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jurisdiction", choices=["us", "ontario", "quebec"])
    ap.add_argument("--sample", type=int, default=0, help="random sentences to time (0 = the whole corpus)")
    ap.add_argument("--seed", type=int, default=20261019)
    ap.add_argument("--rst", choices=["multi", "all", "none"], default="multi")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new sentences (0 = no limit)")
    a = ap.parse_args()
    j = a.jurisdiction
    if os.environ.get("PARSE_THREADS"):
        try:
            import torch
            torch.set_num_threads(int(os.environ["PARSE_THREADS"]))
        except Exception:                               # noqa: BLE001
            pass
    say(f"== parse_corpus_v5 {j}: {VERSION}")
    recs, src = load_sentences(j)
    say(f"   {len(recs):,} sentences in {src.relative_to(ROOT)}; languages {dict(Counter(x['lang'] for x in recs))}")
    sample_mode = a.sample > 0
    if sample_mode:
        rng = random.Random(a.seed)
        idx = sorted(rng.sample(range(len(recs)), min(a.sample, len(recs))))
        todo = [recs[i] for i in idx]
        out_path = DESK / f"sample_{j}.jsonl"
        if out_path.exists():
            out_path.unlink()
        rst_policy = "all"                              # time it on every sampled sentence; the report says what 'multi' would skip
        say(f"   sample of {len(todo)} sentences (seed {a.seed}); the discourse parse runs on all of them so it can be timed")
    else:
        out_path = ROOT / "data" / "dbpedia_pipeline" / j / "statements_v5.jsonl"
        done = done_ids(out_path)
        todo = [x for x in recs if x["sentence_id"] not in done]
        rst_policy = a.rst
        say(f"   {len(done):,} already written to {out_path.relative_to(ROOT)}; {len(todo):,} to do; discourse policy: {rst_policy}")
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        say("   nothing to do"); return
    writer = Writer(out_path)
    stop = {"now": False}

    def on_signal(*_):
        stop["now"] = True
        say("   stopping after this batch (run the same command again to continue)")
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    rows_kept = []                                      # sample mode keeps rows in memory for the report
    t0, n_done, every = time.time(), 0, (50 if sample_mode else 200)
    next_report = every
    # batches of one language, in file order
    i = 0
    while i < len(todo) and not stop["now"]:
        lang = todo[i]["lang"]
        batch = []
        while i < len(todo) and len(batch) < a.batch and todo[i]["lang"] == lang:
            batch.append(todo[i]); i += 1
        try:
            rows = process_batch(batch, lang, rst_policy, keep_secs=sample_mode)
        except SystemExit:
            raise
        except Exception as e:                          # noqa: BLE001
            say(f"   batch failed ({type(e).__name__}: {str(e)[:120]}); doing its sentences one at a time")
            rows = []
            for rec in batch:
                try:
                    rows += process_batch([rec], lang, rst_policy, keep_secs=sample_mode)
                except Exception as e2:                 # noqa: BLE001
                    rows.append({"sentence_id": rec["sentence_id"], "bill_key": rec.get("bill_key"), "session": rec.get("session"),
                                 "date": rec.get("date"), "lang": lang, "text": clean(rec["text"]), "methods": [], "statements": [],
                                 "for_review": [], "note": f"failed: {type(e2).__name__}: {str(e2)[:80]}", "rst": "skipped"})
        for row in rows:
            writer.write(row)
            if sample_mode:
                rows_kept.append(row)
        n_done += len(rows)
        if n_done >= next_report:
            el = time.time() - t0
            rate = n_done / el
            left = (len(todo) - n_done) / max(rate, 1e-9)
            say(f"   {n_done:,} of {len(todo):,} ({rate * 3600:,.0f}/hour; about {left / 3600:.1f} h left)")
            next_report += every
    writer.close()
    el = time.time() - t0
    say(f"   wrote {n_done:,} sentences in {el / 60:.1f} min -> {out_path}")
    if sample_mode:
        old = None
        op = ROOT / "data" / "dbpedia_pipeline" / j / "predications_v3.json"
        if op.exists():
            try:
                old = {c["sentence_id"] for c in json.load(open(op, encoding="utf-8"))}
            except Exception:                           # noqa: BLE001
                old = None
        rep = {"version": VERSION, "yield": yield_report(rows_kept, old), "timing": timing_report(j, n_done, len(recs), rows_kept)}
        (DESK / f"timing_{j}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        y, tm = rep["yield"], rep["timing"]
        say(f"== {j}: claim yield on {y['sentences']} random sentences")
        say(f"   {y['predications']} predications ({y['per_sentence']} per sentence): {y['stated']} stated, {y['embedded']} embedded, "
            f"{y['reported']} reported, {y['appositions']} appositions; {y['sentences_with_a_stated_predication']} sentences have a stated one"
            + (f"; the old extractor had a claim for {y['old_extractor_had_a_claim']}" if old is not None else ""))
        say(f"   {y['lines_sent_to_review (one parser only)']} lines found by one parser only (review); {y['questions_or_too_short']} questions or too short; "
            f"discourse re-read changed {y['stated_lines_re_read_by_discourse']} lines; {y['negated']} negated, {y['hedged']} hedged")
        say(f"== {j}: seconds per sentence " + ", ".join(f"{k} {v}" for k, v in tm["seconds_per_sentence"].items()))
        say(f"   the discourse parse would run on {tm['share_of_sentences_the_discourse_parse_would_run_on (multi policy)'] * 100:.0f}% of sentences under --rst multi")
        say(f"== {j}: projected hours for all {len(recs):,} sentences: " + "; ".join(f"{k} {v}" for k, v in tm["projected_hours"].items()))
        say(f"== wrote {DESK / f'timing_{j}.json'}")
    elif n_done:
        say("   run the same command again to continue, or if it is finished, nothing more happens")


if __name__ == "__main__":
    main()
