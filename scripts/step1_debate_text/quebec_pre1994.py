#!/usr/bin/env python3
"""
quebec_pre1994.py

Quebec health bills of 1985 to 1994 (legislature 33, sessions 1 and 2; legislature 34, sessions 1 to 3).

Why they had no debate text in the rebuilt data:
  1. Their records in quebec_health_bills_combined.json come from the Assembly library's bill files
     (source "bibliotheque_pre1994") and carry a placeholder number, 198 or 199: the first three digits
     of the years in the file name. "34-1_1989-1992_120-F.pdf" was read as Bill 198; it is Bill 120.
     With 198 or 199 for every bill, the 117 records collapsed to 5 keys and nothing could be matched.
  2. Bills before 1994 have no bill page with a "cheminement" on the Assembly site, so the rebuild never
     learned which Journal des debats pages to read. The sitting pages are online in the same format as
     later years, and each session's page lists them month by month.

Steps (each one can be run again; saved pages are never downloaded twice):
  numbers   reads each record's real number from its library file name and checks it two other ways:
            the number the vote-outcomes file gives the same record (matched by its text), and the
            number printed in the record's text where the text is the bill's first page. A record is
            renumbered only when no check disagrees. A reprint file (_Re) is merged into its bill.
  sittings  lists every sitting of sessions 33-1 to 34-3 from the session pages (one request per month)
            and checks that seven sittings known from elsewhere are in the lists
  fetch     downloads the sitting pages not saved yet, into the same Journal cache as later years
  scan      reads every page with quebec_rebuild.py's own parser. A bill-day is a page where the bill has
            its own numbered heading or a procedural line naming it, in its own session. Checks: the
            title printed on the page is the same bill on every day found (a number used again for a
            different bill shows up as a second title); the final-passage day in the vote-outcomes file
            is among the days found; the printed date of each page matches its listing; the sitting
            numbers of each session have no gaps.
  apply     writes the days found into the bill records as their Assembly debates, so that
            quebec_rebuild.py segment cuts them exactly like later years (nothing else is changed)
  all       numbers, sittings, fetch, scan, apply

Writes:
  data/canada/quebec_bills/quebec_health_bills_combined.json   (numbers fixed, debates added; a copy of the
                                                                file from before is kept next to it)
  data/canada/quebec_assembly/v3/pre1994/sitting_days.json, bill_days_found.json, numbers_check.csv
  outputs/audit/quebec_pre1994_rebuild.txt                     (the report)
  outputs/audit/quebec_pre1994_bills.csv                       (one row per bill)
Run from the project folder:  python3 scripts/step1_debate_text/quebec_pre1994.py all
"""
import csv
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from html import unescape
from urllib.parse import urljoin, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import quebec_rebuild as Q      # noqa: E402  (same paths, cache, parser and settings as the rebuild)

ROOT = HERE.parent.parent
OUT = Path(Q.OUT) / "pre1994"
HEALTH = Path(Q.HEALTH)
PRE_OUTCOMES = ROOT / "data" / "canada" / "quebec_bills" / "quebec_pre1994_vote_outcomes.json"
REPORT = ROOT / "outputs" / "audit" / "quebec_pre1994_rebuild.txt"
BILLS_CSV = ROOT / "outputs" / "audit" / "quebec_pre1994_bills.csv"
BASE = os.environ.get("ASSNAT_BASE", "https://www.assnat.qc.ca").rstrip("/")
SESSIONS = ["33-1", "33-2", "34-1", "34-2", "34-3"]
SOURCE = "bibliotheque_pre1994"
FOUND_BY = "journal_scan_1985_1994"
# Sittings known from outside the month lists (web search results and the earlier scan), used to check them.
KNOWN = [("33-1", "19851216", "122661"), ("33-2", "19880607", "123125"), ("33-2", "19881122", "123183"),
         ("33-2", "19881220", "123223"), ("34-1", "19900622", "63259"), ("34-1", "19910619", "63423"),
         ("34-1", "19911128", "63471"), ("34-1", "19920310", "63497"), ("34-1", "19920318", "63505"),
         ("34-2", "19930607", "63721"), ("34-3", "19940329", "63817"), ("34-3", "19940606", "63869")]
DAY = re.compile(r"assemblee-nationale/(\d{2}-\d)/journal-debats/(\d{8})/(\d+)\.html")
FILE_RE = re.compile(r"^(?P<s>\d{2}-\d)_(?P<span>\d{4}(?:-\d{4})?)_(?P<num>\d{1,4})(?P<re>_Re)?"
                     r"(?:\((?P<year>\d{4})\))?-[FA]\.pdf$", re.I)
PREV_SESSION = {"33-2": "33-1", "34-2": "34-1", "34-3": "34-2"}
NUM_RE = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[°ºo]\.?\s*|num[eé]ro\s+)?(\d+)\b")
MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre",
          "novembre", "decembre"]
# a month-list option reads exactly "mars 1992" (perhaps with a count after it); a session option that carries
# dates ("33e legislature, 1re session (16 decembre 1985 - 8 mars 1988)") is NOT a month
MONTH_OPT = re.compile(r"^(" + "|".join(MONTHS) + r")\s+(\d{4})(?:\s*\(\d+\))?$")
PRINTED_DATE = re.compile(r"\b(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})(?:er)?\s+("
                          + "|".join(MONTHS) + r")\s+(\d{4})\b")
VOL_NO = re.compile(r"\bvol\.?\s*(\d+)\s*,?\s*n\s*[°ºo]?\.?\s*(\d+)\b")
# the page's own header: "Le mardi 5 juin 2007 - Vol. 40 N 15" (found by the volume right after the date, since
# speeches and the site's menus carry other dates)
HEADER = re.compile(PRINTED_DATE.pattern + r"\s*[-\u2013\u2014]?\s*" + VOL_NO.pattern[2:])
MIN_WORDS = 40       # a page counts as a bill-day only with a debate stage or at least this many words
# health words, for information only (the health list itself is not changed here)
HEALTH_WORDS = re.compile(r"sante|medic|medec|hopit|hospital|soins|maladi|pharmac|infirmi|tabac|drogue|psychiatr|"
                          r"readaptation|handicap|maternit|dentist|optom|ambulan|vaccin|toxicoman|alcool|"
                          r"services sociaux|sages-femmes|sage-femme|mental|aliment|eau potable|pesticide")
LINES = []
# quebec_rebuild.py with patch_quebec_oldformat.py reads 1985-1987 pages (no section headings) more strictly
import inspect  # noqa: E402
OLD_FORMAT = "old_format" in inspect.signature(Q.parse_page).parameters


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def norm(t):
    return re.sub(r"\s+", " ", Q.strip_accents(str(t or "")).lower()).strip()


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(obj, p):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def canon(s, date, pid):
    return f"{BASE}/fr/travaux-parlementaires/assemblee-nationale/{s}/journal-debats/{date}/{pid}.html"


def write_report():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")


def outcomes():
    po = load(PRE_OUTCOMES, {}) or {}
    items = po.items() if isinstance(po, dict) else enumerate(po)
    out = {}
    for k, v in items:
        if not isinstance(v, dict):
            continue
        s, n = str(v.get("session") or ""), str(v.get("bill_number") or "").strip()
        if s and n.isdigit():
            out[f"{s}-Bill{int(n)}"] = v
    return out


# ------------------------------------------------------------------------------------------- numbers

def parse_file(fn):
    m = FILE_RE.match(str(fn or "").strip())
    if not m:
        return None
    return {"session": m.group("s"), "number": int(m.group("num")), "reprint": bool(m.group("re")),
            "year": int(m.group("year")) if m.group("year") else None}


def number_in_text(t):
    """The bill number printed in the record's text when the text is the bill's first page:
    '... LEGISLATURE Projet de loi 120 Loi sur les services de sante ...' or '...loi 34 Loi modifiant ...'."""
    m = re.search(r"\b(?:projet\s+de\s+)?loi\s+(\d{1,3})\s+(?:\(prive\)\s+)?lo[it]\b", norm(t))
    return int(m.group(1)) if m else None


def cmd_numbers():
    health = load(HEALTH)
    if not isinstance(health, list):
        sys.exit(f"{HEALTH} is missing or not a list. Nothing changed.")
    po = outcomes()
    by_text = defaultdict(set)
    for k, v in po.items():
        t = norm(v.get("title"))
        if t:
            by_text[(str(v.get("session")), t)].add(int(v["bill_number"]))
    rows, c = [], Counter()
    pre = [r for r in health if r.get("source") == SOURCE]
    for rec in pre:
        fn = rec.get("filename") or (rec.get("library_files") or [""])[0]
        f = parse_file(fn)
        old = str(rec.get("placeholder_number") or rec.get("bill_number") or "")
        row = {"session": rec.get("session"), "file": fn, "old_number": old, "number_from_file": "",
               "number_in_outcomes_file": "", "number_in_text": "", "decision": ""}
        if f is None:
            row["decision"] = "kept: file name not readable"
            c["file name not readable"] += 1
            rows.append(row)
            continue
        row["number_from_file"] = f["number"]
        ob = by_text.get((str(rec.get("session")), norm(rec.get("library_snippet") or rec.get("title"))), set())
        row["number_in_outcomes_file"] = ",".join(map(str, sorted(ob)))
        nt = number_in_text(rec.get("library_snippet") or rec.get("title"))
        row["number_in_text"] = nt or ""
        problems = []
        if f["session"] != str(rec.get("session")):
            problems.append(f"file session {f['session']} differs from record session {rec.get('session')}")
        if ob and f["number"] not in ob:
            problems.append("the vote-outcomes file gives another number")
        if nt is not None and nt != f["number"]:
            problems.append("the number printed in the text differs")
        c["outcomes file: same text, same number" if ob and f["number"] in ob else
          ("outcomes file: same text, another number" if ob else "outcomes file: text not there")] += 1
        c["outcomes file has this session and number" if f"{f['session']}-Bill{f['number']}" in po
          else "outcomes file lacks this session and number"] += 1
        if nt is not None:
            c["printed number agrees" if nt == f["number"] else "printed number disagrees"] += 1
        if problems:
            row["decision"] = "kept: " + "; ".join(problems)
            c["kept (a check disagrees)"] += 1
            rows.append(row)
            continue
        if "placeholder_number" not in rec:
            rec["placeholder_number"] = old
        rec["bill_number"] = str(f["number"])
        rec["number_source"] = "library file name; checked against the vote-outcomes file and the printed number"
        rec["library_year"] = f["year"]
        rec["library_reprint"] = f["reprint"]
        rec.setdefault("library_files", [fn])
        rec.setdefault("library_snippet", rec.get("title", ""))
        row["decision"] = "renumbered" if old != str(f["number"]) else "number already right"
        c[row["decision"]] += 1
        rows.append(row)
    # a reprint (_Re) is the same bill: merge it into the bill's record
    groups = defaultdict(list)
    for rec in pre:
        if rec.get("number_source"):
            groups[(rec["session"], int(rec["bill_number"]))].append(rec)
    drop, twice, merged = [], [], []
    for (s, n), recs in sorted(groups.items()):
        if len(recs) < 2:
            continue
        originals = [r for r in recs if not r.get("library_reprint")]
        reprints = [r for r in recs if r.get("library_reprint")]
        oy = originals[0].get("library_year") if len(originals) == 1 else "several"
        # a reprint is the same bill only when nothing says otherwise: one original, and the reprint's year is not
        # a different year given to the original ("075(1986)" + "075_Re(1987)" stay apart)
        if len(originals) == 1 and reprints and all(oy is None or r.get("library_year") in (None, oy) for r in reprints):
            keep = originals[0]
            for r in reprints:
                keep["library_files"] = sorted(set(keep.get("library_files", [])) | set(r.get("library_files", [])))
                keep.setdefault("library_snippets_merged", []).append(r.get("library_snippet", ""))
                drop.append(id(r))
                merged.append((s, n, keep["library_files"]))
            c["reprints merged into their bill"] += len(reprints)
        else:
            years = sorted({r.get("library_year") for r in recs if r.get("library_year")})
            for r in recs:
                r["same_number_in_session"] = True
            twice.append((s, n, years, [r.get("library_files", [""])[0] for r in recs]))
    if drop:
        health[:] = [r for r in health if id(r) not in drop]
    keys = Counter(f"{r['session']}-Bill{r['bill_number']}" for r in health
                   if r.get("source") == SOURCE and r.get("number_source"))
    backup = HEALTH.with_name(HEALTH.stem + "_before_pre1994_numbers.json")
    if not backup.exists():
        shutil.copy2(HEALTH, backup)
    save(health, HEALTH)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "numbers_check.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["session"])
        w.writeheader()
        w.writerows(rows)
    say("=" * 100)
    say("1. Bill numbers of the 1985-1994 records")
    say("=" * 100)
    say(f"records from the library list: {len(pre)}")
    for k in ("renumbered", "number already right", "kept (a check disagrees)", "file name not readable",
              "outcomes file: same text, same number", "outcomes file: same text, another number",
              "outcomes file: text not there", "outcomes file has this session and number",
              "outcomes file lacks this session and number",
              "printed number agrees", "printed number disagrees", "reprints merged into their bill"):
        say(f"   {k:<40} {c.get(k, 0)}")
    say(f"bills now (session + number): {len(keys)}; by session {dict(sorted(Counter(k.split('-Bill')[0] for k in keys).items()))}")
    say(f"CHECK the bills now match the outcomes file's keys: {len(set(keys) & set(po))} of {len(keys)} are there; "
        f"outcomes keys with no bill: {sorted(set(po) - set(keys))[:10]}")
    for r in rows:
        if r["decision"].startswith("kept"):
            say(f"   KEPT AS IS  {r['session']} {r['file']}: {r['decision']}")
    for s, n, files in merged:
        say(f"   reprint merged: {s} Bill {n}: {files}")
    for s, n, years, files in twice:
        say(f"   same number twice in one session: {s} Bill {n} (library years {years}; files {files}); "
            "the scan keeps them apart by the title printed on the Journal pages")
    say(f"backup of the list before this step: {backup.name}; per-record checks: {OUT / 'numbers_check.csv'}")


# ------------------------------------------------------------------------------------------- sittings

def form_state(html, page_url):
    soup = Q.BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if form is None:
        return None
    st = {"action": urljoin(page_url, form.get("action") or page_url), "fields": {}, "selects": {}, "buttons": []}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        t = (inp.get("type") or "text").lower()
        if t in ("submit", "button", "image", "reset"):
            st["buttons"].append((name, inp.get("value") or ""))
            continue
        if t in ("checkbox", "radio") and not inp.has_attr("checked"):
            continue
        st["fields"][name] = inp.get("value") or ""
    for ta in form.find_all("textarea"):
        if ta.get("name"):
            st["fields"][ta["name"]] = ta.get_text()
    for sel in form.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        opts = []
        for o in sel.find_all("option"):
            v = o.get("value") if o.has_attr("value") else o.get_text(" ", strip=True)
            opts.append((v, o.get_text(" ", strip=True), o.has_attr("selected")))
        cur = next((v for v, _, sel_ in opts if sel_), opts[0][0] if opts else "")
        st["selects"][name] = {"options": opts, "current": cur, "onchange": sel.get("onchange") or "",
                               "id": sel.get("id") or ""}
        st["fields"][name] = cur
    for b in form.find_all("button"):
        if b.get("name"):
            st["buttons"].append((b["name"], b.get("value") or ""))
    return st


def option_month(value, text):
    """'199111' for a month-list option reading 'novembre 1991' (or valued 1991-11, 11/1991, 199111).
    Only an option that is a month and nothing else counts: session options carry dates too."""
    m = MONTH_OPT.match(norm(text))
    if m:
        return f"{m.group(2)}{MONTHS.index(m.group(1)) + 1:02d}"
    v = str(value or "").strip()
    if norm(text) and not re.fullmatch(r"[\d/ -]+", norm(text)):
        return None
    for rx, f in ((r"^(\d{4})-?(\d{2})$", lambda m: m.group(1) + m.group(2)),
                  (r"^(\d{1,2})[/-](\d{4})$", lambda m: f"{m.group(2)}{int(m.group(1)):02d}")):
        m = re.match(rx, v)
        if m and 1 <= int(f(m)[4:]) <= 12:
            return f(m)
    return None


def option_session(text):
    m = re.search(r"(\d+)\s*e\s+legislature\D{1,10}(\d+)\s*(?:re|e|er)\s+session", norm(text))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def month_list(st):
    """(select name, [(value, yyyymm)]) of the page's month list, or None. A list of sessions is never taken."""
    best = None
    for name, sel in st["selects"].items():
        opts = [(v, t) for v, t, _ in sel["options"] if str(v).strip()]
        if sum(1 for _, t in opts if option_session(t)) >= 2:
            continue
        months = [(v, option_month(v, t)) for v, t in opts]
        months = [(v, ym) for v, ym in months if ym]
        if months and len(months) >= 0.8 * len(opts) and (best is None or len(months) > len(best[1])):
            best = (name, months)
    return best


def harvest(html, base, s):
    """{(date, page id)} of the sitting pages of session s linked from a page (a date can have two sittings)."""
    found = set()
    for m in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", html or "", re.I):
        d = DAY.search(urljoin(base, unescape(m.group(1).strip())))
        if d and d.group(1) == s:
            found.add((d.group(2), d.group(3)))
    return found


def common_prefix(a, b):
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def describe_form(st, s):
    say(f"   {s}: what the session page offers (for Claude):")
    if st is None:
        say("      no <form> on the page")
        return
    say(f"      form action {st['action']}; hidden fields {[k for k in st['fields'] if k.startswith('__')]}")
    for name, sel in st["selects"].items():
        say(f"      select {name} (id {sel['id']}) onchange {sel['onchange'][:100]!r}: {len(sel['options'])} options, "
            f"first {[o[:2] for o in sel['options'][:3]]}, current {sel['current']!r}")
    say(f"      buttons {st['buttons'][:6]}")


def id_probe(http, s):
    """Diagnostics only: does the site answer a sitting address with a neighbouring page number?"""
    seeds = [k for k in KNOWN if k[0] == s] or [k for k in KNOWN if k[0][:2] == s[:2]]
    if not seeds:
        return
    ks, d, pid = seeds[0]
    for delta in (2, -2, 1):
        url = canon(ks, d, int(pid) + delta)
        try:
            r = http.get(url, headers=Q.UA, timeout=60)
            hd = HEADER.search(norm(unescape(re.sub(r"<[^>]+>", " ", r.text)))) if r.status_code == 200 else None
            say(f"      address test {url} -> HTTP {r.status_code}; printed date {(hd.group(0)[:60] if hd else 'none')}")
        except Q.requests.RequestException as e:
            say(f"      address test {url} -> {type(e).__name__}")
        time.sleep(Q.SLEEP)


def post(http, st, page_url, name, value, mode, button=None):
    """The page after choosing value in the list name, or None. A redirect is followed by posting again to its
    target (requests would turn it into a GET and return the default page, which looks like an answer)."""
    data = dict(st["fields"])
    data[name] = value
    if mode == "autopostback":
        data["__EVENTTARGET"], data["__EVENTARGUMENT"] = name, ""
    else:
        data["__EVENTTARGET"], data["__EVENTARGUMENT"] = "", ""
        if button:
            data[button[0]] = button[1]
    url = st["action"]
    for attempt in range(3):
        try:
            for hop in range(4):
                r = http.post(url, data=data, headers={**Q.UA, "Referer": page_url}, timeout=60,
                              allow_redirects=False)
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                    nxt = urljoin(url, r.headers["Location"])
                    if urlsplit(nxt)[2:4] == urlsplit(url)[2:4]:
                        url = nxt          # the same page at another address (http/https, host): post again
                        continue
                    # post, then read the page it sends you to (what a browser does)
                    r = http.get(nxt, headers={**Q.UA, "Referer": page_url}, timeout=60)
                break
            time.sleep(Q.SLEEP)
            if r.status_code == 200:
                return r.content.decode("utf-8", errors="ignore")
            return None
        except Q.requests.RequestException:
            time.sleep(8 * (attempt + 1))
    return None


def get(http, url):
    for attempt in range(3):
        try:
            r = http.get(url, headers=Q.UA, timeout=60)
            time.sleep(Q.SLEEP)
            if r.status_code in (200, 404):
                return r
        except Q.requests.RequestException:
            pass
        time.sleep(8 * (attempt + 1))
    return None


def list_session(http, s):
    """({(date, page_id)}, how, status) for session s, read month by month from the session page.
    status: ok (every month answered with that month selected), partial (some did not), failed."""
    page_url = f"{BASE}/fr/travaux-parlementaires/assemblee-nationale/{s}/index.html"
    r = get(http, page_url)
    if r is None or r.status_code != 200:
        say(f"   {s}: the session page did not answer ({page_url})")
        return set(), "session page not reachable", "failed"
    page_url = r.url or page_url
    html = r.content.decode("utf-8", errors="ignore")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"session_{s}.html").write_text(html, encoding="utf-8")
    found = harvest(html, page_url, s)
    st = form_state(html, page_url)
    ml = month_list(st) if st is not None else None
    if ml is None:
        describe_form(st, s)
        id_probe(http, s)
        return found, "no month list on the session page", "failed"
    name, months = ml
    buttons = sorted((b for b in st["buttons"] if not re.search(r"recherch|search", b[0], re.I)),
                     key=lambda b: -common_prefix(b[0], name))
    # The month the page shows by default proves nothing (a request the site ignores shows it too), so it is
    # asked last. A month with no sitting is a real answer ("Aucun contenu n'est accessible pour ce mois"): the
    # 33-1 list starts with March, February and January 1988, when the Assembly did not sit (fixed 2026-10-04).
    default = str(st["selects"][name]["current"])
    order = [x for x in months if str(x[0]) != default] + [x for x in months if str(x[0]) == default]
    mode, answered, empty, unanswered = None, [], [], []
    for v, ym in order:
        got, ok = set(), False
        for m in ([mode] if mode else ["autopostback", "button"]):
            if m == "button" and not buttons:
                continue
            h = post(http, st, page_url, name, v, m, buttons[0] if buttons else None)
            st2 = form_state(h, page_url) if h else None
            sel = st2["selects"].get(name) if st2 else None
            # the answer counts only if the page that came back has this month selected
            if sel is None or str(sel["current"]) != str(v):
                continue
            if mode is None and str(v) == default and len(order) > 1:
                continue            # no other month answered, so this one cannot be trusted either
            got, ok, mode, st = harvest(h, page_url, s), True, m, st2
            break
        if ok:
            answered.append(ym)
            if not any(d.startswith(ym) for d, _ in got):
                empty.append(ym)
        else:
            unanswered.append(ym)
        found |= got
        if mode is None and len(unanswered) >= 3:
            break           # three months and neither way of asking works: stop and describe the page
    if mode is None:
        describe_form(st, s)
        id_probe(http, s)
        return found, "the month list did not answer", "failed"
    status = "ok" if not unanswered else "partial"
    say(f"   {s}: {len(months)} months listed, {len(answered)} answered ({mode}), {len(found)} sittings; "
        f"months answered with no sitting: {empty[:12]}; months NOT answered: {unanswered[:12]}")
    return found, f"month list ({mode})", status


def cmd_sittings():
    if Q.requests is None or Q.BeautifulSoup is None:
        sys.exit("pip install requests beautifulsoup4")
    http = Q.requests.Session()
    say("")
    say("=" * 100)
    say("2. Sittings of sessions 33-1 to 34-3, from the session pages")
    say("=" * 100)
    old = {(x["session"], x["date"], str(x["page_id"])): x for x in load(OUT / "sitting_days.json", []) or []}
    out, how, status = dict(old), {}, {}
    for s in SESSIONS:
        found, h, stt = list_session(http, s)
        how[s] = h
        for d, p in sorted(found):
            out[(s, d, p)] = {"session": s, "date": d, "page_id": p, "url": canon(s, d, p), "listed_by": h}
        have = {(x["date"], str(x["page_id"])) for k, x in out.items() if k[0] == s}
        miss = [k for k in KNOWN if k[0] == s and (k[1], k[2]) not in have]
        if miss and stt == "ok":
            stt = "partial"
        status[s] = {"status": stt, "how": h, "known_missing": miss}
    days = sorted(out.values(), key=lambda x: (x["session"], x["date"], str(x["page_id"])))
    save(days, OUT / "sitting_days.json")
    save(status, OUT / "sessions_status.json")
    have = {(x["session"], x["date"], str(x["page_id"])) for x in days}
    hit = [k for k in KNOWN if k in have]
    say(f"sittings listed: {len(days)}; by session {dict(sorted(Counter(x['session'] for x in days).items()))}")
    say(f"CHECK known sittings found in the lists: {len(hit)} of {len(KNOWN)}"
        + ("" if len(hit) == len(KNOWN) else f"; missing {[k for k in KNOWN if k not in have]}"))
    for s in SESSIONS:
        ds = sorted(x["date"] for x in days if x["session"] == s)
        say(f"   {s}: {len(ds)} sittings, {ds[0] if ds else '-'} to {ds[-1] if ds else '-'}  "
            f"[{status[s]['status'].upper()}] ({how.get(s)})")
    bad = [s for s in SESSIONS if status[s]["status"] != "ok"]
    if bad:
        say(f"SESSIONS NOT FULLY LISTED: {bad}. Their bills get only the days found on the sittings that were listed; "
            "the report marks them. Send this report to Claude.")


# ------------------------------------------------------------------------------------------- fetch

def cmd_fetch():
    if Q.requests is None:
        sys.exit("pip install requests beautifulsoup4")
    days = load(OUT / "sitting_days.json", []) or []
    todo = [x for x in days if not (os.path.exists(Q.cache_path(x["url"])) and os.path.getsize(Q.cache_path(x["url"])) > 2000)]
    say("")
    say(f"Sitting pages: {len(days)}; already saved: {len(days) - len(todo)}; downloading: {len(todo)} "
        f"(about {len(todo) * (Q.SLEEP + 1) / 60:.0f} minutes)")
    http, failed = Q.requests.Session(), []
    for i, x in enumerate(todo, 1):
        p = Q.cache_path(x["url"])
        r = get(http, x["url"])
        if r is not None and r.status_code == 200 and len(r.content) > 2000:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(r.content)
        else:
            failed.append(x["url"])
        if i % 25 == 0 or i == len(todo):
            print(f"   {i}/{len(todo)} downloaded, {len(failed)} failed", flush=True)
    save(failed, OUT / "fetch_failed.json")
    say(f"downloads failed: {len(failed)}" + (f" (listed in {OUT / 'fetch_failed.json'}; run this step again)" if failed else ""))


# ------------------------------------------------------------------------------------------- scan

# the cut used up to Oct 3: it decides whether a mention is a title at all (Oct 4 used the cleaner cut below for
# that too, and on your machine "Loi modifiant diverses lois fiscales et d'autres dispositions legislatives" then had
# too few distinctive words to count, so Bill 2's own title disappeared and the 1987 Bill 2's title won)
_TITLE_TAIL_V1 = re.compile(r",\s+(?:ainsi|que|qu['’]|où|dont|soit|conformément|je|j['’]|nous|il|elle|on|car|mais|parce|"
                            r"lequel|laquelle|qui|M\.|Mme|et\s+(?:que|je|nous|qu['’]))\b"
                            r"|\s+(?:M\.|Mme|Monsieur|Madame|Le\s+Pr[eé]sident|La\s+Pr[eé]sidente|pr[eé]sent[eé]\s+par|"
                            r"Pr[eé]sentation|Adoption)\b", re.I)
# the cleaner cut, for the title that is stored and shown (', est-il adopte' and ' est adopte' removed)
_TITLE_TAIL = re.compile(r",?\s+(?:est|sont)-(?:il|elle|ils|elles)\b|,?\s+(?:est|sont)\s+(?:donc\s+|maintenant\s+)?adopt|,\s+(?:mette|fasse|tienne|procede|procède|entende|siege|siège|poursuive|complete|complète|puisse|soit|ait)\b|,\s+(?:ainsi|que|qu['’]|où|dont|soit|conformément|je|j['’]|nous|il|elle|on|car|mais|parce|"
                         r"lequel|laquelle|qui|M\.|Mme|et\s+(?:que|je|nous|qu['’]))\b"
                         r"|\s+(?:M\.|Mme|Monsieur|Madame|Le\s+Pr[eé]sident|La\s+Pr[eé]sidente|pr[eé]sent[eé]\s+par|"
                         r"Pr[eé]sentation|Adoption)\b", re.I)


def page_title(page_text, n):
    """The bill's title as printed after its number ('projet de loi n 2, Loi modifiant diverses lois fiscales ...'),
    with its accents and capitals. Every mention on the page is read and cut where running speech goes on after the
    title (', ainsi que ...', ', qu'elle en adopte le principe ...'); the most frequent form wins, then the shortest."""
    found = Counter()
    for m in re.finditer(r"projet\s+de\s+loi\s+(?:n\s*[°ºo]\.?\s*|num[eé]ro\s+)?" + str(n) +
                         r"\s*,?\s*(?:intitul[eé]e?\s+)?(loi\b[^.;:!?]{5,250})", page_text, re.I):
        t1 = _TITLE_TAIL_V1.split(m.group(1))[0].strip(" ,")
        if len(toks_list(t1)) >= 2:
            t = _TITLE_TAIL.split(m.group(1))[0].strip(" ,")
            found[t if len(re.findall(r"[a-zà-ÿ]{3,}", t.lower())) >= 3 else t1] += 1
    if not found:
        return ""
    return sorted(found, key=lambda t: (-found[t], len(t)))[0]


_STOPT = {"loi", "modifiant", "concernant", "diverses", "dispositions", "legislatives", "autres"}


def toks_list(t):
    return [w for w in Q.content_tokens(t, "fr") if w not in _STOPT]


def toks(t):
    return set(Q.content_tokens(t, "fr")) - {"loi", "modifiant", "concernant", "diverses", "dispositions",
                                             "legislatives", "autres"}


def title_in_snippet(title, snippet):
    """Share of the title's words found in the library text. The library text often has words glued together
    by the PDF reading ('desanteet' for 'de sante et'), so it is compared with its spaces removed."""
    t = [w for w in re.findall(r"[a-z]{4,}", norm(title)) if w not in ("modifiant", "concernant", "dispositions",
                                                                      "legislatives", "autres", "diverses")]
    flat = re.sub(r"[^a-z]", "", norm(snippet))
    return sum(1 for w in t if w in flat) / len(t) if t else 0.0


def _fuzzy(ta, tb):
    """tokens of one title matched to the other's, tolerating the scan's misreadings ('juridiaires' for 'judiciaires')"""
    import difflib
    out = set()
    for w in ta:
        m = difflib.get_close_matches(w, list(tb), n=1, cutoff=0.8) if len(w) >= 5 else ([w] if w in tb else [])
        out.add(m[0] if m else w)
    return out


def same_bill(a, b):
    # a word hyphenated at a line break ("opto-metrie") is joined before comparing
    a, b = (re.sub(r"(?<=[A-Za-zÀ-ÿ])-\s?(?=[a-zà-ÿ])", "", str(x or "")) for x in (a, b))
    ta, tb = toks(a), toks(b)
    ta = _fuzzy(ta, tb)
    if not ta and not tb:
        return norm(a) == norm(b)
    if not ta or not tb:
        return False
    la, lb = toks_list(a), toks_list(b)
    la = [next(iter(_fuzzy({w}, set(lb)))) for w in la]
    k = min(len(la), len(lb), 6)
    if k >= 3 and la[:k] == lb[:k]:
        return True          # same start: one form just runs on longer
    return len(ta & tb) / len(ta | tb) >= 0.5 or (ta <= tb or tb <= ta) and min(len(ta), len(tb)) >= 3


def cmd_scan():
    if Q.BeautifulSoup is None:
        sys.exit("pip install beautifulsoup4")
    days = load(OUT / "sitting_days.json", []) or []
    health = load(HEALTH, []) or []
    po = outcomes()
    pre = [r for r in health if r.get("source") == SOURCE and r.get("number_source")]
    wanted = defaultdict(list)
    for r in pre:
        wanted[(r["session"], int(r["bill_number"]))].append(r)
    say("")
    say("=" * 100)
    say("3. Reading every sitting page")
    say("=" * 100)
    status = load(OUT / "sessions_status.json", {}) or {}
    hits = defaultdict(list)          # (session, number) -> [day info]
    printed_bad, no_header, vol = [], [], defaultdict(set)
    read = with_bills = missing_pages = 0
    for x in sorted(days, key=lambda x: (x["session"], x["date"], str(x["page_id"]))):
        p = Q.cache_path(x["url"])
        if not os.path.exists(p):
            missing_pages += 1
            continue
        with open(p, encoding="utf-8", errors="ignore") as f:
            html = f.read()
        segs, blocks = Q.parse_page(html, old_format=True) if OLD_FORMAT else Q.parse_page(html)
        read += 1
        with_bills += bool(segs)
        plain = norm(unescape(re.sub(r"<[^>]+>", " ", html)))
        hd = HEADER.search(plain)
        if hd:
            printed = f"{hd.group(3)}{MONTHS.index(hd.group(2)) + 1:02d}{int(hd.group(1)):02d}"
            if printed != x["date"]:
                printed_bad.append((x["session"], x["date"], printed))
            vol[(x["session"], int(hd.group(4)))].add(int(hd.group(5)))
        else:
            i = plain.find(" vol")
            no_header.append((x["session"], x["date"], plain[max(0, i - 90): i + 60] if i >= 0 else plain[:150]))
        whole = " ".join(b["text"] for b in blocks)
        for n, paras in segs.items():
            if (x["session"], n) not in wanted and (PREV_SESSION.get(x["session"]), n) not in wanted:
                continue       # the previous session's bills are kept too: a bill reinstated after prorogation
            text = " ".join(q["text"] for q in paras)
            named = Counter(int(m.group(1)) for m in NUM_RE.finditer(norm(text)))
            other = max(((k, v) for k, v in named.items() if k != n), key=lambda kv: kv[1], default=(None, 0))
            hits[(x["session"], n)].append({
                "own_mentions": named.get(n, 0), "other_bill": other[0], "other_mentions": other[1],
                "date": x["date"], "page_id": x["page_id"], "url": x["url"], "n_paragraphs": len(paras),
                "words": len(text.split()), "title": page_title(whole, n),
                "stages": dict(Counter(q["stage"] for q in paras if q.get("stage"))),
                "methods": dict(Counter(q["method"].split(":")[0] for q in paras)),
                "first_paragraph": paras[0]["text"][:200]})
    say(f"pages read: {read}; with at least one bill: {with_bills}; listed but not saved: {missing_pages}")
    say(f"CHECK printed date = listed date: {read - len(printed_bad) - len(no_header)} of {read} pages agree"
        + (f"; differ: {printed_bad[:8]}" if printed_bad else "")
        + (f"; no date and volume line found on {len(no_header)}" if no_header else ""))
    for s_, d_, snip in no_header[:6]:
        say(f"      no date/volume line: {s_} {d_} | ...{snip}...")
    for (s, v), nums in sorted(vol.items()):
        gaps = sorted(set(range(min(nums), max(nums) + 1)) - nums)
        say(f"CHECK sitting numbers {s} Vol. {v}: N° {min(nums)} to {max(nums)}, {len(nums)} numbers, "
            f"gaps {len(gaps)}" + (f" {gaps[:15]}" if gaps else ""))

    # which days go to which record
    found, c = [], Counter()
    by_key, n_short, n_misprint = {}, 0, 0
    for (s, n), recs in sorted(wanted.items()):
        hs_all = sorted(hits.get((s, n), []), key=lambda h: (h["date"], str(h["page_id"])))
        # a page counts only with a debate stage or some words (not a bill named in a list)
        hs = [h for h in hs_all if h["stages"] or h["words"] >= MIN_WORDS]
        n_short += len(hs_all) - len(hs)
        # a heading misprinted in the Journal (Bill 130 on 1986-12-19 heads the final adoption of Bill 150): the text
        # never names its own bill and names another bill three times or more
        misprint = [h for h in hs if h["n_paragraphs"] > 20 and h["own_mentions"] == 0 and h["other_mentions"] >= 3]
        for h in misprint:
            h["misprint"] = f"names Bill {h['other_bill']} {h['other_mentions']}x and never Bill {n}: the heading is a misprint"
        hs = [h for h in hs if h not in misprint]
        n_misprint += len(misprint)
        reused = len(recs) > 1        # two library records with this number in this session
        match = (lambda a, b: toks_list(a)[:8] == toks_list(b)[:8]) if reused else same_bill
        groups = []
        for h in hs_all:        # titles from every day, the short ones too; days are accepted from hs only
            h["_g"] = None
            if not h["title"]:
                continue
            gi = next((i for i, g in enumerate(groups) if match(g["title"], h["title"])), None)
            if gi is None:
                groups.append({"title": h["title"], "dates": [h["date"]], "forms": Counter([h["title"]])})
                gi = len(groups) - 1
            else:
                groups[gi]["dates"].append(h["date"])
                groups[gi]["forms"][h["title"]] += 1
                groups[gi]["title"] = sorted(groups[gi]["forms"], key=lambda t: (-groups[gi]["forms"][t], t != t.capitalize() and t[:1].islower(), len(t)))[0]
            h["_g"] = gi

        def group_of(h):
            if h["_g"] is not None:
                return h["_g"]
            if not groups:
                return 0
            inside = [i for i, g in enumerate(groups) if g["dates"][0] <= h["date"] <= g["dates"][-1]]
            if len(inside) == 1:
                return inside[0]
            return min(range(len(groups)), key=lambda i: min(abs(int(h["date"]) - int(d)) for d in groups[i]["dates"]))
        for i, rec in enumerate(sorted(recs, key=lambda r: r.get("library_year") or 0)):
            key = f"{s}-Bill{n}"
            vote = (po.get(key) or {}).get("vote_date") or ""
            y = rec.get("library_year")
            foreign_from = None
            if len(groups) <= 1 and not reused and y and groups and int(groups[0]["dates"][0][:4]) > y + 1:
                pick, foreign_from = None, groups[0]["dates"][0]
                why = (f"the only title printed under this number ({groups[0]['title'][:60]}) first appears in "
                       f"{foreign_from[:4]}, two or more years after the library year {y}: it is a later bill with "
                       f"this number, so only the days with no title printed before {foreign_from} are kept")
            elif len(groups) <= 1 and not reused:
                pick, why = (0 if hs else None), ("one title on every day found" if groups else
                                                  ("no title printed on the days found" if hs else "no day found"))
            elif groups and (reused or y):
                order = sorted(range(len(groups)), key=lambda j: (abs(int(groups[j]["dates"][0][:4]) - y) if y else 0,
                                                                  groups[j]["dates"][0]))
                pick, why = order[0], f"{len(groups)} title(s); chosen by the library year {y}"
            elif groups and vote:
                cand = [j for j, g in enumerate(groups) if g["dates"][0] <= vote <= g["dates"][-1] or vote in g["dates"]]
                pick, why = (cand[0], f"{len(groups)} titles; chosen by the final-passage day {vote}") if len(cand) == 1 \
                    else (None, f"{len(groups)} different titles under this number and no way to choose")
            elif groups:
                pick, why = None, f"{len(groups)} different titles under this number and no way to choose"
            else:
                pick, why = None, ("no title printed, and this number has two library records in the session"
                                   if hs else "no day found")
            prev = by_key.get(key)
            if prev is not None and prev["pick"] is not None and pick is not None:
                # the pipeline keys bills by session and number, so a second record with the same key cannot be
                # added without merging it with the first; it is listed instead
                pick, why = None, (why + "; NOT ADDED: " + ("same title as the other record with this number"
                                   if pick == prev["pick"] else "a second bill under key " + key)
                                   + " (the first record kept the days)")
            accepted = [h for h in hs if pick is not None and group_of(h) == pick
                        and not (reused and h["_g"] is None and y and int(h["date"][:4]) != y)]
            if foreign_from:
                accepted = [h for h in hs if h["_g"] is None and h["date"] < foreign_from]
            early = [h for h in accepted if y and int(h["date"][:4]) < y]
            if early:
                accepted = [h for h in accepted if h not in early]
                why += f"; {len(early)} day(s) before the library year {y} left out (another bill with this number)"
            title = groups[pick]["title"] if (groups and pick is not None) else ""
            snip = rec.get("library_snippet") or ""
            if accepted and title and number_in_text(snip) and title_in_snippet(title, snip) < 0.7:
                why += "; NOT ADDED: the library's first page shows another title"
                accepted = []
            stt = (status.get(s) or {}).get("status", "not listed")
            if stt != "ok":
                why += f"; the sittings of {s} were not fully listed ({stt}), so days may be missing"
            by_key.setdefault(key, {"pick": pick if accepted else None})
            rec["_scan"] = {"days": [{k: v for k, v in h.items() if k != "_g"} for h in accepted], "title": title,
                            "why": why, "titles": [g["title"] for g in groups], "all_days": [h["date"] for h in hs_all],
                            "vote_date": vote}
            for h in hs_all:
                found.append({"bill_key": key, "bill_session": s, "bill_number": n,
                              **{k: v for k, v in h.items() if k != "_g"},
                              "library_file": (rec.get("library_files") or [""])[0],
                              "accepted": h in accepted, "why": h.get("misprint") or why})
            c["records with days" if accepted else "records with no day"] += 1
    say(f"bill pages left out as a bill named with no debate (no stage, under {MIN_WORDS} words): {n_short}")
    say(f"bill pages left out as a misprinted heading (the text never names the bill and names another bill 3+ times): {n_misprint}")
    # a bill that was still before the Assembly when a session was prorogued is reinstated in the next session of the
    # same legislature, with the same number (34-1 Bill 413 was adopted in 34-2; 34-2 Bill 152 in 34-3): its days there
    # are added when the title printed on them is this bill's
    NEXT = {"33-1": "33-2", "34-1": "34-2", "34-2": "34-3"}
    n_cont = 0
    for rec in pre:
        sc = rec.get("_scan") or {}
        if not sc.get("days") or not sc.get("title"):
            continue
        s, n = rec["session"], int(rec["bill_number"])
        s2 = NEXT.get(s)
        if not s2:
            continue
        taken = {h["date"] for r2 in pre if r2["session"] == s2 and int(r2["bill_number"]) == n for h in (r2.get("_scan") or {}).get("days", [])}
        hs2 = sorted((h for h in hits.get((s2, n), []) if (h["stages"] or h["words"] >= MIN_WORDS) and h["date"] not in taken
                      and not h.get("misprint")), key=lambda h: (h["date"], str(h["page_id"])))
        if not hs2:
            continue
        # the days of the next session whose printed title is this bill's, and the untitled days between them
        titled = [h for h in hs2 if h["title"] and same_bill(h["title"], sc["title"])]
        other = [h for h in hs2 if h["title"] and not same_bill(h["title"], sc["title"])]
        if not titled:
            continue
        hi = titled[-1]["date"]      # untitled days up to the last titled one (the report stage prints no title)
        cont = [h for h in hs2 if h in titled or (not h["title"] and h["date"] <= hi)]
        first_other = min((h["date"] for h in other), default="99999999")
        cont = [h for h in cont if h["date"] < first_other or h in titled]
        sc["days"] = sc["days"] + [{k: v for k, v in h.items() if k != "_g"} for h in cont]
        sc["why"] += f"; {len(cont)} day(s) continued in session {s2} (same title printed)"
        for h in cont:
            found.append({"bill_key": f"{s}-Bill{n}", "bill_session": s, "bill_number": n,
                          **{k: v for k, v in h.items() if k != "_g"},
                          "library_file": (rec.get("library_files") or [""])[0],
                          "accepted": True, "why": f"continued in session {s2} (same title printed)"})
        n_cont += len(cont)
    say(f"bill-days added from the next session of the same legislature (a bill reinstated after prorogation): {n_cont}")
    save(found, OUT / "bill_days_found.json")
    # temporary results for apply
    save([{"session": r["session"], "bill_number": r["bill_number"], "library_files": r.get("library_files"),
           **r.get("_scan", {})} for r in pre], OUT / "scan_result.json")
    say("")
    say("=" * 100)
    say("4. Health bills of 1985-1994 and their debate days")
    say("=" * 100)
    acc = [r for r in pre if r.get("_scan", {}).get("days")]
    n_days = sum(len(r["_scan"]["days"]) for r in acc)
    say(f"bills with at least one debate day: {len(acc)} of {len(pre)}; bill-days: {n_days}")
    say(f"   by session: {dict(sorted(Counter(r['session'] for r in acc).items()))}")
    one = sum(1 for r in acc if len(r['_scan']['titles']) == 1)
    say(f"CHECK one title on every day found: {one} of {len(acc)} bills"
        f" (several titles: {sum(1 for r in acc if len(r['_scan']['titles']) > 1)};"
        f" no title printed: {sum(1 for r in acc if not r['_scan']['titles'])})")
    vt = [(r, r["_scan"]["vote_date"]) for r in acc if r["_scan"]["vote_date"]]
    vin = [r for r, v in vt if v in {h["date"] for h in r["_scan"]["days"]}]
    say(f"CHECK the final-passage day in the vote-outcomes file is a debate day found: {len(vin)} of {len(vt)} bills "
        "that have a vote day there")
    for r, v in vt:
        if r not in vin:
            ds = [h["date"] for h in r["_scan"]["days"]]
            say(f"      {r['session']}-Bill{r['bill_number']}: vote day {v}, days found {ds[:8]}")
    late = sum(1 for r, v in vt if r not in vin and v > max(h["date"] for h in r["_scan"]["days"]))
    say(f"      of the {len(vt) - len(vin)} that differ, {late} have a vote day after the bill's last debate day found; "
        "a vote day in a later session belongs to another bill with the same number")
    tab = Counter()
    for r in acc:
        fin = any("adoption" == k or k == "adoption" for h in r["_scan"]["days"] for k in h["stages"])
        oc = str((po.get(f"{r['session']}-Bill{r['bill_number']}") or {}).get("outcome") or "none")
        r["_scan"]["final_adoption_in_journal"] = fin
        tab[(fin, oc)] += 1
    say("CHECK final adoption debated in the Journal (stage 'adoption') vs the outcome in the vote-outcomes file:")
    for (fin, oc), k in sorted(tab.items(), key=lambda x: (not x[0][0], x[0][1])):
        say(f"      Journal final adoption {'yes' if fin else 'no '}  outcomes file {oc:<16} {k}")
    lt = [r for r in acc if number_in_text(r.get("library_snippet"))]
    for r in lt:
        share = title_in_snippet(r["_scan"]["title"], r.get("library_snippet"))
        say(f"CHECK library first page vs Journal title {r['session']}-Bill{r['bill_number']}: "
            f"{'same bill' if share >= 0.8 else 'DIFFERENT'} ({share:.0%} of the title's words) | {r['_scan']['title'][:80]}")
    say("")
    say("Bills with debate days (title as printed in the Journal; [no health word] marks a title with none):")
    for r in sorted(acc, key=lambda r: (r["session"], int(r["bill_number"]))):
        t = r["_scan"]["title"]
        flag = "" if HEALTH_WORDS.search(norm(t)) else "  [no health word]"
        ds = [h["date"] for h in r["_scan"]["days"]]
        say(f"   {r['session']}-Bill{r['bill_number']:<4} {len(ds):>2} days {ds[0]}..{ds[-1]}  {t[:85]}{flag}")
    say("")
    say("Bills with no debate day found (their number never heads a debate in their session, or cannot be told apart):")
    for r in sorted(pre, key=lambda r: (r["session"], int(r["bill_number"]))):
        if r.get("_scan", {}).get("days"):
            continue
        sc = r.get("_scan", {})
        say(f"   {r['session']}-Bill{r['bill_number']:<4} {sc.get('why', '')}; days with the number: "
            f"{sc.get('all_days', [])[:6]} | {str(r.get('library_snippet') or r.get('title'))[:70]}")
    b2 = next((r for r in pre if r["session"] == "33-1" and str(r["bill_number"]) == "2"), None)
    if b2 is not None:
        say("")
        say("The Sept 24 example, Quebec Bill 2 (1985):")
        for h in b2.get("_scan", {}).get("days", []):
            say(f"   {h['date']}  {h['n_paragraphs']} paragraphs, stages {h['stages']}  | {h['first_paragraph'][:150]}")
        if not b2.get("_scan", {}).get("days"):
            say(f"   no day found ({b2.get('_scan', {}).get('why')})")
    with open(BILLS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bill_key", "library_file", "title_in_journal", "health_word_in_title", "debate_days",
                    "n_days", "titles_seen", "vote_date_in_outcomes", "final_adoption_in_journal", "decision",
                    "old_placeholder_number"])
        for r in sorted(pre, key=lambda r: (r["session"], int(r["bill_number"]))):
            sc = r.get("_scan", {})
            w.writerow([f"{r['session']}-Bill{r['bill_number']}", ";".join(r.get("library_files") or []),
                        sc.get("title", ""), "Y" if HEALTH_WORDS.search(norm(sc.get("title", ""))) else "N",
                        " ".join(h["date"] for h in sc.get("days", [])), len(sc.get("days", [])),
                        " | ".join(sc.get("titles", [])), sc.get("vote_date", ""),
                        {True: "Y", False: "N"}.get(sc.get("final_adoption_in_journal"), ""), sc.get("why", ""),
                        r.get("placeholder_number", "")])
    say(f"one row per bill: {BILLS_CSV}")


# ------------------------------------------------------------------------------------------- apply

def cmd_apply():
    health = load(HEALTH, []) or []
    res = {(x["session"], str(x["bill_number"]), tuple(x.get("library_files") or [])): x
           for x in load(OUT / "scan_result.json", []) or []}
    c = Counter()
    for rec in health:
        if rec.get("source") != SOURCE or not rec.get("number_source"):
            continue
        x = res.get((rec["session"], str(rec["bill_number"]), tuple(rec.get("library_files") or [])))
        # earlier days written by this script are replaced; anything else in the record is left alone
        keep = [d for d in rec.get("assembly_debates") or [] if d.get("found_by") != FOUND_BY]
        new = []
        for h in (x or {}).get("days", []):
            d = h["date"]
            new.append({"label": f"Séance du {int(d[6:])} {MONTHS[int(d[4:6]) - 1]} {d[:4]} "
                                 "(found by the 1985-1994 Journal scan)",
                        "url": h["url"], "found_by": FOUND_BY, "stages": h.get("stages", {})})
        rec["assembly_debates"] = keep + new
        if x and x.get("title"):
            rec["title"] = "Projet de loi n° " + str(rec["bill_number"]) + ", " + x["title"][:1].upper() + x["title"][1:]
            rec["title_source"] = "Journal des debats (the 1985-1994 scan); the library text is in library_snippet"
        c["bills given debate days" if new else "bills with no day"] += 1
        c["bill-days"] += len(new)
    save(health, HEALTH)
    say("")
    say(f"apply: {dict(c)}; written into {HEALTH.name}. Next: python3 scripts/step1_debate_text/quebec_rebuild.py segment")


def main():
    cmds = {"numbers": cmd_numbers, "sittings": cmd_sittings, "fetch": cmd_fetch, "scan": cmd_scan,
            "apply": cmd_apply}
    which = sys.argv[1] if len(sys.argv) == 2 else ""
    if which == "all":
        for k in ("numbers", "sittings", "fetch", "scan", "apply"):
            cmds[k]()
    elif which == "rescan":          # the saved sitting list and pages only: no downloads
        for k in ("numbers", "scan", "apply"):
            cmds[k]()
    elif which in cmds:
        cmds[which]()
    else:
        sys.exit("usage: quebec_pre1994.py numbers|sittings|fetch|scan|apply|all|rescan")
    write_report()
    print(f"\nreport: {REPORT}")
    if which in ("all", "sittings"):
        st = load(OUT / "sessions_status.json", {}) or {}
        bad = [k for k in SESSIONS if (st.get(k) or {}).get("status") != "ok"]
        if bad:
            print(f"Sessions not fully listed: {bad} (exit code 3; what was found is saved and used)")
            sys.exit(3)


if __name__ == "__main__":
    main()
