"""edu_xlsx.py OUT.xlsx [--project DIR] [--misses french_misses.csv]

Discourse first (the Oct 22 design) as one Excel workbook, in the same layout as parser_examples.xlsx: a start page, a
page to go through together, flow pages that carry one sentence through every step, then one page per step with every
sentence. Every cell is printed from the files run_edu.sh writes (outputs/edu/) and the saved parses; nothing is typed
by hand except the notes on the flow pages and the questions. Needs openpyxl.
    python3 scripts/step3_claims/edu_xlsx.py docs/discourse_first_examples.xlsx --misses outputs/edu/french_misses_round5.csv"""
import argparse
import ast
import collections
import copy
import csv
import json
import math
import os
import re
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--project", default=".")
ap.add_argument("--misses", default="")
ap.add_argument("--figures", default="docs/figures", help="folder with the PNG figures from edu_figure_files.py")
A = ap.parse_args()
PROJ = Path(A.project)
RULES = Path(__file__).resolve().parent
PARSES = PROJ / "data" / "parity_oct19" / "parity_parses.json"
O = PROJ / "outputs" / "edu"
sys.argv = [sys.argv[0], str(RULES), str(PARSES)]
sys.path.insert(0, str(RULES))
import edu_pipeline as E      # noqa: E402
import full as F              # noqa: E402
import compare3 as K          # noqa: E402
import combine_lib as C       # noqa: E402
import gold_heldout as GH     # noqa: E402
import parallel_tests as PT   # noqa: E402
import examples_xlsx_docs as DOCS  # noqa: E402
from openpyxl import Workbook                                            # noqa: E402
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side   # noqa: E402
from openpyxl.utils import get_column_letter                             # noqa: E402

P, norm = F.P, K.norm
E.OPT["units_only"] = True
WITHIN_ONLY = {"discourse_subject": False, "demonstrative": False, "said_object": False, "frame_context": False, "relpron": False,
               "apposition_across": False}

FONT = "Calibri"
HEAD = Font(name=FONT, bold=True, size=10, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="595959")
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
NOTE = Font(name=FONT, italic=True, size=9, color="595959")
TITLE = Font(name=FONT, bold=True, size=13)
STEP = Font(name=FONT, bold=True, size=10, color="FFFFFF")
STEP_FILL = PatternFill("solid", fgColor="404040")
BAND = PatternFill("solid", fgColor="F2F2F2")
NOTE_FILL = PatternFill("solid", fgColor="E7E7E7")
GOOD = PatternFill("solid", fgColor="E2EFDA")
BAD = PatternFill("solid", fgColor="FCE4D6")
THIN = Border(bottom=Side(style="thin", color="D9D9D9"))
BLUE, GREEN, GRAY = "4472C4", "70AD47", "A6A6A6"
WRAP = Alignment(wrap_text=True, vertical="top")


def sheet(wb, title, headers, widths, note=None, tab=None):
    ws = wb.create_sheet(title)
    if tab:
        ws.sheet_properties.tabColor = tab
    r0 = 1
    if note:
        c = ws.cell(row=1, column=1, value=note)
        c.font, c.alignment = NOTE, WRAP
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.row_dimensions[1].height = 15 * max(2, math.ceil(len(note) / 150))
        r0 = 2
    for j, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=r0, column=j, value=h)
        c.font, c.fill, c.alignment = HEAD, HEAD_FILL, Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=2)
    ws._r0, ws._next, ws._band = r0, r0 + 1, {}
    return ws


def add(ws, values, group=None, fill=None):
    r = ws._next
    ws._next += 1
    for j, v in enumerate(values, 1):
        c = ws.cell(row=r, column=j, value=v)
        c.font, c.border = BODY, THIN
        c.alignment = Alignment(wrap_text=isinstance(v, str) and len(v) > 40, vertical="top")
    if group is not None and ws._band.setdefault(group, len(ws._band) % 2):
        for j in range(1, len(values) + 1):
            ws.cell(row=r, column=j).fill = BAND
    if fill is not None:
        for j in range(1, len(values) + 1):
            ws.cell(row=r, column=j).fill = fill
    return r


def finish(ws):
    ws.auto_filter.ref = f"A{ws._r0}:{get_column_letter(ws.max_column)}{ws._next - 1}"


def text_page(ws, rows, widths=(30, 120)):
    "A page of (label, text) rows; a row with only a label is a heading."
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    r = 1
    for row in rows:
        if row[0] == "#TITLE":
            ws.cell(row=r, column=1, value=row[1]).font = TITLE
        elif len(row) == 1 or row[1] is None:
            c = ws.cell(row=r, column=1, value=row[0])
            c.font, c.fill = STEP, STEP_FILL
            for j in range(2, len(widths) + 1):
                ws.cell(row=r, column=j).fill = STEP_FILL
        else:
            for j, v in enumerate(row, 1):
                c = ws.cell(row=r, column=j, value=v)
                c.font, c.alignment = (BOLD if j == 1 else BODY), WRAP
        r += 1
    return r


def span_name(sp):
    a, b = sp
    return f"unit {a}" if a == b else ("unit " + " and unit ".join(map(str, range(a, b + 1))) if b - a == 1 else
                                        "units " + ", ".join(map(str, range(a, b))) + f" and {b}")


def says(rec, rl):
    "For an attribution: which side says and which side is said, read from the words (edu_pipeline.attribution_sides)."
    if rl.get("shared") != "attribution":
        return ""
    sayer, said = E.attribution_sides(rl, rec["units"], rec["lang"])
    return f"{span_name(sayer)} says {span_name(said)}"


def line_str(l):
    s = f"{l['subject'] or '(none)'} | {l['verb']}{' (to-infinitive)' if l.get('infinitive') else ''} | {l['object']}"
    return s + ("   [negated]" if l.get("negated") else "")


# ------------------------------------------------------------------ data
ROWS = json.load(open(PARSES, encoding="utf-8"))["rows"]
BY_N = {r["n"]: r for r in ROWS}
MORE_ROWS = json.load(open(O / "more_parses.json", encoding="utf-8"))["rows"]
BY_N.update({r["n"]: r for r in MORE_ROWS})
TREES = json.load(open(O / "edu_trees.json", encoding="utf-8"))
SAVED = {r["n"]: r for f in ("edu_reparsed.json", "more_reparsed.json") for r in json.load(open(O / f, encoding="utf-8"))["rows"]}


def run(n, opt=None):
    saved = dict(E.OPT)
    try:
        E.OPT.update(opt or {})
        return E.process(copy.deepcopy(BY_N[n]), TREES[n])
    finally:
        E.OPT.clear()
        E.OPT.update(saved)


ORDER = [r["n"] for r in ROWS] + [r["n"] for r in MORE_ROWS]
FINAL = {n: run(n) for n in ORDER}
WITHIN = {n: run(n, WITHIN_ONLY) for n in ORDER}
same = sum([(l["unit"], l["subject"], l["verb"], l["object"]) for l in FINAL[n]["lines"]] ==
           [(l["unit"], l["subject"], l["verb"], l["object"]) for l in SAVED[n]["lines"]] for n in ORDER)
print(f"rerun here vs outputs/edu: {same} of {len(ORDER)} sentences give the same lines")
assert same == len(ORDER), "the rules here do not give the saved outputs; rerun run_edu.sh first"


def legislature(n):
    r = BY_N[n]
    sid = r.get("sentence_id") or ""
    if sid:
        return {"US": "US House", "ON": "Ontario", "QC": "Quebec"}.get(sid.split("|")[0], "")
    if n.startswith("more|"):
        return {"US": "US House", "ON": "Ontario", "QC": "Quebec"}[n.split("|")[1]]
    return "(test pair)"


# answer keys and scoring (the same tests as edu_score.py: found = preds.align, exact = subject, verb, object word for word)
TESTS = {}
for t in PT.T:
    for L in ("en", "fr"):
        k = t[L]["lines"]
        TESTS[f"test|{t['id']}|{L}"] = ast.literal_eval(k) if isinstance(k, str) else k


def key_of(r):
    if r["set"] == "sample":
        return C.KEY.get(r["key_n"]) or []
    if r["set"] == "heldout":
        return GH.GH.get(r["key_n"]) or []
    if r["set"] == "test":
        return TESTS.get(r["n"]) or []
    return []


SCORED = []
for r in ROWS:
    key = key_of(r)
    L = FINAL[r["n"]]["lines"]
    al = P.align(key, L) if key else []
    ex = {(norm(x["subject"]), norm(x["verb"]), norm(x["object"])) for x in L}
    for i, k in enumerate(key):
        hit = L[al[i]] if al[i] is not None else None
        exact = (norm(k[0]), norm(k[1]), norm(P._no_note(k[2]))) in ex
        SCORED.append({"n": r["n"], "set": r["set"], "lang": r["lang"], "key": k, "hit": hit, "found": hit is not None, "exact": exact})


def wilson(k, n, z=1.96):
    if not n:
        return (0, 0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * (c - h)), round(100 * (c + h)))


SETNAME = {"test": "simple tests", "sample": "100-sentence sample", "heldout": "held-out"}
SCORES = []
for s in ("test", "sample", "heldout"):
    for lang in ("en", "fr"):
        xs = [x for x in SCORED if x["set"] == s and x["lang"] == lang]
        n, f, e = len(xs), sum(x["found"] for x in xs), sum(x["exact"] for x in xs)
        SCORES.append((SETNAME[s], lang, len({x["n"] for x in xs}), n, f, e, wilson(f, n), wilson(e, n)))
saved_txt = (O / "edu_score_reparsed.txt").read_text(encoding="utf-8") if (O / "edu_score_reparsed.txt").exists() else ""
for name, lang, _, n, f, e, _, _ in SCORES:
    label = {"simple tests": "simple tests", "100-sentence sample": "sample", "held-out": "heldout"}[name] + " " + lang
    m = re.search(re.escape(label) + r"\s+discourse first\s+(\d+)/(\d+)\s+\d+%\s+(\d+)/(\d+)", saved_txt)
    assert m and (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (f, n, e), f"scores here differ from edu_score.py for {label}"
print("scores here match outputs/edu/edu_score_reparsed.txt for all six sets")

# ------------------------------------------------------------------ workbook
wb = Workbook()
wb.remove(wb.active)

# Start here
ws = wb.create_sheet("Start here")
ws.sheet_properties.tabColor = GREEN
sc = {(a, b): (f, n, e) for a, b, _, n, f, e, _, _ in SCORES}
pct = lambda a, b: f"{round(100 * a / b)}%"
start = [
    ("#TITLE", "Discourse first: a constituency tree for each discourse unit"),
    ("What this is", "The design from our Oct 22 meeting, built and run on the saved sentences. Every cell on the gray tabs is printed by "
                     "scripts/step3_claims/edu_xlsx.py from the files run_edu.sh writes (outputs/edu/), so it can be rebuilt after any change."),
    ("What the meeting asked for (from the Oct 22 meeting notes)", None),
    ("Discourse parse first", "Step 1 Discourse parse: isanlp_rst splits each sentence into units and gives the relations between them."),
    ("A constituency parse on each unit, not the sentence", "Step 2 Unit trees: each unit's own text parsed alone (Stanza for English, "
     "Berkeley benepar_fr2 for French). The sentence's own tree is never read."),
    ("Subjects and objects from each unit's tree, connections within", "Step 3-4 Lines, the Step 3 column: what each unit's tree gives before anything is connected."),
    ("The discourse parse makes the connections between units", "Step 3-4 Lines, the Step 4 columns: 'sending ...' is "
     "inferential to unit 0 and takes its subject; 'that is why' points to unit 0 and unit 1 together. Every borrowed part says which unit and relation it came through."),
    ("Only these two parsers, nothing to reconcile", "No dependency parse and no vote anywhere; the notebook checks that the outputs are identical with the dependency parses deleted."),
    ("The same for French", "Flow 2: 'L'an dernier' is the frame for both units, and the sentence gives its two claims."),
    ("More sentences from each parliament", "20 new sentences each from the US House, Ontario and Quebec (IDs starting 'more'), on every gray tab."),
    ("The trees in tree form, a tree inside a tree, drawn like Mann and Thompson", "The flows draw each unit's tree inside the "
     "discourse tree. The same drawing for every sentence: docs/discourse_first_figures.html."),
    ("'unit 0 to unit 2', not 'unit 0 0 to unit 2 2'", "Every relation in Step 1 and on the flows is written that way."),
    ("Bigger figures for the presentation in November", "The flow drawings are saved large in figures/ next to this workbook, for the slides."),
    ("Every step in a consumable data structure, to see which DBpedia elements are there and why or why not", "Step 5 Records for "
     "DBpedia and outputs/edu/discourse_first_records.json. The DBpedia look-up itself has not been run on these yet."),
    ("Results", None),
] + [(f"{name}, {lang} ({ns} sentences)", f"found {f}/{n} ({round(100*f/n)}%, 95% CI {fi[0]} to {fi[1]}), exact {e}/{n} ({round(100*e/n)}%, 95% CI {ei[0]} to {ei[1]})")
         for name, lang, ns, n, f, e, fi, ei in SCORES] + [
    ("Not comparable", "These are scored against our own keys, not the Penn Treebank, so they cannot be compared with the Penn Treebank numbers from "
                       "the Oct 22 workbook. This design has not been run on the Penn Treebank yet."),
    ("About the answer keys", "The sample and held-out keys are working keys drafted with Claude, not a hand-checked gold standard, so 'exact' means "
                              "agreement with those keys. 28 of the 87 French misses come from the keys disagreeing with each other (Check together)."),
    ("How it was checked", "The scores are computed here and by edu_score.py separately and agree; this workbook reruns the pipeline and gets the same "
                           "lines as outputs/edu for all 280 sentences; the results came out the same on my Mac and in a separate copy of the project; "
                           "the notebook has 111 checks and rule tests, all passing."),
    ("Help", "I had Claude help write and test the code and build the gray tabs."),
    ("Tabs", None),
    ("Check together (green)", "The questions for us, mostly about the answer keys."),
    ("Flows (blue)", "One sentence carried through every step on one page: the English and French sentences from Oct 22, and one where it still goes wrong."),
    ("Step 1 to Step 5 (gray)", "Every sentence at each step, with filters."),
    ("Key vs output, French misses", "Every key line next to the output, and every French miss with its cause."),
]
text_page(ws, start)

# Check together
ct = wb.create_sheet("Check together")
ct.sheet_properties.tabColor = GREEN
misses = list(csv.DictReader(open(A.misses, encoding="utf-8-sig"))) if A.misses and Path(A.misses).exists() else []
cause_n = collections.Counter(m["final cause"] for m in misses)
CAUSE = {"KEY": "the answer key (keys disagree or rewrite the text)", "OBJ_SHORT": "object stops too early", "XUNIT": "across units",
         "VERB": "verb form", "SUBJ": "subject span", "CONTROL": "verb + noun + de/à + infinitive", "OBJ_WRONG": "wrong phrase as object",
         "PARSER": "the unit's tree is wrong", "INVERSION": "subject after the verb", "OBJ_LONG": "object runs on", "AMBIG": "ambiguous"}
rows_ct = [
    ("#TITLE", "To go through together"),
    ("1. Is this the structure you had in mind?", None),
    ("Question", "Discourse parse first, a tree per unit, subject and object read within the unit, then the units connected through the discourse "
                 "relations, with no dependency parse. The two sentences from Oct 22 are on Flow 1 and Flow 2."),
    ("2. Conventions for the answer keys (French)", None),
    ("Why it matters", f"Of the {len(misses)} French key lines the pipeline does not match exactly, {cause_n.get('KEY', 0)} come from the keys, not the "
                       "pipeline. The held-out keys and the sample keys follow different rules. These are the questions to settle (with Joanie) "
                       "before the keys are checked by hand. The cases are listed under each question."),
    ("a. Object pronouns", "Does a clitic object stay in the verb? Held-out keys: Elle | l'a dit; le ministre | nous disait. Sample keys: "
                           "Les huit grandes villes | ont supplié | l' (le ministre) d'attendre; and 'y a injecté' written as 'a injecté'. "
                           "In the verb: held-out 17, 20, 22, 26. Out of the verb or dropped: sample 57, 62, 70."),
    ("b. Infinitives", "Is a following de / à + infinitive part of the verb? Sample keys: il | se propose de rendre | disponible ...; "
                       "le gouvernement | s'acharne à faire | des lois. Held-out keys: je | vais attendre | d'avoir sa réponse; "
                       "ma vis-à-vis | a choisi | d'agir avec un adjoint. "
                       "Joined: sample 57, 65, 68 (twice), 93, 94, 99, held-out 25. In the object: held-out 17, 18, 27, sample 56, 94."),
    ("c. Lists", "Is a list kept whole or cut to its first item? Kept: les gens | perdent | leur enthousiasme, leur confiance. "
                 "Cut: La commission parlementaire | peut discuter | de la déclaration de services (the sentence lists three)."),
    ("d. Negation", "Nine keys keep ne ... pas in the verb (je | ne sais pas). Two drop it: le gouvernement libéral | pourra congédier "
                    "(text: ne pourra pas congédier); les libéraux | remplissent (text: ne remplissent). "
                    "Kept: held-out 16, sample 52, 64, 68, 71, 78, 81, 88, 95. Dropped: sample 58, 73."),
    ("e. Articles", "Text 'du projet de loi n° 101': the key writes 'le projet de loi n° 101', the pipeline writes 'projet de loi n° 101'."),
    ("3. Where the design still goes wrong (French)", None),
] + [(f"{CAUSE.get(c, c)}", f"{v} key lines") for c, v in cause_n.most_common() if c != "KEY"] + [
    ("Examples", "Objects that stop too early: les parents | devraient laisser | leurs enfants (key: leurs enfants à la porte des édifices publics). "
                 "Light verbs: ils | n'ont pas | droit à la vignette (key: n'ont pas droit | à la vignette). "
                 "Subject after the verb: 'comme l'ont dit certains journaux' gives no line for certains journaux. "
                 "All of them are on the French misses tab."),
    ("4. Next steps", None),
    ("a", "Settle the conventions, then check the sample and held-out keys by hand (outputs/edu/hand_check.csv is ready for this)."),
    ("b", "Fix the pipeline problems that do not depend on a convention: light verbs, pas encore, subjects after the verb, time phrases taken "
          "as objects, and subjects cut short inside a unit."),
    ("c", "New French sentences from Joanie as a second held-out set."),
    ("d", "Run the design on the Penn Treebank sample so it can be compared with the earlier designs."),
]
text_page(ct, rows_ct)

# Flow pages
FLOWS = [
    ("sample|1", "Flow 1 hardware store", "The English sentence from Oct 22. 'that is why' is read through the explanation relation: 'that' stands for "
     "unit 0 and unit 1 together, the reason for unit 2. 'sending' has no subject in its unit and takes it from unit 0 through elaboration."),
    ("test|A8|fr", "Flow 2 Senat (French)", "The French sentence from Oct 22. 'L'an dernier' is a frame, not a subject, and is kept as the "
     "context of both claims. Each unit gets its own claim, read from its own tree. The French discourse parse makes unit 0 the main part of the frame "
     "relation: 'L'an dernier' contextualizes the whole sentence, and the chamber adopting the bill and the Senate refusing to act are set against it."),
    ("sample|58", "Flow 3 where it fails", "Where the design still goes wrong. The unit tree reads 'n'importe quoi' as a compound pronoun with a verb "
     "inside it, and the object is dropped (key: les libéraux | disent | n'importe quoi). The object of 'se rendent compte' stops at the end of its "
     "unit, though the coordinated verb in unit 2 belongs to it. The key also drops the negation in 'ne remplissent', unlike other keys."),
]


def flow(ws, n, note):
    ws.sheet_properties.tabColor = BLUE
    for j, w in enumerate((16, 14, 70, 40, 46), 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    rec, wit, row = FINAL[n], WITHIN[n], BY_N[n]
    r = 1
    ws.cell(row=r, column=1, value=f"{n}   ({legislature(n)}, {row['lang']})").font = TITLE
    r += 1
    c = ws.cell(row=r, column=1, value=row["text"])
    c.font, c.alignment = Font(name=FONT, size=11), WRAP
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.row_dimensions[r].height = 15 * max(1, math.ceil(len(row["text"]) / 140))
    r += 1
    c = ws.cell(row=r, column=1, value=note)
    c.font, c.fill, c.alignment = NOTE, NOTE_FILL, WRAP
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.row_dimensions[r].height = 15 * max(2, math.ceil(len(note) / 130))
    r += 2

    def step(title, what):
        nonlocal r
        for j in range(1, 6):
            ws.cell(row=r, column=j).fill = STEP_FILL
        ws.cell(row=r, column=1, value=title).font = STEP
        r += 1
        ws.cell(row=r, column=1, value=what).font = NOTE
        r += 1

    def put(vals, bold=False):
        nonlocal r
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=j, value=v)
            c.font, c.alignment, c.border = (BOLD if bold else BODY), WRAP, THIN
        r += 1

    step("STEP 1. Discourse parse", "isanlp_rst: the units, then how they are connected")
    put(["unit", "", "text"], True)
    for u in rec["units"]:
        put([u["unit"], "", u["text"]])
    r += 1
    put(["connection", "relation", "the parser's reading (from its main part)", "parser's own label / main part", "who says what (read from the words)"], True)
    for cn, rl in zip(rec["connections"], rec["relations"]):
        put([cn["from"] + " to " + cn["to"], cn["relation"], cn["reads"].split(": ", 1)[-1], f"{cn.get('parser_label', '')} / {cn['main']}", says(rec, rl)])
    r += 1
    step("STEP 2. A constituency tree for each unit, drawn inside the discourse tree",
         "the discourse relations on top (Mann and Thompson: a vertical line to the main part, an arrow from the supporting part); under each unit, its own constituency tree (punctuation left out)")
    png = FIG.get(n)
    if png:
        from openpyxl.drawing.image import Image as XLImage
        img = XLImage(png)
        w = 1250
        img.height, img.width = int(img.height * w / img.width), w
        ws.add_image(img, f"A{r}")
        r += math.ceil(img.height / 20) + 2
    else:
        put(["unit", "", "tree (bracketed)"], True)
        for u in rec["units"]:
            put([u["unit"], "", "  ".join(u["tree"])])
        r += 1
    step("STEP 3. Subject | verb | object in each unit", "from the unit's own tree only; nothing is taken from another unit yet")
    put(["unit", "", "line", "how (tree rule)"], True)
    for l in wit["lines"]:
        put([l["unit"], "", line_str(l), l.get("how", "")])
    if not wit["lines"]:
        put(["", "", "(no lines)"])
    r += 1
    step("STEP 4. The units connected", "a missing subject or object comes from the connected unit; 'that' stands for the units it points to")
    put(["unit", "", "line", "where the subject came from", "object from / that = / context"], True)
    for l in rec["lines"]:
        extra = "; ".join(x for x in (l.get("object_from") or "", ("that = " + l["refers_to"]) if l.get("refers_to") else "",
                                      ("context: " + "; ".join(l["context"])) if l.get("context") else "") if x)
        put([l["unit"], "", line_str(l), l.get("subject_from") or "its own unit", extra])
    r += 1
    key = key_of(row) if row.get("set") in ("sample", "heldout", "test") else []
    if key:
        step("Against the answer key", "found = a matching output line; exact = subject, verb and object word for word")
        put(["", "", "key line", "found", "exact"], True)
        for x in [x for x in SCORED if x["n"] == n]:
            rr = r
            put(["", "", " | ".join(map(str, x["key"][:3])), "yes" if x["found"] else "no", "yes" if x["exact"] else "no"])
            for j in (4, 5):
                ws.cell(row=rr, column=j).fill = GOOD if ws.cell(row=rr, column=j).value == "yes" else BAD
        r += 1
    step("STEP 5. The record for DBpedia", "one row per claim (tab Step 5 has every sentence)")
    put(["unit", "", "subject | verb | object", "negated / stated", "noun phrases to look up"], True)
    for l in rec["lines"]:
        nps = ", ".join(x for x in (clean_np(l["subject"]), clean_np(l["object"])) if x)
        put([l["unit"], "", line_str(l), f"{'negated' if l.get('negated') else 'not negated'}, {'stated' if l['kind'] == 'asserted' else l['kind']}", nps])


PRON = {"i", "we", "you", "he", "she", "it", "they", "il", "elle", "nous", "vous", "ils", "elles", "je", "on", "that", "this", "which",
        "ça", "ce", "c'", "cela", "qui", "que", "qu'", "there", "here", "le", "la", "les", "l'", "y", "en", "lui", "leur", "me", "te", "se",
        "him", "her", "them", "us", "me", "one", "ceci", "tout", "rien"}


PREP = r"(for|at|in|of|to|on|with|by|from|about|into|over|under|pour|à|au|aux|de|du|d'|en|dans|sur|avec|par|chez|vers|devant|selon)"
CLAUSE = r"^(to|that|whether|if|why|how|what|que|qu'|si|pourquoi|comment|ce que|ce qu')\b|^(be|have|do)\b"


def clean_np(s):
    "The noun phrase to look up: no (inh) or (unstated) note, no leading preposition, and nothing for a pronoun or a clause."
    s = re.sub(r"\(inh\)|\(unstated\)|\(apposition\)", "", s or "").strip(" ,.;:«»“”\"")
    s = re.sub(r"^" + PREP + r"\s*", "", s, flags=re.I) if not re.match(r"^(du|des|de la)\s", s, re.I) or len(s.split()) > 1 else s
    s = s.strip(" ,.;:")
    if not s or re.match(CLAUSE, s, re.I) or s.lower() in PRON | set(getattr(E, "DEMONSTR", set())):
        return ""
    return s


import edu_draw as DRAW                                   # noqa: E402
FIG = {n: str(PROJ / A.figures / (n.replace("|", "_") + ".png")) for n, _, _ in FLOWS if (PROJ / A.figures / (n.replace("|", "_") + ".png")).exists()}
FIGDIR = Path(A.out).with_suffix("").parent / "figures"
try:
    if len(FIG) == len(FLOWS):
        raise StopIteration                                 # all made by edu_figure_files.py already
    from playwright.sync_api import sync_playwright        # draws the figures the same way as docs/discourse_first_figures.html
    FIGDIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(device_scale_factor=2)
        for n, _, _ in FLOWS:
            if n in FIG:
                continue
            pg.set_content(f'<html><body style="margin:0;background:#fff">{DRAW.figure(FINAL[n], simple=True)}</body></html>')
            FIG[n] = str(FIGDIR / (n.replace("|", "_") + ".png"))
            pg.query_selector("svg").screenshot(path=FIG[n])
        br.close()
    print("drew", len(FIG), "figures into", FIGDIR)
except StopIteration:
    print("figures: using the PNGs in", PROJ / A.figures)
except Exception as ex:                                     # noqa: BLE001
    print("figures not drawn here (", type(ex).__name__, "); flows without a PNG in", A.figures, "show the bracketed trees instead")
for n, title, note in FLOWS:
    flow(wb.create_sheet(title), n, note)

# Step 1: the discourse parse, units and relations together (one block per sentence)
p1 = sheet(wb, "Step 1 Discourse parse", ["ID", "Legislature", "Language", "Kind", "Unit or connection", "Text, or the relation", "Parser's own label / main part",
                                          "Who says what (attribution, read from the words)"], [16, 12, 9, 10, 26, 90, 22, 28],
           "isanlp_rst 3.2.2 (UniRST). For each sentence: its units, then the relations between them, written as 'unit 0 and unit 1 to unit 2'. "
           "The French model marks the sayer as the main part of an attribution and the English model marks what is said, so the rules read who says "
           "what from the words (a verb of saying, que / that / si, a quote mark or a colon), shown in the last column.")
p2 = sheet(wb, "Step 2 Unit trees", ["ID", "Unit", "Unit text", "Constituency tree of the unit parsed alone (bracketed)"], [16, 6, 50, 140],
           "Each unit's own text parsed by the constituency parser (English: Stanza, Penn Treebank labels; French: Berkeley benepar_fr2, French Treebank "
           "labels). The sentence's own tree is never read. When the parser returns two trees for one unit, both are shown.")
p3 = sheet(wb, "Step 3-4 Lines", ["ID", "Unit", "Unit text", "Step 3: from the unit's own tree", "Step 4: Subject", "Verb", "Object",
                                  "Where the subject came from", "Where the object came from", "'that' / 'which' =", "Context (frame)"],
           [16, 6, 40, 46, 30, 22, 40, 34, 26, 36, 22],
           "Step 3 is what each unit's own tree gives before anything is connected. Step 4 is the final line after the discourse relations connect the "
           "units. Blank 'came from' means it came from the unit itself; '(added in step 4)' means the line only exists through a connection; "
           "'(joined into the verb before it)' means step 4 made it part of another line ('a choisi' + 'agir' gives 'a choisi d'agir').")
for n in ORDER:
    rec = FINAL[n]
    for u in rec["units"]:
        add(p1, [n, legislature(n), rec["lang"], "unit", f"unit {u['unit']}", u["text"], "", ""], n)
        add(p2, [n, u["unit"], u["text"], "  ".join(u["tree"])], n)
    for cn, rl in zip(rec["connections"], rec["relations"]):
        add(p1, [n, legislature(n), rec["lang"], "relation", cn["from"] + " to " + cn["to"], cn["relation"],
                 f"{cn.get('parser_label', '')} / {cn['main']}", says(rec, rl)], n)
    before = {(l["unit"], l.get("leaf"), l["verb"]): l for l in WITHIN[n]["lines"]}
    by_leaf = {(l["unit"], l.get("leaf")): l for l in WITHIN[n]["lines"] if l.get("leaf") is not None}
    used = set()
    for l in rec["lines"]:
        b = before.get((l["unit"], l.get("leaf"), l["verb"])) or (by_leaf.get((l["unit"], l.get("leaf"))) if l.get("leaf") is not None else None)
        if b is not None:
            used.add(id(b))
        add(p3, [n, l["unit"], rec["units"][l["unit"]]["text"], line_str(b) if b is not None else "(added in step 4)",
                 l["subject"], l["verb"] + (" (to-infinitive)" if l.get("infinitive") else ""), l["object"] + ("   [negated]" if l.get("negated") else ""),
                 l.get("subject_from") or "", l.get("object_from") or "", l.get("refers_to") or "", "; ".join(l.get("context") or [])], n)
    for b in WITHIN[n]["lines"]:
        if id(b) not in used:
            add(p3, [n, b["unit"], rec["units"][b["unit"]]["text"], line_str(b), "(joined into the verb before it in step 4)", "", "", "", "", "", ""], n)
for w in (p1, p2, p3):
    finish(w)

# Step 5: the record for DBpedia
p5 = sheet(wb, "Step 5 Records for DBpedia", ["ID", "Legislature", "Language", "Unit", "Subject", "Verb", "Object", "Negated", "Stated / embedded",
                                              "Subject to look up", "Object to look up", "Needs a referent first"],
           [16, 12, 9, 6, 32, 20, 40, 9, 12, 30, 30, 34], "One row per claim, the shape passed toward the DBpedia check (the full records are in "
           "outputs/edu/discourse_first_records.json). The look-up columns drop pronouns, clauses and a leading preposition ('at Bill 87' gives "
           "'Bill 87'). A pronoun or 'that' needs its referent before a look-up.")
for n in ORDER:
    rec = FINAL[n]
    for l in rec["lines"]:
        raw = re.sub(r"\(inh\)", "", l["subject"]).strip().lower()
        need = ("stands for " + l["refers_to"][:70]) if l.get("refers_to") else (("pronoun: " + l["subject"]) if raw in PRON else "")
        add(p5, [n, legislature(n), rec["lang"], l["unit"], l["subject"], l["verb"], l["object"], "yes" if l.get("negated") else "",
                 "stated" if l["kind"] == "asserted" else l["kind"], clean_np(l["subject"]), clean_np(l["object"]), need], n)
finish(p5)

# Key vs output: every key line, all three sets
kv = sheet(wb, "Key vs output", ["ID", "Set", "Language", "Sentence", "Key subject", "Key verb", "Key object", "Output subject", "Output verb",
                                 "Output object", "Found", "Exact"], [16, 14, 9, 60, 28, 20, 34, 28, 20, 34, 7, 7],
           "Every key line next to the output line it was matched to (simple test pairs, the 100-sentence sample, the held-out set). Found: a matching "
           "line (same verb, overlapping subject and object). Exact: subject, verb and object word for word, ignoring case and punctuation. Green is "
           "exact, orange is not found.")
first = set()
for x in SCORED:
    h = x["hit"] or {"subject": "", "verb": "", "object": ""}
    fill = GOOD if x["exact"] else (None if x["found"] else BAD)
    add(kv, [x["n"], SETNAME[x["set"]], x["lang"], BY_N[x["n"]]["text"] if x["n"] not in first else "", *map(str, x["key"][:3]),
             h["subject"], h["verb"], h["object"], "yes" if x["found"] else "no", "yes" if x["exact"] else "no"], x["n"], fill)
    first.add(x["n"])
finish(kv)

# French misses
if misses:
    fm = sheet(wb, "French misses", ["#", "ID", "Set", "Key subject", "Key verb", "Key object", "Output subject", "Output verb", "Output object",
                                     "What differs", "Cause", "Detail", "Sentence"], [5, 14, 9, 28, 20, 34, 28, 20, 34, 12, 26, 50, 80],
               "Every French key line not matched exactly (sample and held-out), with its cause. The causes are AI readings, not a linguist's: Claude "
               "classified each one and read the trees, a separate Claude agent classified them blind, and the two agreed on 65 of 87 (kappa 0.70) and on "
               "72 of 87 for pipeline versus key. Where they differed, the trees and the other keys decided.")
    for m in misses:
        add(fm, [int(m["#"]), m["sentence"], m["set"], m["key subject"], m["key verb"], m["key object"], m["output subject"], m["output verb"],
                 m["output object"], m["what differs"], CAUSE.get(m["final cause"], m["final cause"]), m["detail"], m["sentence text"]], m["sentence"])
    finish(fm)

wb.save(A.out)
print("wrote", A.out, "with", len(wb.sheetnames), "tabs:", ", ".join(wb.sheetnames))
