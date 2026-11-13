"""dsheet.py EDU_DBPEDIA.json SPOTLIGHT_RAW.json SENSE_CHECK.csv WALK_BASELINE.json OUT.xlsx
The DBpedia step in two tabs: one row per claim (both ends, pages, how found, sense readings, walk), and every Spotlight candidate."""
import sys, json, csv, math, re
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
D = json.load(open(sys.argv[1])); RAW = json.load(open(sys.argv[2]))
SX = {(x["word"], x["page"]): x for x in csv.DictReader(open(sys.argv[3], encoding="utf-8"))}
WB = json.load(open(sys.argv[4])); OUT = sys.argv[5]
base_ns = {(x["n"], x["claim"]) for x in WB["real"]}
TNR = "Times New Roman"
GH = "https://github.com/capriceculkin/legislative-health-factuality/blob/efac9b91e991d8ace3d2bdc5d24cefcf6c508b20"
# line of each claim in the committed edu_dbpedia.json (same file as sys.argv[1])
CL, cur = {}, None
for i, line in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    m = re.match(r'\s*"n": "([^"]+)",', line)
    if m and line.startswith('   "n"'): cur = m.group(1); CL[(cur, 0)] = i
    m = re.match(r'\s*"claim": (\d+),', line)
    if m and cur: CL.setdefault((cur, int(m.group(1))), i)
def ends(x):
    if not x["concepts"]:
        return "", "", "", ""
    pages = "; ".join(f"{k['surface']} → {k['page']}" for k in x["concepts"])
    how = "; ".join(k["how"] + ("" if k["in_graph"] or k["page"] == "(the bill)" else " (not in the graph)") for k in x["concepts"])
    sa = "; ".join(SX.get((k["surface"], k["page"]), {}).get("reading_A", "") for k in x["concepts"] if k["page"] != "(the bill)")
    sb = "; ".join(SX.get((k["surface"], k["page"]), {}).get("reading_B", "") for k in x["concepts"] if k["page"] != "(the bill)")
    return pages, how, sa, sb
def worked(w):
    if not w: return "", "", ""
    if not w["path"]: return "no path", "", 0.0
    ks = [int(k) for k in re.findall(r"\(links (\d+)\)", w["path"])]
    cost = sum(math.log(k) for k in ks)
    ar = "direct link: 1 / (1 + 0) = 1" if not ks else f"1 / (1 + {' + '.join(f'ln {k}' for k in ks)}) = 1 / (1 + {cost:.2f}) = {1 / (1 + cost):.4f}"
    return w["path"].replace("_", " "), ar, w["tau"]
wb = Workbook(); ws = wb.active; ws.title = "Claims"
head = ["Sentence ID", "Legislature", "Sentence", "Subject", "Verb", "Object",
        "Subject page", "Object page", "Why the subject has no page", "Why the object has no page",
        "Subject page right sense?", "Object page right sense?", "Both ends have a page", "Linked in DBpedia through", "Figure", "Claim in the DBpedia output"]
ws.append(head)
LINKS = []
def pages(x):
    return "; ".join(k["page"].replace("_", " ") for k in x["concepts"] if k["page"] != "(the bill)") or ("(the bill)" if x["concepts"] else "")
def why(x):
    return "" if x["status"] == "in DBpedia" else x["status"]
def sense_of(x):
    out = []
    for k in x["concepts"]:
        if k["page"] == "(the bill)": continue
        v = SX.get((k["surface"], k["page"]), {}).get("both_readings", "")
        out.append({"right": "yes", "wrong": "no", "disagree": "readers disagree", "unsure": "unsure"}.get(v, v))
    return "; ".join(out)
def through(w):
    if not w or not w["path"]: return ""
    parts = re.split(r"\s+(?:<-\[[^\]]+\]-|-\[[^\]]+\]->)\s+", w["path"])
    nodes = [re.sub(r"\s+\(links \d+\)$", "", p) for p in parts]
    return " → ".join(n.replace("_", " ") for n in nodes)
for r in D["rows"]:
    for c in r["claims"]:
        both = "yes" if "both ends" in c["verdict"] else "no"
        ws.append([r["n"], r["legislature"], r["text"], c["subject"]["phrase"], c["verb"], c["object"]["phrase"],
                   pages(c["subject"]), pages(c["object"]), why(c["subject"]), why(c["object"]),
                   sense_of(c["subject"]), sense_of(c["object"]), both, through(c.get("walk")), "Open figure", "Open claim"])
        LINKS.append((ws.max_row, f"{GH}/docs/figures/all/{r['n'].replace('|', '_')}.svg", f"{GH}/outputs/dbpedia/edu_dbpedia.json?plain=1#L{CL.get((r['n'], c['claim']), CL[(r['n'], 0)])}"))
widths = [16, 11, 50, 24, 14, 28, 26, 26, 24, 24, 12, 12, 10, 50, 10, 14]
ws2 = wb.create_sheet("Spotlight candidates")
ws2.append(["Sentence ID", "Legislature", "Language", "Phrase", "Character", "Rank", "Candidate page", "Score", "Context score", "Support"])
for r in D["rows"]:
    for c in sorted(RAW.get(r["n"], {}).get("candidates") or [], key=lambda c: c.get("offset") or 0):
        for i, x in enumerate(c["senses"]):
            ws2.append([r["n"], r["legislature"], r["lang"], c["surface"], c.get("offset"), i + 1, x["page"], round(x["score"], 4), round(x["context"], 4), int(x["support"])])
thin = Side(style="thin", color="999999")
for w_, wd in ((ws, widths), (ws2, [16, 11, 9, 24, 10, 6, 40, 8, 12, 10])):
    for i, v in enumerate(wd): w_.column_dimensions[w_.cell(1, i + 1).column_letter].width = v
    for row in w_.iter_rows():
        for cell in row:
            cell.font = Font(name=TNR, size=12, bold=cell.row == 1)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if cell.row == 1: cell.border = Border(bottom=thin)
    w_.freeze_panes = "A2"; w_.auto_filter.ref = w_.dimensions
for row_i, fu, cu in LINKS:
    for col, u in ((15, fu), (16, cu)):
        c_ = ws.cell(row_i, col); c_.hyperlink = u; c_.font = Font(name=TNR, size=12, color="0563C1", underline="single")
wb.save(OUT)
print(ws.max_row - 1, "claims;", ws2.max_row - 1, "candidates")
