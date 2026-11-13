"""examples_docx.py TRACE.json PARSES.json READINGS.csv FIG_PNG_DIR OUT.docx
The examples as a Word file (Times New Roman 12, single spaced) that converts cleanly to Google Docs: same content as
simple_book.py, figures as high-resolution pictures, GitHub links as real hyperlinks."""
import sys, os, runpy
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

trace, parses, readings, figdir, out = sys.argv[1:6]
sys.argv = ["simple_book.py", trace, parses, readings, os.devnull, figdir]
G = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "simple_book.py"))
T, P, RD, LINES, GH, LEG = G["T"], G["P"], G["RD"], G["LINES"], G["GH"], G["LEG"]
relation, note, KIND, order = G["relation"], G["note"], G["KIND"], G["order"]

doc = Document()
st = doc.styles["Normal"]
st.font.name = "Times New Roman"; st.font.size = Pt(12)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
st.paragraph_format.line_spacing = 1.0
st.paragraph_format.space_after = Pt(6)
for sec in doc.sections:
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)

def para(text="", bold=False, italic=False, align=None, after=6):
    p = doc.add_paragraph()
    if text:
        r = p.add_run(text); r.bold = bold; r.italic = italic
    if align: p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    return p

def link(p, url, text):
    rid = p.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), rid)
    r = OxmlElement("w:r"); rp = OxmlElement("w:rPr")
    c = OxmlElement("w:color"); c.set(qn("w:val"), "0563C1"); rp.append(c)
    u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rp.append(u)
    r.append(rp); t = OxmlElement("w:t"); t.text = text; t.set(qn("xml:space"), "preserve"); r.append(t); h.append(r)
    p._p.append(h)

def table(head, rows, widths):
    t = doc.add_table(rows=1, cols=len(head)); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.LEFT
    t.autofit = False
    for i, h in enumerate(head):
        c = t.rows[0].cells[i]; c.text = ""; r = c.paragraphs[0].add_run(h); r.bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v)
    for i, w in enumerate(widths):
        t.columns[i].width = Inches(w)
    grid = t._tbl.tblGrid
    for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
        gc.set(qn("w:w"), str(int(widths[i] * 1440)))
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Inches(w)
            for p in row.cells[i].paragraphs:
                p.paragraph_format.space_after = Pt(0)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)

tot = sum(len(T[n]["stages"][-1]["out"]["lines"]) for n in order)
right = sum(1 for n in order for v in RD.get(n, {}).values() if v["both"] == "right")
para("Examples", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=12)
p = para(after=12); p.add_run("Caprice Culkin").add_break(); p.add_run("Legislative Health Factuality, Solomon Center for Health Law and Policy").add_break(); p.add_run("November 2, 2026")
para("These are 24 sentences, 8 from each legislature, from the latest batch (sentences 201 to 300 per legislature). For each sentence I list the units the discourse parser found, how the units relate, and the claims read from each unit. Units are numbered from 0, as in the parser output and the figures.")
para(f"The Check column is the result of two separate AI readings of each claim: right if both readings say right, wrong if both say wrong. Across these 24 sentences, {right} of {tot} claims are right. Across the whole batch of 300 sentences, 649 of 959 are right (68%).")
para("Each example ends with its figure, as in Mann and Thompson (1988): the discourse relations on top and each unit's constituency tree below. The links under each figure open the figure and the exact rows of claim_readings_fresh2.csv on GitHub, at the commit these were made from.")

for k, n in enumerate(order, 1):
    fin = T[n]["stages"][-1]["out"]; row = P[n]; rd = RD.get(n, {})
    hp = para(f"Example {k}: {LEG[n.split('|')[1]]}", bold=True)
    hp.paragraph_format.page_break_before = True
    para(row["text"], italic=True)
    para(f"Sentence ID: {row.get('sentence_id')}")
    para("Units", bold=True, after=3)
    table(["Unit", "Text"], [[u["unit"], u["text"]] for u in fin["units"]], [0.6, 5.9])
    if fin["relations"]:
        para("How the units relate", bold=True, after=3)
        for r in fin["relations"]:
            q = doc.add_paragraph(relation(r), style="List Bullet"); q.paragraph_format.space_after = Pt(0)
        doc.add_paragraph().paragraph_format.space_after = Pt(0)
    para("Claims", bold=True, after=3)
    rows = []
    for i, l in enumerate(fin["lines"], 1):
        res = rd.get(i, {}).get("both", "")
        res = {"disagree": "readers disagree"}.get(res, res)
        nt = " ".join(x for x in (note(l), KIND.get(l.get("kind"), "")) if x)
        rows.append([l["unit"], l["subject"], l["verb"], l["object"], nt, res])
    table(["Unit", "Subject", "Verb", "Object", "Note", "Check"], rows, [0.55, 1.15, 0.95, 1.55, 1.45, 0.85])
    fn = n.replace("|", "_")
    png = os.path.join(figdir, fn + ".png")
    if os.path.exists(png):
        doc.add_picture(png, width=Inches(6.5))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        para(f"Figure {k}: {n}. Discourse relations on top, each unit's constituency tree below.", align=WD_ALIGN_PARAGRAPH.CENTER)
    q = para(after=2); q.add_run("Figure on GitHub: "); link(q, f"{GH}/docs/figures/all/{fn}.svg", f"{fn}.svg")
    ln = LINES.get(n, [])
    if ln:
        q = para(after=2); q.add_run("Claims and readings on GitHub: ")
        link(q, f"{GH}/outputs/edu/claim_readings_fresh2.csv?plain=1#L{min(ln)}-L{max(ln)}", f"claim_readings_fresh2.csv, lines {min(ln)} to {max(ln)}")
doc.save(out)
print("wrote", out, right, tot)
