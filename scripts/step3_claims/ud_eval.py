"""ud_eval.py   The step 3 gold standard: how accurate our own dependency parsers are, measured by us, on the human
annotated Universal Dependencies test sets (never used to train these models' test scores).

Each parser gets the treebank's own words and sentence breaks (so only the parsing is tested, not tokenizing), parses
them, and is scored two ways:
  1. our scorer here: UAS (right head), LAS (right head and label), and LAS on the base label (obl:arg counts as obl);
  2. the official CoNLL 2018 shared task scorer (conll18_ud_eval.py), run on the same files.
spaCy English uses ClearNLP labels, not UD, so only its UAS can be compared; its LAS is reported as not comparable.

    cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
    python3 scripts/step3_claims/ud_eval.py [--parsers spacy,stanza] [--max 0]
Downloads the test files (git clone, about 200 MB in all) to ~/.ud_eval the first time; writes
outputs/ud_eval/<parser>_<treebank>.conllu and outputs/ud_eval/ud_eval_results.txt. Offline after the first run."""
import argparse, os, subprocess, sys, time, collections
from pathlib import Path

TREEBANKS = {   # name: (language, repository, test file)
    "en_ewt": ("en", "UD_English-EWT", "en_ewt-ud-test.conllu"),
    "en_gum": ("en", "UD_English-GUM", "en_gum-ud-test.conllu"),
    "fr_gsd": ("fr", "UD_French-GSD", "fr_gsd-ud-test.conllu"),
    "fr_sequoia": ("fr", "UD_French-Sequoia", "fr_sequoia-ud-test.conllu"),
    "fr_rhapsodie": ("fr", "UD_French-Rhapsodie", "fr_rhapsodie-ud-test.conllu"),
}
HOME = Path.home() / ".ud_eval"


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def fetch():
    HOME.mkdir(exist_ok=True)
    for repo in sorted({v[1] for v in TREEBANKS.values()} | {"conll2018"}):
        d = HOME / repo
        if d.exists():
            continue
        url = f"https://github.com/{'ufal' if repo == 'conll2018' else 'UniversalDependencies'}/{repo}"
        say(f"downloading {repo}")
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, str(d)], check=True)
    for repo in sorted({v[1] for v in TREEBANKS.values()}):
        c = subprocess.run(["git", "-C", str(HOME / repo), "log", "-1", "--format=%h %cs"], capture_output=True, text=True).stdout.strip()
        say(f"   {repo} at commit {c}")


def read_conllu(path, limit=0):
    """Sentences as lists of (id, form, head, deprel) for syntactic words (no multiword ranges, no empty nodes)."""
    sents, cur, raw, raws = [], [], [], []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            if cur:
                sents.append(cur); raws.append(raw)
                if limit and len(sents) >= limit:
                    break
            cur, raw = [], []
            continue
        if line.startswith("#"):
            raw.append(line); continue
        f = line.split("\t")
        if "-" in f[0] or "." in f[0]:
            continue
        cur.append((int(f[0]), f[1], int(f[6]), f[7]))
    if cur and not (limit and len(sents) >= limit):
        sents.append(cur); raws.append(raw)
    return sents


def write_conllu(path, sents, preds):
    with open(path, "w", encoding="utf-8") as o:
        for k, (g, p) in enumerate(zip(sents, preds)):
            o.write(f"# sent_id = {k + 1}\n")
            for (i, form, _, _), (h, rel) in zip(g, p):
                o.write(f"{i}\t{form}\t_\t_\t_\t_\t{h}\t{rel}\t_\t_\n")
            o.write("\n")


def write_gold(path, sents):
    write_conllu(path, sents, [[(h, r) for (_, _, h, r) in s] for s in sents])


def run_spacy(lang, sents):
    import spacy
    from spacy.tokens import Doc
    nlp = spacy.load({"en": "en_core_web_lg", "fr": "fr_core_news_lg"}[lang], exclude=["ner"])
    out = []
    for s in sents:
        words = [w for _, w, _, _ in s]
        doc = Doc(nlp.vocab, words=words, sent_starts=[True] + [False] * (len(words) - 1))
        for _, proc in nlp.pipeline:
            doc = proc(doc)
        out.append([(0 if t.head.i == t.i else t.head.i + 1, "root" if t.dep_ == "ROOT" else t.dep_) for t in doc])
    return out


def run_stanza(lang, sents):
    import stanza
    nlp = stanza.Pipeline(lang, processors="tokenize,pos,lemma,depparse", tokenize_pretokenized=True, verbose=False, download_method=None)
    out = []
    B = 64
    for k in range(0, len(sents), B):
        chunk = [[w for _, w, _, _ in s] for s in sents[k:k + B]]
        doc = nlp(chunk)
        for sent in doc.sentences:
            out.append([(w.head, w.deprel) for w in sent.words])
    return out


def score(gold, pred, comparable=True):
    c = collections.Counter()
    for g, p in zip(gold, pred):
        for (_, _, gh, gr), (ph, pr) in zip(g, p):
            if gr == "punct":
                c["punct"] += 1
            c["n"] += 1
            c["uas"] += gh == ph
            c["las"] += gh == ph and gr == pr
            c["blas"] += gh == ph and gr.split(":")[0] == pr.split(":")[0]
    n = c["n"] or 1
    return {"words": c["n"], "UAS": 100 * c["uas"] / n, "LAS": 100 * c["las"] / n if comparable else None, "LAS base label": 100 * c["blas"] / n if comparable else None}


def official(gold_path, sys_path):
    s = HOME / "conll2018" / "evaluation_script" / "conll18_ud_eval.py"
    r = subprocess.run([sys.executable, str(s), "-v", str(gold_path), str(sys_path)], capture_output=True, text=True)
    vals = {}
    for line in r.stdout.splitlines():
        f = [x.strip() for x in line.split("|")]
        if len(f) >= 4 and f[0] in ("UAS", "LAS"):
            vals[f[0]] = float(f[3])
    return vals, (r.stderr.strip()[:200] if r.returncode else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsers", default="spacy,stanza")
    ap.add_argument("--treebanks", default=",".join(TREEBANKS))
    ap.add_argument("--max", type=int, default=0, help="sentences per treebank (0 = all)")
    a = ap.parse_args()
    fetch()
    out = Path("outputs/ud_eval"); out.mkdir(parents=True, exist_ok=True)
    lines = []
    for tb in a.treebanks.split(","):
        lang, repo, fn = TREEBANKS[tb]
        gold = read_conllu(HOME / repo / fn, a.max)
        gp = out / f"gold_{tb}.conllu"; write_gold(gp, gold)
        for ps in a.parsers.split(","):
            say(f"{ps} on {tb} ({len(gold)} sentences)")
            t0 = time.time()
            pred = {"spacy": run_spacy, "stanza": run_stanza}[ps](lang, gold)
            assert len(pred) == len(gold) and all(len(p) == len(g) for p, g in zip(pred, gold)), "word counts differ"
            sp = out / f"{ps}_{tb}.conllu"; write_conllu(sp, gold, pred)
            comp = not (ps == "spacy" and lang == "en")
            mine = score(gold, pred, comp)
            off, err = official(gp, sp)
            row = (f"{ps:7s} {tb:13s} words {mine['words']:6d}   ours: UAS {mine['UAS']:5.2f}  "
                   + (f"LAS {mine['LAS']:5.2f}  LAS base {mine['LAS base label']:5.2f}" if comp else "LAS not comparable (ClearNLP labels)")
                   + f"   official: UAS {off.get('UAS', float('nan')):5.2f}" + (f"  LAS (base labels) {off.get('LAS', float('nan')):5.2f}" if comp else "")
                   + (f"   [{err}]" if err else "") + f"   ({time.time() - t0:.0f}s)")
            say(row); lines.append(row)
    res = out / "ud_eval_results.txt"
    res.write_text("Gold words and sentence breaks given; scored by our scorer and by conll18_ud_eval.py\n" + "\n".join(lines) + "\n", encoding="utf-8")
    say(f"== wrote {res}. Send it to the chat.")


if __name__ == "__main__":
    main()
