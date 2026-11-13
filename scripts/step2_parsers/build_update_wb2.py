"""Workbook for David (next steps from the Oct 8 meeting): every step laid out plainly, with yes/no review columns.
Times New Roman 11, black text, grey header boxes, yellow review columns.
usage: build_update_wb2.py statements_v4.json concepts_v3.json spotlight_raw.json rel_linker.json text_evidence.json out.xlsx"""
import json, os, re, sys, urllib.parse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ.setdefault("FULLGRAPH_CACHE", os.path.join(HERE, "tenv/home/.kg_dump"))
import combine_lib as CL, preds as P
import concepts_v3 as C, concepts_v3_15d as O
C.load_pos(); O.load_pos()

ST, CON, RAW, REL, TXT, OUT = sys.argv[1:7]
st = json.load(open(ST)); d = json.load(open(CON)); raw = json.load(open(RAW)); rel = json.load(open(REL)); txt = json.load(open(TXT))
rows_pc = {r["n"]: r for r in json.load(open(os.path.join(HERE, "pc.json")))["rows"]}

FN = "Times New Roman"
B = Font(name=FN, size=11, color="000000"); BB = Font(name=FN, size=11, bold=True, color="000000")
T = Font(name=FN, size=14, bold=True, color="000000"); LINK = Font(name=FN, size=11, color="000000", underline="single")
GREY = PatternFill("solid", fgColor="D9D9D9"); LIGHT = PatternFill("solid", fgColor="F2F2F2"); YEL = PatternFill("solid", fgColor="FFF2B3")
g = Side(style="thin", color="A6A6A6"); BOX = Border(left=g, right=g, top=g, bottom=g)
WR = Alignment(wrap_text=True, vertical="top")
wb = Workbook()


def header(ws, headers, r0=1, review=()):
    for j, h in enumerate(headers, 1):
        c = ws.cell(r0, j, h); c.font = BB; c.fill = YEL if h in review else GREY; c.alignment = WR; c.border = BOX


def cell(ws, r, c, v, review=False, link=None):
    x = ws.cell(r, c, v); x.font = LINK if link else B; x.alignment = WR; x.border = BOX
    if link:
        x.hyperlink = link
    if review:
        x.fill = YEL
    return x


def table(ws, headers, data, widths, review=(), r0=1, links=None):
    header(ws, headers, r0, review)
    for i, row in enumerate(data, r0 + 1):
        for j, v in enumerate(row, 1):
            lk = links(i - r0 - 1, j - 1) if links else None
            cell(ws, i, j, v, headers[j - 1] in review, lk)
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(r0 + 1, 1)
    return r0 + len(data)


def yesno(ws, col, r1, r2):
    if r2 >= r1:
        dv = DataValidation(type="list", formula1='"yes,no"', allow_blank=True, showInputMessage=True, showErrorMessage=True,
                            promptTitle="Review", prompt="Pick yes or no from the arrow on the right of this cell.",
                            errorTitle="Review", error="Please pick yes or no.")
        ws.add_data_validation(dv); dv.add(f"{col}{r1}:{col}{r2}")


def text(ws, ref, t, font=B, merge=None, height=None, fill=None):
    ws[ref] = t; ws[ref].font = font; ws[ref].alignment = WR
    if fill:
        ws[ref].fill = fill
    if merge:
        ws.merge_cells(merge)
    if height:
        ws.row_dimensions[ws[ref].row].height = height


def wiki(lang_title):
    if not lang_title or ":" not in lang_title:
        return None
    lang, title = lang_title.split(":", 1)
    return f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def dbp(page):
    return ("https://dbpedia.org/page/" + urllib.parse.quote(page)) if page and not page.startswith("(") else None


def concepts(lst):
    return "; ".join(f"{a} → {b}" for a, b, *_ in lst) if lst else "(none found)"


KIND = {"asserted": "stated", "embedded": "embedded", "reported": "reported"}

# ======================= 1. Sentences and what each one split into (merged cells)
ws = wb.active; ws.title = "1 Sentences split"
hdr = ["Sentence #", "Language", "Jurisdiction", "Original sentence", "Number of predications", "Predication", "Subject", "Verb", "Object",
       "Found by dependency parse 1 (spaCy)", "Found by dependency parse 2 (Stanza)", "Found by constituency parse",
       "How it is stated", "What the RST (discourse) parse did", "Negated", "Hedged", "Matches an answer-key line?", "Is this predication correct? (reviewer: pick yes/no ▾)",
       "Is 'how it is stated' right? (reviewer: pick yes/no ▾)", "Notes"]
REV1 = hdr[17:20]
header(ws, hdr, 1, REV1)
r = 2; n_pred = 0
for row in st["rows"]:
    key = CL.KEY.get(row["n"], [])
    stl = row["statements"]
    agreed = [s for s in stl if s.get("source") == "agreed"]
    matched = {a for a in P.align(key, agreed) if a is not None} if key else set()
    start = r
    for k, s in enumerate(stl, 1):
        m = ("yes" if (s.get("source") == "agreed" and agreed.index(s) in matched) else "no") if key else "not checked"
        fb = s.get("found_by", [])
        rs = s.get("rst")
        if s.get("source") == "apposition":
            rst_txt = "not used (renaming after a comma, found by spaCy only)"
        elif rs and rs.startswith("parser's reading kept (only"):
            rst_txt = "not re-read (only stated lines are re-read)"
        elif rs and rs.startswith("parser's reading kept"):
            rst_txt = "agreed with the parses"
        else:
            rst_txt = f"changed it from {KIND.get(s.get('kind_parser'), s.get('kind_parser'))} to {KIND.get(s['kind'], s['kind'])} ({rs})"
        vals = [row["n"], row["lang"], row["jurisdiction"], row["text"], len(stl), k, s["subject"], s["verb"], s["object"] or "(none)",
                "yes" if "spacy" in fb else "no", "yes" if "stanza" in fb else "no", "yes" if "const" in fb else "no",
                KIND.get(s["kind"], s["kind"]), rst_txt, "yes" if s.get("negated") else "no", "yes" if s.get("hedged") else "no", m, "", "", ""]
        for j, v in enumerate(vals, 1):
            cell(ws, r, j, v, hdr[j - 1] in REV1)
        r += 1; n_pred += 1
    if r - 1 > start:
        for col in (1, 2, 3, 4, 5):
            ws.merge_cells(start_row=start, start_column=col, end_row=r - 1, end_column=col)
last1 = r - 1
for j, w in enumerate([8, 8, 10, 52, 11, 10, 26, 16, 32, 11, 11, 11, 11, 22, 8, 8, 11, 14, 14, 24], 1):
    ws.column_dimensions[get_column_letter(j)].width = w
ws.freeze_panes = "E2"
yesno(ws, "R", 2, last1); yesno(ws, "S", 2, last1)

# ======================= 2. Concept senses
ws = wb.create_sheet("2 Concept senses (43)")
hdr = ["Sentence #", "Sentence", "Subject or object", "Phrase", "Spotlight's first choice", "Our pick", "Our pick right? (Oct 13 check)",
       "Why we picked it", "Pages counted as right", "Link to our pick", "Is our pick correct? (reviewer: pick yes/no ▾)", "Correct page if wrong", "Notes"]
data = [[x["n"], rows_pc[x["n"]]["text"], x["side"], x["surface"], x["v0"], x["v1"] or "(none)", "yes" if x["v1_right"] else "no",
         x["v1_how"], ", ".join(x["accept"]), (x["v1"] or "") and f"dbpedia.org/page/{x['v1']}", "", "", ""] for x in d["sense_eval"]]
last2 = table(ws, hdr, data, [8, 48, 10, 18, 28, 28, 11, 38, 30, 30, 14, 26, 24], review=hdr[10:],
              links=lambda i, j: dbp(d["sense_eval"][i]["v1"]) if j == 9 else None)
yesno(ws, "K", 2, last2)

# ======================= 3. Stated claims, concept nodes, paths
def why_no_path(s):
    sb, ob = s["v1_subject"], s["v1_object"]
    sp = [x for x in sb if not x[1].startswith("(")]; op = [x for x in ob if not x[1].startswith("(")]
    p = s["v1_path"]
    if p and p["tau"] > 0:
        return "scored"
    if p:
        return "both ends have a concept node, but there is no route between them once 'see also' links are left out"
    if not sb:
        return "no concept node found for the subject (often a pronoun such as I, we, it, or a phrase with no DBpedia page)"
    if not sp:
        return "the subject is the bill under debate, which has no DBpedia page"
    if not ob:
        return "no concept node found for the object"
    if not op:
        return "the object is the bill under debate, which has no DBpedia page"
    return "a concept page exists but has no infobox links in the graph"

ws = wb.create_sheet("3 Claims and paths")
hdr = ["Sentence #", "Language", "Jurisdiction", "Sentence", "Claim (subject | verb | object)", "Negated", "Hedged",
       "Subject concept nodes", "Object concept nodes", "Path score τ", "Links in path", "Why there is no path score", "Path",
       "Are the concept nodes correct? (reviewer: pick yes/no ▾)", "Is the path evidence for the claim? (reviewer: pick yes/no ▾)", "Notes"]
data = []
for s in d["statements"]:
    p = s.get("v1_path") or {}
    w = why_no_path(s)
    data.append([s["n"], s["lang"], s["jurisdiction"], s["sentence"], s["statement"], "yes" if s["negated"] else "no",
                 "yes" if s["hedged"] else "no", concepts(s["v1_subject"]), concepts(s["v1_object"]),
                 p.get("tau") if w == "scored" else None, p.get("links") if w == "scored" else None, "" if w == "scored" else w,
                 p.get("path", "") if w == "scored" else "", "", "", ""])
last3 = table(ws, hdr, data, [8, 8, 10, 44, 38, 8, 8, 28, 28, 9, 8, 34, 56, 14, 16, 24], review=hdr[13:])
yesno(ws, "N", 2, last3); yesno(ws, "O", 2, last3)
for i in range(2, last3 + 1):
    ws.cell(i, 10).number_format = "0.000"

# ======================= 4. Claims vs Wikipedia text (with links)
ws = wb.create_sheet("4 Claims vs Wikipedia")
hdr = ["Sentence #", "Language", "Sentence", "Claim checked", "Negated", "Hedged", "Label", "Support (0 to 1)", "Contradict (0 to 1)",
       "Best sentence found", "Page it came from (link)", "Other page read 1", "Other page read 2", "Other page read 3", "Other page read 4",
       "Is the label correct? (reviewer: pick yes/no ▾)", "Does the sentence bear on the claim? (reviewer: pick yes/no ▾)", "Notes"]
deb = txt["debate"]
data, LK = [], []
for x in deb:
    ev = x["evidence_page"]
    others = [p for p in x["pages_read"] if p != ev][:4]
    others += [""] * (4 - len(others))
    data.append([x["n"], x["lang"], x["sentence"], x["hypothesis"], "yes" if x["negated"] else "no", "yes" if x["hedged"] else "no",
                 x["label"], x["support"], x["contradict"], x["evidence"] or "(no sentence shared words with the claim)",
                 ev.split(":", 1)[1].replace("_", " ") if ev else "", *[o.split(":", 1)[1].replace("_", " ") if o else "" for o in others], "", "", ""])
    LK.append([wiki(ev)] + [wiki(o) for o in others])
last4 = table(ws, hdr, data, [8, 8, 42, 34, 8, 8, 14, 9, 9, 48, 24, 20, 20, 20, 20, 14, 16, 24], review=hdr[15:],
              links=lambda i, j: LK[i][j - 10] if 10 <= j <= 14 else None)
yesno(ws, "P", 2, last4); yesno(ws, "Q", 2, last4)

# ======================= 5. The 300 judged facts, three methods
ws = wb.create_sheet("5 Judged facts, 3 methods")
hdr = ["Relation", "Group", "Subject", "Object", "Path score τ (current, Ciampaglia 2015)", "Path score τ (relation-aware, Shiralkar 2017)",
       "Path (relation-aware)", "Text check label", "Support (0 to 1)", "Contradict (0 to 1)", "Best sentence found", "Subject's Wikipedia page (link)",
       "Is the text check right? (reviewer: pick yes/no ▾)", "Notes"]
facts, LK5 = [], []
for a, b in zip(rel["judged_facts"], txt["judged_facts"]):
    facts.append([a["rel"].replace("_", " "), a["group"], (a["s"] or "(no page)").replace("_", " "), (a["o"] or "(no page)").replace("_", " "),
                  a.get("kl", "not in graph"), a.get("klrel", "not in graph"), a.get("klrel_path", ""), b.get("label", "not checked (no page)"),
                  b.get("support"), b.get("contradict"), b.get("evidence", ""), (a["s"] or "").replace("_", " "), "", ""])
    LK5.append(wiki("en:" + a["s"]) if a["s"] else None)
last5 = table(ws, hdr, facts, [12, 16, 26, 26, 12, 12, 48, 16, 9, 9, 46, 24, 14, 22], review=hdr[12:],
              links=lambda i, j: LK5[i] if j == 11 else None)
yesno(ws, "M", 2, last5)
for i in range(2, last5 + 1):
    for col in (5, 6, 9, 10):
        ws.cell(i, col).number_format = "0.000"

# ======================= 6. Capital punishment
ws = wb.create_sheet("6 This House condemns")
text(ws, "A1", "David's example (Oct 8): \"This House condemns capital punishment.\" The shortest path from each legislature's concept node to the "
     "Capital_punishment node, using factual infobox links only.", BB, "A1:G1", 34)
hdr = ["From", "To", "Path score τ", "Links in path", "Path", "Does this path say anything about the claim? (reviewer: pick yes/no ▾)", "Notes"]
data = [[x["subject"].replace("_", " "), x["object"].replace("_", " "), x.get("tau"), x.get("links"), x.get("path", ""), "", ""]
        for x in d["this_house_condemns_capital_punishment"]]
last6 = table(ws, hdr, data, [32, 20, 10, 8, 90, 20, 26], review=hdr[5:], r0=3)
yesno(ws, "F", 4, last6)

# ======================= 7. Words left out
ws = wb.create_sheet("7 Words left out")
hdr = ["Sentence #", "Sentence", "Word Spotlight spotted", "Page Spotlight gave it", "Part of speech", "Kept anyway (names a party)?",
       "Should it be a concept node? (reviewer: pick yes/no ▾)", "Notes"]
data = []
for n, cands in raw.items():
    t = rows_pc[int(n)]["text"]
    for c in cands:
        pg = c["senses"][0]["page"] if c["senses"] else None
        if not O.has_noun(t, c["offset"], c["surface"]):
            tags = [p for (x, y, p) in O.POS.get(t, []) if x < c["offset"] + len(c["surface"]) and y > c["offset"]]
            data.append([int(n), t, c["surface"], pg, "/".join(tags), "yes" if C.has_noun(t, c["offset"], c["surface"], pg) else "no", "", ""])
data.sort(key=lambda x: (x[0], x[2]))
last7 = table(ws, hdr, data, [8, 50, 18, 34, 12, 12, 16, 24], review=hdr[6:])
yesno(ws, "G", 2, last7)


# ======================= 8. The draft answer key itself (to check: Caprice for English, Joanie for French)
ws = wb.create_sheet("8 Answer key (draft)")
hdr = ["Sentence #", "Language", "Who checks it", "Original sentence", "Key line", "Subject", "Verb", "Object", "How it is stated", "Note",
       "Found by our method?", "Is this key line correct? (reviewer: pick yes/no ▾)", "Correction (if no)", "Is a line missing for this sentence? (reviewer: pick yes/no ▾)", "Notes"]
REV8 = hdr[11:15]
header(ws, hdr, 1, REV8)
r = 2
for row in st["rows"]:
    key = CL.KEY.get(row["n"], [])
    if not key:
        continue
    agreed = [s for s in row["statements"] if s.get("source") == "agreed"]
    al = P.align(key, agreed)
    start = r
    for k, (g, a) in enumerate(zip(key, al), 1):
        vals = [row["n"], row["lang"], "Caprice" if row["lang"] == "en" else "Joanie", row["text"], k, g[0], g[1], g[2] or "(none)",
                KIND.get(g[3], g[3]), g[4] if len(g) > 4 else "", "yes" if a is not None else "no", "", "", "", ""]
        for j, v in enumerate(vals, 1):
            cell(ws, r, j, v, hdr[j - 1] in REV8)
        r += 1
    if r - 1 > start:
        for col in (1, 2, 3, 4, 14):
            ws.merge_cells(start_row=start, start_column=col, end_row=r - 1, end_column=col)
last8 = r - 1
for j, w in enumerate([8, 8, 10, 50, 7, 26, 16, 32, 11, 30, 11, 14, 26, 14, 22], 1):
    ws.column_dimensions[get_column_letter(j)].width = w
ws.freeze_panes = "E2"
yesno(ws, "L", 2, last8)
for rr in range(2, last8 + 1):
    pass
dv = DataValidation(type="list", formula1='"yes,no"', allow_blank=True, showInputMessage=True, prompt="Pick yes or no from the arrow on the right of this cell.")
ws.add_data_validation(dv); dv.add(f"N2:N{last8}")

# ======================= Summary
ws0 = wb.create_sheet("Summary", 0)
for col, w in zip("ABCD", (60, 11, 9, 70)):
    ws0.column_dimensions[col].width = w
text(ws0, "A1", "Factuality pipeline: next steps from the October 8 meeting", T)
text(ws0, "A2", "All results are on the 100-sentence development sample (US House, Ontario, Quebec; English and French), the sample with the hand-made "
     "answer key. Run on Caprice's laptop on October 15 and 16, 2026. Each numbered sheet is one step; the yellow columns are for review.", B, "A2:D2", 46)

def fr(prefix):
    for s in st["summary"]:
        if s.startswith(prefix):
            m = re.search(r"(\d+)/(\d+)", s); return int(m.group(1)), int(m.group(2))
    return None, None
def auc(src, score, comp):
    for s in src["summary"]:
        if s.get("relation") == "all" and s.get("score") == score and s.get("comparison") == comp:
            return s["auc"]
e1, e2 = fr("2 of 3 en"); f1, f2 = fr("2 of 3 fr")
S3 = "'3 Claims and paths'"; S1 = "'1 Sentences split'"; S4 = "'4 Claims vs Wikipedia'"
sections = [
    ("Step 1. Splitting sentences into predications (sheet 1)", [
        ("Draft answer-key lines found, English", e1, e2, "Each sentence is read by two dependency parses (spaCy and Stanza) and a constituency parse; a predication is kept when at least two of the three produce it (sheet 1 shows which ones did). The RST (discourse) parse then decides how each stated one is used. 'Found' means it matches a line in the hand-made answer key."),
        ("Draft answer-key lines found, French", f1, f2, "Same method. It was 80 before the French constituency parser (Berkeley parser, French Treebank model) was working."),
        ("Predications from the 100 sentences", f"=COUNTA({S1}!F2:F{last1})", None, "Counted from sheet 1: one row per predication, 1 to 9 per sentence."),
        ("Lines in the draft answer key (sheet 8)", f"=COUNTA('8 Answer key (draft)'!E2:E{last8})", None, "The answer key is a draft written from the sentence text alone, before looking at any method's output. Caprice checks the English lines and Joanie the French ones on sheet 8; the scores above get recomputed after."),
        ("…stated as fact by the speaker", f"=COUNTIF({S1}!M2:M{last1},\"stated\")", None, "Only stated predications are checked further. 'Embedded' ones sit inside an if-clause, a purpose ('to ...') or a clause describing a noun; 'reported' ones are someone else's words. Neither is something the speaker claims."),
    ]),
    ("Step 2. Matching subjects and objects to concept nodes (sheet 2)", [
        ("Hand-checked phrases matched to the right DBpedia page", f"=COUNTIF('2 Concept senses (43)'!G2:G{last2},\"yes\")", f"=COUNTA('2 Concept senses (43)'!A2:A{last2})", "43 phrases checked by hand on October 13. DBpedia Spotlight (on Dunkleosteus) proposes pages; our checks then reject pages that are films, sports people, located in another country, or not nouns. Spotlight alone gets 29 right."),
    ]),
    ("Step 3. Shortest path between the concept nodes (sheet 3)", [
        ("Stated claims with a concept node at both ends", f"=SUMPRODUCT(({S3}!L2:L{last3}=\"\")*1)+COUNTIF({S3}!L2:L{last3},\"both ends*\")", f"=COUNTA({S3}!A2:A{last3})", "A path can only be looked for when both the subject and the object have a DBpedia page. Column L on sheet 3 gives the reason for every claim that has no path score."),
        ("…with a route between them", f"=COUNT({S3}!J2:J{last3})", None, "Ciampaglia et al. (2015) path score on the 2022 DBpedia infobox graph (7.2 million pages, 20.7 million factual links). Routes through very general, highly connected pages count for less. τ = 1 is a direct link."),
        ("…of those, a direct link", f"=COUNTIF({S3}!K2:K{last3},1)", None, "The only one is Arkansas, country, United States: true, but not the claim, which is about meth lab seizures."),
        ("Claims with no subject concept node", f"=COUNTIF({S3}!L2:L{last3},\"no concept node found for the subject*\")", None, "Mostly pronouns (I, we, it) and phrases with no DBpedia page."),
        ("Claims whose subject or object is the bill itself", f"=COUNTIF({S3}!L2:L{last3},\"*bill under debate*\")", None, "Bills like H.R. 5 or Ontario Bill 45 have no DBpedia page."),
    ]),
    ("Step 4. Checking claims against Wikipedia text (sheet 4)", [
        ("Debate claims supported", f"=COUNTIF({S4}!G2:G{last4},\"supported\")", f"=COUNTA({S4}!A2:A{last4})", "For each claim: Wikipedia search (French Wikipedia for French claims) plus the claim's own concept pages; the 5 sentences sharing the most words with the claim; a multilingual inference model (mDeBERTa-v3, trained on NLI in 27 languages) judges each one. Links to every page read are on sheet 4."),
        ("…contradicted", f"=COUNTIF({S4}!G2:G{last4},\"contradicted\")", None, "Not reliable yet: search often returns unrelated sentences, and the model calls those 'contradicted'."),
        ("…not enough information", f"=COUNTIF({S4}!G2:G{last4},\"not enough information\")", None, "No sentence clearly supports or contradicts the claim."),
    ]),
    ("Step 5. Testing the methods on 300 facts with known answers (sheet 5)", [
        ("Current path score: true vs made-up facts", auc(rel, "kl", "true vs made up"), None, "AUC = the chance that a randomly chosen true fact scores higher than a randomly chosen false one (0.5 is guessing, 1 is perfect). The 300 facts are Google's relation-extraction corpus: 50 judged true, 50 judged false and 50 made up by swapping, for place of birth and for school attended."),
        ("Current path score: true vs judged-false facts", auc(rel, "kl", "true vs judged false"), None, "Judged-false facts are harder than made-up ones: raters read the source text and said it does not support them."),
        ("Relation-aware path score: true vs made-up", auc(rel, "klrel", "true vs made up"), None, "Shiralkar et al. (2017): each step costs more when its link type (school, birthplace...) is unlike the claim's relation. It did not beat the current score here."),
        ("Relation-aware path score: true vs judged-false", auc(rel, "klrel", "true vs judged false"), None, "Same 271 facts as the current score (the others have a page missing from the graph)."),
        ("Wikipedia text check: true vs made-up", auc(txt, "support minus contradict", "true vs made up"), None, "Score = support minus contradict, reading the subject's Wikipedia page. On exactly the same 271 facts as the path scores: 0.93."),
        ("Wikipedia text check: true vs judged-false", auc(txt, "support minus contradict", "true vs judged false"), None, "On the same 271 facts: 0.76. Caveat: Google built its true facts from Wikipedia sentences, so this test favours the text check."),
    ]),
]
r = 4
for title, items in sections:
    text(ws0, f"A{r}", title, BB, f"A{r}:D{r}", fill=LIGHT); ws0[f"A{r}"].border = BOX; r += 1
    for c, h in zip("ABCD", ("Measure", "Value", "Out of", "How it was measured")):
        ws0[f"{c}{r}"] = h; ws0[f"{c}{r}"].font = BB; ws0[f"{c}{r}"].fill = GREY; ws0[f"{c}{r}"].border = BOX
    r += 1
    for a, b, c, dd in items:
        for col, v in zip("ABCD", (a, b, c, dd)):
            ws0[f"{col}{r}"] = v; ws0[f"{col}{r}"].font = B; ws0[f"{col}{r}"].border = BOX; ws0[f"{col}{r}"].alignment = WR
        if isinstance(b, float):
            ws0[f"B{r}"].number_format = "0.000"
        ws0.row_dimensions[r].height = max(30, 15 * (len(dd) // 85 + 1))
        r += 1
    r += 1
text(ws0, f"A{r}", "What this shows", BB, f"A{r}:D{r}", fill=LIGHT); r += 1
for t in ["1. Splitting sentences into predications works: about 90% of answer-key lines in English and 80% in French.",
          "2. The DBpedia shortest paths are not evidence for these claims. The routes run through people's birthplaces and schools, and the relation-aware version did not do better.",
          "3. Wikipedia text separates true from false facts much better than the paths do, on the 300 facts with known answers.",
          "4. On our debate claims the text check needs work: a sentence should only count when it mentions both ends of the claim.",
          "5. Questions for David: what counts as evidence for claims like 'SB-8 bars abortion', and when is the NLP group deadline?"]:
    text(ws0, f"A{r}", t, B, f"A{r}:D{r}", 30); r += 1
r += 1
text(ws0, f"A{r}", "Terms", BB, f"A{r}:D{r}", fill=LIGHT); r += 1
for a, b in [("Predication", "a subject | verb | object statement pulled out of a sentence"),
             ("Concept node", "the DBpedia page a subject or object is matched to (Ciampaglia's term for a node in the knowledge graph)"),
             ("Path score τ", "1 / (1 + the cost of the cheapest path); passing through a page with many links costs more; a direct link scores 1"),
             ("AUC", "the chance a true fact outscores a false one; 0.5 is guessing, 1 is perfect"),
             ("Supported / contradicted", "the inference model's chance (0 to 1) that the best sentence supports or contradicts the claim is 0.5 or more")]:
    ws0[f"A{r}"] = a; ws0[f"A{r}"].font = BB; ws0[f"A{r}"].border = BOX
    ws0[f"B{r}"] = b; ws0[f"B{r}"].font = B; ws0[f"B{r}"].alignment = WR; ws0.merge_cells(f"B{r}:D{r}"); ws0.row_dimensions[r].height = 30; r += 1
r += 1
text(ws0, f"A{r}", "How to review", BB, f"A{r}:D{r}", fill=LIGHT); r += 1
text(ws0, f"A{r}", "Fill in only the yellow columns. Each has a yes/no drop-down.", B, f"A{r}:D{r}"); r += 1
text(ws0, f"A{r}", "Example (sheet 2): sentence 3, 'Medicare' → Medicare_Advantage. Is our pick correct? no. Correct page if wrong: Medicare_(United_States).",
     B, f"A{r}:D{r}", 30, YEL)
ws0.sheet_view.showGridLines = False
wb.properties.creator = "Caprice"; wb.properties.lastModifiedBy = "Caprice"
wb.save(OUT); print(OUT, "predication rows", n_pred)
