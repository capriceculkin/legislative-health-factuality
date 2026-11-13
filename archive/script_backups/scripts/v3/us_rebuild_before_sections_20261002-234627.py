#!/usr/bin/env python3
"""
us_rebuild.py

Rebuilds US bill segments from the Congressional Record.

Why the old approach failed (measured by audit_pipeline.py, check U1):
  1. Files were whole days or whole sections (prayer, Journal, Private Calendar,
     Daily Digest), not one bill's debate, so the US denominator was never bill
     specific and the prayer produced predications.
  2. 1994+ files came from the bound edition (the 2006 file is Vol. 152, Pt. 18)
     instead of the daily edition David pointed to (Vol. 152, No. 135).
  3. PDF text was read straight across the page, gluing the first and middle
     columns together line by line ("funds that will be donated to $20 mil- The
     Clerk read as follows").
  4. Files were named by the roll-call date. When the House sits past midnight the
     vote is stamped with the next calendar day, but the debate is printed in the
     Record of the legislative day (the "2006-12-09" file is really Dec 8, 2006).

New approach:
  plan     one row per (bill, vote date) from health_bills_final_matched.csv and the
           voice-vote file
  segment  for each bill, loads every House unit for the vote date and the days
           before it (legislative-day lookback):
             1994+   daily edition granules from GovInfo (clean text, one granule
                     per topic, header "Congressional Record Volume N, Number N")
             pre-1994 bound edition. Old text is reused only if it shows no column
                     interleaving; otherwise the PDF is re-read column by column
                     using the whitespace gutters between columns, and line-end
                     hyphens are repaired with a dictionary check.
           Anchors are units that name the bill (H.R. N etc.), excluding procedural
           units and rule debates. Units under the same heading as an anchor join
           through the heading hash, which catches continuations.
  verify   two checks per file (names the bill; printed date equals the date used)
           plus interleaving and boilerplate rates, and the running table

Needs: export GOVINFO_API_KEY=... (free key from https://api.data.gov/signup/)
"""
import csv
import datetime as dt
import glob
import html as htmlmod
import io
import os
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import (rp, load_json, save_json, parse_us_bill, us_bill_mention_re, first_long_date, github_url)

try:
    import requests
except ImportError:
    requests = None
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

US = rp("data", "us")
CSV_MATCHED = os.path.join(US, "health_bills_final_matched.csv")
VOICE = os.path.join(US, "voice_vote_speeches_status.json")
OLD_DIR = os.path.join(US, "congressional_record_speeches")
OUT = os.path.join(US, "v3")
CACHE = os.path.join(OUT, "cache")
SEG_DIR = os.path.join(OUT, "cr_segments_v3")
PLAN = os.path.join(OUT, "plan.json")
INDEX = os.path.join(OUT, "segments_index.json")
FLOOR = os.path.join(OUT, "floor_days.json")                   # House debate days per bill (Congress.gov)
FLOOR_TODO = os.path.join(OUT, "floor_days_bound_todo.txt")   # pre-1994 floor days not yet read from PDF
FLOOR_AFTER_VOTE = os.environ.get("US_FLOOR_AFTER_VOTE", "0") == "1"
TABLE = os.path.join(OUT, "us_running_table.csv")
API = "https://api.govinfo.gov"
KEY = os.environ.get("GOVINFO_API_KEY", "")
DAILY_FROM = os.environ.get("US_DAILY_FROM", "1994-01-01")
LOOKBACK_DAILY = int(os.environ.get("US_LOOKBACK_DAILY", "3"))
LOOKBACK_BOUND = int(os.environ.get("US_LOOKBACK_BOUND", "1"))
CLEAN_RATE = float(os.environ.get("US_CLEAN_INTERLEAVE_RATE", "0.002"))
SLEEP = float(os.environ.get("GOVINFO_SLEEP", "0.4"))
UA = {"User-Agent": "Mozilla/5.0 (research; Yale School of Public Health legislative factuality study)"}
# Bound days re-read by reextract_bound.py mark real debate headings with this
# invisible character (capitals at speech size with blank space above). For those
# days sections split ONLY at marked headings, so capitalised bill-text headings
# ("(1) FACTORS FOR ...", "SEC. 2 ...") no longer cut a bill's debate into pieces.
HEAD_MARK = "\u2063"

PROC_TITLES = {
    "PRAYER", "PLEDGE OF ALLEGIANCE", "THE JOURNAL", "MESSAGE FROM THE SENATE", "MESSAGE FROM THE PRESIDENT",
    "GENERAL LEAVE", "ADJOURNMENT", "EXECUTIVE COMMUNICATIONS ETC", "PUBLIC BILLS AND RESOLUTIONS",
    "ADDITIONAL SPONSORS", "REPORTS OF COMMITTEES ON PUBLIC BILLS AND RESOLUTIONS", "LEAVE OF ABSENCE",
    "ENROLLED BILLS SIGNED", "SENATE ENROLLED BILLS SIGNED", "BILLS PRESENTED TO THE PRESIDENT",
    "SPECIAL ORDERS GRANTED", "CONSTITUTIONAL AUTHORITY STATEMENT", "ANNOUNCEMENT BY THE SPEAKER",
    "ANNOUNCEMENT BY THE SPEAKER PRO TEMPORE", "COMMUNICATION FROM THE CLERK OF THE HOUSE", "DAILY DIGEST",
    "HOUSE OF REPRESENTATIVES", "APPOINTMENT OF CONFEREES", "MEMORIALS", "PETITIONS ETC",
    "PRIVATE BILLS AND RESOLUTIONS", "CHANGE OF REFERENCE", "REPORTS OF COMMITTEES ON PRIVATE BILLS AND RESOLUTIONS",
    "LEGISLATIVE PROGRAM", "ORDER OF BUSINESS", "PERSONAL EXPLANATION", "EXTENSIONS OF REMARKS",
    "SENATE BILLS REFERRED", "SENATE CONCURRENT RESOLUTION REFERRED", "CORRECTION TO THE CONGRESSIONAL RECORD",
}
# Record items that are notices, lists or printed text, not debate (found in the
# section-title audit of every US bill-day, outputs/audit/us_sections_diag.txt)
PROC_TITLES |= {
    "CONGRESSIONAL EARMARKS LIMITED TAX BENEFITS OR LIMITED TARIFF BENEFITS", "BUDGETARY EFFECTS OF PAYGO LEGISLATION",
    "AMENDMENTS", "TIME LIMITATION OF REFERRED BILL", "FURTHER MESSAGE FROM THE SENATE", "SENATE ENROLLED BILL SIGNED",
    "ENROLLED BILL SIGNED", "EXTENSION OF REMARKS", "PUBLICATION OF BUDGETARY MATERIAL",
    "DELETIONS OF SPONSORS FROM PUBLIC BILLS AND RESOLUTIONS", "ADDITIONAL SPONSORS TO PUBLIC BILLS AND RESOLUTIONS",
    "REVISIONS TO ALLOCATION FOR HOUSE COMMITTEES", "REPORT OF COMMITTEES ON PUBLIC BILLS AND RESOLUTIONS",
    "WAIVERS OF 3 DAY LAYOVER REQUIREMENT FOR COMMITTEE REPORTS ON LEGISLATION", "SENATE",
    "BILLS PRESENTED TO THE PRESIDENT", "SENATE BILL REFERRED", "EXECUTIVE COMMUNICATIONS",
}
PROC_PREFIXES = ("TEXT OF HOUSE AMENDMENT", "TEXT OF SENATE AMENDMENT", "NOT VOTING", "ANNOUNCEMENT OF INTENTION TO OFFER",
                 "WAIVING REQUIREMENT OF CLAUSE", "REPORT ON RESOLUTION PROVIDING", "AMENDMENTS SUBMITTED",
                 "BUDGETARY EFFECTS OF PAYGO", "CONGRESSIONAL EARMARKS")
# Topic titles shared by many unrelated speeches: never used to pull in extra sections
# by title alone (a section with such a title is kept only if it names the bill itself)
GENERIC_TITLES = {"HEALTH CARE REFORM", "OBAMACARE", "HEALTH CARE", "SENATE", "CONFERENCE REPORT ON H R",
                  "CONFERENCE REPORT ON S", "IN THE COMMITTEE OF THE WHOLE", "HOUSE OF REPRESENTATIVES", "HEALTH",
                  "MEDICARE", "MEDICAID", "AFFORDABLE CARE ACT", "HEALTH CARE COSTS", "HEALTH INSURANCE",
                  "PRESCRIPTION DRUGS", "SPECIAL ORDERS", "MORNING HOUR DEBATE", "RECESS", "AFTER RECESS"}
RULE_PREFIXES = ("PROVIDING FOR CONSIDERATION OF", "PROVIDING FOR THE CONSIDERATION OF", "WAIVING POINTS OF ORDER",
                 "WAIVING A REQUIREMENT OF CLAUSE", "PERMISSION TO", "REQUEST TO", "APPOINTMENT OF",
                 "PROVIDING FOR FURTHER CONSIDERATION OF", "PROVIDING FOR THE FURTHER CONSIDERATION OF")
TITLE_BILL = re.compile(r"(?<!\bU )\b(H R|H RES|H J RES|H CON RES|S|S RES|S J RES|S CON RES) (\d+)\b")
TITLE_TYPE = {"H R": "hr", "H RES": "hres", "H J RES": "hjres", "H CON RES": "hconres", "S": "s", "S RES": "sres",
              "S J RES": "sjres", "S CON RES": "sconres"}


def norm_title(t):
    t = (t or "").upper().replace("--CONTINUED", " ").replace("CONTINUED", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def _compact(t):
    return t.replace(" ", "")


_PROC_COMPACT = None


def is_proc_title(nt):
    """Procedural item. Compared with spaces removed too, because scanned pages split
    words ("GENERAL LEAV E", "RESOLU TIONS")."""
    global _PROC_COMPACT
    if _PROC_COMPACT is None:
        _PROC_COMPACT = {_compact(t) for t in PROC_TITLES}
    c = _compact(nt)
    return (nt in PROC_TITLES or c in _PROC_COMPACT or nt.startswith(RULE_PREFIXES) or nt.startswith(PROC_PREFIXES)
            or any(c.startswith(_compact(p)) for p in RULE_PREFIXES + PROC_PREFIXES))


def title_names_other_bill(nt, btype, number):
    """True when the section title names a bill, and none of the bills it names is this one
    ("CONFERENCE REPORT ON H R 2417 INTELLIGENCE AUTHORIZATION ..." for H.R. 1).
    Not applied to resolutions: a resolution's own debate is often titled by the bill it
    acts on ("DIRECTING THE CLERK ... TO MAKE CORRECTIONS IN THE ENROLLMENT OF H.R. 719"
    is the debate on H. Con. Res. 79)."""
    if str(btype).lower() not in ("hr", "s"):
        return False
    named = [(TITLE_TYPE[m.group(1)], int(m.group(2))) for m in TITLE_BILL.finditer(nt)]
    return bool(named) and (str(btype).lower(), int(number)) not in named


def congress_of(date):
    y = int(date[:4])
    return str((y - 1789) // 2 + 1)


def interleave_rate(text):
    lines = (text or "").splitlines()
    if not lines:
        return 0.0
    bad = sum(1 for ln in lines if re.search(r"\b[a-z]{2,}-\s+[A-Z][a-z]", ln)
              or re.search(r"[a-z,;]\s+(?:\u2018\u2018|'')?(?:SEC\.|SECTION)\s+\d", ln))
    return bad / len(lines)


# =========================================================================== column-aware PDF extraction

def words_to_lines(ws, ytol=3.0):
    ws = sorted(ws, key=lambda w: (w["top"], w["x0"]))
    lines, cur, cur_top = [], [], None
    for w in ws:
        if cur and abs(w["top"] - cur_top) > ytol:
            lines.append(cur)
            cur = []
        if not cur:
            cur_top = w["top"]
        cur.append(w)
    if cur:
        lines.append(cur)
    return [" ".join(x["text"] for x in sorted(line, key=lambda w: w["x0"])) for line in lines]


def split_columns(words, max_cols=4, min_gutter=4.0, sliver=0.08):
    """Find vertical whitespace gutters: x ranges that (almost) no word on the page
    touches. Justified text never lines its word gaps up across a whole page, so a
    strip that stays empty from top to bottom is a column gutter."""
    if not words:
        return []
    left = min(w["x0"] for w in words)
    right = max(w["x1"] for w in words)
    scale = 4
    n = int((right - left) * scale) + 2
    cov = [0] * n
    for w in words:
        a = max(0, int((w["x0"] - left) * scale))
        b = min(n, int((w["x1"] - left) * scale) + 1)
        for i in range(a, b):
            cov[i] += 1
    tol = max(1, int(0.004 * len(words)))
    gaps, start = [], None
    for i in range(n + 1):
        empty = i < n and cov[i] <= tol
        if empty and start is None:
            start = i
        elif not empty and start is not None:
            width = (i - start) / scale
            center = left + (start + i) / 2 / scale
            if width >= min_gutter and left + 0.1 * (right - left) < center < right - 0.1 * (right - left):
                gaps.append((width, center))
            start = None
    cuts = sorted(c for _, c in sorted(gaps, reverse=True)[:max_cols - 1])

    def columns(cs):
        bounds = [left - 1] + cs + [right + 1]
        cols = [[] for _ in range(len(bounds) - 1)]
        for w in words:
            cx = (w["x0"] + w["x1"]) / 2
            for k in range(len(bounds) - 1):
                if bounds[k] <= cx < bounds[k + 1]:
                    cols[k].append(w)
                    break
        return cols

    cols = columns(cuts)
    while cuts:
        small = [k for k, c in enumerate(cols) if len(c) < sliver * len(words)]
        if not small:
            break
        cuts.pop(min(small[0], len(cuts) - 1))
        cols = columns(cuts)
    return cols


def extract_pdf_columns(pdf_path, header_frac=0.05, footer_frac=0.97):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            H = float(page.height)
            head = [w for w in words if w["top"] <= header_frac * H]
            body = [w for w in words if header_frac * H < w["top"] and w["bottom"] < footer_frac * H]
            lines = []
            for col in split_columns(body):
                lines += words_to_lines(col)
            pages.append({"header": " ".join(w["text"] for w in sorted(head, key=lambda w: w["x0"])),
                          "lines": lines})
    return pages


# =========================================================================== OCR repair and blocking

_DICT = None


def dictionary():
    global _DICT
    if _DICT is None:
        _DICT = set()
        for p in ("/usr/share/dict/words", "/usr/dict/words"):
            if os.path.exists(p):
                with open(p, encoding="utf-8", errors="ignore") as f:
                    _DICT = {w.strip().lower() for w in f if w.strip()}
                break
    return _DICT


def dehyphenate(lines, corpus=None):
    """Line-end repair. 'mil-' + 'lion' always joins. 'espe' + 'cially' (OCR lost the
    hyphen) joins only if the joined word is a real word and at least one piece is not."""
    words = dictionary()
    corpus = corpus or Counter()

    def real(w):
        return w in words if words else corpus.get(w, 0) >= 3

    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            out.append("")
            continue
        if out and out[-1] and not ln.startswith(HEAD_MARK) and not out[-1].startswith(HEAD_MARK):
            prev = out[-1]
            nxt = re.match(r"([a-z]+)", ln)
            if nxt and re.search(r"[A-Za-z]-$", prev):
                out[-1] = prev[:-1] + ln
                continue
            frag = re.search(r"(?<![A-Za-z])([A-Za-z]{1,14})$", prev)
            if frag and nxt:
                a, b = frag.group(1).lower(), nxt.group(1)
                if real(a + b) and (not real(a) or not real(b)):
                    out[-1] = prev + ln
                    continue
        out.append(ln)
    return out


def is_caps_header(s):
    s = s.strip()
    if len(s) < 4 or len(s) > 100 or "CONGRESSIONAL RECORD" in s.upper():
        return False
    if re.match(r"^(Mr|Mrs|Ms|Miss|The|H\.\s?R\.|S\.|SEC\.|SECTION|TITLE|\(|\d|\[)", s):
        return False
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.9


SPEAKER_START = re.compile(r"^(?:Mr|Mrs|Ms|Miss)\.\s+[A-Z][A-Z'\-]+|^The\s+(?:SPEAKER|CHAIRMAN|Clerk|CHAIR|"
                           r"SPEAKER pro tempore|Acting CHAIRMAN)")


def caps_blocks(lines, marked=False):
    is_head = (lambda s: s.startswith(HEAD_MARK)) if marked else is_caps_header
    blocks, head, body = [], "", []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if is_head(ln):
            parts = [ln.strip().lstrip(HEAD_MARK)]
            while i + 1 < len(lines) and is_head(lines[i + 1]):
                i += 1
                parts.append(lines[i].strip().lstrip(HEAD_MARK))
            joined = dehyphenate([p.lower() for p in parts])
            if body or head:
                blocks.append((head, body))
            head, body = " ".join(joined).upper(), []
        else:
            body.append(ln)
        i += 1
    if body or head:
        blocks.append((head, body))
    return blocks


def lines_to_paragraphs(lines):
    paras, cur = [], []
    for ln in lines:
        s = ln.strip()
        if not s:
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if SPEAKER_START.match(s) and cur:
            paras.append(" ".join(cur))
            cur = []
        cur.append(s)
    if cur:
        paras.append(" ".join(cur))
    return paras


def daily_paragraphs(text):
    paras, cur = [], []
    for ln in text.splitlines():
        s = ln.rstrip()
        if re.match(r"^\s*\[(?:Congressional Record|House|Senate|Pages?\s|\[Page)", s) or \
                s.strip().startswith("From the Congressional Record Online"):
            continue
        if not s.strip():
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if re.match(r"^\s{2,}\S", s) and cur:
            paras.append(" ".join(cur))
            cur = []
        cur.append(s.strip())
    if cur:
        paras.append(" ".join(cur))
    return [p for p in paras if p]


# =========================================================================== GovInfo

def gget(url, params=None, binary=False, _attempt=0):
    if requests is None:
        sys.exit("pip install requests")
    p = dict(params or {})
    if "api.govinfo.gov" in url:
        if not KEY:
            sys.exit("export GOVINFO_API_KEY=your_key   (free at https://api.data.gov/signup/)")
        p["api_key"] = KEY
    try:
        r = requests.get(url, params=p, headers=UA, timeout=180)
    except requests.RequestException:
        if _attempt >= 5:
            return None
        time.sleep(20 * (_attempt + 1))
        return gget(url, params, binary, _attempt + 1)
    if r.status_code in (401, 403) and "api.govinfo.gov" in url:
        sys.exit(f"GovInfo refused the API key (HTTP {r.status_code}). Set your real key: "
                 f"export GOVINFO_API_KEY=<the key from api.data.gov>  and run again. Nothing was cached.")
    if r.status_code == 404:
        return None
    if r.status_code in (429, 500, 502, 503, 504):
        if _attempt >= 6:
            return None
        time.sleep(min(600, 30 * (2 ** _attempt)))
        return gget(url, params, binary, _attempt + 1)
    if r.status_code >= 400:
        print(f"    HTTP {r.status_code} for {url}", flush=True)
        return None
    time.sleep(SLEEP)
    return r.content if binary else r.json()


def html_to_text(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", "", h)
    return htmlmod.unescape(re.sub(r"<[^>]+>", "", h))


def list_granules(pkg):
    p = os.path.join(CACHE, "granule_lists", pkg + ".json")
    cached = load_json(p)
    if cached is not None:
        return cached.get("granules")
    url, params, out = f"{API}/packages/{pkg}/granules", {"offsetMark": "*", "pageSize": 100}, []
    while url:
        data = gget(url, params)
        if data is None:
            return None            # not cached: a failed request must never be remembered as "no data"
        out += data.get("granules", [])
        url, params = data.get("nextPage"), None
    save_json({"granules": out}, p)
    return out


def package_texts(pkg, grans):
    d = os.path.join(CACHE, "daily", pkg)
    flag = os.path.join(d, "_complete")
    got = {}
    if os.path.exists(flag):
        for f in glob.glob(os.path.join(d, "*.txt")):
            with open(f, encoding="utf-8") as fh:
                got[os.path.basename(f)[:-4]] = fh.read()
        return got
    os.makedirs(d, exist_ok=True)
    summ = gget(f"{API}/packages/{pkg}/summary") or {}
    zlink = (summ.get("download") or {}).get("zipLink")
    if zlink:
        raw = gget(zlink, binary=True)
        if raw:
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    for name in z.namelist():
                        if name.lower().endswith(".htm") and "/html/" in name:
                            got[os.path.basename(name)[:-4]] = html_to_text(z.read(name).decode("utf-8", "replace"))
            except zipfile.BadZipFile:
                pass
    for g in grans:
        gid = g.get("granuleId")
        if (g.get("granuleClass") or "").upper() != "HOUSE" or gid in got:
            continue
        raw = gget(f"https://www.govinfo.gov/content/pkg/{pkg}/html/{gid}.htm", binary=True)
        if raw is None:
            s = gget(f"{API}/packages/{pkg}/granules/{gid}/summary") or {}
            link = (s.get("download") or {}).get("txtLink")
            raw = gget(link, binary=True) if link else None
        if raw:
            got[gid] = html_to_text(raw.decode("utf-8", "replace"))
    for gid, t in got.items():
        with open(os.path.join(d, gid + ".txt"), "w", encoding="utf-8") as f:
            f.write(t)
    open(flag, "w").close()
    return got


_DAILY_HDR = re.compile(r"Congressional Record Volume (\d+), Number (\d+) \((\w+), (\w+ \d{1,2}, \d{4})\)")


def daily_units(day):
    pkg = f"CREC-{day}"
    grans = list_granules(pkg)
    if not grans:
        return []
    texts = package_texts(pkg, grans)
    units = []
    for g in grans:
        if (g.get("granuleClass") or "").upper() != "HOUSE" or g.get("granuleId") not in texts:
            continue
        t = texts[g["granuleId"]]
        m = _DAILY_HDR.search(t[:400])
        units.append({"id": g["granuleId"], "day": day, "title": g.get("title", ""), "text": t,
                      "paragraphs": daily_paragraphs(t), "source": "daily_edition",
                      "printed": {"volume": m.group(1), "number": m.group(2),
                                  "date": first_long_date(m.group(4))} if m else {},
                      "url": f"https://www.govinfo.gov/app/details/{pkg}/{g['granuleId']}"})
    return units


def old_files(day):
    return sorted(glob.glob(os.path.join(OLD_DIR, f"{day}*.txt")))


def bound_text(day, hint_pkgs):
    """Bound edition (pre-1994): ONLY text re-read from the GovInfo PDF by
    reextract_bound.py (source 'pdf_columns_v2', pages checked against the date).
    The old text files and old caches are never used; a day that has not been
    re-read has no text, so its bill is reported NOT FOUND instead of using bad text."""
    c = load_json(os.path.join(CACHE, "bound_text", f"{day}.json"))
    if c is not None and c.get("source") == "pdf_columns_v2":
        return c
    return {"source": "none", "lines": [], "headers": [], "granules": []}


def bound_pkg_url(gids):
    for g in gids or []:
        m = re.match(r"(GPO-CRECB-\d{4}-pt\d+)", g)
        if m:
            return f"https://www.govinfo.gov/app/details/{m.group(1)}/{g}"
    return ""


def bound_units(day, hint_pkgs):
    bt = bound_text(day, hint_pkgs)
    if not bt["lines"]:
        return []
    corpus = Counter(w.lower() for ln in bt["lines"] for w in re.findall(r"[A-Za-z]{3,}", ln))
    lines = dehyphenate(bt["lines"], corpus)
    printed = next((first_long_date(h) for h in bt["headers"] if first_long_date(h)), None) or \
        first_long_date("\n".join(bt["lines"][:60]))
    units = []
    for k, (head, body) in enumerate(caps_blocks(lines, marked=bt.get("source") == "pdf_columns_v2")):
        paras = lines_to_paragraphs(body)
        units.append({"id": f"{day}-block{k:03d}", "day": day, "title": head, "text": head + "\n" + "\n".join(paras),
                      "paragraphs": ([head] if head else []) + paras, "source": bt["source"],
                      "printed": {"date": printed}, "granules": bt["granules"],
                      "url": bound_pkg_url(bt["granules"])})
    return units


# =========================================================================== selection

def select_units(units_by_day, b):
    rx = us_bill_mention_re(b["type"], b["number"])
    anchors, excluded = [], []
    for day, units in units_by_day.items():
        for u in units:
            hits = len(rx.findall(u["text"]))
            if not hits:
                continue
            nt = norm_title(u["title"])
            if is_proc_title(nt):
                excluded.append({"id": u["id"], "day": day, "title": u["title"], "why": "procedural or rule debate"})
                continue
            if title_names_other_bill(nt, b["type"], b["number"]):
                excluded.append({"id": u["id"], "day": day, "title": u["title"], "why": "title names another bill"})
                continue
            if hits >= 2 or rx.search(u["text"][:2500]):
                anchors.append(u)
    if not anchors:
        return None, excluded
    # a section with the same title as an anchor is the same debate continued (the Record
    # splits long debates into several granules), so only on the SAME day, and never for
    # topic titles shared by unrelated speeches ("HEALTH CARE REFORM") or procedural items
    # (a named act's own title, "... ACT OF 2022", may also continue on another day)
    anchor_titles = {(u["day"], norm_title(u["title"])) for u in anchors if norm_title(u["title"])}
    act_titles = {nt for _, nt in anchor_titles if re.search(r"\bACT\b", nt)}
    chosen = {(u["day"], u["id"]): (u, "bill_number") for u in anchors}
    for day, units in units_by_day.items():
        for u in units:
            nt = norm_title(u["title"])
            if (day, u["id"]) in chosen or not nt or ((day, nt) not in anchor_titles and nt not in act_titles):
                continue
            if is_proc_title(nt) or nt in GENERIC_TITLES or title_names_other_bill(nt, b["type"], b["number"]):
                excluded.append({"id": u["id"], "day": day, "title": u["title"],
                                 "why": "same title as the bill's section but a procedural or shared topic title"})
                continue
            chosen[(day, u["id"])] = (u, "title_hash")
    return list(chosen.values()), excluded


# =========================================================================== commands

def cmd_plan():
    bills, bad = [], 0
    if os.path.exists(CSV_MATCHED):
        with open(CSV_MATCHED, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                raw = r.get("bill_number") or r.get("bill") or r.get("bill_id") or ""
                t, n = parse_us_bill(raw)
                date = (r.get("date") or r.get("vote_date") or "")[:10]
                if not t or not re.match(r"\d{4}-\d{2}-\d{2}$", date):
                    bad += 1
                    continue
                bills.append({"congress": str(r.get("congress") or congress_of(date)).strip(), "type": t, "number": n,
                              "vote_date": date, "result": r.get("result", ""), "source": "roll_call", "raw_bill": raw})
    vv = load_json(VOICE, {}) or {}
    for k, v in (vv.items() if isinstance(vv, dict) else enumerate(vv)):
        if not isinstance(v, dict):
            continue
        t, n = parse_us_bill(v.get("bill") or str(k))
        date = str(v.get("passage_date") or v.get("date") or "")[:10]
        if not t or not re.match(r"\d{4}-\d{2}-\d{2}$", date):
            bad += 1
            continue
        bills.append({"congress": str(v.get("congress") or congress_of(date)), "type": t, "number": n,
                      "vote_date": date, "result": "passed (voice vote)", "source": "voice_vote",
                      "raw_bill": v.get("bill") or str(k)})
    plan, seen = [], set()
    for b in bills:
        k = (b["congress"], b["type"], b["number"], b["vote_date"])
        if k in seen:
            continue
        seen.add(k)
        b["bill_key"] = f"{b['congress']}-{b['type'].upper()}{b['number']}"
        b["edition"] = "daily" if b["vote_date"] >= DAILY_FROM else "bound"
        plan.append(b)
    save_json(plan, PLAN, indent=1)
    ed = Counter(b["edition"] for b in plan)
    print(f"Plan: {len(plan)} (bill, vote date) rows; {dict(ed)}; unparseable rows skipped: {bad}")


def window_days(b):
    d0 = dt.date.fromisoformat(b["vote_date"])
    look = LOOKBACK_DAILY if b["edition"] == "daily" else LOOKBACK_BOUND
    return [(d0 - dt.timedelta(days=k)).isoformat() for k in range(look + 1)]


def floor_extra(plan):
    """Congress.gov House debate days that the vote-day windows do not cover, each given
    to the bill's first vote on or after it (so a day is searched once). Days after the
    bill's last vote are left out unless US_FLOOR_AFTER_VOTE=1."""
    floor = load_json(FLOOR, {}) or {}
    rows = defaultdict(list)
    for i, b in enumerate(plan):
        rows[b["bill_key"]].append(i)
    extra = defaultdict(set)
    for bk, ids in rows.items():
        covered = {d for i in ids for d in window_days(plan[i])}
        votes = sorted(ids, key=lambda i: plan[i]["vote_date"])
        for d in floor.get(bk, []):
            if d in covered:
                continue
            tgt = next((i for i in votes if plan[i]["vote_date"] >= d), None)
            if tgt is None and FLOOR_AFTER_VOTE:
                tgt = votes[-1]
            if tgt is not None:
                extra[tgt].add(d)
    return extra


def cmd_floor_days():
    """Reads each bill's Congress.gov action list (data/v3_status_cache/us/{bill}.actions.json)
    and records the days the House debated it (debate, suspension, Committee of the Whole;
    Rules Committee actions are not debate). The segment step searches these days as well
    as the vote day and the days before it, so a debate held earlier than that window
    (H.R. 2454: debated 10/28/1991, voted 10/31/1991) is no longer missed."""
    from compare_debate_days import house_floor
    plan = load_json(PLAN) or sys.exit("Run plan first.")
    status = rp("data", "v3_status_cache", "us")
    out, no_list = {}, []
    for bk in sorted({b["bill_key"] for b in plan}):
        acts = (load_json(os.path.join(status, f"{bk}.actions.json")) or {}).get("actions")
        if acts is None:
            no_list.append(bk)
            continue
        days = sorted(d for d, (kind, _) in house_floor(acts).items() if kind == "debate")
        if days:
            out[bk] = days
    save_json(out, FLOOR, indent=1)
    extra = floor_extra(plan)
    new_days = sorted({d for ds in extra.values() for d in ds})
    todo = []
    for d in new_days:
        if d < DAILY_FROM:
            c = load_json(os.path.join(CACHE, "bound_text", f"{d}.json"))
            if not (c and c.get("source") == "pdf_columns_v2" and c.get("lines")):
                todo.append(d)
    with open(FLOOR_TODO, "w", encoding="utf-8") as f:
        f.write(",".join(todo))
    print(f"Congress.gov House debate days found for {len(out)} bills ({len(no_list)} bills have no action list)")
    print(f"days the vote windows did not cover, now added: {sum(len(v) for v in extra.values())} "
          f"({len(new_days)} distinct dates; {sum(d < DAILY_FROM for d in new_days)} before 1994)"
          + ("" if FLOOR_AFTER_VOTE else "; days after a bill's last vote left out (US_FLOOR_AFTER_VOTE=1 adds them)"))
    print(f"pre-1994 days still to read from the PDF: {len(todo)} -> {FLOOR_TODO}")


_DEBATE_REAL = re.compile(r"DEBATE\s*-|Considered under suspension|Considered under the provisions of rule|"
                          r"Committee of the Whole|GENERAL DEBATE|moved to suspend the rules|moved that the House suspend|"
                          r"Called up by|Considered as privileged|proceeded with|Considered as unfinished business", re.I)
_RULE_ACT = re.compile(r"(?:Rule|Rules Committee Resolution)\s+H\.\s?Res\.\s?(\d+)", re.I)


def _section_inputs(plan):
    """Per bill from its Congress.gov action list: days of any House floor action, days of House floor
    DEBATE (not passage by unanimous consent alone), the H. Res. rules listed for it, and its titles;
    plus the by-hand checks (data/us/v3/section_hand_checks.json)."""
    status = rp("data", "v3_status_cache", "us")
    try:
        from compare_debate_days import house_floor
    except Exception:                                   # noqa: BLE001
        house_floor = None
    floor, debate, rules, titles = {}, {}, {}, {}
    for bk in sorted({b["bill_key"] for b in plan}):
        acts = (load_json(os.path.join(status, f"{bk}.actions.json")) or {}).get("actions")
        if acts is not None and house_floor is not None:
            floor[bk] = set(house_floor(acts))
            debate[bk] = set()
            rules[bk] = set()
            for a in acts:
                t = str(a.get("text", ""))
                d = str(a.get("actionDate", ""))[:10]
                src = str((a.get("sourceSystem") or {}).get("name", ""))
                rules[bk] |= {int(x) for x in _RULE_ACT.findall(t)}
                if not d or "Senate" in src or (re.search(r"\bSenate\b", t) and not re.search(r"\bHouse\b", t)):
                    continue
                if _DEBATE_REAL.search(t) and not re.match(r"^\s*(Rules\s*Committee|Committee on Rules|Rule\s+H)", t, re.I):
                    debate[bk].add(d)
        bill = (load_json(os.path.join(status, f"{bk}.bill.json")) or {}).get("bill") or {}
        titles[bk] = [t for t in (bill.get("title"), (bill.get("latestTitle") or "")) if t]
    hand = load_json(os.path.join(OUT, "section_hand_checks.json"), {}) or {}
    own = hand.get("own_debate_titles", {})
    vehicle = {(v[0], v[1]) for v in hand.get("vehicle_days", [])}
    joint = defaultdict(list)                          # bill_key -> [(day, item title)] read by hand as a joint debate
    for j in hand.get("joint_debates", []):
        joint[j[0]].append((j[1], j[2]))
    return floor, debate, rules, titles, own, vehicle, joint


_TAG_RANK = {"debate": 3, "vehicle": 3, "companion": 3, "speech": 2, "rule": 2, "held": 1}


def cmd_segment():
    # PATCHED_SECTIONS_2026_10_02 PATCHED_SECTIONS2_2026_10_02 PATCHED_SECTIONS3_2026_10_02 PATCHED_SECTIONS4_2026_10_03: text belongs to a bill only from the Record's own line that brings
    # that bill before the House (us_sections.py); other measures' debates and procedural items are
    # taken out only when two independent checks agree; speeches, printed text, roll-call lists and
    # vehicle days are tagged paragraph by paragraph (para_tags) so the choices file decides later.
    import us_sections as SEC
    plan = load_json(PLAN) or sys.exit("Run plan first.")
    os.makedirs(SEG_DIR, exist_ok=True)
    index, missing, emptied = [], [], []
    merged = {}                # (bill_key, debate_day) -> one entry, whichever votes reach it
    extra = floor_extra(plan) if os.path.exists(FLOOR) else {}
    floor, debate, rules, titles, own, vehicle, joint = _section_inputs(plan)
    plan_keys = {(str(b["congress"]), str(b["type"]).lower(), int(b["number"])) for b in plan}
    if extra:
        print(f"also searching {sum(len(v) for v in extra.values())} Congress.gov House debate days "
              f"outside the vote windows (floor_days.json)", flush=True)
    for i, b in enumerate(plan, 1):
        hint = set()               # old text files are not used any more
        units_by_day = {}
        for day in window_days(b):
            units_by_day[day] = daily_units(day) if b["edition"] == "daily" else bound_units(day, hint)
        floor_days = sorted(extra.get(i - 1, set()))
        for day in floor_days:
            units_by_day[day] = daily_units(day) if day >= DAILY_FROM else bound_units(day, hint)
        d0 = dt.date.fromisoformat(b["vote_date"])
        chosen, excluded = select_units(units_by_day, b)
        rx = us_bill_mention_re(b["type"], b["number"])
        res = SEC.refine(b, units_by_day, chosen or [], rx, is_proc_title, frozenset(GENERIC_TITLES),
                         titles.get(b["bill_key"], []), floor.get(b["bill_key"]), own.get(b["bill_key"], []), vehicle,
                         debate_days=debate.get(b["bill_key"]), plan_keys=plan_keys,
                         rules_of_bill=frozenset(rules.get(b["bill_key"], set())), joint=tuple(joint.get(b["bill_key"], ())))
        kept_days = {d for d, r in res.items() if r["paras"]}
        if not kept_days and not chosen:
            missing.append({**b, "days_searched": list(units_by_day),
                            "units_available": {d: len(u) for d, u in units_by_day.items()}, "excluded": excluded})
            print(f"  [{i}/{len(plan)}] {b['bill_key']} {b['vote_date']}: NOT FOUND", flush=True)
            continue
        for day, r in sorted(res.items()):
            k = (d0 - dt.date.fromisoformat(day)).days
            src = ("congress_gov_floor_day" if day in floor_days else
                   "vote_date" if k == 0 else f"vote_date_minus_{k}")
            m = merged.get((b["bill_key"], day))
            if m is None or (src != "congress_gov_floor_day" and (m["src"] == "congress_gov_floor_day" or k < m["k"])):
                prev = m
                m = {"b": b, "k": k, "src": src, "floor": day in floor_days,
                     "paras": prev["paras"] if prev else {}, "units": prev["units"] if prev else {},
                     "removed": prev["removed"] if prev else {}, "held": prev["held"] if prev else {},
                     "notes": prev["notes"] if prev else {},
                     "added": prev["added"] if prev else 0, "votes": prev["votes"] if prev else [],
                     "excluded": prev["excluded"] if prev else []}
                merged[(b["bill_key"], day)] = m
            for order, uid, idx, text, tag in r["paras"]:
                old = m["paras"].get((order, uid, idx))
                if old is None or _TAG_RANK[tag.split("+")[0]] > _TAG_RANK[old[1].split("+")[0]]:
                    m["paras"][(order, uid, idx)] = (text, tag)
            for u, meth in (chosen or []):
                if u["day"] == day:
                    m["units"].setdefault(u["id"], {"id": u["id"], "title": u["title"], "method": meth,
                                                    "source": u["source"], "printed": u.get("printed", {}),
                                                    "url": u.get("url", "")})
            for u in units_by_day.get(day, []):
                if u["id"] in r["units"] and u["id"] not in m["units"]:
                    m["units"][u["id"]] = {"id": u["id"], "title": u["title"], "method": "consideration_line",
                                           "source": u["source"], "printed": u.get("printed", {}), "url": u.get("url", "")}
            for ev in r["removed"]:
                m["removed"][(ev["unit"], ev["kind"], ev["measure"])] = ev
            for h in r["held"]:
                m["held"][(h["unit"], h.get("kind", ""), h.get("measure", ""), h["why"][:40])] = h
            for h in r.get("notes", []):
                m["notes"][(h["unit"], h.get("measure", ""), h["tag"])] = h
            m["added"] = max(m["added"], r["added"])
            m["votes"].append(b["vote_date"])
            m["excluded"] += [e for e in excluded if e["day"] == day and e not in m["excluded"]]
        print(f"  [{i}/{len(plan)}] {b['bill_key']} {b['vote_date']}: kept text on {sorted(kept_days)}", flush=True)
    for (bk, day), m in merged.items():
        b = m["b"]
        kept_keys = {(uid, idx) for (_o, uid, idx) in m["paras"]}
        removed = [ev for ev in m["removed"].values() if not any((ev["unit"], i) in kept_keys for i in ev.get("idx", []))]
        if not any(not re.match(r"^[_\-=\s]{5,}$", t) for t, _ in m["paras"].values()):
            emptied.append({"bill_key": bk, "debate_date": day, "removed": removed})
            continue
        rows = [r for r in sorted(m["paras"].items()) if not re.match(r"^[_\-=\s]{5,}$", r[1][0])]   # item separators
        path = os.path.join(SEG_DIR, f"{bk}_{day}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(t for _, (t, _) in rows) + "\n")
        tags, tag_words, punits = [], Counter(), []
        for (_o, uid, _i), (t, tag) in rows:
            tag_words[tag] += len(t.split())
            if tags and tags[-1][0] == tag:
                tags[-1][1] += 1
            else:
                tags.append([tag, 1])
            if punits and punits[-1][0] == uid:
                punits[-1][1] += 1
            else:
                punits.append([uid, 1])
        used = {uid for (_o, uid, _i) in m["paras"]}
        spoken = any(tag in ("debate", "vehicle", "companion") and SEC.is_debate_speech(t) for _, (t, tag) in rows)
        index.append({**b, "debate_date": day, "date_source": m["src"],
                      "edition": (("daily" if day >= DAILY_FROM else "bound") if m["floor"] else b["edition"]),
                      "file": os.path.relpath(path, US),
                      "votes_served": sorted(set(m["votes"])),
                      "units": [u for uid, u in m["units"].items() if uid in used],
                      "para_tags": tags, "para_units": punits, "tag_words": dict(tag_words),
                      "no_debate": not spoken,
                      "added_paragraphs": m["added"],
                      "removed": [{k: v for k, v in ev.items() if k != "idx"} for ev in removed],
                      "held": [{k: (v[:600] if isinstance(v, str) else v) for k, v in h.items() if k != "idx"}
                               for h in m["held"].values()],
                      "notes": [{k: (v[:300] if isinstance(v, str) else v) for k, v in h.items() if k != "idx"}
                                for h in m["notes"].values()],
                      "excluded": m["excluded"]})
    dup = sum(len(m["votes"]) - 1 for m in merged.values())
    print(f"Bill-days reached from more than one vote, kept once: {sum(len(m['votes']) > 1 for m in merged.values())} "
          f"({dup} repeat entries merged)")
    save_json(index, INDEX, indent=1)
    save_json(missing, os.path.join(OUT, "segments_missing.json"), indent=1)
    save_json(emptied, os.path.join(OUT, "segments_emptied.json"), indent=1)
    print(f"Files written: {len(index)}; bill-votes not found: {len(missing)} (segments_missing.json); "
          f"bill-days left with no text: {len(emptied)} (segments_emptied.json)")


def cmd_verify():
    index = load_json(INDEX) or sys.exit("Run segment first.")
    rows, c = [], Counter()
    for e in index:
        path = os.path.join(US, e["file"])
        with open(path, encoding="utf-8") as f:
            text = f.read()
        rx = us_bill_mention_re(e["type"], e["number"])
        mentions = bool(rx.search(text))
        printed = sorted({u["printed"].get("date") for u in e["units"] if u.get("printed", {}).get("date")})
        date_ok = (e["debate_date"] in printed) if printed else None
        vol = sorted({f"Vol. {u['printed']['volume']}, No. {u['printed']['number']}"
                      for u in e["units"] if u.get("printed", {}).get("volume")})
        boiler = bool(re.search(r"offered the following prayer|The Chaplain|THE JOURNAL|Daily Digest", text))
        rate = interleave_rate(text)
        c["mentions" if mentions else "no_mention"] += 1
        c["date_ok" if date_ok else ("date_unknown" if date_ok is None else "date_mismatch")] += 1
        c["boilerplate"] += boiler
        rows.append({
            "congress": e["congress"], "bill_key": e["bill_key"], "vote_date": e["vote_date"],
            "debate_date": e["debate_date"], "date_source": e["date_source"], "result": e["result"],
            "edition": e["edition"], "issue": "; ".join(vol), "units": len(e["units"]),
            "unit_titles": " | ".join(sorted({u["title"] for u in e["units"]}))[:300],
            "methods": dict(Counter(u["method"] for u in e["units"])),
            "text_source": dict(Counter(u["source"] for u in e["units"])),
            "check1_mentions_bill": "Y" if mentions else "N",
            "check2_printed_date_matches": "" if date_ok is None else ("Y" if date_ok else "N"),
            "printed_dates": ", ".join(printed), "interleave_rate": f"{rate:.4f}",
            "contains_prayer_or_journal": "Y" if boiler else "N",
            "govinfo_url": e["units"][0]["url"] if e["units"] else "", "github_text": github_url(path),
            "excerpt": text[:220].replace("\n", " ")})
    with open(TABLE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bill_key"])
        w.writeheader()
        w.writerows(rows)
    print(f"Files: {len(rows)}")
    print(f"CHECK 1 text names its own bill: {c['mentions']} yes, {c['no_mention']} no")
    print(f"CHECK 2 printed Record date equals the debate date used: {c['date_ok']} yes, {c['date_mismatch']} no, "
          f"{c['date_unknown']} could not be read")
    print(f"Files containing prayer / Journal / Daily Digest text: {c['boilerplate']} (should be 0)")
    print(f"Running table: {TABLE}")


if __name__ == "__main__":
    cmds = {"plan": cmd_plan, "floor-days": cmd_floor_days, "segment": cmd_segment, "verify": cmd_verify,
            "all": lambda: (cmd_plan(), cmd_segment(), cmd_verify())}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit("usage: us_rebuild.py " + "|".join(cmds))
    cmds[sys.argv[1]]()
