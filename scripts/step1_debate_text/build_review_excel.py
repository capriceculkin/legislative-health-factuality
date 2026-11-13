#!/usr/bin/env python3
"""
build_review_excel.py
Review workbooks for David Chartash and Joanie Bouchard.

outputs/health_bills_review.xlsx
    README
    Bills + Sitting Days   one row per bill per sitting day, with
                           full-day transcript link, bill-specific link,
                           French date, and a "lines up" check
    All Predications       every predication, with its sitting-day link

outputs/transcripts_{us,ontario,quebec}.xlsx
    Every paragraph of every bill-specific debate text, per sitting day

Link sources (all verified against the live sites, Sept 2026):
  US daily (1994+)   granule  https://www.govinfo.gov/content/pkg/CREC-{date}/html/{granuleId}.htm
  US daily (1995+)   full day https://www.govinfo.gov/content/pkg/CREC-{date}/pdf/CREC-{date}-house.pdf
  US bound (<1994)   full day https://www.govinfo.gov/content/pkg/GPO-CRECB-{yyyy}-pt{n}/pdf/{granuleId}.pdf
  Ontario            url / para_url stored in hansard_segments_v3.json
  Quebec             url stored in quebec_assembly/v3/segments_index.json
No link is ever invented: if the index has no link, the cell says so.

Run from project root:
    python3 scripts/step1_debate_text/build_review_excel.py
"""

import datetime as dt, json, re, sys
from collections import defaultdict
from pathlib import Path

try:
    import openpyxl
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("pip install openpyxl")

ROOT = Path(__file__).resolve().parent.parent.parent
OUTDIR = ROOT / "outputs"
TODAY = str(dt.date.today())
JURS = ("us", "ontario", "quebec")
CELL_MAX = 32000          # Excel hard limit is 32,767 characters per cell
ROWS_PER_SHEET = 1_000_000

_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


HEALTH_TITLE_RE = re.compile(
    r"health|hospital|medic|nurs|physician|doctor|drug|pharm|dental|dentist|patient|care\b|long-term|ambulance|"
    r"mental|psych|disease|cancer|tobacco|smok|alcohol|vaccin|immuni|public health|insurance premium|ohip|"
    r"clinic|surg|midwi|optom|chiropod|chiropract|physiotherap|podiatr|therap|blood|organ|transplant|"
    r"nutrition|food safety|safe drinking|water|pollut|toxic|pesticide|occupational|workplace safety|"
    r"disab|addict|coroner|death|abortion|fertility|pregnan|child care|seniors|aging|elder|home care|"
    r"laborator|radiat|epidem|pandemic|quarantine|ontario drug|regulated health", re.I)


def clean(v):
    if isinstance(v, str):
        v = _ILLEGAL.sub("", v)
        if len(v) > CELL_MAX:
            v = v[:CELL_MAX] + " [TRUNCATED]"
    return v


def load(p, required=True):
    p = Path(p)
    if not p.exists():
        if required:
            sys.exit(f"Missing required file: {p}")
        print(f"  (optional file not found: {p})")
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def ymd8_to_iso(s):
    s = str(s)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.match(r"^\d{8}$", s) else s


FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]


def fr_date(iso):
    """2021-10-05 -> 'Le mardi 5 octobre 2021' (same form as the Assnat page header)."""
    try:
        d = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    day = "1er" if d.day == 1 else str(d.day)
    return f"Le {FR_DAYS[d.weekday()]} {day} {FR_MONTHS[d.month - 1]} {d.year}"


def en_date(iso):
    try:
        d = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")


def date_from_url(url):
    if not url:
        return ""
    for rx, conv in ((r"/(\d{4}-\d{2}-\d{2})/hansard", None),
                     (r"/journal-debats/(\d{8})/", ymd8_to_iso),
                     (r"CREC-(\d{4}-\d{2}-\d{2})", None)):
        m = re.search(rx, url)
        if m:
            return conv(m.group(1)) if conv else m.group(1)
    return ""


# ---------------------------------------------------------------- US index reading
GRANULE_RE = re.compile(r"(GPO-CRECB-\d{4}-pt\d+(?:-\d+)*|CREC-\d{4}-\d{2}-\d{2}-pt\d+-Pg[A-Za-z0-9-]+)")


def us_units(e):
    """Granule records from a US index entry, whatever shape the index uses
    (list of dicts, list of IDs, or a plain count). Skips 'excluded'."""
    found = {}
    for k, v in e.items():
        if "exclu" in k.lower():
            continue
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, dict):
                uid = x.get("id") or x.get("granuleId") or x.get("granule_id")
                if uid:
                    found.setdefault(str(uid), {"id": str(uid), "url": x.get("url", ""), "title": x.get("title", "")})
            elif isinstance(x, str):
                for uid in GRANULE_RE.findall(x):
                    found.setdefault(uid, {"id": uid, "url": "", "title": ""})
    return list(found.values())


# ---------------------------------------------------------------- US links
def us_granule_link(uid, day=None):
    """Package is taken from the granule ID itself, never from the sitting date,
    so a wrong date in the index shows up as a mismatch instead of a broken link."""
    uid = str(uid)
    m = re.match(r"(GPO-CRECB-\d{4}-pt\d+)", uid)
    if m:
        return f"https://www.govinfo.gov/content/pkg/{m.group(1)}/pdf/{uid}.pdf"
    m = re.match(r"(CREC-\d{4}-\d{2}-\d{2})", uid)
    if m:
        return f"https://www.govinfo.gov/content/pkg/{m.group(1)}/html/{uid}.htm"
    return ""


def us_full_day_link(day, unit_ids):
    """Full House proceedings for that day."""
    if day >= "1995-01-01":
        return f"https://www.govinfo.gov/content/pkg/CREC-{day}/pdf/CREC-{day}-house.pdf", "full House section PDF"
    bound = [u for u in unit_ids if str(u).startswith("GPO-CRECB-")]
    if bound:
        # the bound granule is the whole House day (large PDF)
        return us_granule_link(bound[0], day), "bound edition House day PDF (large file)"
    return "", "no single full-day file for 1994 daily edition; use bill debate links"


# ---------------------------------------------------------------- outcomes + titles
def load_outcomes():
    """data/v3_outcomes.json, built and cross-checked by scripts/step1_debate_text/outcomes_v3.py."""
    t = load(ROOT / "data/v3_outcomes.json", required=False)
    if t is None:
        sys.exit("data/v3_outcomes.json not found. Run first: python3 scripts/step1_debate_text/outcomes_v3.py")
    return t


def load_titles():
    """Official titles: Congress.gov (US), bills_master long title or the OLA page (Ontario),
    the Assemblee nationale list (Quebec); data/v3_title_fixes.json corrects known errors."""
    import html as _h
    titles = {"us": {}, "ontario": {}, "quebec": {}}
    for e in load(ROOT / "data/us/v3/plan.json") or []:
        bk = e["bill_key"]
        bj = ROOT / "data/v3_status_cache/us" / f"{bk}.bill.json"
        t = ""
        if bj.exists():
            try:
                t = ((json.loads(bj.read_text(encoding="utf-8")).get("bill") or {}).get("title") or "")
            except ValueError:
                t = ""
        titles["us"].setdefault(bk, t or e.get("raw_bill", ""))
    for k, v in (load(ROOT / "data/canada/ontario/v3/bills_master.json", required=False) or {}).items():
        t = v.get("long_title", "") or ""
        if not t.strip() or t.strip() == k:
            page = ROOT / "data/v3_status_cache/ontario" / f"{k}.html"
            if page.exists():
                m = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8", errors="ignore"), re.S | re.I)
                if m:
                    t = re.sub(r"\s*\|.*$", "", _h.unescape(" ".join(m.group(1).split())))
        titles["ontario"][k] = t
    for e in load(ROOT / "data/canada/quebec_bills/quebec_health_bills_combined.json") or []:
        n = str(e.get("bill_number", "")).strip()
        if n.isdigit():
            titles["quebec"][f"{e.get('session', '')}-Bill{int(n)}"] = e.get("title", "")
    for fx in load(ROOT / "data/v3_title_fixes.json", required=False) or []:
        titles[fx["jurisdiction"]][fx["bill_key"]] = fx["title"]
    return titles


def load_text_quality():
    p = ROOT / "outputs/audit/us_text_quality.csv"
    if not p.exists():
        print("  (outputs/audit/us_text_quality.csv not found; run the audit first to fill text_check)")
        return {}
    import csv
    with open(p, encoding="utf-8") as f:
        return {(r["bill_key"], r["debate_date"]): r for r in csv.DictReader(f)}


# ---------------------------------------------------------------- US granules from the pipeline's cache
CACHE = ROOT / "data/us/v3/cache"
US_UNIT_HDR = re.compile(r"Congressional Record,?\s+Volume\s+\d+,?\s+(?:Issue|Number)\s+\d+[^\n]*\n")


def norm_title(t):
    t = (t or "").upper().replace("--CONTINUED", " ").replace("CONTINUED", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def quiet_load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


_BOUND = None
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]


def bound_house_granules():
    """date -> [granuleId] for 'House of Representatives: Month D, YYYY' granules in cached CRECB lists."""
    global _BOUND
    if _BOUND is None:
        _BOUND = defaultdict(list)
        for p in (CACHE / "granule_lists").glob("GPO-CRECB-*.json"):
            for g in ((quiet_load(p) or {}).get("granules") or []):
                t = str(g.get("title", ""))
                m = re.match(r"House of Representatives:\s*(" + "|".join(_MONTHS) + r") (\d{1,2}), (\d{4})", t)
                if m:
                    d = f"{m.group(3)}-{_MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"
                    _BOUND[d].append(g["granuleId"])
    return _BOUND


def us_cached_granules(day, text):
    """Returns (granule_ids, how). Bound: House-day granules the pipeline recorded
    in cache/bound_text/{day}.json. Daily: the GovInfo granule list for that day,
    matched to each debate unit's title in the saved text (exact normalized match)."""
    bt = quiet_load(CACHE / "bound_text" / f"{day}.json")
    if bt and bt.get("granules"):
        return list(dict.fromkeys(bt["granules"])), "bound House day recorded by pipeline"
    if day < "1994-01-01":
        hits = bound_house_granules().get(day, [])
        if hits:
            return hits, "bound House day from GovInfo granule list (title date match)"
        return [], "bound edition: no House-day granule found (run fetch_official_status.py us-bound)"
    gl = quiet_load(CACHE / "granule_lists" / f"CREC-{day}.json")
    grans = [g for g in ((gl or {}).get("granules") or []) if str(g.get("granuleClass", "")).upper() == "HOUSE"]
    if not grans:
        return [], "no cached granule list for this day"
    by_title = defaultdict(list)
    for g in grans:
        by_title[norm_title(g.get("title", ""))].append(g["granuleId"])
    ids, ambiguous, unmatched = [], 0, 0
    for chunk in US_UNIT_HDR.split(text)[1:]:
        title = next((ln.strip() for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("[")), "")
        hits = by_title.get(norm_title(title), [])
        if len(hits) == 1:
            ids.append(hits[0])
        elif len(hits) > 1:
            ambiguous += 1
            ids += hits
        else:
            unmatched += 1
    ids = list(dict.fromkeys(ids))
    how = f"matched {len(ids)} granule(s) by title"
    if ambiguous:
        how += f"; {ambiguous} title(s) shared by several granules, all listed"
    if unmatched:
        how += f"; {unmatched} unit(s) not matched"
    return ids, how


# ---------------------------------------------------------------- transcript index
def build_index():
    """
    Returns
      days[(jur, bill_key, iso_date)] = {
          full_day_url, full_day_note, bill_links[list], session_in_link,
          text_file, paragraphs[list of dict] (for transcript export), title
      }
    """
    days = {}

    # US
    us_idx = load(ROOT / "data/us/v3/segments_index.json")
    for e in us_idx:
        bk, d = e["bill_key"], e["debate_date"]
        slot = days.setdefault(("us", bk, d), {"bill_links": [], "unit_ids": [], "files": [], "titles": []})
        f = ROOT / "data/us" / e["file"]
        units = us_units(e)
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        for uid in GRANULE_RE.findall(text[:3000]):
            if uid not in {u["id"] for u in units}:
                units.append({"id": uid, "url": "", "title": ""})
        if not units:
            ids, how = us_cached_granules(d, text)
            units = [{"id": i, "url": "", "title": ""} for i in ids]
            slot["link_how"] = how
        else:
            slot["link_how"] = "granule IDs stored in index"
        for u in units:
            uid = u["id"]
            if uid in slot["unit_ids"]:
                continue
            slot["unit_ids"].append(uid)
            link = us_granule_link(uid) or u.get("url", "")
            if link and link not in slot["bill_links"]:
                slot["bill_links"].append(link)
            if u.get("title"):
                slot["titles"].append(u["title"])
        if f not in slot["files"]:
            slot["files"].append(f)
    for (j, bk, d), slot in days.items():
        if j == "us":
            slot["full_day_url"], slot["full_day_note"] = us_full_day_link(d, slot["unit_ids"])

    # Ontario
    on = load(ROOT / "data/canada/ontario/v3/hansard_segments_v3.json")
    for bk, dmap in on.items():
        for d, paras in dmap.items():
            # OLA sometimes publishes one day as two files: .../hansard and .../hansard-1
            urls = sorted({p.get("url", "") for p in paras if p.get("url")},
                          key=lambda u: (not u.endswith("/hansard"), u))
            first_para = next((p.get("para_url") for p in paras if p.get("para_url")), "")
            note = "" if len(urls) == 1 else (
                "no Hansard URL stored for this bill-date" if not urls else
                "this day is published as " + str(len(urls)) + " files; the others are in more_links")
            days[("ontario", bk, d)] = {
                "full_day_url": urls[0] if urls else "",
                "full_day_note": note,
                "bill_links": ([first_para] if first_para else []) + urls[1:],
                "link_how": "stored in hansard_segments_v3.json",
                "paragraphs": paras,
                "files": [],
                "titles": sorted({p.get("topic", "") for p in paras if p.get("topic")}),
            }

    # Quebec
    qc = load(ROOT / "data/canada/quebec_assembly/v3/segments_index.json")
    for e in qc:
        d = ymd8_to_iso(e.get("date", ""))
        bk = e["bill_key"]
        slot = days.setdefault(("quebec", bk, d), {"full_day_url": "", "full_day_note": "",
                                                   "bill_links": [], "files": [], "titles": [], "stages": [],
                                                   "link_how": "stored in segments_index.json"})
        u = e.get("url", "")
        if u and not slot["full_day_url"]:
            slot["full_day_url"] = u.split("#")[0]
        if u and u not in slot["bill_links"]:
            slot["bill_links"].append(u)
        if e.get("bill_url") and e["bill_url"] not in slot["bill_links"]:
            slot["bill_links"].append(e["bill_url"])
        f = ROOT / "data/canada/quebec_assembly" / e["file"]
        if f not in slot["files"]:
            slot["files"].append(f)
        if e.get("title"):
            slot["titles"].append(e["title"])
        st = e.get("stages")
        if st:
            slot["stages"].append(", ".join(st) if isinstance(st, (list, dict)) else str(st))
    return days


# ---------------------------------------------------------------- styles
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF")
JFILL = {"us": PatternFill("solid", fgColor="DEEAF1"),
         "ontario": PatternFill("solid", fgColor="E2EFDA"),
         "quebec": PatternFill("solid", fgColor="FFF2CC")}
BAD = PatternFill("solid", fgColor="F8CBAD")
LINK = Font(color="0563C1", underline="single")
TOP = Alignment(vertical="top")
WRAP = Alignment(vertical="top", wrap_text=True)


def header(ws, cols, widths):
    ws.append(cols)
    for i, c in enumerate(ws[1], 1):
        c.fill, c.font, c.alignment = HEADER_FILL, HEADER_FONT, Alignment(wrap_text=True, vertical="center")
    for letter, w in widths.items():
        ws.column_dimensions[letter].width = w
    ws.freeze_panes = "B2"


def put_link(cell, url):
    if isinstance(url, str) and url.startswith("http"):
        cell.hyperlink = url
        cell.font = LINK


# ---------------------------------------------------------------- main workbook
def main():
    print("Loading predications ...")
    preds = []
    for j in JURS:
        data = load(ROOT / "data/dbpedia_pipeline" / j / "predications_v3.json")
        for r in data:
            r["jurisdiction"] = j
        preds += data
        print(f"  {j}: {len(data):,}")

    print("Loading sentence counts ...")
    sent_n = defaultdict(int)
    for j in JURS:
        for s in load(ROOT / "data/dbpedia_pipeline" / j / "sentences_v3.json"):
            sent_n[(j, s.get("bill_key", ""), s.get("date", ""))] += 1

    print("Loading outcomes, titles, text checks ...")
    oc = load_outcomes()
    titles = load_titles()
    tq = load_text_quality()
    print("  outcomes: " + ", ".join(f"{j} {sum(1 for v in oc.get(j, {}).values() if v.get('passed') is not None)}"
                                     for j in JURS))

    print("Loading transcript indexes ...")
    days = build_index()
    print(f"  indexed bill-days: " + ", ".join(f"{j} {sum(1 for k in days if k[0] == j)}" for j in JURS))
    us_linked = sum(1 for k, s in days.items() if k[0] == "us" and s.get("bill_links"))
    print(f"  US bill-days with a bill-specific GovInfo link: {us_linked} of {sum(1 for k in days if k[0] == 'us')}")

    # predications grouped per bill-day
    pc = defaultdict(lambda: [0, 0])
    for p in preds:
        k = (p["jurisdiction"], p.get("bill_key", ""), p.get("date", ""))
        pc[k][0] += 1
        if (p.get("language") or p.get("lang")) == "fr":
            pc[k][1] += 1
    bill_tot = defaultdict(int)
    for (j, bk, d), (n, _) in pc.items():
        bill_tot[(j, bk)] += n

    # every bill-day that has predications OR is in the index
    # only bill-days confirmed against an official record by apply_exclusions.py are removed
    exc = load(ROOT / "outputs/audit/exclusions_confirmed.json", required=False) or []
    exc_status = []
    if (ROOT / "outputs/audit/exclusions_applied.csv").exists():
        import csv as _csv
        with open(ROOT / "outputs/audit/exclusions_applied.csv", encoding="utf-8") as f:
            exc_status = list(_csv.DictReader(f))
    proposals = load(ROOT / "data/v3_health_proposals.json", required=False) or []

    def is_excluded(k):
        return any(r["jurisdiction"] == k[0] and r["bill_key"] == k[1] and r.get("date", "*") in ("*", k[2])
                   for r in exc)
    keys = sorted((set(pc) | set(days)) - {k for k in set(pc) | set(days) if is_excluded(k)},
                  key=lambda k: (k[0], k[1], k[2]))
    print(f"  bill-day rows: {len(keys):,}")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # ---------- Bills + Sitting Days
    ws = wb.create_sheet("Bills + Sitting Days")
    widths = {"jurisdiction": 10, "bill_key": 18, "session": 8, "bill_title": 40, "sitting_date": 12,
              "sitting_date_fr": 26, "sitting_date_en": 26, "full_day_transcript": 60, "full_day_note": 30,
              "bill_debate_link_1": 60, "bill_debate_link_2": 45, "more_links": 30, "how_links_found": 30,
              "date_in_link": 12, "lines_up": 9, "lines_up_reason": 40, "text_check": 30,
              "sentences_this_day": 10, "predications_this_day": 10, "french_predications_this_day": 10,
              "predications_bill_total": 10, "passed": 8, "became_law_us": 9, "outcome": 20, "outcome_source": 24,
              "outcome_check": 30, "outcome_date": 12, "all_votes": 40, "official_bill_page": 45,
              "debate_section_titles": 40,
              "REVIEWER: link shows this bill debated? (Y/N/partial)": 22, "REVIEWER: notes": 30}
    cols = list(widths)
    header(ws, cols, {get_column_letter(i + 1): w for i, w in enumerate(widths.values())})
    col = {c: i + 1 for i, c in enumerate(cols)}
    n_bad = 0
    link_by_billday = {}
    r = 1
    for (j, bk, d) in keys:
        slot = days.get((j, bk, d))
        o = oc.get(j, {}).get(bk, {})
        title = titles[j].get(bk) or (slot and "; ".join(dict.fromkeys(slot.get("titles", [])))[:300]) or ""
        n_pred, n_fr = pc.get((j, bk, d), [0, 0])
        full = slot["full_day_url"] if slot else ""
        links = slot["bill_links"] if slot else []
        link_by_billday[(j, bk, d)] = full or (links[0] if links else "")
        if j == "us":
            # the full-day US link is built from the sitting date, so it cannot test anything;
            # read the date from the granule links, which come from GovInfo IDs
            gdates = sorted({date_from_url(l) for l in links if date_from_url(l)})
            url_date = gdates[0] if len(gdates) == 1 else ("; ".join(gdates) if gdates else "")
        else:
            url_date = date_from_url(full) or date_from_url(links[0] if links else "")
        # lines_up: the bill-date must be in the index AND the link date must equal the sitting date
        reasons = []
        if not slot:
            reasons.append("bill-date not in transcript index (no verified link)")
        else:
            if not full and not links:
                reasons.append("no link found")
            if url_date and url_date != d:
                reasons.append(f"date in link {url_date} != sitting date")
            if not url_date and j != "us":
                reasons.append("no date readable in link")
            if j == "us" and slot.get("unit_ids"):
                yrs = {re.search(r"(\d{4})", str(u)).group(1) for u in slot["unit_ids"] if re.search(r"(\d{4})", str(u))}
                if yrs and d[:4] not in yrs:
                    reasons.append(f"granule year {sorted(yrs)} != sitting year")
        soft = []
        if n_pred == 0:
            soft.append("0 predications on this date")
        if j == "us" and slot and not url_date and any(str(u).startswith("GPO-CRECB-") for u in slot.get("unit_ids", [])):
            soft.append("bound edition: link ID carries year only, date checked by year")
        if j == "us" and slot and not links:
            soft.append("no bill-specific GovInfo link; use full-day transcript")
        ok = not reasons
        reasons += soft
        if not ok:
            n_bad += 1
        q = tq.get((bk, d), {}) if j == "us" else {}
        if q:
            pct = float(q.get("pct_scrambled") or 0)
            nb = int(q.get("predications_in_scrambled_text") or 0)
            if q.get("flag_scrambled") == "Y":
                text_check = f"POSSIBLY SCRAMBLED: {pct:.0%} of text; {nb} of {q.get('predications')} predications affected"
            elif nb:
                text_check = f"mostly readable ({pct:.0%} scrambled); {nb} of {q.get('predications')} predications affected"
            elif q.get("flag_scrambled") == "N":
                text_check = "reads as English"
            else:
                text_check = "too short to score"
        else:
            text_check = "" if j != "us" else "not scored (run the audit first)"
        passed = o.get("passed")
        row = {
            "jurisdiction": j, "bill_key": bk,
            "session": bk.rsplit("-Bill", 1)[0] if j != "us" else bk.split("-")[0],
            "bill_title": title, "sitting_date": d, "sitting_date_fr": fr_date(d), "sitting_date_en": en_date(d),
            "full_day_transcript": full, "full_day_note": slot["full_day_note"] if slot else "",
            "bill_debate_link_1": links[0] if len(links) > 0 else "",
            "bill_debate_link_2": links[1] if len(links) > 1 else "",
            "more_links": " | ".join(links[2:]), "how_links_found": slot.get("link_how", "") if slot else "",
            "date_in_link": url_date, "lines_up": "YES" if ok else "NO", "lines_up_reason": "; ".join(reasons),
            "text_check": text_check,
            "sentences_this_day": sent_n.get((j, bk, d), 0), "predications_this_day": n_pred,
            "french_predications_this_day": n_fr, "predications_bill_total": bill_tot.get((j, bk), 0),
            "passed": {1: "YES", 0: "NO"}.get(passed, ""), "outcome": o.get("outcome_raw", ""),
            "became_law_us": o.get("became_law", ""),
            "outcome_source": o.get("source", "") or "no outcome found", "outcome_check": o.get("check", ""),
            "outcome_date": o.get("outcome_date", ""), "all_votes": o.get("all_votes", ""),
            "official_bill_page": o.get("official_url", ""),
            "debate_section_titles": "; ".join(dict.fromkeys(slot.get("titles", [])))[:500] if slot else "",
        }
        ws.append([clean(row.get(c, "")) for c in cols])
        r += 1
        fill = JFILL[j]
        for c in ws[r]:
            c.fill, c.alignment = fill, TOP
        for name in ("full_day_transcript", "bill_debate_link_1", "bill_debate_link_2", "official_bill_page"):
            put_link(ws.cell(r, col[name]), row[name])
        if not ok:
            ws.cell(r, col["lines_up"]).fill = BAD
        if passed is None:
            ws.cell(r, col["passed"]).fill = BAD
        if text_check.startswith(("POSSIBLY", "mostly")):
            ws.cell(r, col["text_check"]).fill = BAD
        if "DISAGREE" in str(o.get("check", "")):
            ws.cell(r, col["outcome_check"]).fill = BAD
    ws.auto_filter.ref = ws.dimensions
    print(f"  Bills + Sitting Days: {ws.max_row - 1:,} rows, {n_bad} flagged NO")

    # ---------- All Predications
    ws2 = wb.create_sheet("All Predications")
    cols2 = ["jurisdiction", "bill_key", "session", "date", "sitting_date_fr", "language", "subject", "verb",
             "verb_lemma", "object", "hedged", "negated", "full_text", "sentence_id", "sitting_day_transcript",
             "us_text_scrambled"]
    header(ws2, cols2, {"A": 10, "B": 18, "C": 8, "D": 11, "E": 24, "F": 6, "G": 28, "H": 18, "I": 14, "J": 28,
                        "K": 7, "L": 7, "M": 70, "N": 24, "O": 60, "P": 10})
    pflag = {}
    pf = ROOT / "outputs/audit/us_predication_text_flags.csv"
    if pf.exists():
        import csv as _csv
        with open(pf, encoding="utf-8") as f:
            pflag = {r["sentence_id"]: r["in_scrambled_text"] for r in _csv.DictReader(f)}
    r2 = 1                                  # row counter (ws.max_row rescans the whole sheet each call)
    for p in preds:
        j, bk, d = p["jurisdiction"], p.get("bill_key", ""), p.get("date", "")
        url = link_by_billday.get((j, bk, d), "")
        r2 += 1
        ws2.append([clean(v) for v in [j, bk, p.get("session", ""), d, fr_date(d),
                                       p.get("language", p.get("lang", "")), p.get("subject", ""), p.get("verb", ""),
                                       p.get("verb_lemma", ""), p.get("object", ""), p.get("hedged", False),
                                       p.get("negated", False), p.get("full_text", ""), p.get("sentence_id", ""), url,
                                       {"Y": "YES", "N": "no", "?": "not located"}.get(pflag.get(p.get("sentence_id", "")), "")
                                       if j == "us" else ""]])
        if j == "us" and pflag.get(p.get("sentence_id", "")) == "Y":
            ws2.cell(r2, 16).fill = BAD
        if url:
            put_link(ws2.cell(r2, 15), url)
    ws2.auto_filter.ref = ws2.dimensions
    print(f"  All Predications: {ws2.max_row - 1:,} rows")

    # ---------- Health list decisions (every predicated bill, with the decision and its reason)
    ws3 = wb.create_sheet("Health list decisions")
    header(ws3, ["jurisdiction", "bill_key", "official_title", "decision", "reason"],
           {"A": 10, "B": 16, "C": 80, "D": 11, "E": 90})
    prop = {(r["jurisdiction"], r["bill_key"]): r for r in proposals}
    kept = sorted({(p["jurisdiction"], p.get("bill_key", "")) for p in preds})
    for j, bk in kept:
        r = prop.get((j, bk))
        ws3.append([clean(v) for v in [j, bk, titles.get(j, {}).get(bk, ""),
                                       "PROPOSED: exclude" if r else "kept",
                                       (r.get("reason", "") + " | " + r.get("evidence", "")) if r else
                                       "the official title states a health subject"]])
        if r:
            ws3.cell(ws3.max_row, 4).fill = BAD
    ws3.auto_filter.ref = ws3.dimensions
    print(f"  Health list decisions: {len(kept)} bills, {sum(1 for k in kept if k in prop)} proposed for exclusion (still in the data)")

    # ---------- Excluded (with the evidence for each)
    ws4 = wb.create_sheet("Excluded bill-days")
    header(ws4, ["status", "jurisdiction", "bill_key", "date", "reason", "official_check"],
           {"A": 10, "B": 10, "C": 18, "D": 12, "E": 80, "F": 90})
    for r in exc_status:
        ws4.append([clean(r.get(c, "")) for c in ("status", "jurisdiction", "bill_key", "date", "reason", "official_check")])
        if r.get("status") == "HELD":
            ws4.cell(ws4.max_row, 1).fill = BAD
    print(f"  Excluded bill-days: {sum(r.get('status') == 'REMOVED' for r in exc_status)} removed, "
          f"{sum(r.get('status') == 'HELD' for r in exc_status)} held")

    # ---------- README
    ws0 = wb.create_sheet("README", 0)
    lines = [
        ("LEGISLATIVE HEALTH FACTUALITY: REVIEW WORKBOOK", True),
        (f"Generated {TODAY}. Prepared for David Chartash and Joanie Bouchard.", False),
        ("", False),
        ("Bills + Sitting Days: one row per bill per sitting day on which it was debated.", False),
        ("All Predications: every subject-verb-object claim extracted, with a link to its sitting day.", False),
        ("Excluded bill-days: sections that are not the bill's debate. REMOVED only when an official record", False),
        ("  (Congress.gov actions, the OLA bill page, or the Hansard itself) confirms it; HELD ones stay in.", False),
        ("Health list decisions: every bill, kept or excluded, with the reason. A bill is kept when its official", False),
        ("  title states a health subject (health care, public health, health professions, drugs, tobacco,", False),
        ("  occupational health, long-term care, health insurance). PROPOSED exclusions are still in the data", False),
        ("  until David and Joanie approve them.", False),
        ("transcripts_us / _ontario / _quebec.xlsx: every paragraph of the bill-specific debate text.", False),
        ("", False),
        ("LINKS", True),
        ("full_day_transcript: the entire sitting day. US 1995+: House section PDF. US before 1994: bound", False),
        ("  Congressional Record PDF for that House day (large file). Ontario: OLA Hansard for that date.", False),
        ("  Quebec: Journal des debats for that sitting (Assemblee nationale).", False),
        ("bill_debate_link: the part of the record covering this bill. US: the GovInfo granule.", False),
        ("  Ontario: the first paragraph anchor for the bill on that date. Quebec: journal page and bill page.", False),
        ("Every link comes from the pipeline's own transcript index. None are constructed guesses.", False),
        ("", False),
        ("DATE CHECKS", True),
        ("sitting_date_fr is written the way the Assemblee nationale header writes it (e.g. Le lundi 4 decembre 1995).", False),
        ("date_in_link is read out of the link itself. lines_up = YES only when the bill-date is in the transcript", False),
        ("  index AND the date inside the link equals the sitting date. Red cells need a look.", False),
        ("US debates can fall a day or two before the recorded vote; the sitting date is the debate date.", False),
        ("", False),
        ("PLEASE FILL", True),
        ("REVIEWER column: open the link and confirm this bill is actually debated there (Y / N / partial).", False),
        ("", False),
        ("OUTCOMES", True),
        ("passed = YES / NO / blank (red). outcome_source says where it came from; outcome_check shows the", False),
        ("  other sources it was compared with (red = a source of the same kind disagrees).", False),
        ("  US: passed = passed the House. Source: the House passage roll call (Voteview); for voice votes,", False),
        ("  the Congress.gov House action; plan.json only when neither exists. became_law_us: Congress.gov.", False),
        ("  Ontario: the OLA bill status page (1995 on): Royal Assent received = YES; did not reach or lost", False),
        ("  third reading before the session ended = NO. Before 1995: the royal assent field of the FSOB file,", False),
        ("  used only if it agrees with the OLA pages on 95%+ of the bills both cover (else left blank).", False),
        ("  Quebec: the Assemblee nationale bill page (Date de la sanction = YES).", False),
        ("  Bills in a session that is still running are left blank (pending), not NO.", False),
        ("", False),
        ("TEXT CHECK (US)", True),
        ("Some US text came from multi-column PDFs or older text files where columns can interleave. Each", False),
        ("  150-word window is compared with the same words shuffled: real prose scores far above its shuffle,", False),
        ("  scrambled text does not. text_check gives the share of scrambled text per bill-day; the column", False),
        ("  us_text_scrambled on All Predications marks each predication taken from scrambled text.", False),
        ("  Those predications should not be scored until the text is re-extracted.", False),
        ("official_bill_page: the legislature's own status page for the bill (Ontario 1995+, Quebec), used", False),
        ("  as the reference for outcomes.", False),
        ("", False),
        ("KNOWN GAPS", True),
        ("US 1994 daily edition has no single full-day file on GovInfo; the granule links cover the debate.", False),
        ("DBpedia/SPARQL factuality scores are not in this workbook yet.", False),
    ]
    for t, b in lines:
        ws0.append([t])
        ws0.cell(ws0.max_row, 1).font = Font(bold=b, size=13 if b else 11, color="1F4E79" if b else "000000")
    ws0.column_dimensions["A"].width = 110
    ws0.sheet_view.showGridLines = False

    OUTDIR.mkdir(exist_ok=True)
    out = OUTDIR / "health_bills_review.xlsx"
    wb.save(out)
    print(f"Saved {out}")

    # ---------- transcript workbooks (write-only, one per jurisdiction)
    # the transcripts leave out the same confirmed bill-days as the sheets above
    tdays = {k: v for k, v in days.items() if not is_excluded(k)}
    for j in JURS:
        write_transcripts(j, tdays, oc.get(j, {}))


def iter_paragraphs(j, slot):
    if j == "ontario":
        for p in slot.get("paragraphs", []):
            yield p.get("speaker", ""), p.get("topic", ""), p.get("text", ""), p.get("para_url", "")
    else:
        for f in slot.get("files", []):
            try:
                txt = Path(f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                yield "", "", f"[TEXT FILE NOT FOUND: {f}]", ""
                continue
            for para in (x.strip() for x in txt.split("\n\n")):
                if para:
                    yield "", "", para, ""


def write_transcripts(j, days, oc):
    wb = openpyxl.Workbook(write_only=True)
    cols = ["bill_key", "sitting_date", "sitting_date_fr", "paragraph_no", "speaker", "topic", "text",
            "paragraph_link", "full_day_transcript", "outcome"]
    sheet_no, rows_in_sheet, total, ws = 0, ROWS_PER_SHEET, 0, None
    for (jj, bk, d) in sorted(k for k in days if k[0] == j):
        slot = days[(jj, bk, d)]
        for i, (spk, topic, text, purl) in enumerate(iter_paragraphs(j, slot), 1):
            if rows_in_sheet >= ROWS_PER_SHEET:
                sheet_no += 1
                ws = wb.create_sheet(f"transcript_{sheet_no}")
                ws.column_dimensions["G"].width = 100
                ws.freeze_panes = "A2"
                hdr = []
                for c in cols:
                    wc = WriteOnlyCell(ws, value=c)
                    wc.font, wc.fill = HEADER_FONT, HEADER_FILL
                    hdr.append(wc)
                ws.append(hdr)
                rows_in_sheet = 0
            full = slot.get("full_day_url", "")
            vals = [bk, d, fr_date(d), i, spk, topic, text, purl, full, oc.get(bk, {}).get("outcome_raw", "")]
            cells = []
            for ci, v in enumerate(vals, 1):
                wc = WriteOnlyCell(ws, value=clean(v))
                if ci == 7:
                    wc.alignment = WRAP
                if ci in (8, 9) and isinstance(v, str) and v.startswith("http"):
                    wc.hyperlink, wc.font = v, LINK
                cells.append(wc)
            ws.append(cells)
            rows_in_sheet += 1
            total += 1
    if total == 0:
        wb.create_sheet("transcript_1").append(cols)
    out = OUTDIR / f"transcripts_{j}.xlsx"
    wb.save(out)
    print(f"Saved {out} ({total:,} paragraphs, {sheet_no} sheet(s))")


if __name__ == "__main__":
    main()
