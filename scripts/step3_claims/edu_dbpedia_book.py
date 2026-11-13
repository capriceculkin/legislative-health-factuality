"""The DBpedia step, every part: method with exact settings, all counts, worked examples, and a workbook with every
candidate, every claim end and every walk for all 190 sentences.
python3 dbook.py EDU_DBPEDIA.json SPOTLIGHT_RAW.json SENSE_CHECK.csv SENSE_ADJUSTED.json WALK_BASELINE.json OUT_PREFIX"""
import sys, json, csv, html, re, math, collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
D = json.load(open(sys.argv[1])); RAW = json.load(open(sys.argv[2]))
SX = {(x["word"], x["page"]): x for x in csv.DictReader(open(sys.argv[3], encoding="utf-8"))}
ADJ = json.load(open(sys.argv[4])); WB = json.load(open(sys.argv[5])); OUT = sys.argv[6]
e = lambda x: html.escape(str(x if x is not None else ""))
rows = D["rows"]

def hops(path):
    """'A <-[p]- B (links 8) -[q]-> C' -> list of (from, relation, direction, to, links of to)"""
    toks = re.split(r"\s+(?=<-\[|-\[)", path)
    start = toks[0].strip(); out = []; cur = start
    for t in toks[1:]:
        m = re.match(r"(<-\[([^\]]+)\]-|-\[([^\]]+)\]->)\s+(\S+)(?:\s+\(links (\d+)\))?", t.strip())
        rel = m.group(2) or m.group(3); back = m.group(2) is not None
        out.append((cur, rel, "←" if back else "→", m.group(4), int(m.group(5)) if m.group(5) else None)); cur = m.group(4)
    return start, out

def arithmetic(w):
    s, hs = hops(w["path"])
    mids = [h[4] for h in hs if h[4] is not None]
    if not mids:
        return "a direct link (no page in between): cost 0, score 1 / (1 + 0) = 1"
    terms = " + ".join(f"ln {k}" for k in mids); vals = " + ".join(f"{math.log(k):.2f}" for k in mids)
    cost = sum(math.log(k) for k in mids)
    return f"cost = {terms} = {vals} = {cost:.2f}; score = 1 / (1 + {cost:.2f}) = {1 / (1 + cost):.4f} (saved: {w['tau']})"

def sense(word, page):
    x = SX.get((word, page))
    if not x:
        return "not in the sense check"
    return f"A: {x['reading_A']} ({x['reason_A']}); B: {x['reading_B']} ({x['reason_B']})"

# ---------------- pick worked examples: 4 per legislature, covering different outcomes
def tags(r):
    t = set()
    for c in r["claims"]:
        if c.get("walk"): t.add("walk")
        for s in ("subject", "object"):
            t.add(c[s]["status"])
            for k in c[s]["concepts"]:
                x = SX.get((k["surface"], k["page"]))
                if x and x["both_readings"] == "wrong": t.add("wrong sense")
                t.add(k["how"].split(",")[0])
    return t
want = ["walk", "wrong sense", "institution of this legislature", "the bill under debate", "senses rejected", "page not in the graph", "common noun", "pronoun"]
picked = []
for leg in ("US House", "Ontario", "Quebec"):
    cands = [r for r in rows if r["legislature"] == leg]
    got = []; covered = set()
    for w_ in want:
        for r in sorted(cands, key=lambda r: -len(tags(r))):
            if r in got or w_ in covered: continue
            if w_ in tags(r):
                got.append(r); covered |= tags(r); break
        if len(got) == 4: break
    for r in sorted(cands, key=lambda r: -len(tags(r))):
        if len(got) >= 4: break
        if r not in got: got.append(r)
    picked += got

def example(k, r):
    raw = RAW.get(r["n"], {})
    h = [f"<section><h2>Example {k}. {e(r['legislature'])} ({e(r['n'])})</h2><p class='sent'>{e(r['text'])}</p>"]
    h.append("<h3>A. What Spotlight returned for the whole sentence</h3><p class='ex'>Every phrase Spotlight spotted, with every candidate page in its order, the overall score, the context score and the support (how many Wikipedia links use that page). Saved in spotlight_edu_raw.json.</p>")
    cands = raw.get("candidates") or []
    if cands:
        h.append("<table class='c'><tr><th>phrase</th><th>at</th><th>candidate pages (score / context / support)</th></tr>")
        for c in sorted(cands, key=lambda c: c.get("offset") or 0):
            ss = "<br>".join(f"{i + 1}. {e(x['page'])} ({x['score']:.2f} / {x['context']:.2f} / {int(x['support'])})" for i, x in enumerate(c["senses"][:8]))
            h.append(f"<tr><td>{e(c['surface'])}</td><td>{e(c.get('offset'))}</td><td class='s2'>{ss}</td></tr>")
        h.append("</table>")
    else:
        h.append("<p class='nc'>Spotlight spotted nothing in this sentence.</p>")
    h.append("<h3>B. Each claim, end by end</h3>")
    for c in r["claims"]:
        h.append(f"<p class='claim'>Claim {c['claim']} (unit {c['unit']}, {e(c['kind'])}{', negated' if c['negated'] else ''}): {e(c['subject']['phrase'])} | {e(c['verb'])} | {e(c['object']['phrase'])}</p>")
        h.append("<table class='c'><tr><th>end</th><th>phrase</th><th>result</th><th>pages found, and how</th><th>in the 2022 graph</th><th>sense check</th></tr>")
        for s in ("subject", "object"):
            x = c[s]
            pages = "<br>".join(f"{e(k['surface'])} → {e(k['page'])}<br><span class='s'>{e(k['how'])}</span>" for k in x["concepts"]) or "none"
            ing = "<br>".join("yes" if k["in_graph"] else "no" for k in x["concepts"]) or ""
            sc = "<br>".join(e(sense(k["surface"], k["page"])) for k in x["concepts"] if k["page"] != "(the bill)") or ""
            res = e(x["status"]) + (f"<br><span class='s'>{e(x['reason'])}</span>" if x["reason"] else "")
            h.append(f"<tr><td>{s}</td><td>{e(x['phrase'])}</td><td>{res}</td><td>{pages}</td><td>{ing}</td><td class='s'>{sc}</td></tr>")
        h.append("</table>")
        w = c.get("walk")
        if w and not w["path"]:
            h.append(f"<p class='ex'><b>Walk</b>: both ends have pages ({e(w['subject'])}, {e(w['object'])}), but no path links them in the graph: score 0.</p>")
        elif w:
            st, hs = hops(w["path"])
            hh = "".join(f"<tr><td>{e(a)}</td><td>{d} {e(rel)}</td><td>{e(b)}</td><td>{e(n) if n else 'end'}</td><td>{f'{math.log(n):.2f}' if n else ''}</td></tr>" for a, rel, d, b, n in hs)
            h.append(f"<p class='ex'><b>Walk</b> between {e(w['subject'])} and {e(w['object'])}: {w['links']} links.</p><table class='c'><tr><th>from</th><th>link</th><th>to</th><th>links of the page passed through</th><th>ln</th></tr>{hh}</table>")
            h.append(f"<p class='ar'>{e(arithmetic(w))}</p>")
            if w.get("tau_no_direct") != w["tau"]:
                h.append(f"<p class='s'>Without the direct link: {e(w['path_no_direct'])}, score {w['tau_no_direct']}</p>")
        h.append(f"<p class='s'>Verdict: {e(c['verdict'])}</p>")
    h.append("</section>")
    return "".join(h)

S = D["summary"]
adj = ADJ
def pct(a, b): return f"{a}/{b} ({100 * a / b:.0f}%)"
leg_rows = "".join(f"<tr><td>{g}</td><td>{adj['strict'][g + '|claims']}</td><td>{pct(adj['strict'][g + '|both'], adj['strict'][g + '|claims'])}</td><td>{pct(adj['lenient'][g + '|both'], adj['lenient'][g + '|claims'])}</td><td>{pct(adj['strict'][g + '|walk'], adj['strict'][g + '|claims'])}</td></tr>"
                   for g in ("US House", "Ontario", "Quebec", "English", "French", "asserted", "all"))
sc = collections.Counter(x["both_readings"] for x in SX.values())
real = WB["real"]
real_rows = "".join(f"<tr><td>{e(x['n'])}</td><td>{e(x['claim'])}</td><td>{e(', '.join(x['s']))}</td><td>{e(', '.join(x['o']))}</td><td>{x['tau']}</td></tr>" for x in real)
front = f"""<section class='front'><h1>The DBpedia step, every part</h1>
<p class='meta'>Legislative Health Factuality. Caprice Culkin, for David Chartash and Joanie Bouchard. November 2026. Working document. Run on the current (round 7) claims for the 190 sentences with saved Spotlight answers: 100 from the first sample, 30 held out, 60 from the new draw.</p>
<h3>1. What goes in</h3><p>Each claim from the discourse-first pipeline: a subject phrase, a verb and an object phrase, with the unit, whether it is asserted, reported or embedded, and whether it is negated. 531 claims in all.</p>
<h3>2. Spotlight</h3><p>DBpedia Spotlight, run on the whole sentence (English model on port 2222, French model on 2223, through the tunnel), using its <i>candidates</i> call at confidence 0.3, so every candidate page for every phrase comes back, not only the first. The answers are saved (spotlight_edu_raw.json), so the rest of the step reruns without the tunnel.</p>
<h3>3. Finding a page for each end of a claim (concepts_v3.py, version 1)</h3><ol>
<li><b>The bill.</b> “this bill”, “the legislation”, “H.R. 3962”, “ce projet de loi”, “la loi”: marked as the bill under debate, not looked up.</li>
<li><b>Institutions of the legislature.</b> A fixed list per legislature: “the House” → United_States_House_of_Representatives; “this government” → Government_of_Ontario; “le gouvernement” → Government_of_Quebec; Medicare, Medicaid, CMS, FDA, CDC, OHIP, RAMQ and others.</li>
<li><b>Exact page titles.</b> The longest capitalised run that is exactly a page title (“Cancer Care Ontario”).</li>
<li><b>Spotlight phrases inside the end.</b> Roman numerals are dropped. The words must include a noun or a name (parts of speech from the saved spaCy parse for the first 100 sentences, from the unit trees for the other 90): this drops “His” → Wilhelm_His_Sr. and “You” → Israel. French candidate pages are mapped to English pages through French Wikipedia’s language links, then fr.dbpedia.org.</li>
<li><b>Choosing the sense.</b> Spotlight’s first candidate is kept unless the page says it is in another country (its country, location or state links, or a country in its title), or it is a film, album, journal or sports sense when the sentence has no such words. Then the next of up to 8 candidates is kept if it passes the same checks and a neighbouring page shares a word with the sentence; otherwise none.</li>
<li><b>Common nouns.</b> If nothing was found, a fixed list of common nouns: doctor → Physician, patients → Patient, medication → Medication, taxpayers → Taxpayer: 116 English and French words pointing to 39 pages.</li>
<li><b>In the graph?</b> A page counts only if it is in the 2022 graph below.</li></ol>
<h3>4. The graph</h3><p>DBpedia mappingbased-objects, release 2022.12.01 (English): the links from Wikipedia infoboxes. 7,220,726 pages and 20,708,852 links, after leaving out 340,629 “see also” (rdfs:seeAlso) and “not to be confused with” (owl:differentFrom) links, which say nothing about the world.</p>
<h3>5. The walk score (after Ciampaglia et al. 2015)</h3><p>Links are followed in both directions. Stepping onto a page costs the natural log of its number of links, and the end page costs nothing, so cost = the sum of ln(links) over the pages passed through, and score τ = 1 / (1 + cost). A direct link scores 1; no path scores 0. The cheapest path is found with Dijkstra’s algorithm over the whole graph; for a claim with several pages at an end, the best pair counts. The score without the direct link is also kept. For a negated claim the claim score is 1 − τ.</p>
<h3>6. The sense check</h3><p>Every word and page pair the step produced (284 pairs) was judged twice, separately, by two AI readers: is this the meaning of the word in this sentence? Both right: {sc['right']}; both wrong: {sc['wrong']}; the readers disagree: {sc['disagree']}; unsure: {sc.get('unsure', 0)}. Strict counting keeps a page only when both say right; lenient keeps it when either does. Walks are recomputed between kept pages only.</p>
<h3>7. The baseline for walks</h3><p>The {WB['real_pairs']} claims whose two ends are both judged right (strict) are compared with {WB['shuffled_pairs']} shuffled pairs: the subject pages of one claim with the object pages of another (random seed 20261102).</p>
<h3>Results</h3>
<table class='c'><tr><th></th><th>claims</th><th>both ends right, strict</th><th>both ends right, lenient</th><th>walk between right ends (strict)</th></tr>{leg_rows}</table>
<p>Before the sense check, as linked: 68/531 claims (13%) have a page at both ends and 53 (10%) have a walk.</p>
<table class='c'><tr><th></th><th>real claim pairs</th><th>shuffled pairs</th></tr>
<tr><td>a walk exists</td><td>{100 * WB['real_share_with_walk']:.0f}%</td><td>{100 * WB['shuffled_share_with_walk']:.0f}%</td></tr>
<tr><td>median walk score</td><td>{WB['real_median_tau']:.3f}</td><td>{WB['shuffled_median_tau']:.3f}</td></tr>
<tr><td>chance a real pair scores above a shuffled one (0.5 = no difference)</td><td colspan=2>{WB['auc_real_over_shuffled']:.2f}</td></tr></table>
<p>So in this graph a walk does not separate real claims from random pairs. Checked one way only, on 41 pairs.</p>
<h3>The full summary printed by the run</h3><pre>{e(chr(10).join(l for l in (S if isinstance(S, str) else json.dumps(S, indent=1)).splitlines() if "/tmp/" not in l and "Oct 15 comparison" not in l))}</pre>
<h3>The 41 claims used in the baseline</h3><table class='c'><tr><th>sentence</th><th>claim</th><th>subject pages</th><th>object pages</th><th>τ</th></tr>{real_rows}</table>
<p class='s'>Every claim end, every Spotlight candidate and every walk for all 190 sentences is in the workbook dbpedia_every_part.xlsx.</p></section>"""
CSS = """body{font-family:Calibri,Carlito,Arial,sans-serif;color:#1B2A3A;font-size:11pt;margin:0}section{page-break-before:always}section.front{page-break-before:auto}
h1{color:#14324A;font-size:22pt;margin:0 0 4pt}h2{color:#14324A;font-size:16pt;border-bottom:2px solid #C2672B;padding-bottom:3pt;margin:0 0 6pt}h3{color:#C2672B;font-size:12pt;margin:12pt 0 3pt}
.sent{font-family:Cambria,Caladea,Georgia,serif;font-size:13pt}.meta,.s{color:#5B7C99;font-size:9.5pt}.s2{font-size:9pt}.ex{color:#3A4654;font-size:10pt;margin:3pt 0}
.claim{font-weight:bold;color:#14324A;margin:10pt 0 2pt}.ar{font-family:'Courier New',monospace;font-size:9pt;color:#9A4F12}.nc{color:#5B7C99;font-style:italic}
table.c{border-collapse:collapse;width:100%;margin:3pt 0;font-size:9.5pt}table.c th{background:#14324A;color:#fff;text-align:left;padding:3pt 5pt}table.c td{border:1px solid #D5DDE4;padding:3pt 5pt;vertical-align:top}
pre{font-size:8pt;white-space:pre-wrap;background:#F4F6F8;padding:6pt}li{margin-bottom:3pt}"""
open(OUT + ".html", "w", encoding="utf-8").write(f"<!doctype html><html><head><meta charset='utf-8'><title>DBpedia every part</title><style>{CSS}</style></head><body>{front}{''.join(example(k, r) for k, r in enumerate(picked, 1))}</body></html>")

# ---------------- workbook
wb = Workbook(); H = Font(bold=True, color="FFFFFF"); F = PatternFill("solid", fgColor="14324A")
def sheet(name, head, data, widths):
    ws = wb.create_sheet(name); ws.append(head)
    for c in ws[1]: c.font, c.fill = H, F
    for d in data: ws.append(d)
    for i, w in enumerate(widths): ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
ws = wb.active; ws.title = "Start here"
for line in ["The DBpedia step, every part, for the 190 sentences with saved Spotlight answers (round 7 claims).",
             "Candidates: every phrase Spotlight spotted in each sentence and every candidate page, with its scores.",
             "Claim ends: every subject and object of every claim, what was found, how, whether it is in the graph, and the sense check.",
             "Walks: every walk, link by link, with the score worked out.",
             "Sense check: the two readings of every word and page pair.", "Baseline: the 41 real pairs used to test whether walks mean anything.",
             "Method and settings: see dbpedia_every_part.pdf, part 1."]:
    ws.append([line])
ws.column_dimensions["A"].width = 120
cand = []
for r in rows:
    for c in (RAW.get(r["n"], {}).get("candidates") or []):
        for i, x in enumerate(c["senses"]):
            cand.append([r["n"], r["legislature"], r["lang"], c["surface"], c.get("offset"), i + 1, x["page"], round(x["score"], 4), round(x["context"], 4), x["support"], x.get("types", "")])
sheet("Candidates", ["sentence", "legislature", "language", "phrase", "at character", "rank", "candidate page", "score", "context score", "support", "types"], cand, [14, 11, 8, 22, 10, 6, 40, 8, 10, 10, 30])
ends = []
for r in rows:
    for c in r["claims"]:
        for s in ("subject", "object"):
            x = c[s]
            base = [r["n"], r["legislature"], r["text"], c["claim"], c["unit"], c["kind"], c["negated"], f"{c['subject']['phrase']} | {c['verb']} | {c['object']['phrase']}", s, x["phrase"], x["status"], x["reason"]]
            if not x["concepts"]:
                ends.append(base + ["", "", "", "", "", "", ""])
            for k in x["concepts"]:
                sx = SX.get((k["surface"], k["page"]), {})
                ends.append(base + [k["surface"], k["page"], k["how"], k["in_graph"], sx.get("reading_A", ""), sx.get("reading_B", ""), c["verdict"]])
sheet("Claim ends", ["sentence", "legislature", "text", "claim", "unit", "kind", "negated", "claim text", "end", "phrase", "result", "reason", "words", "page", "how found", "in graph", "sense A", "sense B", "claim verdict"], ends,
      [14, 11, 40, 6, 5, 9, 8, 40, 8, 25, 18, 30, 15, 28, 30, 8, 8, 8, 25])
walks = []
for r in rows:
    for c in r["claims"]:
        w = c.get("walk")
        if not w: continue
        if not w["path"]:
            walks.append([r["n"], c["claim"], f"{c['subject']['phrase']} | {c['verb']} | {c['object']['phrase']}", w["subject"], w["object"], "", "(no path in the graph)", "score 0", w["tau"], w["tau_no_direct"], "", w["claim_score"]]); continue
        walks.append([r["n"], c["claim"], f"{c['subject']['phrase']} | {c['verb']} | {c['object']['phrase']}", w["subject"], w["object"], w["links"], w["path"], arithmetic(w), w["tau"], w["tau_no_direct"], w["path_no_direct"], w["claim_score"]])
sheet("Walks", ["sentence", "claim", "claim text", "subject page", "object page", "links", "path", "score worked out", "τ", "τ without the direct link", "path without the direct link", "claim score"], walks,
      [14, 6, 40, 22, 22, 6, 60, 50, 7, 9, 50, 8])
sheet("Sense check", list(next(iter(SX.values())).keys()), [list(x.values()) for x in SX.values()], [5, 15, 25, 6, 10, 22, 6, 20, 30, 8, 30, 8, 30, 10])
sheet("Baseline", ["sentence", "claim", "subject pages", "object pages", "τ"], [[x["n"], x["claim"], ", ".join(x["s"]), ", ".join(x["o"]), x["tau"]] for x in real], [14, 50, 30, 30, 8])
wb.save(OUT + ".xlsx")
print("examples", [r["n"] for r in picked], "candidates", len(cand), "ends", len(ends), "walks", len(walks))
