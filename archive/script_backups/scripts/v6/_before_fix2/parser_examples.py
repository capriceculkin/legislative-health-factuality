"""parser_examples.py RULES PARSES [--wsj WSJ_PARSES --treebank TREEBANK_DIR] [--out docs/parser_examples]

David, Oct 20: "Coming to our meeting with some examples of parses from each of the parsers applied to a set of
sentences would be helpful." One Markdown page per sentence (GitHub shows Markdown as a formatted page), each with:
  1. spaCy's dependency parse    2. Stanza's dependency parse    3. the constituency tree    4. the discourse units
  5. the lines our rules read from each parse    6. what the 2-of-3 vote kept and dropped    7. the output triples
and, for the Penn Treebank sentences, the gold lines from the annotators' marks next to them.
An index page (README.md) links every sentence and lists where each parser comes from.
Reads the saved parses only: no parser runs, nothing outside --out changes. Plain python3, no packages.
At the end it prints the GitHub address of every page, read from this project's git remote."""
import sys, os, json, argparse, re, subprocess
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("rules"); ap.add_argument("parses")
ap.add_argument("--wsj", default="outputs/wsj/wsj_parses.json")
ap.add_argument("--treebank", default="data/ptb_sample/combined")
ap.add_argument("--out", default="docs/parser_examples")
A = ap.parse_args()
sys.argv = [sys.argv[0], A.rules, A.parses]
sys.path.insert(0, A.rules)
import full as F             # noqa: E402
S, P, C = F.S, F.P, F.C

DEBATE = [  # (row, why it is here)
    ("sample|1", "David's sentence: two actions, a recipient with a negation, and a 'that is why'"),
    ("sample|6", "David's sentence: refused to act, on what and when"),
    ("test|A8|fr", "the same sentence in French"),
    ("test|D2|en", "an indirect object: told the minister that ..."),
    ("test|D2|fr", "the same in French: dit au ministre que ..."),
    ("test|F4|en", "urged someone to act: two claims sharing one person"),
    ("test|F4|fr", "the same in French"),
    ("test|A10|en", "an apposition: Jean Martin, the health minister"),
    ("test|A10|fr", "the same in French"),
    ("sample|11", "a complement clause: they are found to be in violation"),
    ("sample|15", "a recipient and a clause object: research tells us ..."),
    ("sample|17", "where the vote loses a right line (say repeal)"),
    ("sample|37", "a long sentence where all three parsers agree"),
    ("sample|41", "an inherited subject: new legislation to consolidate ..."),
    ("sample|57", "French: a passive matched to its active form, pronoun objects"),
    ("sample|74", "French: two parsers share the same mistake and it passes the vote"),
]
WSJ = [("wsj_0001.mrg", 1), ("wsj_0001.mrg", 2), ("wsj_0003.mrg", 1), ("wsj_0008.mrg", 6), ("wsj_0010.mrg", 18), ("wsj_0039.mrg", 22)]
SOURCES = """| Parser | What it gives | Code (GitHub) | Model used |
|---|---|---|---|
| spaCy 3.8 (Explosion) | dependency parse | https://github.com/explosion/spaCy | en_core_web_lg, fr_core_news_lg 3.8.0 (https://github.com/explosion/spacy-models) |
| Stanza 1.15 (Stanford NLP) | dependency parse; English constituency tree | https://github.com/stanfordnlp/stanza | combined_charlm (UD 2.18); English constituency ptb3-revised_charlm |
| Berkeley Neural Parser (benepar 0.2.0) | French constituency tree | https://github.com/nikitakit/self-attentive-parser | benepar_fr2 |
| isanlp_rst (UniRST) | discourse units and relations | https://github.com/tchewik/isanlp_rst | tchewik/isanlp_rst_v3, unirst |
"""


def esc(x):
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def dep_table(toks, name):
    out = [f"**{name}** (each word, its relation, and the word it attaches to)", "", "| # | word | relation | attaches to |", "|---|---|---|---|"]
    for t in toks:
        h = toks[t[5]][1] if t[5] is not None and t[5] < len(toks) else "ROOT"
        out.append(f"| {t[0] + 1} | {esc(t[1])} | {esc(t[4])} | {esc(h)} |")
    return out


def tree_lines(n, depth=0):
    if isinstance(n, str):
        return [n]
    kids = n[1]
    if all(isinstance(k, str) for k in kids):
        return ["  " * depth + f"({n[0]} {' '.join(kids)})"]
    pre = lambda k: not isinstance(k, str) and all(isinstance(x, str) for x in k[1])
    if all(pre(k) for k in kids):          # a phrase of words only: one line, (NP (DT the) (NNP Senate))
        return ["  " * depth + f"({n[0]} " + " ".join(f"({k[0]} {' '.join(k[1])})" for k in kids) + ")"]
    out = ["  " * depth + f"({n[0]}"]
    for k in kids:
        out += tree_lines(k, depth + 1)
    out[-1] += ")"
    return out


def as_tree(t):
    return P.parse_tree(t) if isinstance(t, str) else P._tuples(t)


def line_txt(x):
    o = x.get("object") or "(no object)"
    kind = {"asserted": "stated"}.get(x.get("kind"), x.get("kind", ""))
    return f"{esc(x.get('subject'))} \\| {esc(x.get('verb'))} \\| {esc(o)} — {kind}".replace(" — ", ", ")


def record_rows(fr):
    out = ["| # | subject | predicate | object | recipient | when | polarity, status | needs a referent | parsers | tied to |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for i, L in enumerate(fr["lines"]):
        rc = L["record"]
        obj = rc["object"] or (f"{rc['object_inferred']} (inferred)" if rc["object_inferred"] else "")
        rec = (rc["recipient"] or "") + (f" (not: {rc['recipient_not']})" if rc.get("recipient_not") else "") + \
              (f" [{L.get('recipient_function')}]" if rc["recipient"] else "")
        when = (rc["when"] or "") + (" (inherited)" if rc.get("when_inherited") else "")
        links = "; ".join(f"line {l['to'] + 1}, {l['relation']}" + (f" ('{l['word']}')" if l["word"] else "") +
                          (f", discourse {l['discourse_shared']}" if l.get("discourse") else "") for l in L["links"])
        nr = "; ".join(f"{x['slot']}: {x['words']}" for x in L["needs_referent"])
        out.append(f"| {i + 1} | {esc(rc['subject'])} | {esc(rc['predicate'])} | {esc(obj)} | {esc(rec)} | {esc(when)} | "
                   f"{rc['polarity']}, {esc(rc['status'])} | {esc(nr)} | {rc['parsers_agreeing']} of 3 | {esc(links)} |")
    return out


def page(row, why, gold=None):
    L = [f"# {esc(row['text'])}", "", f"*{why}*  ", f"Source: `{row['n']}`, language: {row['lang']}", ""]
    L += ["## 1. spaCy dependency parse", ""] + dep_table(row["deps_spacy"], "spaCy") + [""]
    L += ["## 2. Stanza dependency parse", ""]
    for k, s in enumerate(row["deps_stanza"]):
        L += dep_table(s, "Stanza" + (f", sentence piece {k + 1}" if len(row["deps_stanza"]) > 1 else "")) + [""]
    L += ["## 3. Constituency tree", "", ("Stanza, Penn Treebank labels" if row["lang"] == "en" else "Berkeley benepar_fr2, French Treebank labels") + ":", "", "```"]
    for t in row.get("trees", []):
        L += tree_lines(as_tree(t))
    L += ["```", ""]
    d = row.get("disc_native")
    L += ["## 4. Discourse units (isanlp_rst)", ""]
    if d and d.get("edus"):
        for k, e in enumerate(d["edus"]):
            L.append(f"- unit {k}: {esc(e.get('text') or row['text'][e['start']:e['end']])}")
        for r in d.get("relations", []):
            L.append(f"- units {r['left'][0]}-{r['left'][1]} with {r['right'][0]}-{r['right'][1]}: **{r['relation']}** ({r.get('nuclearity', '')})")
    else:
        L.append("not run for this sentence" + (" (the treebank sentences are parsed without discourse)" if row.get("set") == "wsj" else ""))
    L.append("")
    res = S.analyze(P, C, row, "native", "prod", "multi")
    L += ["## 5. Lines our rules read from each parse", "", "| from spaCy | from Stanza | from the tree |", "|---|---|---|"]
    a, b, c = res["spacy"], res["stanza"], res["const"]
    for i in range(max(len(a), len(b), len(c), 1)):
        L.append("| " + " | ".join(line_txt(x[i]) if i < len(x) else "" for x in (a, b, c)) + " |")
    L += ["", "## 6. The 2-of-3 vote", "", "**Kept** (two or three parsers have the line):", ""]
    for x in res["vote"]:
        fb = x.get("found_by") or []
        L.append(f"- {line_txt(x)} (found by {', '.join(fb) if fb else 'the vote'})" +
                 (" (apposition: read from spaCy's parse and added after the vote)" if x.get("verb", "").startswith("is (apposition)") else ""))
    L += ["", "**Dropped** (one parser only, held for review):", ""]
    L += [f"- {line_txt(x)} (only {', '.join(x.get('found_by') or [])})" for x in res["review"]] or ["- none"]
    fr = F.full_row(row)
    L += ["", "## 7. Output: one triple per clause", ""] + record_rows(fr) + [""]
    if gold is not None:
        L += ["## Gold, from the Penn Treebank annotators' marks", "",
              "| subject | verb | object | recipient | what kind | understood subject |", "|---|---|---|---|---|---|"]
        for g in gold:
            L.append(f"| {esc(g['subject'])} | {esc(g['verb'])} | {esc(g['object'])} | {esc(g['recipient'])} | {esc(g['object_kind'])} | {esc(g['subject_understood'])} |")
        L.append("")
    L += ["---", "Made by `scripts/v6/parser_examples.py` from the saved parses. [All sentences](README.md)"]
    return "\n".join(L) + "\n"


def slug(n):
    return re.sub(r"[^A-Za-z0-9]+", "_", n).strip("_")


def main():
    out = Path(A.out); out.mkdir(parents=True, exist_ok=True)
    rows = {r["n"]: r for r in json.load(open(A.parses, encoding="utf-8"))["rows"]}
    made = []
    for n, why in DEBATE:
        if n in rows:
            f = slug(n) + ".md"; (out / f).write_text(page(rows[n], why), encoding="utf-8"); made.append((f, n, why, rows[n]["text"]))
        else:
            print("   not in the saved parses, skipped:", n)
    if Path(A.wsj).exists() and Path(A.treebank).exists():
        import ptb_gold as G
        gold = {(fl, k): G.gold_lines(root) for fl, k, root in G.treebank_sentences(A.treebank)}
        wr = {(r["file"], r["k"]): r for r in json.load(open(A.wsj, encoding="utf-8"))["rows"]}
        for fl, k in WSJ:
            r = wr.get((fl, k))
            if r is None:
                continue
            f = slug(f"{fl.replace('.mrg', '')}_{k}") + ".md"
            why = "Penn Treebank sentence: our parsers and rules next to the annotators' marks"
            (out / f).write_text(page(r, why, gold.get((fl, k), [])), encoding="utf-8"); made.append((f, r["n"], why, r["text"]))
    else:
        print("   Penn Treebank pages skipped: run step 5 of the bundle first (outputs/wsj/wsj_parses.json)")
    idx = ["# Parser examples", "",
           "Each sentence below has its own page: spaCy's and Stanza's dependency parses, the constituency tree, the discourse units, "
           "the lines our rules read from each parse, what the 2-of-3 vote kept and dropped, and the output triples. "
           "Made from the parses saved on Oct 19 (debate sentences) and the Penn Treebank run (WSJ sentences).", "",
           "## Where each parser comes from", "", SOURCES, "## Sentences", "", "| page | sentence | why it is here |", "|---|---|---|"]
    for f, n, why, text in made:
        idx.append(f"| [{esc(n)}]({f}) | {esc(text[:110])}{'...' if len(text) > 110 else ''} | {esc(why)} |")
    (out / "README.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print(f"== wrote {len(made)} sentence pages and README.md to {out}/")
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
        if m:
            base = f"https://github.com/{m.group(1)}/blob/main/{out.as_posix()}"
            print("   After you push, the pages are at:")
            print(f"   {base}/README.md")
            for f, n, *_ in made:
                print(f"   {base}/{f}")
    except Exception:                           # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
