"""
crec_ocr.py
Second machine reading of bound Congressional Record page images with Tesseract,
used to correct the GovInfo text layer word by word, conservatively.

For each page: render the image, cut it into the same columns the geometric reader
found, read each column with Tesseract, line the Tesseract words up against the
GovInfo reading, and for each place where they differ:

  - letter/digit confusion in a number ("ll" vs "11", "l" vs "1", "IO" vs "10"):
    take the digits
  - GovInfo word(s) not a real word, Tesseract word is a real word, spelling close
    (similarity >= 0.6): take Tesseract, keeping GovInfo's capitalisation
  - anything else: keep GovInfo; if the GovInfo word is not a real word, list it for
    review with Tesseract's suggestion and the surrounding words

"Real word" = in the system word list (/usr/share/dict/words on a Mac) or used at
least twice elsewhere in that day's text.
"""
import os, re, shutil, subprocess, tempfile
from collections import Counter
from difflib import SequenceMatcher

TOK = re.compile(r"[A-Za-z0-9]+")
_DICT = None


def dictionary():
    global _DICT
    if _DICT is None:
        _DICT = set()
        for p in ("/usr/share/dict/words", "/usr/dict/words", os.environ.get("WORDLIST", "")):
            if p and os.path.exists(p):
                with open(p, encoding="utf-8", errors="ignore") as f:
                    _DICT |= {w.strip().lower() for w in f if w.strip()}
    return _DICT


def tesseract_available():
    return shutil.which("tesseract") is not None


def ocr_image(path, psm="4"):
    r = subprocess.run(["tesseract", path, "-", "--psm", psm, "-l", "eng"], capture_output=True, text=True)
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def column_crops(pil_img, page_w, page_h, gutters, top_frac=0.065, bottom_frac=0.965, pad=4):
    sx, sy = pil_img.width / page_w, pil_img.height / page_h
    bounds = [pad] + list(gutters) + [page_w - pad]
    return [pil_img.crop((int(bounds[k] * sx), int(top_frac * page_h * sy),
                          int(bounds[k + 1] * sx), int(bottom_frac * page_h * sy)))
            for k in range(len(bounds) - 1)]


def _join_splits(tokens, vocab):
    """Tesseract keeps line-break splits ('associa', 'tion'); join a pair when the
    joined word is known and at least one piece is not."""
    out, i = [], 0
    while i < len(tokens):
        if i + 1 < len(tokens):
            a, b = tokens[i], tokens[i + 1]
            j = (a + b).lower()
            if j in vocab and (a.lower() not in vocab or b.lower() not in vocab):
                out.append(a + b)
                i += 2
                continue
        out.append(tokens[i])
        i += 1
    return out


def _case_like(src, new):
    letters = [c for c in src if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) >= 0.6:
        return new.upper()
    if src[:1].isupper():
        return new[:1].upper() + new[1:].lower()
    return new.lower()


NUMISH = re.compile(r"^[lIO0-9]+$")


def correct_lines(lines, tess_lines, day_counts, context_page=""):
    """Returns (new_lines, fixes, reviews). lines keep their structure (and any
    heading marker); only word spans are replaced."""
    D = dictionary()

    def known(w):
        """For the GovInfo side: roman numerals count as known, so '(iii)' is never 'fixed'."""
        lw = w.lower()
        return lw in D or w.isdigit() or day_counts.get(lw, 0) >= 2 or bool(re.fullmatch(r"[ivxlcdm]+", lw))

    def real(w):
        """For a Tesseract replacement: a real word of 3+ letters (dictionary or used 2+ times
        that day). Roman-numeral-looking strings do not qualify ('XC' is not a fix for 'lXC')."""
        lw = w.lower()
        return len(lw) >= 3 and w.isalpha() and (lw in D or day_counts.get(lw, 0) >= 2)

    def decide(g_words, t_words):
        gj, tj = "".join(g_words), "".join(t_words)
        if gj.lower() == tj.lower():
            return None
        if len(g_words) == 1 and len(t_words) == 1 and NUMISH.match(gj) and tj.isdigit() \
                and len(gj) == len(tj) and not gj.isdigit():
            return tj                                  # "ll" -> "11", "l" -> "1", "IO" -> "10"
        if real(tj) and not all(known(w) for w in g_words) and \
                SequenceMatcher(None, gj.lower(), tj.lower()).ratio() >= 0.6:
            return _case_like(gj, tj)                  # also joins Tesseract splits: "AU THORIZED"
        return None

    # GovInfo tokens with their (line, start, end)
    g_tok, g_pos = [], []
    for li, ln in enumerate(lines):
        for m in TOK.finditer(ln):
            g_tok.append(m.group(0))
            g_pos.append((li, m.start(), m.end()))
    vocab = D | {w for w, c in day_counts.items() if c >= 2}
    t_tok = _join_splits(TOK.findall(" ".join(tess_lines)), vocab)
    sm = SequenceMatcher(None, [x.lower() for x in g_tok], [x.lower() for x in t_tok], autojunk=False)
    edits, fixes, reviews = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace" or (i2 - i1) > 3 or (j2 - j1) > 3:
            continue
        if "".join(g_tok[i1:i2]).lower() == "".join(t_tok[j1:j2]).lower():
            continue                                   # same letters split differently ("Journa l" / "Jour nal")
        # equal counts and each pair alike: judge word by word; otherwise the block as a whole
        if (i2 - i1) == (j2 - j1) and (i2 - i1) > 1 and all(
                SequenceMatcher(None, g_tok[i1 + k].lower(), t_tok[j1 + k].lower()).ratio() >= 0.5
                or (NUMISH.match(g_tok[i1 + k]) and t_tok[j1 + k].isdigit())
                for k in range(i2 - i1)):
            pieces = [((k, k + 1), [g_tok[k]], [t_tok[j1 + k - i1]]) for k in range(i1, i2)]
        else:
            pieces = [((i1, i2), g_tok[i1:i2], t_tok[j1:j2])]
        for (a1, a2), g_words, t_words in pieces:
            if "".join(g_words).lower() == "".join(t_words).lower():
                continue                               # same letters, only spacing differs
            ctx = " ".join(g_tok[max(0, a1 - 6):min(len(g_tok), a2 + 6)])
            new = decide(g_words, t_words)
            same_line = len({g_pos[k][0] for k in range(a1, a2)}) == 1
            if new is not None and same_line:
                li, s0, _ = g_pos[a1]
                edits.append((li, s0, g_pos[a2 - 1][2], new))
                fixes.append({"page": context_page, "govinfo": " ".join(g_words), "tesseract": " ".join(t_words),
                              "used": new, "context": ctx})
            elif not all(known(w) for w in g_words):
                reviews.append({"page": context_page, "govinfo": " ".join(g_words), "tesseract": " ".join(t_words),
                                "context": ctx})
    new_lines = list(lines)
    for li, s, e, new in sorted(edits, key=lambda x: (x[0], -x[1])):
        ln = new_lines[li]
        new_lines[li] = ln[:s] + new + ln[e:]
    return new_lines, fixes, reviews


def image_gutters(pil_img, page_w, top_frac=0.065, bottom_frac=0.965):
    """Column gutters found from the page image itself (for pages with no text layer):
    the lightest vertical strip near 1/3 and near 2/3 of the width. Returns page units."""
    from PIL import Image
    body = pil_img.crop((0, int(top_frac * pil_img.height), pil_img.width, int(bottom_frac * pil_img.height)))
    ink = body.point(lambda v: 255 if v < 140 else 0).resize((body.width, 1), Image.BOX)
    col = list(ink.getdata())
    out = []
    for lo, hi in ((0.25, 0.42), (0.58, 0.75)):
        a, b = int(lo * len(col)), int(hi * len(col))
        x = min(range(a, b), key=lambda i: col[i])
        out.append(x * page_w / pil_img.width)
    return out


def ocr_header(pdf_path, index, resolution=300):
    """Tesseract reading of the running head (top strip) of one page."""
    import pdfplumber
    fd, p = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            img = pdf.pages[index].to_image(resolution=resolution).original.convert("L")
        img.crop((0, 0, img.width, int(0.075 * img.height))).save(p)
        return " ".join(ocr_image(p, psm="6"))
    finally:
        os.remove(p)


def ocr_pages(pdf_path, page_infos, resolution=300, workers=None):
    """page_infos: list of dicts with 'index', 'gutters'. Returns {index: [tesseract lines]}.
    Renders each page once, runs Tesseract on its columns in parallel."""
    import pdfplumber
    from concurrent.futures import ThreadPoolExecutor
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    tmp = tempfile.mkdtemp(prefix="crec_ocr_")
    jobs = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for info in page_infos:
                page = pdf.pages[info["index"]]
                img = page.to_image(resolution=resolution).original.convert("L")
                gut = info["gutters"]
                if gut is None:                       # no text layer: find the columns in the image
                    gut = image_gutters(img, float(page.width))
                for k, crop in enumerate(column_crops(img, float(page.width), float(page.height), gut)):
                    p = os.path.join(tmp, f"p{info['index']:04d}_c{k}.png")
                    crop.save(p)
                    jobs.append((info["index"], k, p))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(lambda j: (j[0], j[1], ocr_image(j[2])), jobs))
        out = {}
        for idx, k, lines in sorted(results):
            out.setdefault(idx, []).extend(lines)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
