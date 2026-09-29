"""
crec_columns.py
Reads bound Congressional Record PDF pages (scanned images with a machine-read
text layer) in true reading order, two independent ways, and checks they agree.

  geometric   pdfplumber word boxes: find the running head by its CONGRESSIONAL
              RECORD line, find column gutters from rows (so a full-width title
              cannot hide a gutter), read column by column inside each horizontal
              band, and put full-width lines (titles, footers) between bands.
  stored      pypdf: the order the OCR software stored the text in. It also keeps
              soft hyphens (U+00AD) at line-end word breaks, which gives exact
              de-hyphenation.

compare_page() aligns the two word sequences. A page is accepted only when they
agree (same words, same order) above a threshold.
"""
import re
from collections import Counter
from difflib import SequenceMatcher

SOFT = "­"
HEAD_RE = re.compile(r"CONGRESSIONAL\s+RECORD", re.I)
MARK = "⁣"          # invisible marker put in front of real debate headings
HEAD_START_BAD = re.compile(r"^[\"'`“‘(\[\d]|^(?:SEC\.|SECTION|TITLE|Mr|Mrs|Ms|Miss|The|H\.\s?R\.|S\.)")
ONE_WORD_HEADS = {"PRAYER", "ADJOURNMENT", "RECESS", "QUORUM"}


TIME_STAMP = re.compile(r"^\S?\s?\d{4}$")     # the Record's time marker, OCR'd as "D 1210", "0 1210"


def is_debate_heading(text, size, speech_size, continuation=False):
    """A Congressional Record debate heading: capitals, printed at speech size (bill
    text and quoted letters are set smaller), not opening like bill text or a
    speaker line, no bracket (names like '[Mr. LEACH].' wrap onto caps lines)."""
    t = text.strip()
    letters = [c for c in t if c.isalpha()]
    if len(t) < 4 or len(t) > 100 or len(letters) < 4 or "CONGRESSIONAL RECORD" in t.upper():
        return False
    if sum(c.isupper() for c in letters) / len(letters) < 0.9 or HEAD_START_BAD.match(t) or "]" in t:
        return False
    if speech_size and size < 0.95 * speech_size:
        return False
    if re.search(r"\.\s?[-\u2014]", t):      # run-in bill-text head: "FORFEITED.-", "STATUS.-In"
        return False
    return continuation or len(t.split()) >= 2 or t.strip(" .") in ONE_WORD_HEADS
FOOT_RE = re.compile(r"This symbol represents|Matter set in this typeface|AUTHENTICATED|GOVERNMENT|INFORMATION\s*$|^GPO$",
                     re.I)


# ----------------------------------------------------------------------------- geometric
def _rows(words, ytol=3.0):
    rows, cur, top = [], [], None
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if cur and abs(w["top"] - top) > ytol:
            rows.append(cur)
            cur = []
        if not cur:
            top = w["top"]
        cur.append(w)
    if cur:
        rows.append(cur)
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def _gutters(rows, left, right, max_cols=4, min_width=3.0, row_frac=0.04):
    """x positions covered by at most row_frac of rows = gutters."""
    scale = 2
    n = int((right - left) * scale) + 2
    cov = [0] * n
    for r in rows:
        seen = set()
        for w in r:
            for i in range(max(0, int((w["x0"] - left) * scale)), min(n, int((w["x1"] - left) * scale) + 1)):
                seen.add(i)
        for i in seen:
            cov[i] += 1
    tol = max(1, int(row_frac * len(rows)))
    gaps, start = [], None
    for i in range(n + 1):
        empty = i < n and cov[i] <= tol
        if empty and start is None:
            start = i
        elif not empty and start is not None:
            width = (i - start) / scale
            center = left + (start + i) / 2 / scale
            if width >= min_width and left + 0.15 * (right - left) < center < right - 0.15 * (right - left):
                gaps.append((width, center))
            start = None
    return sorted(c for _, c in sorted(gaps, reverse=True)[:max_cols - 1])


def _spans(row, cuts):
    """A row is full-width only if a word actually crosses a gutter (by 2pt+ on
    each side). Justified column headings run right up to the gutter but never
    cross it, so they stay in their column."""
    return any(w["x0"] < c - 2 and w["x1"] > c + 2 for c in cuts for w in row)


def geometric_page(page):
    """Returns dict(header, lines, dropped) with lines in reading order."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["size"])
    if not words:
        return {"header": "", "lines": [], "dropped": []}
    rows = _rows(words)
    H = float(page.height)
    # running head: the first row (within the top 12%) containing CONGRESSIONAL RECORD
    head_i = next((i for i, r in enumerate(rows[:8])
                   if r[0]["top"] < 0.12 * H and HEAD_RE.search(" ".join(w["text"] for w in r))), None)
    header = " ".join(w["text"] for w in rows[head_i]) if head_i is not None else ""
    body = rows[head_i + 1:] if head_i is not None else rows
    dropped = []
    keep = []
    for r in body:
        t = " ".join(w["text"] for w in r)
        if FOOT_RE.search(t) and r[0]["top"] > 0.85 * H:
            dropped.append(t)
        else:
            keep.append(r)
    ws = [w for r in keep for w in r]
    if not ws:
        return {"header": header, "lines": [], "dropped": dropped}
    left, right = min(w["x0"] for w in ws), max(w["x1"] for w in ws)
    cuts = _gutters(keep, left, right)
    sz = Counter(round(w["size"], 1) for w in ws)
    speech = sz.most_common(1)[0][0] if sz else 0

    heights = sorted(r[0]["bottom"] - r[0]["top"] for r in keep)
    line_h = heights[len(heights) // 2] if heights else 8.0
    state = {"prev": None}

    def emit(r, gap_ok):
        """A heading must look like one AND either have blank space above it or
        continue a heading on the line before (headings wrap over 2-3 lines)."""
        t = " ".join(w["text"] for w in r)
        size = sorted(w["size"] for w in r)[len(r) // 2]
        prev = state["prev"]
        cont = prev is not None and prev.startswith(MARK)
        head = is_debate_heading(t, size, speech, continuation=cont) and (gap_ok or cont)
        line = (MARK + t) if head else t
        out.append(line)
        state["prev"] = line
    # bands separated by full-width rows
    out, band = [], []

    def flush(band_rows):
        bounds = [left - 1] + cuts + [right + 1]
        for k in range(len(bounds) - 1):
            col = [w for r in band_rows for w in r if bounds[k] <= (w["x0"] + w["x1"]) / 2 < bounds[k + 1]]
            prev_bottom = None
            after_stamp = False
            for r in _rows(col):
                top = min(w["top"] for w in r)
                if prev_bottom is None:
                    # top of a column: no line above to measure; fine unless the last
                    # line of the previous column broke mid-word or was bill-text capitals
                    p = state["prev"] or ""
                    letters = [c for c in p if c.isalpha()]
                    caps_prev = bool(letters) and not p.startswith(MARK) and \
                        sum(c.isupper() for c in letters) / len(letters) >= 0.9
                    gap_ok = not p.rstrip().endswith("-") and not caps_prev
                else:
                    gap_ok = after_stamp or (top - prev_bottom) >= 0.8 * line_h
                t = " ".join(w["text"] for w in r)
                if TIME_STAMP.match(t):
                    out.append(t)
                    after_stamp = True
                    prev_bottom = max(w["bottom"] for w in r)
                    continue
                emit(r, gap_ok)
                after_stamp = False
                prev_bottom = max(w["bottom"] for w in r)

    for r in keep:
        if cuts and _spans(r, cuts):
            flush(band)
            band = []
            emit(r, True)
        else:
            band.append(r)
    flush(band)
    return {"header": header, "lines": out, "dropped": dropped, "gutters": [round(c) for c in cuts],
            "speech_size": speech}


# ----------------------------------------------------------------------------- stored order (pypdf)
def stored_page(pypdf_page):
    t = pypdf_page.extract_text() or ""
    t = t.replace(SOFT + "\n", "").replace(SOFT + " \n", "").replace(SOFT, "")
    lines = [ln.strip() for ln in t.splitlines()]
    header = ""
    if lines and HEAD_RE.search(" ".join(lines[:2])):
        # pypdf puts the running head first; drop the line(s) holding it
        k = 1 if HEAD_RE.search(lines[0]) else 2
        header, lines = " ".join(lines[:k]), lines[k:]
    lines = [ln for ln in lines if ln and not FOOT_RE.search(ln)]
    return {"header": header, "lines": lines}


# ----------------------------------------------------------------------------- compare
def _tokens(lines):
    return re.findall(r"[A-Za-z0-9]+", " ".join(lines).lower())


def _letters(lines):
    return re.sub(r"[^a-z0-9]", "", " ".join(lines).lower())


def compare_page(geo_lines, stored_lines):
    """Letter-level alignment of the two readings (spaces, hyphens and punctuation
    removed, so word splitting cannot affect it). order_agreement = share of the
    stored letters matched, in order, by the geometric reading."""
    a, b = _letters(geo_lines), _letters(stored_lines)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    matched = sum(bl.size for bl in sm.get_matching_blocks())
    return {"geo_letters": len(a), "stored_letters": len(b),
            "order_agreement": matched / max(1, len(b)), "geo_matched": matched / max(1, len(a)),
            "opcodes": [op for op in sm.get_opcodes() if op[0] != "equal" and max(op[2] - op[1], op[4] - op[3]) > 25],
            "a": a, "b": b}


def read_page(plumber_page, pypdf_page):
    """Final reading: geometric order (correct for headings), letter runs and
    line-end breaks repaired from the stored text, then compared with it."""
    g = geometric_page(plumber_page)
    s = stored_page(pypdf_page)
    toks = _tokens(s["lines"])
    lines = join_hyphen_breaks(collapse_letter_runs(g["lines"], set(toks)), toks)
    cmp = compare_page(lines, s["lines"])
    return {"header": g["header"] or s["header"], "lines": lines, "stored_lines": s["lines"],
            "dropped": g["dropped"], "gutters": g.get("gutters", []), "compare": cmp}


def collapse_letter_runs(lines, vocab):
    """Letter-spaced small capitals come out as single letters ("F A C T O R S").
    Rejoin a run of 3+ single letters into words found in this page's own stored
    text (longest match first). Runs that cannot be matched are joined as one word."""
    out = []
    for ln in lines:
        toks = ln.split(" ")
        res, i = [], 0
        while i < len(toks):
            j = i
            while j < len(toks) and re.fullmatch(r"[A-Za-z][.,;:)]?", toks[j]):
                j += 1
            if j - i >= 3:
                letters = "".join(t[0] for t in toks[i:j])
                trail = toks[j - 1][1:] if len(toks[j - 1]) > 1 else ""
                k, words = 0, []
                while k < len(letters):
                    m = next((e for e in range(len(letters), k, -1) if letters[k:e].lower() in vocab and e - k > 1), None)
                    if m is None:
                        words = [letters]
                        break
                    words.append(letters[k:m])
                    k = m
                res.append(" ".join(words) + trail)
                i = j
            else:
                res.append(toks[i])
                i += 1
        out.append(" ".join(res))
    return out


def join_hyphen_breaks(lines, stored_text_tokens=None):
    """Geometric lines lose the soft hyphen. Rejoin a line-final fragment with the
    next line's first word when the joined word occurs in the stored (pypdf) text,
    which kept the exact breaks. This uses the page's own evidence, not a dictionary."""
    toks = list(stored_text_tokens or [])
    vocab = set(toks)
    pairs = set(zip(toks, toks[1:]))
    out = []
    for ln in lines:
        if out and out[-1] and not out[-1].startswith(MARK) and not ln.startswith(MARK):
            m1 = re.search(r"([A-Za-z]+)-?$", out[-1])
            m2 = re.match(r"([A-Za-z]+)(.*)$", ln)
            if m1 and m2:
                a, b = m1.group(1), m2.group(1)
                if (a + b).lower() in vocab and (a.lower(), b.lower()) not in pairs:
                    out[-1] = out[-1][:m1.start()] + a + b + m2.group(2)
                    continue
        out.append(ln)
    return out
