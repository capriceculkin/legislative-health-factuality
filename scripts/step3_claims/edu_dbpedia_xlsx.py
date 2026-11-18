"""edu_dbpedia_xlsx.py EDU_DBPEDIA.json OUT.xlsx [SENSE_CHECK.csv [ADJUSTED.json]]

The DBpedia check (edu_dbpedia.py) as a workbook to read and mark: a start page, every claim with the concepts at its
two ends and why an end has none, every concept once (word and page) to mark right or wrong, the reasons counted, and
the comparison with the Oct 15 run. Every cell is printed from edu_dbpedia.json. Needs openpyxl.
    python3 scripts/step3_claims/edu_dbpedia_xlsx.py outputs/dbpedia/edu_dbpedia.json docs/dbpedia_check.xlsx"""
import collections
import csv
import json
import math
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

d = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]
SENSE = {}                      # (word, page) -> the two independent readings of whether the page is what the speaker means
if len(sys.argv) > 3:
    for x in csv.DictReader(open(sys.argv[3], encoding="utf-8")):
        SENSE[(x["word"], x["page"])] = x
ADJ = json.load(open(sys.argv[4], encoding="utf-8")) if len(sys.argv) > 4 else None
FONT = "Calibri"
HEAD = Font(name=FONT, bold=True, size=10, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="595959")
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
NOTE = Font(name=FONT, italic=True, size=9, color="595959")
TITLE = Font(name=FONT, bold=True, size=13)
BAND = PatternFill("solid", fgColor="F2F2F2")
MARK = PatternFill("solid", fgColor="FFF2CC")
THIN = Border(bottom=Side(style="thin", color="D9D9D9"))
WRAP = Alignment(wrap_text=True, vertical="top")


def sheet(wb, title, headers, widths, note=None):
    ws = wb.create_sheet(title)
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
    ws._r0, ws._next, ws._band, ws._mark = r0, r0 + 1, {}, [j for j, h in enumerate(headers, 1) if h.startswith(("Right", "Note"))]
    return ws


def add(ws, values, group=None):
    r = ws._next
    ws._next += 1
    band = group is not None and ws._band.setdefault(group, len(ws._band) % 2)
    for j, v in enumerate(values, 1):
        c = ws.cell(row=r, column=j, value=v)
        c.font, c.border = BODY, THIN
        c.alignment = Alignment(wrap_text=isinstance(v, str) and len(v) > 30, vertical="top")
        if j in ws._mark:
            c.fill = MARK
        elif band:
            c.fill = BAND
    return r


def finish(ws):
    ws.auto_filter.ref = f"A{ws._r0}:{get_column_letter(ws.max_column)}{ws._next - 1}"


def cons(side):
    return "\n".join(f"{c['surface']} -> {c['page']}" for c in side["concepts"]) or ""


rows = d["rows"]
claims = [(r, c) for r in rows for c in r["claims"]]
wb = Workbook()
ws = wb.active
ws.title = "Start here"
ws.column_dimensions["A"].width = 30
ws.column_dimensions["B"].width = 125
start = [
    ("#TITLE", "DBpedia concepts in the discourse-first claims"),
    ("What was asked (Oct 22)", None),
    ("Oct 22 meeting notes", "David expects fewer DBpedia-worthy facts than hoped, since many claims will be plain statements that "
                             "are not DBpedia concepts."),
    ("Oct 22 meeting notes", "How are we identifying what is in DBpedia and what is not?"),
    ("Oct 22 meeting notes", "Keep the output of each step in a data structure that can be read, to see which DBpedia elements are "
                             "present and why or why not."),
    ("Oct 22 meeting notes", "Most DBpedia matches will likely come from nouns and the links between them."),
    ("Oct 22 meeting notes", "It will give a sense of how much of the speech is encyclopedic fact."),
    ("What this does", None),
    ("Concepts", "The same concept step as the Oct 15 run (scripts/step2_parsers/concepts_v3.py, version 1, unchanged): the institutions of each "
                 "legislature, exact page titles for names, Spotlight's senses re-ranked by the sentence, the common-noun list, French "
                 "pages mapped to English. Run on the subject and the object of every claim the discourse-first pipeline read."),
    ("The walk", "Between a subject concept and an object concept on the 2022 infobox graph (the Ciampaglia path score; 'see also' "
                 "links left out). A score near 1 is a short walk; 0 means no walk."),
    ("Why not", "For every end with no concept, the reason: a pronoun, a whole clause, a number, no object, the bill under debate, "
                "Spotlight spotted nothing, Spotlight's senses were rejected (with the reason), not a noun or a name, or not in the graph."),
    ("Data", f"{len(rows)} sentences (the 100 sample sentences, the 30 held-out sentences and the 60 new ones; the made-up test pairs "
             f"are left out), {len(claims)} claims. Every sentence, unit, claim, concept and walk is in outputs/dbpedia/edu_dbpedia.json."),
    ("Graph and Spotlight", f"{d['graph']}; Spotlight answers: {d['spotlight']}."),
    ("Results", None),
]
start += [("", ln) for ln in d["summary"].split("\n") if ln.strip()]
if SENSE:
    vals = collections.Counter(x["both_readings"] for x in SENSE.values())
    start += [("Is each page the right sense?", None),
              ("How this was checked", f"Every distinct word and page pair ({len(SENSE)}) was read twice, independently, by two AI readers "
               "working only from the sentence (not the web): is this page the thing the speaker means? Both readings are on the Concepts "
               "tab. They are one kind of check done twice, not a person's check; the Right? column is for that."),
              ("Both readings say right", str(vals["right"])), ("Both readings say wrong", str(vals["wrong"])),
              ("The readings disagree or are unsure", str(len(SENSE) - vals["right"] - vals["wrong"]))]
if ADJ:
    def line(mode, g):
        a = ADJ[mode]; n = a[f"{g}|claims"]
        return f"{g}: both ends right {a[f'{g}|both']}/{n} ({100 * a[f'{g}|both'] / n:.0f}%), a walk between them {a[f'{g}|walk']}/{n}"
    start += [("Counting only right senses", None),
              ("Strict (both readings right)", "; ".join(line("strict", g) for g in ("all", "US House", "Ontario", "Quebec"))),
              ("Lenient (either reading right)", "; ".join(line("lenient", g) for g in ("all", "US House", "Ontario", "Quebec"))),
              ("", "The walk is recomputed between right pages only. These replace 'both ends in DBpedia' above as the share of claims "
                   "that are encyclopedic facts, until a person has checked the senses.")]
start += [
    ("How to check", None),
    ("Concepts tab", "Every word and page pair once. Mark Right? yes or no (is this the thing the speaker means?). One mark covers "
                     "every claim it appears in."),
    ("Claims tab", "Every claim. Mark Right? for the why-not reasons, and add any concept that was missed."),
    ("What the marks are for", "Nothing here has been checked by a person yet. The concepts and the reasons are the program's; the "
                               "marks are the check."),
]
r = 1
for a, b in start:
    if a == "#TITLE":
        ws.cell(row=r, column=1, value=b).font = TITLE
    elif b is None:
        r += 1
        ws.cell(row=r, column=1, value=a).font = BOLD
    else:
        ws.cell(row=r, column=1, value=a).font = BOLD if a else BODY
        c = ws.cell(row=r, column=2, value=b)
        c.font = Font(name="Consolas" if a == "" else FONT, size=10)
        c.alignment = WRAP
    r += 1

# ------------------------------------------------------------------ concepts once
cw = sheet(wb, "Concepts", ["Word", "Page", "How it was found", "Claims", "Sentences", "Example sentence", "DBpedia page",
                            "Worth a look", "Reading A", "Reading B", "Right?", "Note"],
           [24, 34, 40, 8, 26, 70, 40, 22, 30, 30, 9, 30],
           note="Every word and page pair the concept step gave, once. 'Worth a look': a name whose page name shares no word with it "
                "(like AHP -> Krasue on Oct 15), or a concept judged wrong in the Oct 13 hand check.")
pairs = collections.OrderedDict()
for r, c in claims:
    for s in ("subject", "object"):
        for x in c[s]["concepts"]:
            k = (x["surface"], x["page"])
            p = pairs.setdefault(k, {"how": x["how"], "n": 0, "sents": [], "ex": r["text"], "link": x["dbpedia"], "odd": x["page_name_unlike_words"],
                                     "old": x["hand_checked_oct13"]})
            p["n"] += 1
            if r["n"] not in p["sents"]:
                p["sents"].append(r["n"])
def first(kv):
    sx = SENSE.get(kv[0])
    bad = 0 if sx and sx["both_readings"] == "wrong" else 1 if sx and sx["both_readings"] != "right" else 2
    return (bad, not kv[1]["odd"], kv[0][1].startswith("("), kv[0][1].lower())


for (w, pg), p in sorted(pairs.items(), key=first):
    look = "page name unlike the word" if p["odd"] else ("judged wrong on Oct 13" if p["old"] is False else "")
    sx = SENSE.get((w, pg))
    if sx and sx["both_readings"] != "right":
        look = (look + "; " if look else "") + ("both readings say wrong" if sx["both_readings"] == "wrong" else "the readings disagree")
    ra = f"{sx['reading_A']}: {sx['reason_A']}" if sx else ""
    rb = f"{sx['reading_B']}: {sx['reason_B']}" if sx else ""
    add(cw, [w, pg, p["how"], p["n"], ", ".join(p["sents"][:6]) + (" ..." if len(p["sents"]) > 6 else ""), p["ex"], p["link"], look, ra, rb, "", ""])
finish(cw)

# ------------------------------------------------------------------ every claim
hw = sheet(wb, "Claims", ["Sentence", "Legislature", "Language", "Unit", "Kind", "Subject", "Subject concepts", "Subject: why none",
                          "Verb", "Object", "Object concepts", "Object: why none", "Verdict", "Walk score", "The walk",
                          "Concepts elsewhere in the unit", "Right?", "Note"],
           [14, 11, 8, 5, 9, 26, 26, 34, 14, 30, 26, 34, 24, 8, 50, 24, 8, 26],
           note="One row per claim, grouped by sentence. 'Why none' is filled only for an end with no concept. 'Concepts elsewhere in the unit': "
                "pages in the claim's own unit that are at neither end (in the verb or an adjunct).")
for r, c in claims:
    w = c["walk"] or {}
    add(hw, [r["n"], r["legislature"], "English" if r["lang"] == "en" else "French", c["unit"], c["kind"] + (" (negated)" if c["negated"] else ""),
             c["subject"]["phrase"], cons(c["subject"]), "" if c["subject"]["status"] == "in DBpedia" else f"{c['subject']['status']}: {c['subject']['reason']}",
             c["verb"], c["object"]["phrase"], cons(c["object"]), "" if c["object"]["status"] == "in DBpedia" else f"{c['object']['status']}: {c['object']['reason']}",
             c["verdict"], w.get("tau", ""), w.get("path", ""), ", ".join(c["unit_concepts_not_in_claim"]), "", ""], group=r["n"])
finish(hw)

# ------------------------------------------------------------------ reasons counted
rw = sheet(wb, "Why none, counted", ["End", "Status", "All", "US House", "Ontario", "Quebec", "English", "French", "Example"],
           [9, 26, 7, 9, 9, 9, 9, 9, 80])
for s in ("subject", "object"):
    st = collections.defaultdict(list)
    for r, c in claims:
        st[c[s]["status"]].append((r, c))
    for k, v in sorted(st.items(), key=lambda kv: -len(kv[1])):
        ex = next((f"{r['n']}: '{c[s]['phrase']}' ({c[s]['reason']})" for r, c in v if c[s]["reason"]), f"{v[0][0]['n']}: '{v[0][1][s]['phrase']}'")
        add(rw, [s, k, len(v)] + [sum(1 for r, _c in v if r["legislature"] == L) for L in ("US House", "Ontario", "Quebec")]
            + [sum(1 for r, _c in v if r["lang"] == g) for g in ("en", "fr")] + [ex], group=s)
finish(rw)

# ------------------------------------------------------------------ Oct 15
o = d.get("compared_with_oct15") or {}
ow = sheet(wb, "Compared with Oct 15", ["Measure", "Oct 15 (statements v4)", "Now (discourse first)", "Note"], [46, 22, 22, 70])
if o:
    def pc(a, b):
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "0/0"
    add(ow, ["Asserted claims in the 100 sample sentences", o["oct15_claims"], o["now_claims"], "the same sentences, the same concept step"])
    add(ow, ["Both ends in DBpedia", pc(o["oct15_both"], o["oct15_claims"]), pc(o["now_both"], o["now_claims"]), ""])
    add(ow, ["A walk links the two ends", pc(o["oct15_walk"], o["oct15_claims"]), pc(o["now_walk"], o["now_claims"]), ""])
    add(ow, ["Claims with the same subject and object in both runs", o["same_claims"], o["same_claims"],
             f"the same concepts for {o['same_concepts']}; these must match, since the concept step is unchanged"])
    if "spotlight_same" in o:
        add(ow, ["Spotlight's candidates, the same as on Oct 15", f"{o['spotlight_same']} sentences", "",
                 f"different for {o['spotlight_different']} (a different answer means the Spotlight server or its model changed)"])
    for x in o.get("different", []):
        add(ow, [f"different: {x[0]}", x[3], x[4], f"'{x[1]}' / '{x[2]}'"])
else:
    add(ow, ["The Oct 15 files were not found", "", "", "run edu_dbpedia.py with --oct15 pointing at the folder with concepts_v3.json"])
finish(ow)
wb.save(OUT)
print(f"wrote {OUT}: {len(claims)} claims, {len(pairs)} distinct concepts")
