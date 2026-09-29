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
from collections import Counter

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
RULE_PREFIXES = ("PROVIDING FOR CONSIDERATION OF", "PROVIDING FOR THE CONSIDERATION OF", "WAIVING POINTS OF ORDER",
                 "WAIVING A REQUIREMENT OF CLAUSE", "PERMISSION TO", "REQUEST TO", "APPOINTMENT OF")


def norm_title(t):
    t = (t or "").upper().replace("--CONTINUED", " ").replace("CONTINUED", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def is_proc_title(nt):
    return nt in PROC_TITLES or nt.startswith(RULE_PREFIXES)


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
            save_json({"granules": None}, p)
            return None
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
    cache = os.path.join(CACHE, "bound_text", f"{day}.json")
    c = load_json(cache)
    if c is not None:
        return c
    old = ""
    for f in old_files(day):
        with open(f, encoding="utf-8", errors="ignore") as fh:
            old += fh.read() + "\n"
    gids = re.findall(r"---\s*(GPO-CRECB-[\w-]+?)\s*---", old)
    if not gids and hint_pkgs:
        for pkg in hint_pkgs:
            for g in list_granules(pkg) or []:
                gd = first_long_date(g.get("title", "")) or str(g.get("dateIssued", ""))[:10]
                if gd == day and "HOUSE" in (g.get("title", "") + str(g.get("granuleClass", ""))).upper():
                    gids.append(g["granuleId"])
    rate = interleave_rate(old) if old else None
    res = None
    if old and rate is not None and rate < CLEAN_RATE:
        res = {"source": "old_text_clean", "lines": old.splitlines(), "headers": [], "granules": gids}
    elif gids and pdfplumber is not None:
        lines, headers = [], []
        for gid in gids:
            m = re.match(r"(GPO-CRECB-\d{4}-pt\d+)", gid)
            if not m:
                continue
            pdf_path = os.path.join(CACHE, "bound_pdf", gid + ".pdf")
            if not os.path.exists(pdf_path):
                raw = gget(f"https://www.govinfo.gov/content/pkg/{m.group(1)}/pdf/{gid}.pdf", binary=True)
                if raw and raw[:4] == b"%PDF":
                    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
                    with open(pdf_path, "wb") as f:
                        f.write(raw)
            if os.path.exists(pdf_path):
                for pg in extract_pdf_columns(pdf_path):
                    headers.append(pg["header"])
                    lines += pg["lines"] + [""]
        if lines:
            res = {"source": "pdf_columns", "lines": lines, "headers": headers, "granules": gids}
    if res is None and old:
        res = {"source": "old_text_interleaved", "lines": old.splitlines(), "headers": [], "granules": gids}
    if res is None:
        res = {"source": "none", "lines": [], "headers": [], "granules": gids}
    res["interleave_rate"] = interleave_rate("\n".join(res["lines"]))
    save_json(res, cache)
    return res


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
            if hits >= 2 or rx.search(u["text"][:2500]):
                anchors.append(u)
    if not anchors:
        return None, excluded
    titles = {norm_title(u["title"]) for u in anchors if norm_title(u["title"])}
    chosen = {(u["day"], u["id"]): (u, "bill_number") for u in anchors}
    for day, units in units_by_day.items():
        for u in units:
            nt = norm_title(u["title"])
            if (day, u["id"]) not in chosen and nt and not is_proc_title(nt) and nt in titles:
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


def cmd_segment():
    plan = load_json(PLAN) or sys.exit("Run plan first.")
    os.makedirs(SEG_DIR, exist_ok=True)
    index, missing = [], []
    for i, b in enumerate(plan, 1):
        d0 = dt.date.fromisoformat(b["vote_date"])
        look = LOOKBACK_DAILY if b["edition"] == "daily" else LOOKBACK_BOUND
        hint = set()
        for f in old_files(b["vote_date"]):
            with open(f, encoding="utf-8", errors="ignore") as fh:
                hint |= set(re.findall(r"(GPO-CRECB-\d{4}-pt\d+)", fh.read(5000)))
        units_by_day = {}
        for k in range(look + 1):
            day = (d0 - dt.timedelta(days=k)).isoformat()
            units_by_day[day] = daily_units(day) if b["edition"] == "daily" else bound_units(day, hint)
        chosen, excluded = select_units(units_by_day, b)
        if not chosen:
            missing.append({**b, "days_searched": list(units_by_day),
                            "units_available": {d: len(u) for d, u in units_by_day.items()}, "excluded": excluded})
            print(f"  [{i}/{len(plan)}] {b['bill_key']} {b['vote_date']}: NOT FOUND", flush=True)
            continue
        by_day = {}
        for u, method in chosen:
            by_day.setdefault(u["day"], []).append((u, method))
        for day, items in sorted(by_day.items()):
            path = os.path.join(SEG_DIR, f"{b['bill_key']}_{day}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(p for u, _ in items for p in u["paragraphs"]) + "\n")
            k = (d0 - dt.date.fromisoformat(day)).days
            index.append({**b, "debate_date": day, "date_source": "vote_date" if k == 0 else f"vote_date_minus_{k}",
                          "file": os.path.relpath(path, US),
                          "units": [{"id": u["id"], "title": u["title"], "method": m, "source": u["source"],
                                     "printed": u.get("printed", {}), "url": u.get("url", "")} for u, m in items],
                          "excluded": [e for e in excluded if e["day"] == day]})
        print(f"  [{i}/{len(plan)}] {b['bill_key']} {b['vote_date']}: {len(chosen)} units on {sorted(by_day)}",
              flush=True)
    save_json(index, INDEX, indent=1)
    save_json(missing, os.path.join(OUT, "segments_missing.json"), indent=1)
    print(f"Files written: {len(index)}; bill-votes not found: {len(missing)} (segments_missing.json)")


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
    cmds = {"plan": cmd_plan, "segment": cmd_segment, "verify": cmd_verify,
            "all": lambda: (cmd_plan(), cmd_segment(), cmd_verify())}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit("usage: us_rebuild.py " + "|".join(cmds))
    cmds[sys.argv[1]]()
