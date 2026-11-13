#!/usr/bin/env python3
"""
quebec_rebuild.py

Rebuilds Quebec bill segments from the Journal des debats, using each health
bill's own legislative history (cheminement) as the list of debate dates and URLs.

Why the old approach failed (measured by audit_pipeline.py, checks Q1 and Q2):
  1. Segments were cut by regex markers on flattened text, so a marker could fire
     in the middle of a sentence. The Bill 28 file starts "plus tot aujourd'hui sur
     l'adoption du principe" because the real paragraph began "Nous reprenons le
     debat, ajourne plus tot aujourd'hui, ...".
  2. Files were named by date and bill number only, and nothing checked that the
     text actually mentions that bill (Joanie: "this exists but the bill is not
     mentioned").
  3. Every bill on a sitting day was segmented, including non-health bills
     (Bill 2 fiscal and Bill 3 mines in 1985), and later joins were by date.
  4. Debates listed in the cheminement were missed when the day used a heading
     the markers did not know (Bill 116 on 1995-12-04 has no file; that day only
     has files for bills 88, 92, 93 and 102).

New approach:
  fetch    downloads each Journal page listed in the health bills' cheminement
  segment  walks each page paragraph by paragraph. The current bill is set by a bill
           heading ("Projet de loi n 116") or by a procedural anchor at the start of a
           paragraph ("propose l'adoption du principe du projet de loi n 116",
           "Nous reprenons le debat ... projet de loi n 28"), kept through stage
           sub-headings, and cleared by any top-level section heading. A bill number
           mentioned inside a speech never switches the bill. Every segment therefore
           starts at a paragraph boundary and every paragraph belongs to one bill or none.
           If a listed debate has no numbered heading or anchor, the block with the best
           title overlap is used only if it clearly beats every other block.
  verify   two checks per segment plus coverage, and the running table
  all      runs all three

Output: data/canada/quebec_assembly/v3/bill_segments_v3/<billsession>_bill<N>_<YYYYMMDD>_<page>.txt
Filenames carry the bill's session so the same number in two sessions can never collide.
"""
import csv
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import (rp, load_json, save_json, sha, strip_accents, content_tokens, fr_bill_re, en_bill_re,
                       github_url, lang_heuristic)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = BeautifulSoup = None

QC = rp("data", "canada", "quebec_assembly")
HEALTH = rp("data", "canada", "quebec_bills", "quebec_health_bills_combined.json")
OUT = os.path.join(QC, "v3")
CACHE = os.path.join(OUT, "journal_cache")
SEG_DIR = os.path.join(OUT, "bill_segments_v3")
INDEX = os.path.join(OUT, "segments_index.json")
TABLE = os.path.join(OUT, "quebec_running_table.csv")
OLD_SEG = os.path.join(QC, "bill_segments")
SLEEP = float(os.environ.get("ASSNAT_SLEEP", "1.5"))
UA = {"User-Agent": "Mozilla/5.0 (research; Yale School of Public Health legislative factuality study)"}

N_NUM = r"(?:n\s*[\u00b0\u00bao]\.?\s*|numero\s+)?(?P<num>\d+)"
# Patterns below run on accent-stripped lowercase text.
TOP_SECTIONS = [
    "affaires courantes", "affaires du jour", "declarations de deputes", "questions et reponses orales",
    "votes reportes", "motions sans preavis", "avis touchant les travaux des commissions",
    "renseignements sur les travaux de l'assemblee", "depot de documents", "depot de rapports",
    "depot de petitions", "presentation de projets de loi", "debats de fin de seance", "ajournement",
    "affaires prioritaires", "affaires inscrites par les deputes de l'opposition", "motions du gouvernement",
    "interventions portant sur une violation", "reponses orales aux petitions", "questions et reponses ecrites",
    "motion de suspension des regles", "discours d'ouverture", "fin de la seance", "haut de la page",
    "periode de questions", "direction des travaux parlementaires",
]
STAGE_HEADS = ["adoption du principe", "reprise du debat", "prise en consideration du rapport", "adoption",
               "presentation", "mise aux voix", "etude detaillee", "renvoi", "motion de scission",
               "motion de report", "debat restreint", "vote", "sanction", "suite du debat", "debat sur",
               "debat sur l'adoption"]
BILL_HEAD_RE = re.compile(r"^(?:[a-z' ]{0,120}?\s)?projet\s+de\s+loi\s+" + N_NUM + r"\b")
FR_ANCHORS = [
    ("principe", re.compile(r"propose\s+l['\u2019]adoption\s+du\s+principe\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
    ("adoption", re.compile(r"propose\s+l['\u2019]adoption\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
    ("rapport", re.compile(r"prise\s+en\s+consideration\s+du\s+rapport[^.]{0,250}?projet\s+de\s+loi\s+" + N_NUM)),
    ("reprise", re.compile(r"(?:reprend|reprenons|reprise\s+du|poursuit|poursuivons)\s+(?:le\s+)?debat[^.]{0,250}?"
                           r"projet\s+de\s+loi\s+" + N_NUM)),
    ("rapport", re.compile(r"prend\s+en\s+consideration\s+le\s+rapport[^.]{0,300}?projet\s+de\s+loi\s+" + N_NUM)),
    ("principe", re.compile(r"debat\s+sur\s+l['\u2019]adoption\s+du\s+principe\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
    ("principe", re.compile(r"^\W{0,3}que\s+le\s+principe\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
    ("presentation", re.compile(r"presente\s+le\s+projet\s+de\s+loi\s+" + N_NUM)),
    ("feuilleton", re.compile(r"article\s+\d+\s+du\s+feuilleton[^.]{0,250}?projet\s+de\s+loi\s+" + N_NUM)),
    ("en_principle", re.compile(r"adoption\s+in\s+principle\s+of\s+bill\s+(?P<num>\d+)")),
]


def norm(t):
    return re.sub(r"\s+", " ", strip_accents(t or "").lower()).strip()


# --------------------------------------------------------------------------- expected debates

def expected_debates():
    health = load_json(HEALTH, []) or []
    out, no_urls = [], []
    for rec in health:
        num = str(rec.get("bill_number", "")).strip()
        if not num.isdigit():
            continue
        seen, got = set(), False
        for d in rec.get("assembly_debates") or []:
            url = (d.get("url") or "").split("#")[0]
            m = re.search(r"/(\d{8})/(\d+)\.html", url)
            if not m or url in seen:
                continue
            seen.add(url)
            got = True
            sm = re.search(r"assemblee-nationale/(\d+-\d+)/", url)
            out.append({"bill_session": rec.get("session", ""), "bill_number": int(num),
                        "title": rec.get("title", ""), "date": m.group(1), "page_id": m.group(2),
                        "sitting_session": sm.group(1) if sm else "", "url": url, "label": d.get("label", ""),
                        "bill_url": rec.get("bill_url", ""), "source": rec.get("source", "")})
        if not got:
            no_urls.append(rec)
    return out, no_urls


def cache_path(url):
    m = re.search(r"assemblee-nationale/([\d-]+)/journal-debats/(\d{8})/(\d+)\.html", url)
    name = f"{m.group(1)}_{m.group(2)}_{m.group(3)}.html" if m else sha(url) + ".html"
    return os.path.join(CACHE, name)


def cmd_fetch():
    if requests is None:
        sys.exit("pip install requests beautifulsoup4")
    debates, no_urls = expected_debates()
    urls = sorted({d["url"] for d in debates})
    os.makedirs(CACHE, exist_ok=True)
    print(f"Health-bill Assembly debates listed: {len(debates)} on {len(urls)} Journal pages. "
          f"Health bills with no Assembly URLs (mostly pre-1994): {len(no_urls)}")
    failed = []
    for i, u in enumerate(urls, 1):
        p = cache_path(u)
        if os.path.exists(p) and os.path.getsize(p) > 2000:
            continue
        ok = False
        for attempt in range(4):
            try:
                r = requests.get(u, headers=UA, timeout=60)
                if r.status_code == 200 and len(r.content) > 2000:
                    with open(p, "wb") as f:
                        f.write(r.content)
                    ok = True
                    break
                time.sleep(10 * (attempt + 1))
            except requests.RequestException:
                time.sleep(10 * (attempt + 1))
        if not ok:
            failed.append(u)
        if i % 25 == 0 or i == len(urls):
            print(f"  {i}/{len(urls)} pages, {len(failed)} failed", flush=True)
        time.sleep(SLEEP)
    save_json(failed, os.path.join(OUT, "fetch_failed.json"))


# --------------------------------------------------------------------------- page parsing

def looks_like_heading_text(text):
    if len(text) > 200:
        return False
    n = norm(text).strip(" .:")
    if BILL_HEAD_RE.match(n) or any(n.startswith(s) for s in TOP_SECTIONS) or any(n.startswith(s) for s in STAGE_HEADS):
        return (not text.rstrip().endswith(".")) or len(text) < 90
    return False


# ---------------------------------------------------------------------------- page parsing
#
# Verified structure of assnat Journal pages (checked on real cached pages, 35-1 to 43-3):
#   * The debate text is in <p> tags inside a custom <contenu> element.
#   * The table of contents is a custom <tabledesmatieres> element.
#   * BOTH sit inside a <form> tag. Nothing may be deleted from the tree before they
#     are read: decompose() on the form destroys everything inside it, which is what
#     made every earlier version return zero bills.
#   * Old pages (e.g. 1995): each section label appears twice, as an outer <p> holding
#     <a name="951204009"> and as a centered copy inside <center>.
#   * New pages (e.g. 2025): section labels are <p> tags carrying _Toc anchors; the
#     TOC entries do not contain bill numbers, the heading text does.
# The parser therefore reads headings by their TEXT, identified as headings by
# structure (centered, or carrying an anchor listed in the TOC, or a _Toc anchor).

_BILL_HEAD_TXT = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[\u00b0\u00bao]\.?\s*|numero\s+)?(\d+)\b")
_TOP_RE = re.compile(
    r"^(?:affaires courantes|affaires du jour|questions et reponses|periode de questions"
    r"|votes reportes|motions sans preavis|depot de (?:documents?|rapports?|petitions?)|declarations? de deputes|ajournement"
    r"|renseignements sur les travaux|avis touchant|affaires prioritaires|affaires inscrites"
    r"|motions du gouvernement|debats de fin de seance|interventions portant|reponses orales"
    r"|direction des travaux|presentation de projets de loi|motion de suspension des regles)")
# Sections where a bill heading is a document tabling or a question, not a debate.
_NO_DEBATE_SECTIONS = ("depot de", "questions et reponses", "periode de questions", "declaration",
                       "reponses orales", "renseignements sur les travaux", "avis touchant",
                       "motions sans preavis")
# Stage headings that only occur when the Assembly debates or decides a bill. On end-of-session
# days (and under the exceptional procedure) the bills are taken up right after "Depot de rapports
# de commissions" or "Motions sans preavis", with no new "Affaires du jour" heading, so a bill
# heading there followed by one of these stages starts that bill's debate.
_DEBATE_STAGE_HEADS = ("adoption du principe", "reprise du debat", "prise en consideration du rapport",
                       "adoption", "suite du debat", "debat sur l'adoption", "commission pleniere")
# A short line that is only a bill heading ("Projet de loi n 116" or "Projet de loi n 116 Loi modifiant ..."),
# even when the page does not format it as a heading. Capital P and no trailing , ; or . so the
# lists inside a motion ("... les projets de loi suivants: projet de loi n 37, ...") never match.
_BILL_LINE_RAW = re.compile(r"^Projet\s+de\s+loi\s+(?:n\s*[\u00b0\u00bao]\.?\s*|num[e\u00e9]ro\s+)?\d")
# The chair calling the next item ("Le Vice-President: L'article 24 du feuilleton. L'Assemblee prend en
# consideration le rapport ... sur le projet de loi n 42") moves the debate to that bill even when the
# page prints no new bill heading (end-of-session days take up several bills in a row this way).
_CHAIR = re.compile(r"^(?:le|la)\s+(?:vice-)?presidente?(?:\s+suppleante?)?\b")
_SWITCH_STAGES = ("principe", "adoption", "rapport", "reprise")
_FALLBACK_SECTIONS = ("affaires du jour", "affaires prioritaires", "affaires inscrites", "motions du gouvernement")
_SPLIT_NUM = re.compile(r"(projet\s+de\s+loi\s+(?:n\s*[\u00b0\u00bao]\.?\s*|numero\s+)?\d+)\s+(\d+)\b")

# PATCHED_OLDFORMAT_2026_10_05: pages of 1985-1987 print no section headings ("Affaires du jour" ...), so on
# them, for bills of the 1985-1994 sessions only, a heading that is not part of the bill's own business ends it,
# and the older wording of the Chair's call starts a bill. See patch_quebec_oldformat.py.
_OLD_STRUCT = re.compile(r"^(?:affaires courantes|affaires du jour)")
_OLD_CONTINUE = ("adoption", "reprise", "prise en consideration", "mise aux voix", "vote", "renvoi", "etude detaillee",
                 "commission pleniere", "remarques preliminaires", "debat", "motion de report", "motion de scission",
                 "motion de renvoi", "motion d'amendement", "motion de sous-amendement", "motion de cloture",
                 "document depose", "documents deposes", "suite", "(suite)", "replique", "loi ", "article",
                 "articles", "dispositions", "amendement", "sous-amendement", "presentation", "titre", "chapitre",
                 "section ", "question de reglement", "questions de reglement", "rappel au reglement",
                 "point de reglement", "decision", "consentement", "intervention", "suspension", "explication",
                 "rapport de la commission pleniere")
_OLD_NAME = re.compile(r"^(?:m|mm|mme|mmes|mlle)\.?\s+[a-z]|^(?:le|la)\s+(?:vice-)?presidente?\b")
# while the bill itself is studied in committee of the whole, only clearly other business ends it
_OLD_OTHER = re.compile(r"^(?:questions?\s+orales?|questions\s+et\s+reponses|motions?\b|enonce|declarations?\b|depot\b"
                        r"|diagramme|leader|lettres?\b|credits|etats\s+financiers|annexe|ajournement|avis\b"
                        r"|renseignements|messages?\b|commission\s+pleniere|affaires|projets?\s+de\s+loi"
                        r"|rapport\s+de\s+la\s+commission\s+(?!pleniere)|nomination|deces|hommage|condoleances)")
_OLD_ANCHORS = [
    ("principe", re.compile(r"propos\w*\s+l['’]adoption\s+du\s+principe\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
    ("adoption", re.compile(r"(?:propos\w*|debat\s+(?:pour|sur))\s+l['’]adoption\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
]
_OLD_CALL = re.compile(r"^(?:(?:le|la)\s+(?:vice-)?presidente?[^:]{0,40}:\s*)?a\s+l['’]article\s+\d+\s*,?\s*"
                       r"(?:du|au)\s+feuilleton[^.]{0,250}?projet\s+de\s+loi\s+" + N_NUM)


def _old_continues(n):
    if n.startswith("commission pleniere") and "credits" in n:
        return False          # the study of the budget credits is not a bill's study
    return n.startswith(_OLD_CONTINUE) or n.startswith(tuple(STAGE_HEADS)) or bool(_OLD_NAME.match(n))


def _old_keeps(n, in_study):
    return _old_continues(n) or (in_study and not _OLD_OTHER.match(n))


def _old_study(n, current, study_bill):
    """the bill whose committee-of-the-whole study is under way (None when none is)"""
    if n.startswith(("commission pleniere", "etude detaillee")) and "credits" not in n:
        return current
    if n.startswith(("mise aux voix du rapport", "rapport de la commission", "adoption", "prise en consideration")):
        return None
    return study_bill


def _old_stage(head, num):
    """the stage a Chair's call names ('motion proposant l'adoption du principe' -> principe)"""
    for st, rx in _OLD_ANCHORS + FR_ANCHORS:
        m = rx.search(head) if st != "feuilleton" else None
        if m and int(m.group("num")) == num:
            return st
    return "feuilleton"


def _is_old_session(d):
    try:
        return int(str(d.get("bill_session") or "99-1").split("-")[0]) <= 34
    except ValueError:
        return False


# PATCHED_OLDFORMAT2_2026_10_05: more of a bill's own business on the older pages
_OLD_CONTINUE2 = re.compile(r"^(?:depot\s+du\s+rapport\s+de\s+la\s+commission|depot\s+d['’](?:un\s+)?amendements?"
                            r"|motion\s+d['’]ajournement\s+du\s+debat|projet\s+de\s+loi\s)")
_OLD_BILL_MOTION = re.compile(r"^motion\s+(?:proposant\s+(?:de\s+|que\s+(?:le\s+)?)?(?:scinder|reporter|renvoyer|"
                              r"projet\s+de\s+loi)|de\s+(?:report|scission|renvoi|cloture))")
_old_continues_v1 = _old_continues


def _old_continues(n):  # noqa: F811
    return _old_continues_v1(n) or bool(_OLD_CONTINUE2.match(n)) or bool(_OLD_BILL_MOTION.match(n))


def _join_number(n):
    """'projet de loi n 3 7' -> 'projet de loi n 37' (some pages split the number across tags)."""
    return _SPLIT_NUM.sub(r"\1\2", n)


def _norm(t):
    return re.sub(r"\s+", " ", strip_accents(t or "").lower()).strip(" .:")


def _read_toc_labels(soup):
    """anchor id -> label text, from the table of contents (both page formats)."""
    labels = {}
    toc = soup.find("tabledesmatieres")
    if toc:
        for a in toc.find_all("a", href=True):
            labels[a["href"].lstrip("#")] = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
    return labels


def _is_heading(p, toc_labels):
    # A section label is short. A long paragraph is debate text even if it carries an anchor.
    if len(p.get_text(" ", strip=True)) > 250:
        return False
    if p.find_parent("center") is not None or p.find("center") is not None:
        return True
    # 2007-2009 pages mark headings only with <p align="CENTER"> and carry no _Toc anchor in the body
    if (p.get("align") or "").strip().lower() == "center":
        return True
    if "center" in (p.get("style") or "").lower():
        return True
    for a in p.find_all("a", attrs={"name": True}):
        name = a["name"]
        if name in toc_labels or name.startswith("_Toc"):
            return True
    return False


# Some 2007-2009 pages are written as XHTML where many paragraphs are self-closed and EMPTY
# (<p align="CENTER" />) and the words follow outside the tag, up to the next paragraph mark.
# Real example, 38-1 journal of 2007-06-05 (the heading of Bill 1 and the minister's first paragraph):
#     <p align="CENTER" /><a name="_Toc168894497">Projet de loi n</a></font><font>°</font><font> 1<p /></font>
#     <p align="JUSTIFY" /><b>M. Couillard:</b> Merci, M. le Président. ... du projet de loi n</font><font>°</font><font> 1, d'abord ...<p />
# Reading only the inside of <p> tags drops those words (25% of that page, including every bill
# heading). On such pages the paragraphs are rebuilt from the marks themselves: each <p ...>,
# <p ... /> or </p> starts a new paragraph, which takes every word up to the next mark, keeps the
# align/style of the tag that opened it and the anchors inside it. Words are joined with one space,
# the same way the parser reads a normal <p>. Pages where every word already sits inside a <p>
# are returned unchanged, so this cannot alter any page that was read correctly before.
_SELF_CLOSED_P = re.compile(r"<p\b[^>]*/\s*>", re.I)
_CONTENU_SPAN = re.compile(r"(<contenu\b[^>]*>)(.*?)(</contenu\s*>)", re.I | re.S)
_BREAK_TAGS = {"p", "center", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "td", "li", "ul", "ol"}
_SKIP_TAGS = ["script", "style", "tabledesmatieres"]


def words_outside_p(html):
    """(words inside <contenu>, words the <p>-based reading misses). Used for the fix and its check."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("contenu")
    if root is None:
        return 0, 0
    total = outside = 0
    for s in root.find_all(string=True):
        if s.find_parent(_SKIP_TAGS) is not None:
            continue
        k = len(str(s).split())
        total += k
        if s.find_parent("p") is None:
            outside += k
    return total, outside


def repair_selfclosed_paragraphs(html):
    """Returns (html, changed). See the comment above."""
    from html import escape
    from html.parser import HTMLParser
    m = _CONTENU_SPAN.search(html)
    if not m or not _SELF_CLOSED_P.search(m.group(2)) or words_outside_p(html)[1] == 0:
        return html, False

    paras = []

    class _Flat(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.skip = 0
            self.center = 0
            self.cur = None
            self._open({})

        def _open(self, attrs):
            self.cur = {"attrs": {k: v for k, v in attrs.items() if k in ("align", "style") and v},
                        "anchors": [], "words": [], "center": self.center > 0}

        def _flush(self):
            if self.cur and (self.cur["words"] or self.cur["anchors"]):
                paras.append(self.cur)
            self.cur = None

        def _mark(self, attrs):
            self._flush()
            self._open(attrs)

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag in _SKIP_TAGS:
                self.skip += 1
                return
            if tag == "center":
                self.center += 1
            if tag in _BREAK_TAGS:
                self._mark(a if tag == "p" else {})
            elif tag == "a" and a.get("name") and not self.skip:
                self.cur["anchors"].append(a["name"])

        def handle_startendtag(self, tag, attrs):
            if tag in _BREAK_TAGS:
                self._mark(dict(attrs) if tag == "p" else {})
            elif tag == "a" and dict(attrs).get("name") and not self.skip:
                self.cur["anchors"].append(dict(attrs)["name"])

        def handle_endtag(self, tag):
            if tag in _SKIP_TAGS:
                self.skip = max(0, self.skip - 1)
                return
            if tag in _BREAK_TAGS:
                if tag == "center":
                    self.center = max(0, self.center - 1)
                self._mark({})

        def handle_data(self, data):
            if not self.skip:
                w = data.strip()
                if w:
                    self.cur["words"].append(w)

    f = _Flat()
    f.feed(m.group(2))
    f.close()
    f._flush()
    out = []
    for p in paras:
        attrs = "".join(f' {k}="{escape(v)}"' for k, v in p["attrs"].items())
        body = "".join(f'<a name="{escape(n)}"></a>' for n in p["anchors"]) + escape(" ".join(p["words"]))
        tag = f"<p{attrs}>{body}</p>"
        out.append(f"<center>{tag}</center>" if p["center"] else tag)
    return html[:m.start(2)] + "\n".join(out) + html[m.end(2):], True


def parse_page(html, old_format=False):
    """Returns (segments, blocks).
    segments: {bill_number: [{"text", "method", "stage"}]} in page order.
    blocks:   every paragraph in order as {"text", "heading", "bill", "section"},
              used by the title-similarity fallback."""
    html, _ = repair_selfclosed_paragraphs(html)
    soup = BeautifulSoup(html, "html.parser")   # nothing is removed from the tree
    toc_labels = _read_toc_labels(soup)
    root = soup.find("contenu") or soup.body or soup
    # PATCHED_OLDFORMAT_2026_10_05: the stricter reading is used only for 1985-1994 bills on a page with
    # neither "Affaires courantes" nor "Affaires du jour" as a heading
    strict = bool(old_format) and not any(
        _OLD_STRUCT.match(_norm(q.get_text(" ", strip=True))) for q in root.find_all("p") if _is_heading(q, toc_labels))
    study_bill = None
    # PATCHED_OLDFORMAT2_2026_10_05: a heading printed over several lines is read as one heading
    hrun, hprev, last_heading, cont = "", (None, None, None), False, False
    current, method, stage, section = None, None, None, ""
    pending = None      # (bill, block index): a bill heading seen inside a section the parser skips
    segments, blocks = {}, []
    for p in root.find_all("p"):
        if p.find("tabledesmatieres") is not None or p.find_parent("tabledesmatieres") is not None:
            continue
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        if len(text) < 3:
            continue
        n = _norm(text)
        structural = _is_heading(p, toc_labels)
        bill_line = (len(text) <= 250 and bool(_BILL_LINE_RAW.match(text))
                     and not text.rstrip().endswith((",", ";", ".")))
        if structural or bill_line:
            blocks.append({"text": text, "heading": True, "bill": current, "section": section})
            cont = strict and last_heading and text[:1].islower()
            if cont:
                hrun = hrun + " " + n
            else:
                hrun, hprev = n, (current, method, stage)
            last_heading = True
            if structural and _TOP_RE.match(n):
                section, current, method, stage, pending = n, None, None, None, None
                continue
            nj = _join_number(n)
            m = _BILL_HEAD_TXT.search(nj)
            if m and len(text) <= 250 and not section.startswith(_NO_DEBATE_SECTIONS):
                current, method = int(m.group(1)), ("heading" if structural else "heading_line")
                stage = next((s for s in STAGE_HEADS if s in n), None)
                pending = None
            elif m and len(text) <= 250 and nj.startswith("projet de loi"):
                pending = (int(m.group(1)), len(blocks))
            elif (current is None and pending is not None and n.startswith(_DEBATE_STAGE_HEADS)
                  and len(blocks) - pending[1] <= 4):
                current, method = pending[0], "heading_then_stage"
                stage = next((s for s in STAGE_HEADS if n.startswith(s)), None)
                section, pending = "affaires du jour (implied: bill heading followed by a debate stage)", None
            elif (strict and cont and current is None and hprev[0] is not None and not _TOP_RE.match(hrun)
                  and _old_keeps(hrun, study_bill == hprev[0])):
                current, method, stage = hprev    # the rest of a heading printed over several lines
            elif current is not None and strict and not _old_keeps(hrun, study_bill == current):
                current, method, stage = None, None, None    # another item begins (older pages)
            elif current is not None:
                stage = next((s for s in STAGE_HEADS if n.startswith(s)), stage)
                if strict:
                    study_bill = _old_study(n, current, study_bill)
            continue
        last_heading = False
        if current is None and not section.startswith(_NO_DEBATE_SECTIONS):
            head = n[:400]
            # A paragraph in quotation marks is a motion being read out (a closure motion lists
            # every stage of the bill it covers); only an anchor that starts the paragraph counts
            # there ("Que le principe du projet de loi n 898 soit adopte").
            quoted = text.lstrip()[:1] in "\u00ab\"\u201c"
            for st, rx in (FR_ANCHORS + _OLD_ANCHORS if strict and _CHAIR.match(n) else FR_ANCHORS):
                if quoted and not rx.pattern.startswith("^"):
                    continue
                m = rx.search(head)
                if m:
                    current, method, stage = int(m.group("num")), "text_anchor", st
                    break
        elif current is not None and _CHAIR.match(n):
            head = n[:400]
            for st, rx in (FR_ANCHORS + _OLD_ANCHORS if strict else FR_ANCHORS):
                m = rx.search(head) if st in _SWITCH_STAGES else None
                if m and int(m.group("num")) != current:
                    current, method, stage = int(m.group("num")), "chair_anchor", st
                    break
        if strict:
            m = _OLD_CALL.match(n[:400])
            if m and int(m.group("num")) != current:
                current, method = int(m.group("num")), "chair_anchor"
                stage = _old_stage(n[:400], current)
        blocks.append({"text": text, "heading": False, "bill": current, "section": section})
        if current is not None:
            segments.setdefault(current, []).append({"text": text, "method": method, "stage": stage})
    return segments, blocks


def page_blocks(html):
    """Compatibility wrapper for the tests: one block per paragraph."""
    return [{"text": b["text"], "heading": b["heading"], "_bill": b["bill"]} for b in parse_page(html)[1]]


def label_blocks(blocks):
    return [(b.get("_bill"), "heading" if b.get("_bill") is not None else None, None) for b in blocks]


def title_fallback(blocks, target, title):
    """Last resort when the page has no heading or anchor for the target bill:
    pick the stretch of unassigned debate paragraphs whose words best cover the
    bill title, only if it clearly beats every other stretch and names no other bill."""
    t_toks = set(content_tokens(title, "fr"))
    if not t_toks:
        return None, 0.0
    runs, cur = [], []
    for i, b in enumerate(blocks):
        # only where bills are debated: a maiden speech or a member's statement can share
        # many words with a bill title (37-1 Bill 56 on 2004-10-19 picked a new member's speech)
        free = (not b["heading"]) and b["bill"] is None and b["section"].startswith(_FALLBACK_SECTIONS)
        if free:
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    scored = []
    for run in runs:
        text = " ".join(blocks[i]["text"] for i in run)
        others = {int(x) for x in _BILL_HEAD_TXT.findall(_norm(text))}
        if others - {target}:
            continue
        scored.append((len(t_toks & set(content_tokens(text, "fr"))) / len(t_toks), run))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return None, 0.0
    best, second = scored[0][0], (scored[1][0] if len(scored) > 1 else 0.0)
    if best >= 0.6 and best - second >= 0.15:
        return scored[0][1], best
    return None, best


def cmd_probe():
    """Run the parser on real cached pages (oldest, newest, and the Bill 116 page) and show
    what it finds, before touching anything. Takes a few seconds."""
    if BeautifulSoup is None:
        sys.exit("pip install beautifulsoup4")
    debates, _ = expected_debates()
    by_page = {}
    for d in debates:
        by_page.setdefault(cache_path(d["url"]), []).append(d["bill_number"])
    pages = sorted(p for p in by_page if os.path.exists(p))
    if not pages:
        sys.exit("No cached pages. Run fetch first.")
    picks = [pages[0], pages[len(pages) // 2], pages[-1]]
    picks += [p for p in pages if "19951204" in p][:1]
    ok = 0
    for p in dict.fromkeys(picks):
        with open(p, encoding="utf-8", errors="ignore") as f:
            segs, blocks = parse_page(f.read())
        wanted = sorted(set(by_page[p]))
        found = {b: len(segs.get(b, [])) for b in wanted}
        ok += all(found.values())
        print(f"{os.path.basename(p)}: {len(blocks)} paragraphs read, bills on page {sorted(segs)}")
        for b in wanted:
            first = segs[b][0]["text"][:90] if segs.get(b) else "NOT FOUND"
            print(f"    listed bill {b}: {found[b]} paragraphs | {first}")
    print(f"\n{ok} of {len(dict.fromkeys(picks))} probe pages found every listed bill.")


def cmd_segment():
    if BeautifulSoup is None:
        sys.exit("pip install beautifulsoup4")
    debates, no_urls = expected_debates()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SEG_DIR, exist_ok=True)
    index, missing, c = [], [], Counter()
    cache = {}
    pages_parsed = pages_with_bills = 0
    for i, d in enumerate(debates, 1):
        p = cache_path(d["url"])
        if not os.path.exists(p):
            missing.append({**d, "reason": "page not fetched"})
            c["not_fetched"] += 1
            continue
        if p not in cache:
            with open(p, encoding="utf-8", errors="ignore") as f:
                cache[p] = parse_page(f.read(), old_format=_is_old_session(d))
            pages_parsed += 1
            pages_with_bills += bool(cache[p][0])
            if pages_parsed == 25 and pages_with_bills == 0:
                sys.exit("STOPPED: 25 pages parsed and no bill found on any of them. The page structure "
                         "differs from what the parser expects. Run: python3 scripts/v3/quebec_rebuild.py probe")
        segs, blocks = cache[p]
        paras = segs.get(d["bill_number"], [])
        if not paras:
            # The title-matching fallback is off. Every section it produced that was read by hand
            # was about something else: a new member's maiden speech (37-1 Bill 56, 2004-10-19),
            # congratulations to the new Speaker (38-1 Bill 1, 2007-05-15), the budget debate
            # (42-1 Bill 52, 2020-03-10) and the Assembly's own estimates (42-1 Bill 7, 2019-05-07).
            # A section now needs a heading or procedural line that names its bill; the best title
            # overlap is still recorded so a missing day can be looked at.
            _, score = title_fallback(blocks, d["bill_number"], d["title"])
            missing.append({**d, "reason": f"no heading or procedural line names the bill "
                                           f"(best title overlap {score:.2f}; title fallback off)",
                            "bills_found_on_page": sorted(segs)})
            c["missing"] += 1
            continue
        text = "\n\n".join(x["text"] for x in paras)
        path = os.path.join(SEG_DIR, f"{d['bill_session']}_bill{d['bill_number']}_{d['date']}_{d['page_id']}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        c["written"] += 1
        index.append({**d, "file": os.path.relpath(path, QC), "bill_key": f"{d['bill_session']}-Bill{d['bill_number']}",
                      "n_paragraphs": len(paras), "methods": dict(Counter(x["method"].split(":")[0] for x in paras)),
                      "stages": dict(Counter(x["stage"] for x in paras if x.get("stage")))})
        if i % 200 == 0:
            print(f"  {i}/{len(debates)} debates, {c['written']} written", flush=True)
    save_json(index, INDEX, indent=1)
    save_json(missing, os.path.join(OUT, "segments_missing.json"), indent=1)
    with open(os.path.join(OUT, "health_bills_without_assembly_urls.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["session", "bill_number", "title", "source"])
        for r in no_urls:
            w.writerow([r.get("session"), r.get("bill_number"), r.get("title"), r.get("source")])
    print(f"Listed debates: {len(debates)}. Written: {c['written']}. Missing: {c['missing']}. "
          f"Not fetched: {c['not_fetched']}. Pages parsed: {pages_parsed}, with at least one bill: {pages_with_bills}.")
    print(f"Health bills with no Assembly URLs (not covered by this rebuild): {len(no_urls)}")


def cmd_verify():
    index = load_json(INDEX) or sys.exit("Run segment first.")
    debates, _ = expected_debates()
    rows, c = [], Counter()
    for e in index:
        path = os.path.join(QC, e["file"])
        with open(path, encoding="utf-8") as f:
            text = f.read()
        paras = [p for p in text.split("\n\n") if p.strip()]
        mentions = bool(fr_bill_re(e["bill_number"]).search(text) or en_bill_re(e["bill_number"]).search(text))
        first_alpha = re.search(r"[A-Za-z\u00c0-\u00ff]", text)
        mid_sentence = bool(first_alpha and first_alpha.group(0).islower())
        old_file = os.path.join(OLD_SEG, f"{e['date']}_bill{e['bill_number']}.txt")
        en_paras = sum(1 for p in paras if lang_heuristic(p)[0] == "en")
        c["mentions" if mentions else "no_mention"] += 1
        c["mid_sentence_start"] += mid_sentence
        c["old_file_existed" if os.path.exists(old_file) else "old_file_missing"] += 1
        rows.append({
            "bill_session": e["bill_session"], "bill_number": e["bill_number"], "title": e["title"],
            "debate_date": f"{e['date'][:4]}-{e['date'][4:6]}-{e['date'][6:]}", "sitting_session": e["sitting_session"],
            "stages": e["stages"], "n_paragraphs": e["n_paragraphs"], "english_paragraphs": en_paras,
            "methods": e["methods"], "check1_mentions_bill": "Y" if mentions else "N",
            # PATCHED_VERIFY7_2026_10_03: 1985-1994 sections come from the Journal scan, not a cheminement
            "check2_listed_in_cheminement": ("Y" if e.get("source") != "bibliotheque_pre1994"
                                             else "N: found by the 1985-1994 Journal scan"), "starts_mid_sentence": "Y" if mid_sentence else "N",
            "old_file_existed": "Y" if os.path.exists(old_file) else "N",
            "journal_url": e["url"], "bill_url": e["bill_url"], "github_text": github_url(path),
            "excerpt": paras[0][:220] if paras else ""})
    with open(TABLE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bill_number"])
        w.writeheader()
        w.writerows(rows)
    print(f"Segments: {len(rows)} for {len(debates)} listed debates "
          f"(coverage {100.0 * len(rows) / max(len(debates), 1):.1f}%)")
    print(f"CHECK 1 text names its own bill: {c['mentions']} yes, {c['no_mention']} no")
    n_scan = sum(1 for r in rows if r["check2_listed_in_cheminement"] != "Y")
    print(f"CHECK 2 every segment comes from a debate listed in the bill's cheminement: {len(rows) - n_scan} of {len(rows)} "
          f"by construction; the other {n_scan} are 1985-1994 days found by the Journal scan (quebec_pre1994.py)")
    print(f"Segments starting mid-sentence: {c['mid_sentence_start']} (should be 0)")
    print(f"Debates the old pipeline had no file for: {c['old_file_missing']}")
    print(f"Running table: {TABLE}")


if __name__ == "__main__":
    cmds = {"fetch": cmd_fetch, "probe": cmd_probe, "segment": cmd_segment, "verify": cmd_verify,
            "all": lambda: (cmd_fetch(), cmd_segment(), cmd_verify())}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit("usage: quebec_rebuild.py " + "|".join(cmds))
    cmds[sys.argv[1]]()
