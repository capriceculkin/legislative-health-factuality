"""edu_draw.py   The "tree inside a tree" figure (Oct 22): the discourse tree drawn the way Mann and Thompson draw RST
analyses, with each unit's constituency tree in place of the unit's number at the bottom.

  Mann-Thompson conventions used here:
  - a horizontal line spans the units a relation covers
  - the main part (nucleus) hangs from it on a straight vertical line
  - the supporting part (satellite) is joined to the main part by a curved arrow pointing at the main part,
    labelled with the relation
  - two equal parts (multinuclear, e.g. contrast, joint) both hang on straight lines, the label on the span line

figure(record) -> SVG text, for one sentence record written by edu_pipeline.py. Plain python3."""
import html

esc = html.escape
LEAF_W, LEVEL_H, CHAR_W, FONT = 58, 30, 6.6, 12
INK, MUTED, LINE, ACCENT = "#1f2328", "#5b6168", "#9aa1a9", "#2f4a63"


def _leaves(n):
    return 1 if isinstance(n, str) else sum(_leaves(k) for k in n[1])


def _depth(n):
    return 0 if isinstance(n, str) else 1 + max(_depth(k) for k in n[1])


def _strip_root(t):
    while not isinstance(t, str) and t[0] in ("ROOT", "TOP") and len(t[1]) == 1 and not isinstance(t[1][0], str):
        t = t[1][0]
    return t


PUNCT = {"PONCT", ",", ".", ":", "``", "''", "-LRB-", "-RRB-", "HYPH"}


def _no_punct(n):
    "The tree without punctuation leaves, for the simple figure."
    if isinstance(n, str):
        return n
    kids = [_no_punct(k) for k in n[1] if isinstance(k, str) or k[0] not in PUNCT]
    kids = [k for k in kids if k is not None and (isinstance(k, str) or k[1])]
    return [n[0], kids] if kids else None


def _leaf_w(w):
    return max(34, len(w) * CHAR_W + 12)


def _words(n):
    return [n] if isinstance(n, str) else [w for k in n[1] for w in _words(k)]


def tree_size(t):
    t = _strip_root(t)
    return sum(_leaf_w(w) for w in _words(t)), _depth(t) * LEVEL_H + 16


def tree_parts(t, x0, y0):
    """SVG pieces for one constituency tree with its top-left corner at (x0, y0)."""
    t = _strip_root(t)
    dmax = _depth(t)
    parts, k = [], [x0]

    def place(n, d):
        if isinstance(n, str):
            x = k[0] + _leaf_w(n) / 2; k[0] += _leaf_w(n)
            y = y0 + dmax * LEVEL_H + 4
            parts.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{FONT}" fill="{INK}" text-anchor="middle">{esc(n)}</text>')
            return x, y - 12
        kids = [place(c, d + 1) for c in n[1]]
        x = sum(p[0] for p in kids) / len(kids); y = y0 + d * LEVEL_H + 10
        for cx, cy in kids:
            parts.append(f'<line x1="{x:.0f}" y1="{y + 4:.0f}" x2="{cx:.0f}" y2="{cy - 8:.0f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="10.5" font-weight="600" fill="{MUTED}" text-anchor="middle">{esc(n[0])}</text>')
        return x, y
    place(t, 0)
    return parts


def _wrap(text, width):
    per = max(8, int(width / CHAR_W))
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > per and cur:
            out.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return out + ([cur] if cur else [])


def figure(rec, show_lines=True, simple=False):
    """simple=True is the figure as described in the meeting and drawn by Mann and Thompson: the discourse relations
    on top with span numbers (0-1), and under each unit only its constituency tree (no punctuation, no repeated text,
    no extracted lines, no boxes)."""
    units = rec["units"]
    trees = [[n for n in (u.get("tree_nodes") or [])] for u in units]
    if simple:
        show_lines = False
        trees = [[t for t in (_no_punct(x) for x in ts) if t is not None] for ts in trees]
    # column width per unit: its trees side by side, or its text
    cols = []
    for u, ts in zip(units, trees):
        tw = sum(tree_size(t)[0] for t in ts) + 12 * max(len(ts) - 1, 0)
        cols.append(max(tw, 150))
    gap = 26
    xs, x = [], 20
    for w in cols:
        xs.append((x, x + w)); x += w + gap
    W = x - gap + 20
    rels = rec["relations"]

    # levels: a relation sits one level above the relations its two sides are made of
    def key(sp):
        return (sp[0], sp[1])
    by_span = {}
    for r in sorted(rels, key=lambda r: r["right"][1] - r["left"][0]):
        lv = 1
        for side in (r["left"], r["right"]):
            if key(side) in by_span:
                lv = max(lv, by_span[key(side)]["level"] + 1)
        by_span[(r["left"][0], r["right"][1])] = {"rel": r, "level": lv}
    top = max([v["level"] for v in by_span.values()], default=0)
    STEP = 74
    head_h = top * STEP + 26
    text_lines = [[] if simple else _wrap(f"{u['text']}", w) for u, w in zip(units, cols)]
    text_h = max(len(t) for t in text_lines) * 15 + 22 if units else 0
    tree_h = max([max([tree_size(t)[1] for t in ts], default=30) for ts in trees], default=30)
    line_rows = [[l for l in rec["lines"] if l["unit"] == u["unit"]] for u in units] if show_lines else [[] for _ in units]

    def line_text(l):
        return f'{l["subject"]} | {l["verb"]} | {l["object"]}' + (f'  (context: {"; ".join(c.split(" (")[0] for c in l["context"])})' if l.get("context") else "")
    wrapped = [[w for l in ls for w in _wrap(line_text(l), cw * 0.93)] for ls, cw in zip(line_rows, cols)]
    lines_h = (max(len(x) for x in wrapped) * 15 + 26) if show_lines and any(line_rows) else 0
    H = head_h + text_h + tree_h + lines_h + 30
    parts = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>',
             f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             f'<path d="M0,0 L10,5 L0,10 z" fill="{ACCENT}"/></marker></defs>']

    def cx(sp):
        return (xs[sp[0]][0] + xs[sp[1]][1]) / 2

    def ytop(sp):
        "Where a line from above meets this span: its own relation line, or the top of the unit."
        if sp[0] == sp[1]:
            return head_h
        v = by_span.get(key(sp))
        return head_h - v["level"] * STEP + 18 if v else head_h

    for (a, b), v in sorted(by_span.items(), key=lambda kv: kv[1]["level"]):
        r, lv = v["rel"], v["level"]
        y = head_h - lv * STEP + 18
        L, R = r["left"], r["right"]
        x1, x2 = xs[a][0] + 6, xs[b][1] - 6
        parts.append(f'<line x1="{x1:.0f}" y1="{y}" x2="{x2:.0f}" y2="{y}" stroke="{INK}" stroke-width="1.6"/>')
        names = [f"unit {i}" for i in range(a, b + 1)]
        label = f"{a}-{b}" if simple else ", ".join(names[:-1]) + " and " + names[-1]
        parts.append(f'<text x="{x1 + 2:.0f}" y="{y - 5}" font-size="{12 if simple else 10}" fill="{MUTED}">{esc(label)}</text>')
        if r["main"] is None:                     # equal parts: both hang straight down, label on the line
            for side in (L, R):
                parts.append(f'<line x1="{cx(side):.0f}" y1="{y}" x2="{cx(side):.0f}" y2="{ytop(side):.0f}" stroke="{INK}" stroke-width="1.6"/>')
            parts.append(f'<text x="{(cx(L) + cx(R)) / 2:.0f}" y="{y + 16}" font-size="12" font-weight="700" fill="{ACCENT}" text-anchor="middle">{esc(r["shared"])}</text>')
        else:
            nuc = r["main"]; sat = R if nuc == L else L
            parts.append(f'<line x1="{cx(nuc):.0f}" y1="{y}" x2="{cx(nuc):.0f}" y2="{ytop(nuc):.0f}" stroke="{INK}" stroke-width="1.6"/>')
            sx, nx = cx(sat), cx(nuc)
            sy, ny = ytop(sat), ytop(nuc)
            ny2 = ny if nuc[0] == nuc[1] else ny
            peak = y + 26                          # the arc runs just under the span line, as in Mann and Thompson
            end_y = max(ny2 - 4, y + 34)
            ex_ = nx + (6 if sx > nx else -6)
            parts.append(f'<path d="M{sx:.0f},{sy - 2:.0f} C{sx:.0f},{peak:.0f} {ex_:.0f},{peak:.0f} {ex_:.0f},{end_y:.0f}" '
                         f'fill="none" stroke="{ACCENT}" stroke-width="1.4" marker-end="url(#ah)"/>')
            mx = (sx + ex_) / 2                                     # the middle of the arc (t = 0.5 of the curve)
            my = (sy - 2 + 6 * peak + end_y) / 8
            lw = 7.2 * len(r["shared"]) + 8
            parts.append(f'<rect x="{mx - lw / 2:.0f}" y="{my - 13:.0f}" width="{lw:.0f}" height="16" fill="#ffffff"/>')
            parts.append(f'<text x="{mx:.0f}" y="{my:.0f}" font-size="12" font-weight="700" fill="{ACCENT}" text-anchor="middle">{esc(r["shared"])}</text>')

    for i, (u, (a, b)) in enumerate(zip(units, xs)):
        y = head_h + 4
        if not simple:
            parts.append(f'<rect x="{a}" y="{y}" width="{b - a}" height="{text_h + tree_h + lines_h}" fill="none" stroke="{LINE}" stroke-dasharray="3 3"/>')
        parts.append(f'<text x="{(a + b) / 2 if simple else a + 6:.0f}" y="{y + 15}" font-size="{13 if simple else 12}" font-weight="700" fill="{INK}"'
                     f'{" text-anchor=" + chr(34) + "middle" + chr(34) if simple else ""}>unit {u["unit"]}</text>')
        for j, tl in enumerate(text_lines[i]):
            parts.append(f'<text x="{a + 6}" y="{y + 31 + 15 * j}" font-size="12" fill="{INK}">{esc(tl)}</text>')
        tx = a + 6
        for t in trees[i]:
            parts += tree_parts(t, tx, y + text_h + 6)
            tx += tree_size(t)[0] + 12
        if show_lines:
            ly = y + text_h + tree_h + 18
            for j, s in enumerate(wrapped[i]):
                parts.append(f'<text x="{a + 6}" y="{ly + 15 * j}" font-size="11.5" fill="{ACCENT}">{esc(s)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" '
            f'font-family="Calibri, Carlito, Arial, sans-serif">' + "".join(parts) + "</svg>")
