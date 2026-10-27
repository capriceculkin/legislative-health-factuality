"""edu_figures.py EDU_OUT.json OUT.html [--rows sample|1,sample|6,...]

The "tree inside a tree" figures: for each sentence, the discourse tree drawn over its units (Mann and Thompson style:
a bar over the units each relation joins, the main part marked), the constituency tree of every unit drawn out under
it, and the lines read from each unit. Static SVG in one HTML page, no scripts. Plain python3."""
import sys, json, html, re, argparse

ap = argparse.ArgumentParser()
ap.add_argument("edu"); ap.add_argument("out")
ap.add_argument("--rows", default="sample|1,sample|6,test|A8|fr,sample|2,sample|17,test|D2|en,test|F4|en,heldout|3")
A = ap.parse_args()
D = {r["n"]: r for r in json.load(open(A.edu, encoding="utf-8"))["rows"]}
if A.rows.startswith("first:"):            # the first N sentences of each legislature (for the new sentences)
    k = int(A.rows.split(":")[1]); seen = {}
    WANT = []
    for n in D:
        g = n.split("|")[1] if n.count("|") >= 2 else n
        if seen.get(g, 0) < k:
            WANT.append(n); seen[g] = seen.get(g, 0) + 1
else:
    WANT = [x for x in A.rows.split(",") if x in D]
SOURCE = {D[n]["tree_source"] for n in WANT}
TREE_NOTE = ("Each unit's tree comes from parsing that unit on its own." if SOURCE == {"reparsed"} else
             "Each unit's tree is the sentence's tree cut down to that unit; parsing each unit on its own is the next run.")

esc = html.escape
LEAF_W, LEVEL_H, PAD = 64, 34, 10


def parse(s):
    toks = re.findall(r"\(|\)|[^\s()]+", s)
    pos = 0
    def node():
        nonlocal pos
        pos += 1
        lab = toks[pos]; pos += 1
        kids = []
        while toks[pos] != ")":
            if toks[pos] == "(":
                kids.append(node())
            else:
                kids.append(toks[pos]); pos += 1
        pos += 1
        return (lab, kids)
    return node()


def depth(n):
    return 0 if isinstance(n, str) else 1 + max(depth(k) for k in n[1])


def nleaves(n):
    return 1 if isinstance(n, str) else sum(nleaves(k) for k in n[1])


def tree_svg(t):
    """A constituency tree drawn top down; words along the bottom."""
    if t[0] in ("ROOT", "TOP") and len(t[1]) == 1 and not isinstance(t[1][0], str):
        t = t[1][0]
    n = nleaves(t); dmax = depth(t)
    W = max(n * LEAF_W, 120) + 2 * PAD; H = dmax * LEVEL_H + 40
    parts, counter = [], [0]
    def place(node, d):
        if isinstance(node, str):
            x = PAD + counter[0] * LEAF_W + LEAF_W / 2; counter[0] += 1
            y = dmax * LEVEL_H + 18
            parts.append(f'<text x="{x:.0f}" y="{y}" class="w">{esc(node)}</text>')
            return x, y - 12
        xs = [place(k, d + 1) for k in node[1]]
        x = sum(p[0] for p in xs) / len(xs); y = d * LEVEL_H + 14
        for (cx, cy) in xs:
            parts.append(f'<line x1="{x:.0f}" y1="{y + 4}" x2="{cx:.0f}" y2="{cy - 10:.0f}" class="e"/>')
        parts.append(f'<text x="{x:.0f}" y="{y}" class="l">{esc(node[0])}</text>')
        return x, y
    place(t, 0)
    return W, H, f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="constituency tree">' + "".join(parts) + "</svg>"


def disc_svg(units, rels, widths):
    """Relations drawn as bars over the units they join, smallest spans lowest; the main part's end of a bar carries
    a vertical line, the other side an arrow pointing to it; equal parts both get a line."""
    xs, x = [], 0
    for w in widths:
        xs.append((x, x + w)); x += w
    W = x
    order = sorted(rels, key=lambda r: (r["right"][1] - r["left"][0], r["left"][0]))
    level, H0 = [], 26
    for i, r in enumerate(order):
        a, b = r["left"][0], r["right"][1]
        lv = 0
        for j in range(i):
            a2, b2 = order[j]["left"][0], order[j]["right"][1]
            if a2 >= a and b2 <= b:
                lv = max(lv, level[j] + 1)
        level.append(lv)
    lvmax = max(level, default=0)
    H = (lvmax + 1) * 40 + H0
    parts = []
    def cx(span):
        return (xs[span[0]][0] + xs[span[1]][1]) / 2
    for r, lv in zip(order, level):
        y = H - H0 - lv * 40 - 10
        L, R = r["left"], r["right"]
        xl, xr = cx(L), cx(R)
        parts.append(f'<line x1="{xl:.0f}" y1="{y}" x2="{xr:.0f}" y2="{y}" class="bar"/>')
        for side, xx in (("L", xl), ("R", xr)):
            span = L if side == "L" else R
            is_main = r["main"] is None or r["main"] == span
            parts.append(f'<line x1="{xx:.0f}" y1="{y}" x2="{xx:.0f}" y2="{y + 22}" class="{"nuc" if is_main else "sat"}"/>')
            if not is_main:
                parts.append(f'<circle cx="{xx:.0f}" cy="{y + 22}" r="3" class="dot"/>')
        parts.append(f'<text x="{(xl + xr) / 2:.0f}" y="{y - 6}" class="rel">{esc(r["shared"])}</text>')
    for i, (a, b) in enumerate(xs):
        parts.append(f'<text x="{(a + b) / 2:.0f}" y="{H - 4}" class="u">unit {i}</text>')
    return W, H, f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="discourse tree">' + "".join(parts) + "</svg>"


import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import edu_draw as DRAW                     # noqa: E402   the same tree-inside-a-tree drawing as the notebook


def sentence_block(r):
    rel_rows = "".join(f"<li>{esc(c['from'] + ' to ' + c['to'])}: {esc(c['relation'])} (parser: {esc(c.get('parser_label', ''))}); main part {esc(c['main'])}</li>"
                       for c in r.get("connections", [])) or "<li>one unit, no relations</li>"
    rows = "".join(
        f'<tr><td>{l["unit"]}</td><td>{esc(l["subject"])}</td><td>{esc(l["verb"])}</td><td>{esc(l["object"])}</td>'
        f'<td>{esc(l.get("subject_from") or "its own unit")}{(" &middot; " + esc(l["object_from"])) if l.get("object_from") else ""}'
        f'{(" &middot; that = " + esc(l["refers_to"])) if l.get("refers_to") else ""}{(" &middot; context: " + esc("; ".join(l["context"]))) if l.get("context") else ""}</td></tr>'
        for l in r["lines"])
    return f'''<section class="card" id="{esc(r["n"].replace("|", "-"))}">
<h2>{esc(r["n"])}</h2>
<p class="sent">{esc(r["text"])}</p>
<h3>Units and how the discourse parse connects them</h3>
<ul class="rels">{rel_rows}</ul>
<div class="scroll">{DRAW.figure(r, simple=True)}</div>
<h3>Lines</h3>
<div class="scroll"><table><tr><th>Unit</th><th>Subject</th><th>Verb</th><th>Object</th><th>Where a part came from</th></tr>{rows}</table></div>
</section>'''


def sentence_block_old(r):
    trees = []
    for u in r["units"]:
        svgs = [tree_svg(parse(t)) for t in u["tree"]] or [(160, 40, '<svg viewBox="0 0 160 40" width="160" height="40"><text x="80" y="24" class="w">(no tree)</text></svg>')]
        trees.append((sum(s[0] for s in svgs) + 24, svgs))
    widths = [w for w, _ in trees]
    dw, dh, dsvg = disc_svg(r["units"], r["relations"], widths)
    cols = "".join(
        f'<div class="unit" style="width:{w}px"><div class="utext"><b>unit {u["unit"]}</b> {esc(u["text"])}</div>'
        + "".join(s[2] for s in svgs) + "</div>" for u, (w, svgs) in zip(r["units"], trees))
    rows = "".join(
        f'<tr><td>{l["unit"]}</td><td>{esc(l["subject"])}</td><td>{esc(l["verb"])}</td><td>{esc(l["object"])}</td>'
        f'<td>{esc({"asserted": "stated"}.get(l["kind"], l["kind"] or ""))}{", negated" if l["negated"] else ""}</td>'
        f'<td>{esc(l.get("subject_from") or "")}{(" &middot; " + esc(l["object_from"])) if l.get("object_from") else ""}</td></tr>'
        for l in r["lines"])
    rel_rows = "".join(f"<li>{esc(x['reads'])}</li>" for x in r["relations"]) or "<li>one unit, no relations</li>"
    return f'''<section class="card" id="{esc(r["n"].replace("|", "-"))}">
<h2>{esc(r["n"])}</h2>
<p class="sent">{esc(r["text"])}</p>
<h3>1. Discourse units and how they connect</h3>
<ul class="rels">{rel_rows}</ul>
<div class="scroll"><div class="canvas" style="width:{max(dw, sum(widths))}px">{dsvg}<div class="units">{cols}</div></div></div>
<h3>2. Lines read from each unit's tree</h3>
<div class="scroll"><table><tr><th>Unit</th><th>Subject</th><th>Verb</th><th>Object</th><th>Status</th><th>Where a missing part came from</th></tr>{rows}</table></div>
</section>'''


page = f'''<title>Discourse First Figures</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* Layout: one card per sentence; the discourse bars sit directly above the units, each unit's tree below its text */
:root{{--bg:#f6f7f8;--panel:#ffffff;--ink:#1f2328;--muted:#5b6168;--line:#c9ced4;--soft:#eceef1;--accent:#3d4f63;
  --body:Calibri,Carlito,"Segoe UI",system-ui,sans-serif}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#16181b;--panel:#1e2125;--ink:#e7e9ec;--muted:#a3a9b1;--line:#454b52;--soft:#262a2f;--accent:#9fb3c8;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#16181b;--panel:#1e2125;--ink:#e7e9ec;--muted:#a3a9b1;--line:#454b52;--soft:#262a2f;--accent:#9fb3c8;color-scheme:dark}}
body{{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.5}}
.wrap{{max-width:1200px;margin:0 auto;padding-block:24px 60px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;flex-direction:column;gap:18px}}
h1{{font-size:1.6rem;margin:0}} h2{{font-size:1.15rem;margin:0}} h3{{font-size:.95rem;margin:12px 0 6px;color:var(--muted)}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px 18px;min-width:0}}
.sent{{background:var(--soft);padding:8px 10px;border-radius:4px;margin:8px 0}}
.scroll{{overflow-x:auto}}
.canvas{{display:flex;flex-direction:column}}
.units{{display:flex}}
.unit{{border-left:1px dashed var(--line);padding:4px 6px;box-sizing:border-box}}
.utext{{font-size:.85rem;margin-bottom:4px;max-width:100%}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}} th,td{{border:1px solid var(--line);padding:4px 7px;text-align:left;vertical-align:top}} th{{background:var(--soft)}}
.rels{{margin:0 0 6px;padding-left:20px;font-size:.92rem}}
.key{{font-size:.9rem;color:var(--muted)}}
</style>
<div class="wrap">
<header><h1>Discourse first, then a tree per unit</h1>
<p class="key">Drawn the way Mann and Thompson draw discourse trees: a line spans the units a relation covers; the main part hangs from it on a straight line; the supporting part is joined to it by a curved arrow labelled with the relation; equal parts both hang on straight lines. In place of each unit's number is that unit's own constituency tree, and under it the subject | verb | object lines read from it. {TREE_NOTE}</p></header>
{"".join(sentence_block(D[n]) for n in WANT)}
</div>'''
open(A.out, "w", encoding="utf-8").write(page)
print("wrote", A.out, "with", len(WANT), "sentences")
