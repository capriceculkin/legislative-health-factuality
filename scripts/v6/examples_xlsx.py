"""examples_xlsx.py RULES PARSES OUT.xlsx [--wsj WSJ_PARSES --treebank TREEBANK_DIR]

Every example sentence through every step, as one Excel workbook: one sheet per step, one row per word, line or
triple, so the examples can be read, sorted and filtered. Nothing is typed by hand; every cell is printed from the
saved parses by this script. Needs openpyxl."""
import sys, os, json, argparse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("rules"); ap.add_argument("parses"); ap.add_argument("out")
ap.add_argument("--wsj", default=""); ap.add_argument("--treebank", default="")
ap.add_argument("--outputs", default="outputs", help="folder with the score files copied into the Scores sheet")
ap.add_argument("--repo", default="", help="GitHub address of this project (https://github.com/OWNER/REPO); files tracked in git get a link")
A = ap.parse_args()
sys.argv = [sys.argv[0], A.rules, A.parses]
sys.path.insert(0, A.rules)
import full as F             # noqa: E402
import examples_xlsx_docs as D  # noqa: E402
import examples_flow as FL      # noqa: E402

FEATURED = [
    ("sample|1", "Flow 1 hardware store", "All three parses hang 'to themselves ... to others' on 'sending' (Stanza through 'themselves', with 'others' joined to it); the output splits it into the recipient (to others) and the negated part (not to themselves). 'That is why' becomes a result tie from 'we need the check' back to the first clause, and the line 'that | is | why ...' is folded into that tie. spaCy and the tree marked 'we need the check' embedded and Stanza stated; the vote took embedded (two of three), and the output step (full.py, the 'that is why' rule) changes it to stated, because it is what the speaker concludes. Limit: the discourse parse says the first two clauses together explain the last; the tie points to the first clause only, and 'that' is not resolved."),
    ("sample|6", "Flow 2 Senate (English)", "Refused to act on what, and when? The object is not in the words, so the output says it is not stated and offers 'legislation identical to H.R. 5', marked inferred. 'Last year' opens the sentence and is carried to the Senate clause, marked inherited. The tree reads 'to act' as a separate complement of 'refused': its line 'the Senate | refused | to act' was the tree's alone and was dropped, while its second half 'the Senate | to act' matched the dependency lines on the verb, which is why the tree counts as agreeing. The inferred object comes from one rule: a clause with no object, tied by 'but' to a clause that has one. 'Last year' is not yet turned into a year."),
    ("test|A8|fr", "Flow 3 Senat (French)", "The same sentence in French. The French tree parser read it correctly, but our French tree rules do not read a clause written as a coordination node (COORD), so they produce a wrong line, 'la Chambre (inh) | agir', and the Senate line is found by 2 of 3 parsers, not 3. A rule fix to make."),
    ("test|D2|en", "Flow 4 told the minister", "An indirect object. spaCy labels 'the minister' an object (dobj), Stanza an indirect object (iobj). The output puts the minister in the recipient slot, and what was told, the that-clause, becomes its own line tied to this one."),
    ("sample|17", "Flow 5 where the vote fails", "A line the key has is lost. spaCy reads 'say' as a helper verb of 'repeal'; Stanza reads 'repeal' as a clause under 'say'. Only the tree has a line for 'repeal these health care rights' (and with the wrong subject, 'My Republican friends', who are only saying it), so the vote drops it. The line the vote keeps, 'say repeal', is itself wrong and is marked stated, which gives the speaker words that are really reported. This is the cost of requiring two parsers, and a case where the discourse check (attribution) should have relabelled the line and did not."),
]
S, P, C = F.S, F.P, F.C
from openpyxl import Workbook                                       # noqa: E402
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side   # noqa: E402
from openpyxl.utils import get_column_letter                        # noqa: E402
from openpyxl.worksheet.hyperlink import Hyperlink                  # noqa: E402

DEBATE = [
    ("sample|1", "two actions, a recipient with a negation, and 'that is why'"),
    ("sample|6", "refused to act: on what, and when?"),
    ("test|A8|fr", "the same sentence in French"),
    ("test|D2|en", "indirect object: told the minister that ..."),
    ("test|D2|fr", "the same in French: dit au ministre que ..."),
    ("test|F4|en", "urged someone to act: two claims sharing one person"),
    ("test|F4|fr", "the same in French"),
    ("test|A10|en", "apposition: Jean Martin, the health minister"),
    ("test|A10|fr", "the same in French"),
    ("sample|11", "complement clause: they are found to be in violation"),
    ("sample|15", "recipient and clause object: research tells us ..."),
    ("sample|17", "where the vote loses a line the key has (say repeal)"),
    ("sample|37", "a long sentence with several clauses (and a wrong 'time' tie)"),
    ("sample|41", "inherited subject: new legislation to consolidate ..."),
    ("sample|57", "French: a passive matched to its active form; pronoun objects"),
    ("sample|74", "French: two parsers share the same mistake and it passes the vote"),
] + [(n, "random debate sentence (English), seed 20261021") for n in ("sample|40", "sample|30", "sample|42", "sample|2", "sample|49", "sample|43", "sample|27")] \
  + [(n, "random debate sentence (French), seed 20261021") for n in ("sample|94", "sample|100", "sample|65", "sample|88", "sample|78", "sample|95", "sample|52")]
WSJ = [("wsj_0001.mrg", 1), ("wsj_0001.mrg", 2), ("wsj_0003.mrg", 1), ("wsj_0003.mrg", 2), ("wsj_0003.mrg", 3), ("wsj_0003.mrg", 7),
       ("wsj_0008.mrg", 6), ("wsj_0010.mrg", 18), ("wsj_0039.mrg", 22), ("wsj_0044.mrg", 76), ("wsj_0049.mrg", 19), ("wsj_0112.mrg", 6)]

FONT = "Calibri"
HEAD = Font(name=FONT, bold=True, size=10, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="595959")
BODY = Font(name=FONT, size=10)
BAND = PatternFill("solid", fgColor="F2F2F2")
THIN = Border(bottom=Side(style="thin", color="D9D9D9"))
KIND = {"asserted": "stated"}
SLOT = {"recipient_not": "not to"}


def sheet(wb, title, headers, widths, note=None):
    ws = wb.create_sheet(title)
    r0 = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = Font(name=FONT, italic=True, size=9, color="595959")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.row_dimensions[1].height = 30
        ws.cell(row=1, column=1).alignment = Alignment(wrap_text=True, vertical="top")
        r0 = 2
    for j, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=r0, column=j, value=h)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=2)
    ws._r0 = r0
    ws._next = r0 + 1          # own row counter: setting freeze_panes touches a cell, so max_row is one too high
    ws._band = {}
    return ws


def add(ws, values, group=None):
    r = ws._next; ws._next += 1
    for j, v in enumerate(values, 1):
        c = ws.cell(row=r, column=j, value=v)
        c.font = BODY
        c.alignment = Alignment(wrap_text=isinstance(v, str) and len(v) > 40, vertical="top")
        c.border = THIN
    if group is not None:          # shade every other sentence so rows of one sentence read as a block
        k = ws._band.setdefault(group, len(ws._band) % 2)
        if k:
            for j in range(1, len(values) + 1):
                ws.cell(row=r, column=j).fill = BAND
    return r


def finish(ws):
    ws.auto_filter.ref = f"A{ws._r0}:{get_column_letter(ws.max_column)}{ws._next - 1}"


import re as _re, subprocess as _sp
_TRACKED = None


def tracked():
    global _TRACKED
    if _TRACKED is None:
        try:
            out = _sp.run(["git", "ls-files"], capture_output=True, text=True, timeout=30).stdout.split("\n")
            _TRACKED = {x.strip() for x in out if x.strip()}
        except Exception:                               # noqa: BLE001
            _TRACKED = set()
        _TRACKED |= {"docs/parser_examples.xlsx"} | {"scripts/v6/" + os.path.basename(x) for x in os.listdir(A.rules) if x.endswith((".py", ".sh", ".json"))}
    return _TRACKED


def gh(text):
    """The GitHub link for the first project path in a cell, if that file (or folder) is in the repo."""
    if not A.repo or not text:
        return None
    for m in _re.finditer(r"((?:scripts|data|outputs|docs)/[A-Za-z0-9_./*{},-]+)", str(text)):
        p = m.group(1).rstrip(".,;)")
        p = p.split("{")[0].split("*")[0].rstrip("/")           # a pattern links to its folder
        files = tracked()
        if p in files:
            return f"{A.repo}/blob/main/{p}"
        if any(f.startswith(p + "/") for f in files):
            return f"{A.repo}/tree/main/{p}"
    return None


LINK = Font(name="Calibri", size=10, color="404040", underline="single")


def link(cell, url):
    if url:
        cell.hyperlink = url
        f = cell.font
        cell.font = Font(name=f.name or "Calibri", size=f.size or 10, bold=f.bold, color="404040", underline="single")


def link_column(ws, col):
    for r in range(ws._r0 + 1, ws._next):
        c = ws.cell(row=r, column=col)
        link(c, gh(c.value))


def go(cell, sheet_name, row, col="A"):
    """A link inside this workbook: clicking the cell jumps to that sheet and row."""
    cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'{sheet_name}'!{col}{row}")
    f = cell.font
    cell.font = Font(name="Calibri", size=f.size or 10, bold=f.bold, color="404040", underline="single")


def internal_links(wb, flow_all, flow_at, sents):
    """Every sentence ID, on every sheet, jumps to that sentence's flow. On the Sentences sheet the five counts jump to
    the sentence's first row in each step sheet, and each flow title jumps back to the Sentences list."""
    flow_name = flow_all.title
    step_sheets = {"F": "5 Lines by parser", "G": "5 Lines by parser", "H": "5 Lines by parser", "I": "6 Vote", "J": "7 Output triples"}
    first = {}
    for name in ("1 spaCy parse", "2 Stanza parse", "3 Tree", "4 Discourse", "5 Lines by parser", "6 Vote", "7 Output triples"):
        ws = wb[name]
        for r in range(ws._r0 + 1, ws._next):
            n = ws.cell(row=r, column=1).value
            if n is None:
                continue
            first.setdefault((name, n), r)
            if n in flow_at:
                go(ws.cell(row=r, column=1), flow_name, flow_at[n])
    sent_row = {}
    for r in range(sents._r0 + 1, sents._next):
        n = sents.cell(row=r, column=1).value
        sent_row[n] = r
        if n in flow_at:
            go(sents.cell(row=r, column=1), flow_name, flow_at[n])
        for col, name in step_sheets.items():
            sub = {"F": "spaCy", "G": "Stanza", "H": "Tree"}.get(col)
            ws = wb[name]
            target = None
            for rr in range(ws._r0 + 1, ws._next):
                if ws.cell(row=rr, column=1).value == n and (sub is None or ws.cell(row=rr, column=2).value == sub):
                    target = rr; break
            if target:                     # the count cell holds a formula, so the link goes inside it (works in Excel and LibreOffice)
                c = sents[f"{col}{r}"]
                c.value = f'=HYPERLINK("#\'{name}\'!A{target}",{str(c.value)[1:]})'
                c.font = Font(name="Calibri", size=10, color="404040", underline="single")
    if "8 Treebank gold" in wb.sheetnames:
        ws = wb["8 Treebank gold"]
        for r in range(ws._r0 + 1, ws._next):
            key = (ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value)
            if key in flow_at:
                go(ws.cell(row=r, column=1), flow_name, flow_at[key])
    for n, r in flow_at.items():          # flow title -> back to the list
        if isinstance(n, str) and n in sent_row:
            c = flow_all.cell(row=r, column=1)
            c.hyperlink = Hyperlink(ref=c.coordinate, location=f"'{sents.title}'!A{sent_row[n]}")
            c.font = Font(name="Calibri", size=13, bold=True, color="404040", underline="single")
    for ws in wb:
        if ws.title.startswith("Flow ") and ws.title != flow_name:
            t = ws.cell(row=1, column=1)
            n = str(t.value or "").split("   ")[0]
            if n in sent_row:
                t.hyperlink = Hyperlink(ref=t.coordinate, location=f"'{sents.title}'!A{sent_row[n]}")
                t.font = Font(name="Calibri", size=13, bold=True, color="404040", underline="single")


def tree_str(n):
    if isinstance(n, str):
        return n
    return "(" + n[0] + " " + " ".join(tree_str(k) for k in n[1]) + ")"


def head_word(toks, t):
    return ("ROOT", 0) if t[5] is None or t[5] >= len(toks) else (toks[t[5]][1], toks[t[5]][0] + 1)


def main():
    rows = {r["n"]: r for r in json.load(open(A.parses, encoding="utf-8"))["rows"]}
    wb = Workbook(); wb.remove(wb.active)
    readme = wb.create_sheet("Read me")
    FL.overview(wb.create_sheet("Start here"), gh, link)
    feat_ws = []
    for n, title, note in FEATURED:
        if n in rows:
            ws_ = wb.create_sheet(title); FL.setup(ws_); feat_ws.append((ws_, n, note))
    wsj_feat = wb.create_sheet("Flow 6 treebank") if (A.wsj and Path(A.wsj).exists() and A.treebank) else None
    flow_all = wb.create_sheet("Flow, every sentence"); FL.setup(flow_all)
    how = sheet(wb, "How it works", ["Step", "What it does", "Input, and where it comes from", "Code", "Output", "Shown in sheet",
                                     "How it is checked (gold standard)", "Known limits"], [22, 46, 40, 36, 34, 18, 44, 40],
                "Each step of the pipeline: what goes in, the exact file or script, what comes out, how it is checked, and what is known to go wrong.")
    for row_ in D.PIPELINE:
        add(how, list(row_))
    fil = sheet(wb, "Files", ["File (in the project)", "What it is", "Made by, when", "Made from"], [44, 70, 40, 30],
                "Where every file comes from.")
    for row_ in D.FILES:
        add(fil, list(row_))
    sents = sheet(wb, "Sentences", ["ID", "Set", "Language", "Sentence", "Why it is here", "spaCy lines", "Stanza lines",
                                    "Tree lines", "Kept by the vote", "Output triples", "Source (sentence ID: legislature|bill|date|page|sentence)", "Source file"],
                  [14, 9, 9, 70, 40, 10, 10, 10, 10, 10, 40, 44])
    sp = sheet(wb, "1 spaCy parse", ["ID", "Word #", "Word", "Lemma", "Part of speech", "Relation", "Attaches to (word #)", "Attaches to (word)"],
               [14, 8, 18, 16, 12, 14, 12, 18], "spaCy 3.8.14 dependency parse. Source: data/parity_oct19/parity_parses.json, field deps_spacy (parity_collect.py, Oct 19). English labels are ClearNLP (OntoNotes), French labels are Universal Dependencies. Meanings: sheet Labels.")
    st = sheet(wb, "2 Stanza parse", ["ID", "Word #", "Word", "Lemma", "Part of speech", "Relation", "Attaches to (word #)", "Attaches to (word)"],
               [14, 8, 18, 16, 12, 14, 12, 18], "Stanza 1.15.0 dependency parse. Source: data/parity_oct19/parity_parses.json, field deps_stanza. Universal Dependencies labels, both languages. Meanings: sheet Labels.")
    tr = sheet(wb, "3 Tree", ["ID", "Parser", "Constituency tree (bracketed)"], [14, 24, 150],
               "Source: parity_parses.json, field trees. English: Stanza constituency parser, Penn Treebank labels. French: Berkeley parser benepar_fr2, French Treebank labels. Meanings: sheet Labels.")
    di = sheet(wb, "4 Discourse", ["ID", "Kind", "Unit # or units", "Text or relation", "Nuclearity", "Shared label (both languages)"], [14, 10, 14, 80, 11, 18],
               "Source: parity_parses.json, field disc_native (isanlp_rst 3.2.2, UniRST). Parsed with the other parsers; used after the vote, and only when the vote kept 2+ lines or a speech word appears. The English and French models use different label sets; the shared label maps both to one set.")
    li = sheet(wb, "5 Lines by parser", ["ID", "Parser", "Line #", "Subject", "Verb", "Object", "Status", "Negated", "Hedged"],
               [14, 10, 7, 34, 22, 40, 11, 9, 9], "What our rules (scripts/v6/preds.py, const_fr.py) read from each parse separately, before the vote. Recomputed from the saved parses each time this workbook is built.")
    vo = sheet(wb, "6 Vote", ["ID", "Decision", "Subject", "Verb", "Object", "Status", "Found by"], [14, 26, 34, 22, 40, 11, 20],
               "combine_lib.py vote(). Kept: two or three parsers produced a matching line under the loose test (same polarity, verbs sharing a word or its first 4 letters, subjects and objects each sharing a content word or both empty), so 'found by' does not mean the lines were identical. Dropped: one parser only, held for review. Appositions are read from spaCy's parse and added after the vote.")
    ou = sheet(wb, "7 Output triples", ["ID", "Line #", "Subject", "Predicate", "Object", "Object inferred (not in the words)", "Recipient", "Recipient kind",
                                        "Not to (negated recipient)", "When", "When inherited", "Polarity", "Status", "Needs a referent before DBpedia",
                                        "Parsers agreeing", "Tied to (line, how)", "Discourse (shared label)"],
               [14, 7, 30, 20, 36, 26, 20, 22, 16, 16, 10, 10, 14, 30, 10, 30, 16],
               "full.py record(): one triple per clause, the record passed toward DBpedia. Line numbers count from 1 within each sentence.")

    for n, why in DEBATE:
        r = rows.get(n)
        if r is None:
            print("   not in the saved parses, skipped:", n); continue
        sid = r.get("sentence_id") or ""
        jur = {"US": "us", "ON": "ontario", "QC": "quebec"}.get(sid.split("|")[0], "")
        srcfile = f"data/dbpedia_pipeline/{jur}/sentences_v3.json" if jur else "scripts/v6/parallel_tests.py (a written test pair)"
        add(sents, [n, r["set"], r["lang"], r["text"], why, None, None, None, None, None, sid or "(test pair, not from the record)", srcfile], n)
        for t in r["deps_spacy"]:
            hw, hi = head_word(r["deps_spacy"], t)
            add(sp, [n, t[0] + 1, t[1], t[2], t[3], t[4], hi, hw], n)
        for s_ in r["deps_stanza"]:
            for t in s_:
                hw, hi = head_word(s_, t)
                add(st, [n, t[0] + 1, t[1], t[2], t[3], t[4], hi, hw], n)
        for t in r.get("trees", []):
            add(tr, [n, "Stanza (PTB)" if r["lang"] == "en" else "Berkeley benepar_fr2 (FTB)", tree_str(P.parse_tree(t) if isinstance(t, str) else P._tuples(t))], n)
        d = r.get("disc_native")
        if d and d.get("edus"):
            for k, e in enumerate(d["edus"]):
                add(di, [n, "unit", k, e.get("text") or r["text"][e["start"]:e["end"]], "", ""], n)
            for rel in d.get("relations", []):
                add(di, [n, "relation", f"{rel['left'][0]}-{rel['left'][1]} with {rel['right'][0]}-{rel['right'][1]}", rel["relation"],
                         rel.get("nuclearity", ""), F.DISC_SHARED.get(rel["relation"], rel["relation"])], n)
        else:
            add(di, [n, "none", "", "not run for this sentence (only when 2+ lines are kept or a speech word appears)", "", ""], n)
        res = S.analyze(P, C, r, "native", "prod", "multi")
        for src, name in (("spacy", "spaCy"), ("stanza", "Stanza"), ("const", "Tree")):
            for i, x in enumerate(res[src], 1):
                add(li, [n, name, i, x.get("subject"), x.get("verb"), x.get("object") or "", KIND.get(x.get("kind"), x.get("kind")),
                         "yes" if x.get("negated") else "", "yes" if x.get("hedged") else ""], n)
        for x in res["vote"]:
            fb = x.get("found_by") or []
            app = (x.get("verb") or "").startswith("is (apposition)")
            add(vo, [n, "added after the vote (apposition)" if app else "kept", x.get("subject"), x.get("verb"), x.get("object") or "",
                     KIND.get(x.get("kind"), x.get("kind")), ", ".join(fb)], n)
        for x in res["review"]:
            add(vo, [n, "dropped (one parser only)", x.get("subject"), x.get("verb"), x.get("object") or "", KIND.get(x.get("kind"), x.get("kind")),
                     ", ".join(x.get("found_by") or [])], n)
        fr = F.full_row(r)
        for i, L in enumerate(fr["lines"], 1):
            rc = L["record"]
            ties = "; ".join(f"line {l['to'] + 1}, {l['relation']}" + (f" ('{l['word']}')" if l["word"] else "") for l in L["links"])
            disc = "; ".join(l.get("discourse_shared") or "" for l in L["links"] if l.get("discourse"))
            add(ou, [n, i, rc["subject"], rc["predicate"], rc["object"] or "", rc["object_inferred"] or "", rc["recipient"] or "",
                     L.get("recipient_function", "") if rc["recipient"] else "", rc.get("recipient_not") or "", rc["when"] or "",
                     "yes" if rc.get("when_inherited") else "", rc["polarity"], rc["status"].replace("asserted", "stated"),
                     "; ".join(f"{SLOT.get(x['slot'], x['slot'])}: {x['words']}" for x in L["needs_referent"]), rc["parsers_agreeing"], ties, disc], n)
    # counts per sentence, as formulas over the step sheets
    r0 = sents._r0
    for row in range(r0 + 1, sents._next):
        f = {"F": "=COUNTIFS('5 Lines by parser'!$A:$A,$A{r},'5 Lines by parser'!$B:$B,\"spaCy\")",
             "G": "=COUNTIFS('5 Lines by parser'!$A:$A,$A{r},'5 Lines by parser'!$B:$B,\"Stanza\")",
             "H": "=COUNTIFS('5 Lines by parser'!$A:$A,$A{r},'5 Lines by parser'!$B:$B,\"Tree\")",
             "I": "=COUNTIFS('6 Vote'!$A:$A,$A{r},'6 Vote'!$B:$B,\"kept\")",
             "J": "=COUNTIFS('7 Output triples'!$A:$A,$A{r})"}
        for col, fm in f.items():
            sents[f"{col}{row}"] = fm.format(r=row)
            sents[f"{col}{row}"].font = BODY
    # Penn Treebank: gold marks against our rules
    if A.treebank and Path(A.treebank).exists():
        import ptb_gold as G
        tb = sheet(wb, "8 Treebank gold", ["File", "Sentence #", "Sentence", "Source of our line", "Gold subject", "Gold verb", "Gold object",
                                           "Gold recipient", "Kind of object (gold)", "Understood subject (gold)", "Our subject", "Our verb",
                                           "Our object", "Our recipient"],
                   [13, 9, 60, 22, 26, 14, 34, 18, 22, 16, 26, 14, 34, 18],
                   "Gold: the Penn Treebank's hand annotation (Marcus et al. 1993), turned into lines by ptb_gold.py. 'Tree rules on gold tree' runs our rules "
                   "on the treebank's own tree with the marks removed, so a wrong line is a rule error; the tree rules have no recipient label, so they put a recipient in the object slot. "
                   "'Vote' rows (only when built with the treebank parses) use our parsers on the plain text.")
        gold = {(f, k): root for f, k, root in G.treebank_sentences(A.treebank)}
        wr = {}
        if A.wsj and Path(A.wsj).exists():
            wr = {(r["file"], r["k"]): r for r in json.load(open(A.wsj, encoding="utf-8"))["rows"]}
        for f, k in WSJ:
            root = gold.get((f, k))
            if root is None:
                continue
            gl = G.gold_lines(root)
            variants = [("tree rules on gold tree", [{"subject": o["subject"], "verb": o["verb"], "object": o["object"], "recipient": ""}
                                                     for o in P.from_constituency("(ROOT " + G.to_str(G.strip_marks(root)) + ")", "en")])]
            if (f, k) in wr:
                variants.append(("vote (our parsers)", [{"subject": L["subject"], "verb": L["verb"], "object": L["object"], "recipient": L.get("recipient") or ""}
                                                         for L in F.full_row(wr[(f, k)])["lines"]]))
            for g in gl:
                for name, ours in variants:
                    v = P.fold(g["verb"])[-1:]
                    o = next((x for x in ours if v and v[0] in P.fold(x["verb"] or "")), None)
                    add(tb, [f, k, G.txt(root), name, g["subject"] or "(unstated)", g["verb"], g["object"], g["recipient"], g["object_kind"] or "",
                             g["subject_understood"] or "", (o or {}).get("subject", "NOT FOUND"), (o or {}).get("verb", ""), (o or {}).get("object", ""),
                             (o or {}).get("recipient", "")], f"{f}{k}")
        finish(tb)

    import ast as _ast
    rl = sheet(wb, "Rules", ["File", "Function", "What it does (from the code's own description)"], [26, 30, 120],
               "Every rule function, with the description written in the code (a description can be shorter than the code: matches() says 'same verb', and the code's verb test is verb_match(), a shared word or its first 4 letters). The bottleneck is the vote: combine_lib.py vote() with the match test in preds.py matches() and verb_match().")
    for fn in ("preds.py", "const_fr.py", "lexicon.py", "frames.py", "combine_lib.py", "full.py"):
        fp = Path(A.rules) / fn
        if not fp.exists():
            continue
        tree_ = _ast.parse(fp.read_text(encoding="utf-8"))
        for node in _ast.walk(tree_):
            if isinstance(node, (_ast.FunctionDef,)) and _ast.get_docstring(node):
                doc = " ".join(_ast.get_docstring(node).split())
                add(rl, [f"scripts/v6/{fn}", node.name + "()", doc[:900]])
    link_column(rl, 1)
    rf = sheet(wb, "Record fields", ["Field in the output", "What it holds", "Grammatical function (Huddleston and Pullum ch. 4)", "Read from (parse labels or rule)", "Example"],
               [18, 50, 36, 60, 30], "Why each part of the output is what it is: the linguistic function behind each field of the record.")
    for row_ in D.RECORD_FIELDS:
        add(rf, list(row_))
    import parallel_tests as PT
    import ast as _ast2
    ss = sheet(wb, "Simple sentences", ["Pair", "Group", "Construction", "Language", "Sentence", "Expected lines (written key)", "Our output",
                                        "Found (loose match)", "Exactly right (subject, verb, object)", "Negation and status as expected"],
               [7, 11, 26, 9, 46, 48, 62, 11, 13, 13],
               "45 pairs, one construction each, in English and French, built to change one thing at a time. The expected lines were drafted with AI assistance and are being checked by hand. "
               "Found (loose match): every expected line has an output line sharing a content word in subject, verb and object (the vote's test). Exactly right: the same three slots word for word, where the output's object slot also holds its recipient and other parts, as compare3.py scores it. "
               "Negation and status: the matched line has the expected polarity and stated / reported / embedded. "
               "Pair D2 (told the minister that ...) counts as not found in both languages: the key was written before the recipient slot and puts the person told in the object slot, "
               "while the output puts him in the recipient slot and points the object to what was told. The run script (parity_score.txt), which scores the earlier three-slot lines, passes D2.")
    import compare3 as K3
    for t in PT.T:
        for L_ in ("en", "fr"):
            n = f"test|{t['id']}|{L_}"
            if n not in rows:
                continue
            try:
                key = _ast2.literal_eval(t[L_]["lines"]) if isinstance(t[L_]["lines"], str) else t[L_]["lines"]
            except Exception:                    # noqa: BLE001
                key = []
            res_ = S.analyze(P, C, rows[n], "native", "prod", "multi")
            al = P.align(key, res_["final"]) if key else []
            fr_ = F.full_row(rows[n])
            def show_(x):
                rc = x["record"]
                obj = rc["object"] or (f"(not stated; inferred: {rc['object_inferred']})" if rc["object_inferred"] else "(none)")
                tags = ["NEGATED" if rc["polarity"] == "negative" else "", rc["status"].replace("asserted", "stated")]
                return (f"{rc['subject']} | {rc['predicate']} | {obj}" + (f"   recipient: {rc['recipient']}" if rc["recipient"] else "")
                        + "   [" + ", ".join(t_ for t_ in tags if t_) + "]")
            outl = "\n".join(show_(x) for x in fr_["lines"])
            def keyshow(k):
                neg = P.gold_negated(k)
                kind = {"asserted": "stated"}.get(k[3], k[3]) if len(k) > 3 else ""
                return " | ".join(str(v) for v in k[:3]) + "   [" + ", ".join(x for x in ("NEGATED" if neg else "", kind) if x) + "]"
            # marks computed on the same full-predication lines the 'Our output' column shows, the way compare3.py scores them
            Lf = K3.as_lines(fr_)
            alf = P.align(key, Lf) if key else []
            exact_set = {(K3.norm(x["subject"]), K3.norm(x["verb"]), K3.norm(x["full"])) for x in Lf}
            if key:
                found_ = "yes" if all(a is not None for a in alf) else "no"
                exact_ = "yes" if all((K3.norm(k[0]), K3.norm(k[1]), K3.norm(k[2])) in exact_set for k in key) else "no"
                lab_ = "yes" if all(a is not None and Lf[a].get("kind") == k[3] and bool(Lf[a].get("negated")) == P.gold_negated(k)
                                    for k, a in zip(key, alf)) else "no"
            else:
                found_ = exact_ = lab_ = "yes (none expected, none produced)" if not fr_["lines"] else "no (none expected)"
            add(ss, [t["id"], t.get("group", ""), t.get("construction", ""), L_, t[L_]["text"],
                     "\n".join(keyshow(k) for k in key) or "(none: a question is not a claim)", outl or "(none)", found_, exact_, lab_], t["id"])
    finish(ss); finish(rl); finish(rf)
    lab = sheet(wb, "Labels", ["Where it appears", "Label", "What it means"], [30, 46, 90], "Every label used in the parse sheets, in plain words.")
    for row_ in D.LABELS:
        add(lab, list(row_))
    qs = sheet(wb, "Questions", ["Question a reviewer may ask", "Answer", "Where to look"], [46, 100, 34],
               "Answers state what was done and what was not. The answers are written text; any number they quote comes from a score file copied into the Scores sheet.")
    for row_ in D.QUESTIONS:
        add(qs, list(row_))
    sc = sheet(wb, "Scores", ["Copied from the output files, line by line (nothing retyped)"], [160],
               "Each block names its file and when the file was last written. Rerunning the scripts and rebuilding this workbook updates it.")
    for line in ("HOW TO READ THE COLUMNS",
                 "found / loose found: the key line has an output line with the same polarity, verbs sharing a word or its first 4 letters, and subjects and objects each sharing a content word (or both empty).",
                 "exact: subject, verb and object word for word (after folding case and punctuation).",
                 "heads (treebank): found, and subject and object each contain the gold head word and no word from outside the gold phrase.",
                 "subj+verb right: the subject and the verb are right, whatever the object.",
                 "recipient kept (ptb_rules): the gold recipient's words appear in our object or recipient slot; with the tree rules alone they land in the object slot, since the tree has no recipient label. recipient right (wsj_score): in the recipient slot and not in the object slot.",
                 "extra / lines not in gold: output lines that match no key line. right label: found with the right status (stated, reported, embedded).",
                 "McNemar p and the interval are two different tests on the same paired lines; when the test gives p = 0.06 and the interval just excludes zero, the difference is borderline.",
                 "dep_disagree, English rows: subject and object arcs only, so 'all words' there means all subject and object words.", ""):
        rr_ = add(sc, [line]); sc.cell(row=rr_, column=1).data_type = "s"
        if line == "HOW TO READ THE COLUMNS":
            sc.cell(row=rr_, column=1).font = Font(name="Calibri", bold=True, size=10)
    import time as _t
    for rel, what in (("scores_v6b/compare3.txt", "debate keys: each parser, the vote and the tree-first designs; exact and loose; paired tests"),
                      ("scores_v6b/strict.txt", "debate keys: loose against exact"), ("wsj/wsj_score.txt", "Penn Treebank gold: every method"),
                      ("scores_v6b/ptb_rules.txt", "Penn Treebank: tree rules on the gold trees, 20 sentences in full, then the totals"),
                      ("ud_eval/ud_eval_results.txt", "UD test sets: spaCy and Stanza dependency accuracy"), ("ud_eval/README.md", "why spaCy English looks low on UD"),
                      ("scores_v6b/dep_disagree.txt", "where spaCy and Stanza disagree, and who is right"), ("scores_v6b/pronouns.txt", "pronouns and roles in place of names"),
                      ("machine.txt", "machine and software")):
        fp = Path(A.outputs) / rel
        r_ = add(sc, [f"FILE outputs/{rel}: {what}" + (f" (last written {_t.strftime('%Y-%m-%d %H:%M', _t.localtime(fp.stat().st_mtime))})" if fp.exists() else " (not found when this workbook was built)")])
        sc.cell(row=r_, column=1).font = Font(name=FONT, bold=True, size=10)
        sc.cell(row=r_, column=1).fill = PatternFill("solid", fgColor="D9D9D9")
        if fp.exists():
            for line in fp.read_text(encoding="utf-8").splitlines():
                rr = add(sc, [line])
                sc.cell(row=rr, column=1).data_type = "s"          # a line like "== all" is text, not a formula
                sc.cell(row=rr, column=1).font = Font(name="Calibri", size=9)
                sc.cell(row=rr, column=1).alignment = Alignment(wrap_text=False)
        add(sc, [""])
    src = sheet(wb, "Sources", ["Parser", "What it gives", "Version", "Model", "Code (GitHub)", "Trained on"], [30, 34, 10, 40, 50, 70])
    for row_ in [("spaCy (Explosion)", "dependency parse", "3.8.14", "en_core_web_lg 3.8.0, fr_core_news_lg 3.8.0", "https://github.com/explosion/spaCy",
                  "English: OntoNotes 5, converted to dependencies with ClearNLP (model metadata). French: UD French Sequoia 2.8, WikiNER (model metadata)."),
                 ("Stanza (Stanford NLP)", "dependency parse; English constituency tree", "1.15.0", "combined_charlm (UD 2.18); English constituency ptb3-revised_charlm", "https://github.com/stanfordnlp/stanza",
                  "Dependencies, English: UD EWT, GUM, GUMReddit, PUD, Pronouns and a hand-parsed set; French: UD GSD, ParisStories, Rhapsodie, Sequoia and a hand-parsed set (resources_1.15.0.json). English tree: the revised Penn Treebank 3."),
                 ("Berkeley Neural Parser (benepar)", "French constituency tree", "0.2.0", "benepar_fr2", "https://github.com/nikitakit/self-attentive-parser",
                  "The French data of the SPMRL 2013/2014 shared task (French Treebank); 88.43 F1 on its test set (README). Based on XLM-R."),
                 ("isanlp_rst (UniRST)", "discourse units and relations", "3.2.2", "tchewik/isanlp_rst_v3, unirst", "https://github.com/tchewik/isanlp_rst",
                  "One multilingual model trained on the corpora of 11 languages; relation labels from RST-DT for English and ANNODIS for French. Relations right 55.2 (English RST-DT) and 30.6 (French ANNODIS) on its test sets (README).")]:
        add(src, list(row_))
    for col in (3, 4, 5):
        link_column(how, col)
    link_column(fil, 1); link_column(fil, 3)
    link_column(sents, 12)
    for r in range(src._r0 + 1, src._next):
        c = src.cell(row=r, column=5); link(c, c.value if str(c.value).startswith("https://") else None)
    for ws in (how, fil, sents, sp, st, tr, di, li, vo, ou, src, lab, qs):
        finish(ws)

    why_of = dict(DEBATE)
    for ws_, n, note in feat_ws:
        FL.block(ws_, 1, rows[n], why_of.get(n, ""), note, F, S, P, C, KIND, gh=gh, link=link)
    rr = 1
    flow_at = {}                                   # sentence ID -> first row of its flow in "Flow, every sentence"
    for n, why in DEBATE:
        if n in rows:
            flow_at[n] = rr
            rr = FL.block(flow_all, rr, rows[n], why, None, F, S, P, C, KIND, gh=gh, link=link)
    if A.treebank and Path(A.treebank).exists() and A.wsj and Path(A.wsj).exists():
        import ptb_gold as G
        gold = {(f, k): root for f, k, root in G.treebank_sentences(A.treebank)}
        wr = {(r["file"], r["k"]): r for r in json.load(open(A.wsj, encoding="utf-8"))["rows"]}
        if wsj_feat is not None and ("wsj_0010.mrg", 18) in wr:
            FL.setup(wsj_feat)
            FL.block(wsj_feat, 1, wr[("wsj_0010.mrg", 18)], "Penn Treebank: the executives gave the chefs a standing ovation",
                     "A sentence the annotators marked by hand. Compare our output (step 7) with their answer (step 8): 'the chefs' is the indirect object, 'a standing ovation' the object, and 'Knowing ...' has an understood subject (the executives).",
                     F, S, P, C, KIND, gold=G.gold_lines(gold[("wsj_0010.mrg", 18)]), gh=gh, link=link)
        for f, k in WSJ:
            if (f, k) in wr and (f, k) in gold:
                flow_at[wr[(f, k)]["n"]] = rr
                flow_at[(f, k)] = rr
                rr = FL.block(flow_all, rr, wr[(f, k)], "Penn Treebank sentence: ours against the annotators' answer", None, F, S, P, C, KIND, gold=G.gold_lines(gold[(f, k)]), gh=gh, link=link)
    internal_links(wb, flow_all, flow_at, sents)
    readme.column_dimensions["A"].width = 120
    lines = [
        ("Parser examples, step by step", True),
        ("Start with 'Start here' (the pipeline as boxes), then the Flow sheets: each one follows one real sentence from the record to the output triple, top to bottom. 'Flow, every sentence' does the same for all of them. The numbered sheets after that hold the same data as tables, for sorting and filtering.", False),
        ("Each example sentence goes through every step of the pipeline. One sheet per step; the ID column links the rows of one sentence across sheets.", False),
        ("", False),
        ("How it works: every step, its input file, its code, its output, how it is checked and its known limits.", False),
        ("Files: where every file comes from.", False),
        ("Sentences: the example sentences, where each comes from (sentence ID and file), and how many lines each step produced (counted by formula from the other sheets).", False),
        ("1 spaCy parse, 2 Stanza parse: every word, its relation, and the word it attaches to.", False),
        ("3 Tree: the constituency tree for each sentence.", False),
        ("4 Discourse: the discourse units and the relations between them.", False),
        ("5 Lines by parser: the subject | verb | object lines our rules read from each parse, separately.", False),
        ("6 Vote: which lines the 2-of-3 vote kept and which it dropped.", False),
        ("7 Output triples: one triple per clause with recipient, time, polarity, status, slots that need a referent, and ties between clauses.", False),
        ("8 Treebank gold: Wall Street Journal sentences, the annotators' gold lines next to ours.", False),
        ("Simple sentences: 45 English-French pairs, one construction each, with the expected lines and ours.", False),
        ("Rules: every rule function in the code, with its own description; the bottleneck is the vote.", False),
        ("Record fields: why each part of the output is what it is (the grammatical function behind each field).", False),
        ("Labels: every label in the parse sheets, in plain words.", False),
        ("Questions: what a reviewer is likely to ask, the answer, and where to look.", False),
        ("Scores: the score files copied in line by line, each with its file name and date.", False),
        ("Sources: each parser's version, model and code.", False),
        ("", False),
        ("How this file was made: printed by scripts/v6/examples_xlsx.py from the parses saved on Oct 19 (debate) and the Penn Treebank sample. "
         "Every parse, line, triple, count and score file is printed by the scripts. The explanations (step descriptions, flow notes, answers in Questions) are written text; "
         "where an answer quotes a number, it comes from one of the score files in the Scores sheet (compare3, strict, ptb_rules, ud_eval, machine), except the 88% and 93% for the treebank conversion, which come from the two review checks described in Questions. The code was written by Caprice with AI assistance. The debate answer keys used for scoring elsewhere were drafted "
         "with AI assistance and are not a gold standard; the Penn Treebank marks are human annotation.", False),
        ("Filters are on every sheet: filter the ID column to follow one sentence.", False),
        ("Every sentence ID (sample|1, test|A8|fr ...) is a link: click it to jump to that sentence's flow, top to bottom. On the Sentences sheet, the counts jump to that sentence's rows in each step sheet, and each flow's title jumps back to the Sentences list.", False),
        ("Blue underlined file names are links to that file in the project's GitHub repository. Files that are not in the repository (the Penn Treebank sample, under its license) have no link.", False),
    ]
    for i, (t, b) in enumerate(lines, 1):
        c = readme.cell(row=i, column=1, value=t)
        c.font = Font(name=FONT, size=12 if b else 10, bold=b)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(A.out)
    print("wrote", A.out, "with", len(wb.sheetnames), "sheets")


if __name__ == "__main__":
    main()
