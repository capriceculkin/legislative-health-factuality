#!/usr/bin/env python3
"""run_compare.py   (reads only; writes ~/Desktop/parser_comparison.xlsx and ~/Desktop/parser_comparison.json)
Every predication in the 100 spot-check sentences, four ways: spaCy dependency parse, Stanza dependency parse,
Stanza constituency tree, and the linking words between clauses. The 20 sentences with an answer key are scored."""
import json, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import preds as P
from gold import G

DESK = Path.home() / "Desktop"
sample = json.loads((HERE / "spot_check_sample_v19.json").read_text(encoding="utf-8"))["claims"]


def need(mod, pipname):
    try:
        return __import__(mod)
    except ImportError:
        print(f"   installing {pipname} (first run only; Stanza brings PyTorch, which can take a few minutes)")
        for extra in ([], ["--user"]):
            if subprocess.call([sys.executable, "-m", "pip", "install", "-q", *extra, pipname]) == 0:
                break
        else:
            sys.exit(f"Could not install {pipname} into {sys.executable}. Paste the lines above into the chat. Nothing changed.")
        import importlib, site
        importlib.invalidate_caches()
        try:
            sys.path.append(site.getusersitepackages())
        except Exception:
            pass
        return __import__(mod)


spacy = need("spacy", "spacy")
stanza = need("stanza", "stanza")
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

print("== loading spaCy models")
SP = {"en": spacy.load("en_core_web_lg"), "fr": spacy.load("fr_core_news_lg")}
print(f"   spaCy {spacy.__version__}; Stanza {stanza.__version__}")
ST, CONST = {}, {}


def stanza_pipe(lang, procs):
    stanza.download(lang, processors=procs, verbose=False)
    return stanza.Pipeline(lang, processors=procs, tokenize_no_ssplit=True, verbose=False)


for lang in ("en", "fr"):
    tries = [("tokenize,mwt,pos,lemma,depparse", True), ("tokenize,pos,lemma,depparse", True)]
    if lang == "fr":
        tries = tries[:1]
    err = None
    if lang == "en":      # Stanza ships constituency models for English but not French (its default_constituency list has no "fr")
        for base, _ in tries:
            try:
                ST[lang], CONST[lang] = stanza_pipe(lang, base + ",constituency"), True
                break
            except Exception as e:
                err = e
    if lang not in CONST:
        if err is not None:
            print(f"   Stanza {lang}: constituency would not load ({type(err).__name__}: {str(err)[:120]}); dependency only")
        for base, _ in tries:
            try:
                ST[lang], CONST[lang] = stanza_pipe(lang, base), False
                break
            except Exception as e:
                err = e
        else:
            sys.exit(f"Stanza {lang} would not load: {type(err).__name__}: {err}. Paste this into the chat. Nothing changed.")
print(f"   Stanza constituency: English {'yes' if CONST['en'] else 'no'}, French {'yes' if CONST['fr'] else 'no'}")


def clean(t):
    return " ".join(t.replace("``", "“").replace("''", "”").split())


rows = []
t0 = time.time()
for n, c in enumerate(sample, 1):
    lang, text = c["language"], clean(c["full_text"])
    r = {"n": n, "lang": lang, "jurisdiction": c["jurisdiction"], "sentence_id": c["sentence_id"], "text": text,
         "v19_claim": f"{c['subject']} | {c['verb']} | {c['object']}", "preds_version": "v2"}
    doc = SP[lang](text)
    toks = P.from_spacy(doc)
    r["spacy"] = P.from_dependencies(toks)
    r["spacy_links"] = P.discourse([t.text for t in toks], r["spacy"], P.connective_slots_dep(toks))
    sd = ST[lang](text)
    st_preds, st_words, co_preds, co_words, trees, st_slots, co_slots = [], [], [], [], [], set(), set()
    for sent in sd.sentences:
        off = len(st_words)
        tk = P.from_stanza(sent)
        st_slots |= {i + off for i in P.connective_slots_dep(tk)}
        for p in P.from_dependencies(tk):
            p["at"] += off; st_preds.append(p)
        st_words += [t.text for t in tk]
        if CONST[lang] and getattr(sent, "constituency", None) is not None:
            off2 = len(co_words)
            try:
                tree = P.from_stanza_tree(sent.constituency); trees.append(str(sent.constituency))
                co_slots |= {i + off2 for i in P.connective_slots_tree(P._flatten_neg_advp(tree))}
                for p in P.from_constituency(tree, lang):
                    p["at"] += off2; co_preds.append(p)
                co_words += P.leaves(tree)
            except Exception as e:
                co_preds.append({"subject": "", "verb": f"(could not read the tree: {type(e).__name__}: {e})", "object": "", "kind": "", "how": "", "negated": False, "hedged": False, "at": 0})
    r["stanza"], r["stanza_links"] = st_preds, P.discourse(st_words, st_preds, st_slots)
    r["const"], r["const_links"], r["trees"] = co_preds, P.discourse(co_words, co_preds, co_slots) if co_preds else [], trees
    r["deps_spacy"] = [(t.i, t.text, t.lemma, t.upos, t.dep, t.head, t.feats, t.ws, t.disp) for t in toks]
    r["deps_stanza"] = [[(t.i, t.text, t.lemma, t.upos, t.dep, t.head, t.feats, t.ws, t.disp) for t in P.from_stanza(s)] for s in sd.sentences]
    rows.append(r)
    if n % 20 == 0:
        print(f"   {n} sentences ({time.time() - t0:.0f}s)")

METHODS = [("spacy", "spaCy dependency"), ("stanza", "Stanza dependency"), ("const", "Stanza constituency")]

# ---------------------------------------------------------------- scoring against the answer key
score_rows = []
for r in rows:
    if r["n"] not in G:
        continue
    gold = G[r["n"]]
    al = {m: P.align(gold, r[m]) for m, _ in METHODS}
    for m, _ in METHODS:
        r[m + "_hits"] = sum(x is not None for x in al[m])
    for k, g in enumerate(gold):
        score_rows.append({"n": r["n"], "lang": r["lang"], "k": k + 1, "gold": g,
                           **{m: al[m][k] is not None for m, _ in METHODS},
                           **{m + "_which": (al[m][k] + 1 if al[m][k] is not None else None) for m, _ in METHODS},
                           **{m + "_kind": (r[m][al[m][k]]["kind"] if al[m][k] is not None else None) for m, _ in METHODS}})


def fmt(preds, links):
    if not preds:
        return "(none)"
    out = []
    for k, p in enumerate(preds, 1):
        flags = (" NOT" if p.get("negated") else "") + (" HEDGED" if p.get("hedged") else "")
        out.append(f"[{k}] {p['subject']} | {p['verb']} | {p['object']}  ({p['kind']}: {p['how']}{flags})")
    if links:
        out.append("Links: " + "; ".join(links))
    return "\n".join(out)


def fmt_gold(gold):
    return "\n".join(f"[{k}] {s} | {v} | {o}  ({kind}{': ' + note if note else ''})" for k, (s, v, o, kind, note) in enumerate(gold, 1))


# ---------------------------------------------------------------- workbook
F = "Arial"
base, bold, white = Font(name=F, size=10), Font(name=F, size=10, bold=True), Font(name=F, size=10, bold=True, color="FFFFFF")
hdr, keyfill = PatternFill("solid", fgColor="1F3864"), PatternFill("solid", fgColor="E2EFDA")
line, thin = Side(style="thin", color="808080"), Side(style="thin", color="D9D9D9")
wrap = Alignment(wrap_text=True, vertical="top")
wb = Workbook()


def sheet(ws, heads, widths):
    for i, (h, w) in enumerate(zip(heads, widths), 1):
        c = ws.cell(1, i, h); c.font = white; c.fill = hdr; c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[c.column_letter].width = w
    ws.freeze_panes = "D2"


def put(ws, r, vals, fills=()):
    for i, v in enumerate(vals, 1):
        c = ws.cell(r, i, v); c.font = base; c.alignment = wrap; c.border = Border(top=line, bottom=line, left=thin, right=thin)
        if i in fills: c.fill = keyfill


ws = wb.active; ws.title = "Side by side (20)"
heads = ["Claim #", "Language", "Sentence", "Answer key", "spaCy dependency", "Stanza dependency", "Stanza constituency",
         "Old claim (v19, one per sentence)"] + [f"{t}: predications" for _, t in METHODS] + [f"{t}: match the key" for _, t in METHODS]
sheet(ws, heads, [7, 10, 42, 48, 48, 48, 48, 30, 11, 11, 11, 11, 11, 11])
k = 2
for r in rows:
    if r["n"] in G:
        put(ws, k, [r["n"], "English" if r["lang"] == "en" else "French", r["text"], fmt_gold(G[r["n"]]),
                    fmt(r["spacy"], r["spacy_links"]), fmt(r["stanza"], r["stanza_links"]), fmt(r["const"], r["const_links"]) if CONST[r["lang"]] else "(Stanza has no French constituency model)", r["v19_claim"],
                    len(r["spacy"]), len(r["stanza"]), len(r["const"]), r["spacy_hits"], r["stanza_hits"], r["const_hits"]], fills=(4,))
        k += 1
last_side = k - 1

ws2 = wb.create_sheet("All 100")
sheet(ws2, ["Claim #", "Language", "Sentence", "spaCy dependency", "Stanza dependency", "Stanza constituency", "Old claim (v19)", "Sentence ID"],
      [7, 10, 42, 50, 50, 50, 30, 34])
for k, r in enumerate(rows, 2):
    put(ws2, k, [r["n"], "English" if r["lang"] == "en" else "French", r["text"], fmt(r["spacy"], r["spacy_links"]),
                 fmt(r["stanza"], r["stanza_links"]), fmt(r["const"], r["const_links"]) if r["const"] or CONST[r["lang"]] else "(Stanza has no French constituency model)",
                 r["v19_claim"], r["sentence_id"]])

ws3 = wb.create_sheet("Scoring")
sheet(ws3, ["Claim #", "Language", "Kind", "Answer key predication", "Found: spaCy", "Found: Stanza dep", "Found: constituency",
            "spaCy: which one", "Stanza dep: which one", "Constituency: which one",
            "spaCy: same kind", "Stanza dep: same kind", "Constituency: same kind"], [7, 10, 10, 60, 12, 14, 16, 12, 14, 16, 14, 14, 16])
for k, s in enumerate(score_rows, 2):
    s_, v, o, kind, note = s["gold"]
    put(ws3, k, [s["n"], "English" if s["lang"] == "en" else "French", kind, f"{s_} | {v} | {o}",
                 *["n/a" if m == "const" and not CONST[s["lang"]] else "Yes" if s[m] else "No" for m, _ in METHODS], *[f"[{s[m + '_which']}]" if s[m] else "" for m, _ in METHODS],
                 *[("Yes" if s[m + "_kind"] == kind else f"No ({s[m + '_kind']})") if s[m] else "" for m, _ in METHODS]])
last_score = len(score_rows) + 1

ws4 = wb.create_sheet("Scores")
sheet(ws4, ["Measure", "Group", "spaCy dependency", "Stanza dependency", "Stanza constituency"], [44, 16, 18, 18, 20])
ws4.freeze_panes = "C2"
R = 2
cols = {"spacy": "E", "stanza": "F", "const": "G"}
for group, cond in (("All", ""), ("English", ',Scoring!$B$2:$B${L},"English"'), ("French", ',Scoring!$B$2:$B${L},"French"')):
    cond = cond.replace("{L}", str(last_score))
    for measure, kind in (("Answer key predications found (asserted only)", "asserted"), ("Answer key predications found (all kinds)", None)):
        ws4.cell(R, 1, measure); ws4.cell(R, 2, group)
        for j, (m, _) in enumerate(METHODS, 3):
            col = cols[m]
            kc = f',Scoring!$C$2:$C${last_score},"{kind}"' if kind else ""
            ws4.cell(R, j, f'=IFERROR(COUNTIFS(Scoring!${col}$2:${col}${last_score},"Yes"{kc}{cond})/COUNTIFS(Scoring!${col}$2:${col}${last_score},"<>n/a"{kc}{cond}),"")')
            ws4.cell(R, j).number_format = "0%"
        R += 1
ws4.cell(R, 1, "Of the lines found, kind (asserted / embedded / reported) agrees with the key"); ws4.cell(R, 2, "All")
for j, (m, _) in enumerate(METHODS, 3):
    kc = {"spacy": "K", "stanza": "L", "const": "M"}[m]
    ws4.cell(R, j, f'=IFERROR(COUNTIF(Scoring!{kc}2:{kc}{last_score},"Yes")/(COUNTIF(Scoring!{kc}2:{kc}{last_score},"Yes")+COUNTIF(Scoring!{kc}2:{kc}{last_score},"No*")),"")')
    ws4.cell(R, j).number_format = "0%"
R += 1
ws4.cell(R, 1, "Predications produced (20 sentences)"); ws4.cell(R, 2, "All")
for j, col in enumerate(("I", "J", "K"), 3):
    ws4.cell(R, j, f"=SUM('Side by side (20)'!{col}2:{col}{last_side})")
R += 1
ws4.cell(R, 1, "Share of produced predications that match the key"); ws4.cell(R, 2, "All")
for j, (a, b) in enumerate((("L", "I"), ("M", "J"), ("N", "K")), 3):
    ws4.cell(R, j, f"=IFERROR(SUM('Side by side (20)'!{a}2:{a}{last_side})/SUM('Side by side (20)'!{b}2:{b}{last_side}),\"\")")
    ws4.cell(R, j).number_format = "0%"
R += 2
for txt in ("How a match is counted: same verb (first four letters of a content word), at least one shared content word in the object",
            "(or both empty), and a shared word in the subject (a carried-over or pronoun subject counts). It is automatic and loose;",
            "read the Side by side sheet to judge the borderline ones. Stanza has no French constituency model, so that column is English only.",
            f"Stanza constituency available: English {'yes' if CONST['en'] else 'no'}, French {'yes' if CONST['fr'] else 'no'}."):
    ws4.cell(R, 1, txt).font = Font(name=F, size=9, italic=True); R += 1
for w in wb.worksheets:
    for row in w.iter_rows():
        for c in row:
            if c.font is None or c.font.name != F:
                c.font = Font(name=F, size=c.font.size if c.font else 10, bold=c.font.b if c.font else False,
                              italic=c.font.i if c.font else False, color=c.font.color if c.font else None)

out = DESK / "parser_comparison.xlsx"
wb.save(out)
(DESK / "parser_comparison.json").write_text(json.dumps({"stanza_constituency": CONST, "rows": rows}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
tot = {m: sum(s[m] for s in score_rows) for m, _ in METHODS}
den = {m: [s for s in score_rows if m != "const" or CONST[s["lang"]]] for m, _ in METHODS}
ass = [s for s in score_rows if s["gold"][3] == "asserted"]
print(f"== answer key: {len(score_rows)} predications ({len(ass)} asserted) in {len(G)} sentences")
for m, t in METHODS:
    a = [s for s in den[m] if s["gold"][3] == "asserted"]
    print(f"   {t}: found {tot[m]} of {len(den[m])}; asserted {sum(s[m] for s in a)} of {len(a)}")
print(f"== wrote {out} and parser_comparison.json on the Desktop. Attach both to the chat.")
