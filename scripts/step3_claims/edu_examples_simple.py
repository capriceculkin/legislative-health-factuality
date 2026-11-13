"""simple_book.py TRACE.json PARSES.json READINGS.csv OUT.html
A short examples document: for each sentence, its units, how they relate, and the claims, with the two readings."""
import sys, json, csv, html, re, collections
T = json.load(open(sys.argv[1]))["res"]
P = {r["n"]: r for r in json.load(open(sys.argv[2]))["rows"]}
RD = collections.defaultdict(dict)
for r in csv.DictReader(open(sys.argv[3], encoding="utf-8")):
    RD[r["sentence"]][int(r["claim"])] = r
OUT, FIG = sys.argv[4], sys.argv[5]
import base64
GH = "https://github.com/capriceculkin/legislative-health-factuality/blob/efac9b91e991d8ace3d2bdc5d24cefcf6c508b20"
LINES = collections.defaultdict(list)
for i, line in enumerate(open(sys.argv[3], encoding="utf-8"), 1):
    if i > 1: LINES[line.split(",", 1)[0]].append(i)
e = lambda x: html.escape(str(x if x is not None else ""))
LEG = {"US": "US House", "ON": "Ontario", "QC": "Quebec"}
MEANING = {"elaboration": "adds detail to", "background": "gives background for", "attribution": "says who is speaking in",
           "purpose": "gives the purpose of", "explanation": "gives the reason for", "cause-result": "is the cause or result of",
           "condition": "is a condition for", "evaluation": "comments on", "time-sequence": "comes before or after",
           "manner-means": "says how", "comparison": "is compared with", "contrast": "contrasts with",
           "joint": "is listed with", "same-unit": "continues"}

def span(sp):
    a, b = sp[0], sp[1]
    return f"unit {a}" if a == b else f"units {a} to {b}" if b - a > 1 else f"units {a} and {b}"

def relation(r):
    lab, L, R, M = r["shared"], r["left"], r["right"], r.get("main")
    if not M:
        if lab == "same-unit":
            return f"{span(L).capitalize()} and {span(R)} are one clause, split by an insertion (same-unit)."
        return f"{span(L).capitalize()} and {span(R)} have equal weight ({lab})."
    main, other = (L, R) if list(M) == list(L) else (R, L)
    return f"{span(other).capitalize()} {MEANING.get(lab, lab)} {span(main)} ({lab}). The main part is {span(main)}."

def renum(t):
    return re.sub(r"\bunit (\d+)", lambda m: f"unit {int(m.group(1))}", t or "")

def note(l):
    sf = l.get("subject_from") or ""
    if not sf:
        return ""
    m = re.match(r"unit (\d+) \(([^)]*)\)", sf)
    if m:
        return f"Subject taken from unit {int(m.group(1))} through the {m.group(2).split(':')[0]} relation."
    m = re.match(r"'(\w+)' stands for the last noun phrase of unit (\d+)", sf)
    if m:
        return f"“{m.group(1)}” stands for the last noun phrase of unit {int(m.group(2))}."
    if sf.startswith("an infinitive or gerund") or "who does it is not in the words" in sf:
        return "No subject in the words."
    return renum(sf.split(":")[0]).capitalize() + "."

KIND = {"asserted": "", "reported": "Reported speech, not the speaker’s own claim.", "embedded": "", "question": "A question."}
order = sorted(T, key=lambda n: (["US", "ON", "QC"].index(n.split("|")[1]), int(n.split("|")[2])))
parts = []
for k, n in enumerate(order, 1):
    fin = T[n]["stages"][-1]["out"]; row = P[n]; rd = RD.get(n, {})
    h = [f"<section><h2>Example {k}: {LEG[n.split('|')[1]]}</h2><p class='sent'>{e(row['text'])}</p><p>Sentence ID: {e(row.get('sentence_id'))}</p>"]
    h.append("<h3>Units</h3><table class='c'><tr><th>Unit</th><th>Text</th></tr>" +
             "".join(f"<tr><td>{u['unit']}</td><td>{e(u['text'])}</td></tr>" for u in fin["units"]) + "</table>")
    if fin["relations"]:
        h.append("<h3>How the units relate</h3><ul>" + "".join(f"<li>{e(relation(r))}</li>" for r in fin["relations"]) + "</ul>")
    h.append("<h3>Claims</h3><table class='c'><tr><th>Unit</th><th>Subject</th><th>Verb</th><th>Object</th><th>Note</th><th>Check</th></tr>")
    for i, l in enumerate(fin["lines"], 1):
        r = rd.get(i, {})
        res = r.get("both", "")
        res = {"right": "right", "wrong": "wrong", "disagree": "readers disagree"}.get(res, res)
        nt = " ".join(x for x in (note(l), KIND.get(l.get("kind"), "")) if x)
        h.append(f"<tr><td>{l['unit']}</td><td>{e(l['subject'])}</td><td>{e(l['verb'])}</td><td>{e(l['object'])}</td><td>{e(nt)}</td><td>{e(res)}</td></tr>")
    h.append("</table>")
    fn = n.replace("|", "_")
    try:
        b64 = base64.b64encode(open(f"{FIG}/{fn}.png", "rb").read()).decode()
        h.append(f"<img src='data:image/png;base64,{b64}'><p class='cap'>Figure {k}: {e(n)}. Discourse relations on top, each unit's constituency tree below.</p>")
    except OSError:
        pass
    ln = LINES.get(n, [])
    links = [f"<a href='{GH}/docs/figures/all/{fn}.svg'>Figure on GitHub</a>"]
    if ln:
        links.append(f"<a href='{GH}/outputs/edu/claim_readings_fresh2.csv?plain=1#L{min(ln)}-L{max(ln)}'>Claims and readings on GitHub (lines {min(ln)} to {max(ln)})</a>")
    h.append("<p>" + " · ".join(links) + "</p></section>")
    parts.append("".join(h))
tot = sum(len(T[n]["stages"][-1]["out"]["lines"]) for n in order)
right = sum(1 for n in order for v in RD.get(n, {}).values() if v["both"] == "right")
front = f"""<section class='front'><h1>Examples</h1>
<p>Caprice Culkin<br>Legislative Health Factuality, Solomon Center for Health Law and Policy<br>November 2, 2026</p>
<p>These are 24 sentences, 8 from each legislature, from the latest batch (sentences 201 to 300 per legislature). For each sentence I list the units the discourse parser found, how the units relate, and the claims read from each unit. Units are numbered from 0, as in the parser output and the figures.</p>
<p>The Check column is the result of two separate AI readings of each claim: right if both readings say right, wrong if both say wrong. Across these 24 sentences, {right} of {tot} claims are right. Across the whole batch of 300 sentences, 649 of 959 are right (68%).</p>
<p>Each example ends with its figure, as in Mann and Thompson (1988): the discourse relations on top and each unit's constituency tree below.  The links under each figure open the figure and the exact rows of claim_readings_fresh2.csv on GitHub, at the commit these were made from.</p></section>"""
CSS = """body{font-family:'Times New Roman',Tinos,Times,serif;color:#000;font-size:12pt;line-height:1.0;margin:0}
section{margin:0;page-break-before:always}section.front{page-break-before:auto}h1{font-size:12pt;font-weight:bold;text-align:center;margin:0 0 12pt}
h2{font-size:12pt;font-weight:bold;margin:0 0 6pt}h3{font-size:12pt;font-weight:bold;margin:8pt 0 4pt}p{margin:0 0 8pt}
ul{margin:0 0 6pt;padding-left:18pt}li{margin:0}.sent{font-style:italic}
table.c{border-collapse:collapse;width:100%;margin:0 0 6pt;font-size:12pt;line-height:1.0}
a{color:#000}img{max-width:100%;max-height:5.2in;display:block;margin:8pt auto 0}.cap{text-align:center;margin:4pt 0 6pt}
table.c th{border:1px solid #000;text-align:left;padding:2pt 4pt}table.c td{border:1px solid #000;padding:2pt 4pt;vertical-align:top}"""
open(OUT, "w", encoding="utf-8").write(f"<!doctype html><html><head><meta charset='utf-8'><title>Examples</title><style>{CSS}</style></head><body>{front}{''.join(parts)}</body></html>")
print("wrote", OUT, right, tot)
