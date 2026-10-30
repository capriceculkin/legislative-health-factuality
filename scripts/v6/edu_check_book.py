"""edu_check_book.py OUT_BASE RECORDS.json [MORE.json ...] [--rows id,id,...]

A check book for reading the output by hand: one sentence per page with its tree-inside-a-tree figure (edu_draw,
simple=True), the discourse relations written as "unit 0 and unit 1 to unit 2", every claim the pipeline read from
it with where each part came from, and blank columns to mark each claim right or wrong and to write any claim it
missed. Writes OUT_BASE.html (opens in any browser, figures at full size) and OUT_BASE.pdf (tabloid landscape) when
playwright is installed. By default: the new sentences drawn at random from each legislature (IDs starting "more|").
    python3 scripts/v6/edu_check_book.py docs/discourse_first_check_book outputs/edu/more_reparsed.json"""
import argparse
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edu_draw as DRAW  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("records", nargs="+")
ap.add_argument("--rows", default="", help="sentence IDs to include, in order; default: every 'more|' sentence")
A = ap.parse_args()

recs = {}
for f in A.records:
    for r in json.load(open(f, encoding="utf-8"))["rows"]:
        recs[r["n"]] = r
LEG = {"US": "US House", "ON": "Ontario", "QC": "Quebec"}


def order_key(n):
    p = n.split("|")
    return (["US", "ON", "QC"].index(p[1]) if len(p) > 2 and p[1] in LEG else 9, int(p[2]) if len(p) > 2 and p[2].isdigit() else 0, n)


want = [n for n in A.rows.split(",") if n in recs] if A.rows else sorted((n for n in recs if n.startswith("more|")), key=order_key)
if not want:
    sys.exit("no sentences to put in the check book (check --rows or the records file)")
esc = html.escape


def legislature(r):
    p = r["n"].split("|")
    if len(p) > 2 and p[1] in LEG:
        return LEG[p[1]]
    sid = r.get("sentence_id") or ""
    return LEG.get(sid.split("|")[0], "") if sid else ""


def came_from(l):
    parts = []
    parts.append("subject: " + (l.get("subject_from") or "its own unit"))
    if l.get("object_from"):
        parts.append("object: " + l["object_from"])
    if l.get("refers_to"):
        parts.append("that = " + l["refers_to"])
    if l.get("context"):
        parts.append("context: " + "; ".join(l["context"]))
    return parts


BOX = '<span class="box"></span>'


def page(i, n, r):
    lines = r["lines"]
    # the figure gives up height to the table: every claim and unit listed below it takes room on the same page
    fig_h = max(2.2, 4.3 - 0.30 * max(0, len(lines) - 3) - 0.13 * max(0, len(r["units"]) - 3) - 0.12 * (len(r["text"]) // 160))
    fig = DRAW.figure(r, simple=True).replace("<svg ", f'<svg style="max-height:{fig_h:.2f}in" ', 1)
    rels = "".join(f"<li>{esc(c['from'] + ' to ' + c['to'])}: {esc(c['relation'])}</li>" for c in r.get("connections", [])) \
        or "<li>one unit, no relations</li>"
    units = "".join(f"<li><b>unit {u['unit']}</b> {esc(u['text'])}</li>" for u in r["units"])
    if lines:
        body = "".join(
            f"<tr><td>{k}</td><td>{l['unit']}</td><td>{esc(l['subject'])}</td><td>{esc(l['verb'])}"
            f"{' <i>(to-infinitive)</i>' if l.get('infinitive') else ''}</td><td>{esc(l['object'])}"
            f"{' <i>(negated)</i>' if l.get('negated') else ''}</td>"
            f"<td class='src'>{'<br>'.join(esc(x) for x in came_from(l))}</td>"
            f"<td class='mark'>{BOX} yes &nbsp; {BOX} no</td><td class='note'></td></tr>" for k, l in enumerate(lines, 1))
    else:
        body = "<tr><td colspan='8' class='none'>The pipeline found no claims in this sentence.</td></tr>"
    return f"""<section class="page">
<div class="top"><span>{esc(r['n'])} &middot; {esc(legislature(r))} &middot; {'English' if r['lang'] == 'en' else 'French'}</span><span>{i} of {n}</span></div>
<p class="sent">{esc(r['text'])}</p>
<div class="fig">{fig}</div>
<div class="two"><div><h3>Units</h3><ol class="plain">{units}</ol></div><div><h3>How the discourse parse connects them</h3><ul class="plain">{rels}</ul></div></div>
<h3>Claims</h3>
<table><tr><th style="width:3%">#</th><th style="width:4%">Unit</th><th style="width:17%">Subject</th><th style="width:11%">Verb</th><th style="width:20%">Object</th>
<th style="width:21%">Where each part came from</th><th style="width:9%">Right?</th><th style="width:15%">Note</th></tr>{body}</table>
<h3>Claims the pipeline missed</h3>
<div class="missed"></div><div class="missed"></div>
</section>"""


CSS = """
@page { size: 17in 11in; margin: 0.5in; }
* { box-sizing: border-box; }
body { margin: 0; font-family: Carlito, Calibri, 'Helvetica Neue', Arial, sans-serif; color: #111; font-size: 11pt; background: #fff; }
.page { page-break-after: always; padding: 6px 0; }
.page:last-child { page-break-after: auto; }
.top { display: flex; justify-content: space-between; font-size: 9pt; color: #555; border-bottom: 2px solid #222; padding-bottom: 4px; margin-bottom: 8px; }
.sent { font-size: 13pt; margin: 4px 0 8px; }
.fig { border: 1px solid #ccc; padding: 6px; overflow-x: auto; margin-bottom: 8px; }
.fig svg { display: block; max-width: 100%; max-height: 3.9in; width: auto; height: auto; margin: 0 auto; }
@media screen { .fig svg { max-width: none; max-height: none; } }
.two { display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px; }
h3 { font-size: 11pt; margin: 8px 0 4px; color: #222; }
ol.plain, ul.plain { margin: 0; padding-left: 0; list-style: none; font-size: 10pt; color: #333; }
ol.plain li, ul.plain li { margin: 1px 0; }
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
th { text-align: left; background: #222; color: #fff; padding: 4px 6px; font-weight: 600; }
td { border-bottom: 1px solid #ccc; padding: 3px 6px; vertical-align: top; }
td.src { color: #444; font-size: 9pt; }
td.none { color: #555; font-style: italic; }
.box { display: inline-block; width: 11px; height: 11px; border: 1px solid #333; vertical-align: -1px; }
.missed { border-bottom: 1px solid #999; height: 22px; }
.cover h1 { font-size: 22pt; margin: 0 0 6px; }
.cover p, .cover li { font-size: 12pt; max-width: 1100px; color: #222; }
.cover ul { padding-left: 20px; }
"""

legs = sorted({legislature(recs[n]) for n in want if legislature(recs[n])})
cover = f"""<section class="page cover">
<h1>Check book: claims read discourse first</h1>
<p>{len(want)} sentences{(' from the ' + ', '.join(legs)) if legs else ''}, one per page.
{'They were drawn at random from each legislature (20 each, seed 20261026), and no rule was written while looking at them.' if all(n.startswith('more|') for n in want) else ''}</p>
<p>Each page shows the sentence, its figure (the discourse parse drawn the Mann and Thompson way on top, each unit's own constituency tree
under it), the units, how the discourse parse connects them, and every claim the pipeline read, with where each part of the claim came from.</p>
<ul>
<li><b>Right?</b> Is this a claim the speaker makes, with the right subject, verb and object?</li>
<li><b>Note</b> What is wrong, if anything (subject, verb, object, or where a part came from).</li>
<li><b>Claims the pipeline missed</b> Any claim in the sentence that is not in the table.</li>
</ul>
<p>The tag list for the trees is in Parse_tag_reference.pdf. Made by scripts/v6/edu_check_book.py from the pipeline's saved output.</p>
</section>"""
doc = (f'<!doctype html><html><head><meta charset="utf-8"><title>Check Book</title><style>{CSS}</style></head><body>'
       + cover + "".join(page(i, len(want), recs[n]) for i, n in enumerate(want, 1)) + "</body></html>")
open(A.out + ".html", "w", encoding="utf-8").write(doc)
print(f"wrote {A.out}.html with {len(want)} sentences")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.set_content(doc)
        pg.pdf(path=A.out + ".pdf", width="17in", height="11in", print_background=True,
               margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"})
        b.close()
    print(f"wrote {A.out}.pdf")
except Exception as ex:                  # noqa: BLE001
    print(f"   no PDF ({type(ex).__name__}); open {A.out}.html in a browser and print it to PDF (tabloid, landscape)")
