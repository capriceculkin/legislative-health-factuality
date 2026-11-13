#!/usr/bin/env python3
"""
reextract_bound.py
Re-reads every pre-1994 (bound edition) House day from the GovInfo PDF, column
by column, and replaces the old interleaved text the pipeline had used.

For each bound debate day (plan.json bound rows: vote date and the day before):
  1. find the House-day granule (pipeline cache, GovInfo granule lists from
     fetch_official_status.py us-bound, or markers in the old text files)
  2. download the PDF if not cached
  3. read every page two independent ways (crec_columns.py):
       geometric: word positions, gutters, full-width lines
       stored:    the scanner's own text order (pypdf)
     accept the page if they agree >= 99.5% letter for letter; if not, keep the
     reading whose line breaks form ordinary word pairs (the other reading
     interleaves columns); flag the page if that test is also inconclusive
  4. check the date printed in each page header equals the debate day
  5. write data/us/v3/cache/bound_text/{day}.json in the format us_rebuild.py
     reads (old version kept in cache/bound_text_old/)

Then rebuild the segments with the pipeline's own code:
    python3 scripts/step1_debate_text/us_rebuild.py segment

Second pass, --ocr: for the days where a bill's debate was found (segments_index.json),
read every page a second time with Tesseract and correct the GovInfo words
conservatively (crec_ocr.py). Needs: brew install tesseract. Then segment again.

Report: outputs/audit/bound_reextract_pages.csv (every page),
        outputs/audit/bound_ocr_corrections.csv, outputs/audit/bound_ocr_review.csv
Run from project root:
    python3 scripts/step1_debate_text/reextract_bound.py            [--only 1991-06-10]
    python3 scripts/step1_debate_text/reextract_bound.py --ocr      [--only 1991-06-10]
"""
import csv, datetime as dt, glob, json, os, re, shutil, sys, time, warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import pdfplumber
    from pypdf import PdfReader
except ImportError:
    sys.exit("pip install pdfplumber pypdf")
import crec_columns as C
import crec_ocr as O

US = ROOT / "data" / "us"
CACHE = US / "v3" / "cache"
BT = CACHE / "bound_text"
BT_OLD = CACHE / "bound_text_old"
PDFDIR = CACHE / "bound_pdf"
AUD = ROOT / "outputs" / "audit"
AUD.mkdir(parents=True, exist_ok=True)
LOOKBACK = int(os.environ.get("US_LOOKBACK_BOUND", "1"))
DAILY_FROM = os.environ.get("US_DAILY_FROM", "1994-01-01")
AGREE = 0.995
JOIN_FLAG = 0.15
UA = {"User-Agent": "Mozilla/5.0 (research; Yale School of Public Health legislative factuality study)"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
W = re.compile(r"[a-z]+")


def long_date(s):
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2}),\s*(\d{4})", s or "")
    if not m:
        return ""
    return f"{m.group(3)}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def house_granules(day):
    """Candidate House-day PDFs for a date, most trustworthy first. GovInfo's own
    granule title ("House of Representatives: June 10, 1991") comes first; the old
    pipeline's choice was wrong for several days (a different date, or a whole day
    including the Senate). Every candidate is still checked against the page headers."""
    cands = []
    hits = []
    for p in (CACHE / "granule_lists").glob(f"GPO-CRECB-{day[:4]}-pt*.json"):
        for g in ((load(p) or {}).get("granules") or []):
            t = str(g.get("title", ""))
            if t.startswith("House of Representatives") and long_date(t) == day:
                hits.append(g["granuleId"])
    if hits:
        cands.append((sorted(set(hits)), "GovInfo granule list (title date)"))
    # Nothing from the old pipeline is used: no old cache, no old text markers.
    return cands


def get_pdf(gid):
    path = PDFDIR / f"{gid}.pdf"
    if path.exists() and path.read_bytes()[:4] == b"%PDF":
        return path
    import urllib.request
    m = re.match(r"(GPO-CRECB-\d{4}-pt\d+)", gid)
    url = f"https://www.govinfo.gov/content/pkg/{m.group(1)}/pdf/{gid}.pdf"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                raw = r.read()
            if raw[:4] == b"%PDF":
                PDFDIR.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                return path
        except Exception as e:
            print(f"    download attempt {attempt + 1} failed: {e}")
        time.sleep(15 * (attempt + 1))
    return None


def join_plausibility(lines, inside):
    ok = tot = 0
    for a, b in zip(lines, lines[1:]):
        wa, wb = W.findall(a.lower()), W.findall(b.lower())
        if wa and wb:
            tot += 1
            ok += inside[(wa[-1], wb[0])] > 0
    return ok / tot if tot else 1.0


def read_pdf(path, day, ocr=False, ocr_log=None):
    reads = []
    r = PdfReader(str(path))
    n_pages = len(r.pages)
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            reads.append(C.read_page(page, r.pages[i]))
    tess = O.ocr_pages(path, [{"index": i, "gutters": rd["gutters"]} for i, rd in enumerate(reads)]) if ocr else {}
    # pages with no GPO text layer at all: Tesseract is the only reading available
    blank = [i for i, rd in enumerate(reads) if not rd["lines"] and not rd.get("stored_lines")]
    if blank:
        print(f"    {path.name}: {len(blank)} of {n_pages} pages have no text layer; reading them with Tesseract only")
        tess_blank = O.ocr_pages(path, [{"index": i, "gutters": None} for i in blank])
        for i in blank:
            head = O.ocr_header(path, i)
            # no font sizes on an image: a debate heading is a capitals line by the same text
            # rules as the text-layer reader; marked so the segmenter cuts bill sections there
            t_lines = [(C.MARK + ln) if C.is_debate_heading(ln, 0, 0) and not C.TIME_STAMP.match(ln.strip()) else ln
                       for ln in tess_blank.get(i, [])]
            reads[i] = {**reads[i], "header": head, "lines": t_lines, "stored_lines": [],
                        "ocr_only": True, "compare": {"order_agreement": 0.0, "geo_matched": 0.0}}
    inside = Counter()
    for rd in reads:
        for ln in rd["lines"]:
            w = W.findall(ln.lower())
            inside.update(zip(w, w[1:]))
    out, rows = [], []
    for i, rd in enumerate(reads, 1):
        c = rd["compare"]
        g = join_plausibility(rd["lines"], inside)
        s = join_plausibility(rd["stored_lines"], inside)
        hdate = long_date(rd["header"])
        if not hdate:
            # header line not recognised (OCR damage to "CONGRESSIONAL RECORD"): the printed
            # date is still in the running head, which is then the first line of the page text
            top = " ".join(rd["lines"][:2]) + " | " + " ".join(rd.get("stored_lines", [])[:2])
            hdate = long_date(top)
        body = " ".join(rd["lines"])
        speech = len(re.findall(r"\b(?:Mr|Mrs|Ms|Miss)\.\s+[A-Z]{2,}|The (?:SPEAKER|CHAIRMAN|Clerk)", body))
        tally = bool(re.search(r"\[Roll No\.|YEAS\s*[-\u2014]+\s*\d|NAYS\s*[-\u2014]+\s*\d|NOT VOTING\s*[-\u2014]+\s*\d", body))
        if rd.get("ocr_only"):
            decision, lines = ("OCR-ONLY: page has no GPO text layer; one reading (Tesseract), check page image"
                               if rd["lines"] else "FLAG: no text layer and Tesseract read nothing"), rd["lines"]
        elif c["order_agreement"] >= AGREE and c["geo_matched"] >= AGREE:
            decision, lines = "accepted: both readers agree", rd["lines"]
        elif c["order_agreement"] >= 0.98 and c["geo_matched"] >= 0.98:
            decision, lines = "accepted: readers agree on 98%+ (small local differences)", rd["lines"]
        elif tally and speech <= 2:
            decision, lines = "accepted: roll-call name list, no speech on page", rd["lines"]
        elif g >= s and g >= JOIN_FLAG:
            decision, lines = "accepted: readers differ, geometric line breaks are ordinary text", rd["lines"]
        elif s > g and s >= JOIN_FLAG:
            decision, lines = "accepted: readers differ, stored order line breaks are ordinary text", rd["stored_lines"]
        else:
            decision, lines = "FLAG: readers differ and neither is clearly right; check page image", rd["lines"]
        if hdate and (hdate[5:] != day[5:] or abs(int(hdate[:4]) - int(day[:4])) > 1):
            decision = f"FLAG: page header date {hdate} is not {day}; " + decision
        n_fix = n_rev = 0
        if ocr and not rd.get("ocr_only"):
            day_counts = Counter(t.lower() for rd2 in reads for ln in rd2["lines"] for t in O.TOK.findall(ln))
            lines, fixes, reviews = O.correct_lines(lines, tess.get(i - 1, []), day_counts, context_page=i)
            n_fix, n_rev = len(fixes), len(reviews)
            for f in fixes:
                ocr_log["fix"].append({"day": day, "pdf": path.name, **f})
            for f in reviews:
                ocr_log["review"].append({"day": day, "pdf": path.name, **f})
        rows.append({"day": day, "pdf": path.name, "page": i, "header": rd["header"][:80], "header_date": hdate,
                     "gutters": rd["gutters"], "agreement": round(c["order_agreement"], 4),
                     "geo_matched": round(c["geo_matched"], 4), "join_geo": round(g, 3), "join_stored": round(s, 3),
                     "decision": decision, "ocr_corrections": n_fix, "ocr_review": n_rev})
        out.append({"header": rd["header"], "lines": lines})
    return out, rows


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    only_set = set(only.split(",")) if only else None
    ocr = "--ocr" in sys.argv
    report_only = "--report-only" in sys.argv     # recompute the page report; leave the text files alone
    days = set()
    if ocr:
        if not O.tesseract_available():
            sys.exit("Tesseract not found. Install it: brew install tesseract")
        if not O.dictionary():
            sys.exit("No word list found at /usr/share/dict/words (set WORDLIST=/path/to/words)")
        idx = load(US / "v3" / "segments_index.json") or sys.exit("Run us_rebuild.py segment first.")
        days = {e["debate_date"] for e in idx if e.get("edition") == "bound" or e.get("debate_date", "") < DAILY_FROM}
        print(f"second reading (Tesseract) for days with a bill debate: {len(days)}; word list: {len(O.dictionary()):,} words")
    else:
        plan = load(US / "v3" / "plan.json") or sys.exit("data/us/v3/plan.json not found")
        for b in plan:
            if b.get("edition") == "bound" or b.get("vote_date", "") < DAILY_FROM:
                d0 = dt.date.fromisoformat(b["vote_date"])
                for k in range(LOOKBACK + 1):
                    days.add((d0 - dt.timedelta(days=k)).isoformat())
    if ocr and only_set:
        days = set(only_set)          # --only with --ocr: read exactly these days, both readers
    days = sorted(d for d in days if not only_set or d in only_set)
    print(f"bound debate days to read: {len(days)}")
    ocr_log = {"fix": [], "review": []}
    BT_OLD.mkdir(parents=True, exist_ok=True)
    all_rows, summary = [], Counter()
    for n, day in enumerate(days, 1):
        cands = house_granules(day)
        if not cands:
            print(f"[{n}/{len(days)}] {day}: no House granule found; run fetch_official_status.py us-bound")
            summary["no granule"] += 1
            continue
        lines, headers, rows, gids, how = [], [], [], [], ""
        t0 = time.time()
        for cand, cand_how in cands:
            c_lines, c_headers, c_rows, c_log = [], [], [], {"fix": [], "review": []}
            for gid in cand:
                pdf = get_pdf(gid)
                if pdf is None:
                    print(f"[{n}/{len(days)}] {day}: could not download {gid}")
                    continue
                pages, prow = read_pdf(pdf, day, ocr=ocr, ocr_log=c_log)
                c_rows += prow
                for pg in pages:
                    c_headers.append(pg["header"])
                    c_lines += pg["lines"] + [""]
            dated = [r for r in c_rows if r["header_date"]]
            # a page is on the wrong day if its printed month/day differ; a year that is
            # off by one with the same month/day is an OCR slip on the header ("1992" for "1991")
            wrong = [r for r in dated if r["header_date"][5:] != day[5:]
                     or abs(int(r["header_date"][:4]) - int(day[:4])) > 1]
            senate = sum("SENATE" in r["header"].upper() for r in c_rows)
            if c_rows and dated and len(wrong) <= 0.1 * len(dated) and senate <= 0.1 * len(c_rows):
                lines, headers, rows, gids, how = c_lines, c_headers, c_rows, cand, cand_how
                ocr_log["fix"] += c_log["fix"]
                ocr_log["review"] += c_log["review"]
                break
            n_txt = sum(1 for r in c_rows if r["header"] or r["agreement"] > 0)
            print(f"    candidate had {len(c_rows)} pages, {n_txt} with readable text/header")
            print(f"[{n}/{len(days)}] {day}: REJECTED {cand} from {cand_how}: "
                  f"{len(wrong)} of {len(dated)} page headers show another date "
                  f"({Counter(r['header_date'] for r in wrong).most_common(2)}), {senate} Senate pages")
            summary["wrong PDF rejected"] += 1
        if not lines:
            print(f"[{n}/{len(days)}] {day}: no PDF whose pages carry this date; day emptied so no wrong-day "
                  f"text is used (run fetch_official_status.py us-bound, then this again)")
            summary["no correct PDF"] += 1
            if report_only:
                continue
            src = BT / f"{day}.json"
            if src.exists() and not (BT_OLD / f"{day}.json").exists():
                shutil.copy2(src, BT_OLD / f"{day}.json")
            BT.mkdir(parents=True, exist_ok=True)
            with open(src, "w", encoding="utf-8") as f:
                json.dump({"source": "none", "lines": [], "headers": [], "granules": [],
                           "reason": "no PDF whose page headers carry this date"}, f)
            continue
        flags = sum(r["decision"].startswith("FLAG") for r in rows)
        src = BT / f"{day}.json"
        if not report_only and src.exists() and not (BT_OLD / f"{day}.json").exists():
            shutil.copy2(src, BT_OLD / f"{day}.json")
        BT.mkdir(parents=True, exist_ok=True)
        with open(os.devnull if report_only else src, "w", encoding="utf-8") as f:
            json.dump({"source": "pdf_columns_v2", "lines": lines, "headers": headers, "granules": list(gids),
                       "granule_source": how, "interleave_rate": 0.0, "pages": len(rows), "pages_flagged": flags,
                       "ocr": "two_engine" if ocr else "govinfo_layer",
                       "ocr_corrections": sum(r.get("ocr_corrections", 0) for r in rows),
                       "ocr_review": sum(r.get("ocr_review", 0) for r in rows),
                       "ocr_only_pages": sum(r["decision"].startswith("OCR-ONLY") for r in rows)}, f)
        all_rows += rows
        summary["days re-read"] += 1
        summary["pages"] += len(rows)
        summary["pages flagged"] += flags
        summary["pages read by Tesseract only (no text layer)"] += sum(r["decision"].startswith("OCR-ONLY") for r in rows)
        if ocr:
            summary["ocr corrections"] += sum(r["ocr_corrections"] for r in rows)
            summary["ocr review"] += sum(r["ocr_review"] for r in rows)
        n_fix = sum(r["ocr_corrections"] for r in rows)
        n_rev = sum(r["ocr_review"] for r in rows)
        secs = int(time.time() - t0)
        ocr_note = f", {n_fix} words corrected, {n_rev} for review ({secs}s)" if ocr else ""
        kinds = dict(Counter(r["decision"].split(":")[0] for r in rows))
        print(f"[{n}/{len(days)}] {day}: {len(rows)} pages, {flags} flagged{ocr_note}; {kinds}")
    def write_report(name, rows_):
        """With --only, keep the other days' rows already in the report (replace only these days)."""
        path = AUD / name
        if only_set and path.exists():
            with open(path, encoding="utf-8") as f:
                old_rows = [r for r in csv.DictReader(f) if r.get("day") not in set(days)]
            rows_ = old_rows + rows_
        cols = []
        for r in rows_:
            for k in r:
                if k not in cols:
                    cols.append(k)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols or ["day"], extrasaction="ignore")
            w.writeheader()
            w.writerows(rows_)
    write_report("bound_reextract_pages.csv", all_rows)
    if ocr:
        write_report("bound_ocr_corrections.csv", ocr_log["fix"])
        write_report("bound_ocr_review.csv", ocr_log["review"])
        print(f"Word corrections: {AUD / 'bound_ocr_corrections.csv'}")
        print(f"Words for a person to check (with page number): {AUD / 'bound_ocr_review.csv'}")
    print(f"\nSummary: {dict(summary)}")
    print(f"Every page: {AUD / 'bound_reextract_pages.csv'}")
    print("Next:  python3 scripts/step1_debate_text/us_rebuild.py segment  &&  python3 scripts/step1_debate_text/us_rebuild.py verify")


if __name__ == "__main__":
    main()
