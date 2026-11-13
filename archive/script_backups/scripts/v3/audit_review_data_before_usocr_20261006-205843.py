#!/usr/bin/env python3
"""
audit_review_data.py

Full audit of everything bill-specific before the review sheet goes to
David and Joanie. Every date and link is checked by at least two
independent methods.

  A  bill_key / session / date format on every predication and sentence
  B  predication -> sentence join (bill_key, date, session must agree)
  C  predication dates exist in the transcript index for that bill
  D  transcript dates: index date vs date parsed from the URL vs
     date printed in the transcript (US header, Quebec French header)
     plus a weekday cross-check
  E  outcomes: US duplicate votes, Ontario/Quebec coverage and why missing
  F  health list membership: every predicated bill is a health bill
  G  coverage: health bills with no transcript at all
  H  US text: readable English or scrambled columns (per 150-word window)
  I  each bill-day section names its own bill (number, or title words in heading)

Run from project root:
    python3 scripts/v3/audit_review_data.py

Writes:
    outputs/audit/audit_report.txt
    outputs/audit/audit_issues.csv
"""

import csv, datetime as dt, glob, json, os, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "outputs" / "audit"
OUT.mkdir(parents=True, exist_ok=True)

P = {
    "pred":   lambda j: ROOT / "data" / "dbpedia_pipeline" / j / "predications_v3.json",
    "sent":   lambda j: ROOT / "data" / "dbpedia_pipeline" / j / "sentences_v3.json",
    "us_plan":   ROOT / "data" / "us" / "v3" / "plan.json",
    "us_index":  ROOT / "data" / "us" / "v3" / "segments_index.json",
    "us_missing": ROOT / "data" / "us" / "v3" / "segments_missing.json",
    "on_segs":   ROOT / "data" / "canada" / "ontario" / "v3" / "hansard_segments_v3.json",
    "on_fsob":   ROOT / "data" / "canada" / "ontario" / "ontario_fsob_votes.json",
    "on_bills":  ROOT / "data" / "canada" / "ontario" / "ontario_bill_index.json",
    "qc_index":  ROOT / "data" / "canada" / "quebec_assembly" / "v3" / "segments_index.json",
    "qc_cache":  ROOT / "data" / "canada" / "quebec_assembly" / "v3" / "journal_cache",
    "qc_health": ROOT / "data" / "canada" / "quebec_bills" / "quebec_health_bills_combined.json",
    "qc_nourl":  ROOT / "data" / "canada" / "quebec_assembly" / "v3" / "health_bills_without_assembly_urls.csv",
}

KEY_RE = {
    "us":      re.compile(r"^(\d+)-([A-Z]+)(\d+)$"),
    "ontario": re.compile(r"^(\d+-\d+)-Bill(\d+)$"),
    "quebec":  re.compile(r"^(\d+-\d+)-Bill(\d+)$"),
}
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
FR_MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
             "aout", "septembre", "octobre", "novembre", "decembre"]
FR_DATE_RE = re.compile(
    r"\b(" + "|".join(FR_DAYS) + r")\s+(\d{1,2})(?:er)?\s+(" + "|".join(FR_MONTHS) + r")\s+(\d{4})\b")
EN_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
             "august", "september", "october", "november", "december"]

# ---------------------------------------------------------------- helpers
report_lines = []
issues = []          # rows for audit_issues.csv
results = []         # (check, status, detail)


def say(s=""):
    print(s)
    report_lines.append(s)


def issue(check, jur, bill_key, date, problem, detail=""):
    issues.append({"check": check, "jurisdiction": jur, "bill_key": bill_key,
                   "date": date, "problem": problem, "detail": str(detail)[:500]})


def verdict(check, ok, detail):
    status = "PASS" if ok else "FAIL"
    results.append((check, status, detail))
    say(f"  [{status}] {check}: {detail}")


def info(check, detail):
    results.append((check, "INFO", detail))
    say(f"  [INFO] {check}: {detail}")


def load(p, required=True):
    if not Path(p).exists():
        if required:
            say(f"  MISSING FILE: {p}")
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def valid_iso(d):
    if not isinstance(d, str) or not ISO_RE.match(d):
        return False
    try:
        dt.date.fromisoformat(d)
        return True
    except ValueError:
        return False


def ymd8_to_iso(s):
    s = str(s)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.match(r"^\d{8}$", s) else s


def date_from_url(url):
    """Pull the sitting date out of the URL string itself (method 2)."""
    if not url:
        return ""
    m = re.search(r"/(\d{4}-\d{2}-\d{2})/hansard", url)                     # Ontario
    if m:
        return m.group(1)
    m = re.search(r"/journal-debats/(\d{8})/", url)                         # Quebec
    if m:
        return ymd8_to_iso(m.group(1))
    m = re.search(r"CREC-(\d{4}-\d{2}-\d{2})", url)                         # US daily
    if m:
        return m.group(1)
    return ""


def parse_fr_date(text):
    """French long date -> (iso, weekday_name). Uses first match."""
    t = strip_accents(text)
    m = FR_DATE_RE.search(t)
    if not m:
        return None, None
    day, d, mon, y = m.group(1), int(m.group(2)), FR_MONTHS.index(m.group(3)) + 1, int(m.group(4))
    try:
        return dt.date(y, mon, d).isoformat(), day
    except ValueError:
        return None, day


def parse_en_date(text):
    m = re.search(r"\b(" + "|".join(EN_MONTHS) + r")\s+(\d{1,2}),\s+(\d{4})", text.lower())
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), EN_MONTHS.index(m.group(1)) + 1, int(m.group(2))).isoformat()
    except ValueError:
        return None


def examples(lst, n=8):
    return ", ".join(map(str, list(lst)[:n])) + (" ..." if len(lst) > n else "")


# ---------------------------------------------------------------- load
say("=" * 78)
say(f"FACTUALITY AUDIT  {dt.datetime.now():%Y-%m-%d %H:%M}")
say("=" * 78)

preds, sents = {}, {}
for j in ("us", "ontario", "quebec"):
    preds[j] = load(P["pred"](j)) or []
    sents[j] = load(P["sent"](j)) or []
    say(f"Loaded {j}: {len(preds[j]):,} predications, {len(sents[j]):,} sentences")

us_plan = load(P["us_plan"]) or []
us_index = load(P["us_index"]) or []
us_missing = load(P["us_missing"], required=False) or []
on_segs = load(P["on_segs"]) or {}
on_fsob = load(P["on_fsob"]) or {}
on_bills = load(P["on_bills"], required=False) or []
qc_index = load(P["qc_index"]) or []
qc_health = load(P["qc_health"]) or []
say(f"US plan entries {len(us_plan)}, US index entries {len(us_index)}, "
    f"Ontario segment bills {len(on_segs)}, Quebec index entries {len(qc_index)}")

# ============================================================ A. formats
say("\n" + "-" * 78 + "\nA. bill_key / session / date format\n" + "-" * 78)
for j in ("us", "ontario", "quebec"):
    bad_key, bad_date, bad_sess = [], [], []
    for p in preds[j]:
        bk, d, s = p.get("bill_key", ""), p.get("date", ""), str(p.get("session", ""))
        m = KEY_RE[j].match(bk or "")
        if not m:
            bad_key.append(bk)
            continue
        if not valid_iso(d):
            bad_date.append((bk, d))
        prefix = m.group(1)
        if s != prefix:
            bad_sess.append((bk, s))
    verdict(f"A1 {j} predication bill_key format", not bad_key,
            f"{len(bad_key)} bad of {len(preds[j]):,}" + (f" e.g. {examples(set(bad_key))}" if bad_key else ""))
    verdict(f"A2 {j} predication date is a real ISO date", not bad_date,
            f"{len(bad_date)} bad" + (f" e.g. {examples(bad_date)}" if bad_date else ""))
    verdict(f"A3 {j} predication session matches bill_key prefix", not bad_sess,
            f"{len(bad_sess)} mismatched" + (f" e.g. {examples(Counter(bad_sess).most_common(8))}" if bad_sess else ""))
    for bk, d in bad_date[:200]:
        issue("A2", j, bk, d, "invalid date on predication")
    for bk, s in list(Counter(bad_sess))[:200]:
        issue("A3", j, bk, "", "session field does not match bill_key", s)

# ============================================================ B. pred -> sentence join
say("\n" + "-" * 78 + "\nB. predication -> sentence join (independent source for bill_key/date)\n" + "-" * 78)
for j in ("us", "ontario", "quebec"):
    if not sents[j]:
        verdict(f"B {j}", False, "no sentences file")
        continue
    sid_field = "sentence_id" if "sentence_id" in sents[j][0] else ("id" if "id" in sents[j][0] else None)
    if sid_field is None:
        verdict(f"B {j} sentence id field", False, f"sentence keys: {list(sents[j][0].keys())}")
        continue
    smap = {s[sid_field]: (s.get("bill_key", ""), s.get("date", ""), str(s.get("session", ""))) for s in sents[j]}
    orphan, bk_mis, date_mis, sess_mis, id_mis = 0, [], [], [], []
    for p in preds[j]:
        sid = p.get("sentence_id")
        rec = smap.get(sid)
        if rec is None:
            orphan += 1
            continue
        if rec[0] != p.get("bill_key"):
            bk_mis.append((sid, p.get("bill_key"), rec[0]))
        if rec[1] != p.get("date"):
            date_mis.append((sid, p.get("date"), rec[1]))
        if rec[2] != str(p.get("session", "")):
            sess_mis.append((sid, p.get("session"), rec[2]))
        if isinstance(sid, str) and p.get("bill_key") and p["bill_key"] not in sid:
            id_mis.append((sid, p.get("bill_key")))
    verdict(f"B1 {j} every predication has its sentence", orphan == 0, f"{orphan} orphans")
    verdict(f"B2 {j} predication bill_key == sentence bill_key", not bk_mis,
            f"{len(bk_mis)} mismatches" + (f" e.g. {examples(bk_mis, 3)}" if bk_mis else ""))
    verdict(f"B3 {j} predication date == sentence date", not date_mis,
            f"{len(date_mis)} mismatches" + (f" e.g. {examples(date_mis, 3)}" if date_mis else ""))
    verdict(f"B4 {j} predication session == sentence session", not sess_mis, f"{len(sess_mis)} mismatches")
    verdict(f"B5 {j} sentence_id string contains bill_key", not id_mis,
            f"{len(id_mis)} mismatches" + (f" e.g. {examples(id_mis, 3)}" if id_mis else ""))
    for x in (bk_mis + date_mis)[:300]:
        issue("B", j, x[1], "", "predication disagrees with its sentence", x)
    # the same sentence stored twice (a bill-day read twice) counts its claims twice
    sid_counts = Counter(s[sid_field] for s in sents[j])
    dup_ids = [(k, n) for k, n in sid_counts.items() if n > 1]
    dup_days = sorted({"|".join(str(k).split("|")[1:3]) for k, _ in dup_ids})
    verdict(f"B6 {j} every sentence is stored once", not dup_ids,
            f"{sum(n - 1 for _, n in dup_ids):,} extra copies on {len(dup_days)} bill-day(s)"
            + (f" e.g. {examples(dup_days, 5)}" if dup_days else ""))
    for d in dup_days[:200]:
        issue("B6", j, d.split("|")[0], d.split("|")[-1], "sentences stored more than once", "")
    del smap, sid_counts

# ============================================================ transcript index maps
# (bill_key, iso_date) -> dict(url_full_day, urls, printed_dates, session_in_url, ...)
idx = {"us": {}, "ontario": {}, "quebec": {}}

GRANULE_RE = re.compile(r"(GPO-CRECB-\d{4}-pt\d+(?:-\d+)*|CREC-\d{4}-\d{2}-\d{2}-pt\d+-Pg[A-Za-z0-9-]+)")
US_HDR_RE = re.compile(r"\((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
                       r"([A-Z][a-z]+ \d{1,2}, \d{4})\)")


def us_units(e):
    """Granule records from a US index entry, whatever shape the index uses.
    Accepts units as a list of dicts, a list of IDs, or a plain count (then IDs
    are looked for in every other field). Never reads the 'excluded' field."""
    found = {}
    for k, v in e.items():
        if "exclu" in k.lower():
            continue
        vals = v if isinstance(v, list) else [v]
        for x in vals:
            if isinstance(x, dict):
                uid = x.get("id") or x.get("granuleId") or x.get("granule_id")
                if uid:
                    found.setdefault(str(uid), {"id": str(uid), "url": x.get("url", ""),
                                                "printed": x.get("printed") or {}, "title": x.get("title", "")})
            elif isinstance(x, str):
                for uid in GRANULE_RE.findall(x):
                    found.setdefault(uid, {"id": uid, "url": "", "printed": {}, "title": ""})
    return list(found.values())


def us_text_header_date(e):
    """Third method: date printed in the saved debate text itself."""
    f = ROOT / "data" / "us" / str(e.get("file", ""))
    try:
        head = f.read_text(encoding="utf-8", errors="ignore")[:3000]
    except OSError:
        return None, []
    m = US_HDR_RE.search(head)
    return (parse_en_date(m.group(1)) if m else None), GRANULE_RE.findall(head)


if us_index:
    e0 = us_index[0]
    say("\nUS index layout (first entry): " + ", ".join(
        f"{k}:{type(v).__name__}" + (f"[{len(v)}]" if isinstance(v, (list, dict)) else f"={str(v)[:40]!r}")
        for k, v in e0.items()))
    say("US 'units' field types across index: " + str(dict(Counter(type(e.get('units')).__name__ for e in us_index))))

us_no_units = 0
for e in us_index:
    bk, d = e.get("bill_key", ""), e.get("debate_date", "")
    slot = idx["us"].setdefault((bk, d), {"units": [], "date_source": set(), "urls": set(),
                                          "printed": set(), "text_dates": set()})
    slot["date_source"].add(e.get("date_source", ""))
    units = us_units(e)
    tdate, tids = us_text_header_date(e)
    if tdate:
        slot["text_dates"].add(tdate)
    for uid in tids:
        if uid not in {u["id"] for u in units}:
            units.append({"id": uid, "url": "", "printed": {}, "title": ""})
    if not units:
        us_no_units += 1
    for u in units:
        slot["units"].append(u)
        if u.get("url"):
            slot["urls"].add(u["url"])
        pd_ = (u.get("printed") or {}).get("date")
        if pd_:
            slot["printed"].add(pd_)
if us_index:
    say(f"US index entries with no granule ID anywhere (entry or text file): {us_no_units} of {len(us_index)}")

for bk, days in on_segs.items():
    for d, paras in days.items():
        urls = {p.get("url", "") for p in paras}
        sess_api = {str(p.get("session_api", p.get("session", ""))) for p in paras}
        idx["ontario"][(bk, d)] = {"urls": urls, "session_api": sess_api, "n": len(paras)}

for e in qc_index:
    bk, d = e.get("bill_key", ""), ymd8_to_iso(e.get("date", ""))
    slot = idx["quebec"].setdefault((bk, d), {"urls": set(), "sitting_session": set(), "page_ids": set(), "raw": []})
    slot["urls"].add(e.get("url", ""))
    slot["sitting_session"].add(str(e.get("sitting_session", "")))
    if e.get("page_id") is not None:
        slot["page_ids"].add(str(e.get("page_id")))
    slot["raw"].append(e)

# ============================================================ C. predication dates in index
say("\n" + "-" * 78 + "\nC. every predication (bill_key, date) exists in the transcript index\n" + "-" * 78)
for j in ("us", "ontario", "quebec"):
    pairs = Counter((p.get("bill_key"), p.get("date")) for p in preds[j])
    missing = [(k, n) for k, n in pairs.items() if k not in idx[j]]
    n_missing_preds = sum(n for _, n in missing)
    verdict(f"C1 {j} predication bill-dates found in index", not missing,
            f"{len(missing)} of {len(pairs)} bill-dates ({n_missing_preds:,} predications) not in index"
            + (f" e.g. {examples([k for k, _ in missing], 5)}" if missing else ""))
    for (bk, d), n in missing[:500]:
        issue("C1", j, bk, d, "predication date not in transcript index", f"{n} predications")
    # reverse: index bill-dates with no predications (informational)
    no_preds = [k for k in idx[j] if k not in pairs]
    info(f"C2 {j} index bill-dates with zero predications", f"{len(no_preds)} of {len(idx[j])}")
_us_days = Counter((e.get("bill_key"), e.get("debate_date")) for e in us_index)
_rep = sorted(k for k, n in _us_days.items() if n > 1)
verdict("C3 us each bill-day appears once in the transcript index", not _rep,
        f"{len(us_index)} entries, {len(_us_days)} bill-days, {len(_rep)} listed more than once"
        + (f" e.g. {examples(_rep, 5)}" if _rep else ""))

# ============================================================ D. dates, three ways
say("\n" + "-" * 78 + "\nD. sitting dates: index vs URL vs printed/French header vs weekday\n" + "-" * 78)

# --- Ontario
bad_url_date, bad_multi, bad_sess, weekend = [], [], [], []
for (bk, d), s in idx["ontario"].items():
    # OLA publishes some days as two files: .../hansard and .../hansard-1 (both real).
    # Only a missing URL, or URLs pointing at different dates, is a problem.
    real = {u for u in s["urls"] if u}
    if not real or len({date_from_url(u) for u in real}) > 1 or \
            any(not re.search(r"/hansard(-\d+)?$", u) for u in real):
        bad_multi.append((bk, d, sorted(s["urls"])))
    for u in s["urls"]:
        ud = date_from_url(u)
        if ud != d:
            bad_url_date.append((bk, d, u))
        m = re.search(r"/parliament-(\d+)/session-(\d+)/", u or "")
        bill_sess = bk.rsplit("-Bill", 1)[0]
        if m and f"{m.group(1)}-{m.group(2)}" != bill_sess:
            bad_sess.append((bk, d, f"{m.group(1)}-{m.group(2)}"))
    if valid_iso(d) and dt.date.fromisoformat(d).weekday() >= 5:
        weekend.append((bk, d))
_conf = ROOT / "outputs/audit/exclusions_confirmed.json"
_gone = {(e["bill_key"], e["date"]) for e in (json.loads(_conf.read_text(encoding="utf-8")) if _conf.exists() else [])
         if e["jurisdiction"] == "ontario"}
_n_gone = sum(1 for x in bad_url_date if (x[0], x[1]) in _gone)
bad_url_date = [x for x in bad_url_date if (x[0], x[1]) not in _gone]
if _n_gone:
    say(f"  ({_n_gone} Ontario bill-day(s) removed as confirmed exclusions are not counted in D1)")
verdict("D1 ontario URL date == index date", not bad_url_date,
        f"{len(bad_url_date)} mismatches" + (f" e.g. {examples(bad_url_date, 3)}" if bad_url_date else ""))
verdict("D2 ontario every bill-date has Hansard URL(s) for that one date", not bad_multi,
        f"{len(bad_multi)} bill-dates with a missing URL or URLs for different dates"
        + (f" e.g. {examples(bad_multi, 3)}" if bad_multi else ""))
info("D2b ontario days published as two files (hansard + hansard-1)",
     sum(1 for s in idx["ontario"].values() if len({u for u in s["urls"] if u}) > 1))
for x in bad_multi:
    issue("D2", "ontario", x[0], x[1], "missing Hansard URL or URLs for different dates", x[2])
verdict("D3 ontario URL parliament/session == bill session", not bad_sess,
        f"{len(bad_sess)} mismatches" + (f" e.g. {examples(bad_sess, 5)}" if bad_sess else ""))
info("D4 ontario sitting dates on a weekend (Ontario rarely sits weekends; check these)",
     f"{len(weekend)}" + (f" e.g. {examples(weekend, 5)}" if weekend else ""))
for x in bad_url_date: issue("D1", "ontario", x[0], x[1], "URL date differs from index date", x[2])
for x in bad_sess:     issue("D3", "ontario", x[0], x[1], "URL session differs from bill session", x[2])
for x in weekend:      issue("D4", "ontario", x[0], x[1], "weekend sitting date, verify")

# --- Quebec
bad_url_date, bad_sess, no_url, weekend = [], [], [], []
for (bk, d), s in idx["quebec"].items():
    for u in s["urls"]:
        if not u:
            no_url.append((bk, d))
            continue
        ud = date_from_url(u)
        if ud != d:
            bad_url_date.append((bk, d, u))
        m = re.search(r"/assemblee-nationale/(\d+-\d+)/journal-debats/", u)
        if m and m.group(1) not in s["sitting_session"]:
            bad_sess.append((bk, d, m.group(1), sorted(s["sitting_session"])))
    if valid_iso(d) and dt.date.fromisoformat(d).weekday() >= 5:
        weekend.append((bk, d))
verdict("D5 quebec URL date == index date", not bad_url_date,
        f"{len(bad_url_date)} mismatches" + (f" e.g. {examples(bad_url_date, 3)}" if bad_url_date else ""))
verdict("D6 quebec URL session == sitting_session", not bad_sess, f"{len(bad_sess)} mismatches")
verdict("D7 quebec every index entry has a journal URL", not no_url, f"{len(no_url)} missing")
info("D8 quebec weekend sitting dates", f"{len(weekend)}" + (f" e.g. {examples(weekend, 5)}" if weekend else ""))
for x in bad_url_date: issue("D5", "quebec", x[0], x[1], "URL date differs from index date", x[2])
for x in no_url:       issue("D7", "quebec", x[0], x[1], "no journal URL")

# Quebec French header date from cached journal pages (third independent method)
cache_dir = P["qc_cache"]
cache_files = [f for f in glob.glob(str(cache_dir / "**" / "*"), recursive=True) if os.path.isfile(f)]
say(f"  Quebec journal cache files found: {len(cache_files)}")
if cache_files:
    say(f"  cache filename examples: {examples([os.path.relpath(f, cache_dir) for f in cache_files[:5]], 5)}")
by_token = defaultdict(list)
for f in cache_files:
    for tok in re.findall(r"\d{4,}", os.path.basename(f)):
        by_token[tok].append(f)
fr_checked, fr_ok, fr_bad, fr_nodate, fr_wd_bad, fr_nocache = 0, 0, [], 0, [], 0
for (bk, d), s in idx["quebec"].items():
    cands = set()
    for pid in s["page_ids"]:
        cands.update(by_token.get(pid, []))
    for u in s["urls"]:
        m = re.search(r"/(\d{8})/(\d+)\.html", u or "")
        if m:
            cands.update(by_token.get(m.group(2), []))
    if not cands:
        fr_nocache += 1
        continue
    got = None
    for f in sorted(cands):
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read(200_000)
        except OSError:
            continue
        iso, wd = parse_fr_date(txt)
        if iso:
            got = (iso, wd, f)
            break
    if got is None:
        fr_nodate += 1
        continue
    fr_checked += 1
    iso, wd, f = got
    if iso == d:
        fr_ok += 1
    else:
        fr_bad.append((bk, d, iso, os.path.basename(f)))
    if wd and valid_iso(d) and FR_DAYS[dt.date.fromisoformat(d).weekday()] != wd:
        fr_wd_bad.append((bk, d, wd))
if fr_checked:
    verdict("D9 quebec French header date ('Le mardi 5 octobre 2021') == index date", not fr_bad,
            f"{fr_ok} match, {len(fr_bad)} differ, of {fr_checked} checked; "
            f"{fr_nocache} bill-dates had no cached page, {fr_nodate} cached pages had no French date"
            + (f"; e.g. {examples(fr_bad, 3)}" if fr_bad else ""))
    verdict("D10 quebec French weekday matches calendar weekday of index date", not fr_wd_bad,
            f"{len(fr_wd_bad)} mismatches" + (f" e.g. {examples(fr_wd_bad, 3)}" if fr_wd_bad else ""))
else:
    info("D9 quebec French header date", f"could not check: {fr_nocache} bill-dates had no cached page, "
         f"{fr_nodate} had no French date in cache. Send me the cache filename examples above.")
for x in fr_bad:
    issue("D9", "quebec", x[0], x[1], "French header date differs from index date", f"header={x[2]} file={x[3]}")

# --- US
bad_printed, bad_uid, no_printed, weekend, src = [], [], 0, [], Counter()
for (bk, d), s in idx["us"].items():
    for ds in s["date_source"]:
        src[ds] += 1
    printed = s["printed"] | s["text_dates"]
    if printed:
        if d not in printed:
            bad_printed.append((bk, d, sorted(printed)))
    else:
        no_printed += 1
    for u in s["units"]:
        uid = str(u.get("id", ""))
        m = re.match(r"CREC-(\d{4}-\d{2}-\d{2})", uid)
        if m and m.group(1) != d:
            bad_uid.append((bk, d, uid))
        m = re.match(r"GPO-CRECB-(\d{4})-pt", uid)
        if m and m.group(1) != d[:4]:
            bad_uid.append((bk, d, uid))
    if valid_iso(d) and dt.date.fromisoformat(d).weekday() >= 5:
        weekend.append((bk, d))
verdict("D11 us printed 'Congressional Record' header date == debate_date", not bad_printed,
        f"{len(bad_printed)} mismatches, {no_printed} bill-dates with no printed date (bound edition has none)"
        + (f" e.g. {examples(bad_printed, 3)}" if bad_printed else ""))
verdict("D12 us granule ID date/year == debate_date", not bad_uid,
        f"{len(bad_uid)} mismatches" + (f" e.g. {examples(bad_uid, 3)}" if bad_uid else ""))
info("D13 us debate_date source (vote_date = same day as vote; minus_k = k days before)", dict(src))
info("D14 us weekend debate dates (House does sit some weekends, e.g. 2010-03-21)",
     f"{len(weekend)}" + (f" e.g. {examples(weekend, 5)}" if weekend else ""))
for x in bad_printed: issue("D11", "us", x[0], x[1], "printed header date differs", x[2])
for x in bad_uid:     issue("D12", "us", x[0], x[1], "granule id date differs", x[2])

# ============================================================ E. outcomes
say("\n" + "-" * 78 + "\nE. outcomes\n" + "-" * 78)
# US: multiple votes per bill_key
by_bk = defaultdict(list)
for e in us_plan:
    by_bk[e.get("bill_key", "")].append(e)
dups = {k: v for k, v in by_bk.items() if len(v) > 1}
conflict = {k: v for k, v in dups.items() if len({(x.get("result") or "") for x in v}) > 1}
info("E1 us plan entries vs unique bill_keys",
     f"{len(us_plan)} entries, {len(by_bk)} unique bills, {len(dups)} bills have 2+ votes")
info("E2 us bills whose plan.json votes differ (raw file; outcome now decided in E6)",
        f"{len(conflict)} bills" + (f" e.g. {examples(list(conflict), 6)}" if conflict else ""))
for k, v in conflict.items():
    issue("E2", "us", k, "", "multiple votes with different results",
          "; ".join(f"{x.get('vote_date')}:{x.get('result') or 'BLANK'}" for x in sorted(v, key=lambda x: x.get("vote_date", ""))))
us_pred_keys = {p["bill_key"] for p in preds["us"]}
no_result = [k for k in us_pred_keys if not any((x.get("result") or "").strip() for x in by_bk.get(k, []))]
info("E3 us predicated bills with no result in plan.json (raw file; see E6 for the final outcome)",
        f"{len(no_result)} of {len(us_pred_keys)}" + (f" e.g. {examples(sorted(no_result))}" if no_result else ""))
for k in no_result:
    issue("E3", "us", k, "", "no vote result recorded", by_bk.get(k, [{}])[0].get("source", ""))

# Ontario
fsob_keys, fsob_by_num = {}, defaultdict(list)
fsob_sessions = set(on_fsob.keys())
fsob_nrec = {k: len(v.get("records", [])) for k, v in on_fsob.items()}
for sk, sd in on_fsob.items():
    for r in sd.get("records", []):
        try:
            n = int(r.get("bill_number"))
        except (TypeError, ValueError):
            continue
        fsob_keys[f"{sk}-Bill{n}"] = r
        fsob_by_num[n].append(sk)
on_pred_keys = sorted({p["bill_key"] for p in preds["ontario"]})
on_missing = [k for k in on_pred_keys if k not in fsob_keys]
info("E4 ontario predicated bills in ontario_fsob_votes.json (raw file; see E6 for the final outcome)",
        f"{len(on_pred_keys) - len(on_missing)} found, {len(on_missing)} missing")
why = Counter()
for k in on_missing:
    sess = k.rsplit("-Bill", 1)[0]
    n = int(k.rsplit("-Bill", 1)[1])
    if sess not in fsob_sessions:
        reason = "session not in fsob file at all"
    elif fsob_nrec.get(sess, 0) == 0:
        reason = "session in fsob file but has 0 records"
    elif fsob_by_num.get(n):
        reason = f"same bill number found under other session(s): {','.join(sorted(set(fsob_by_num[n])))}"
    else:
        reason = "session has records, this bill has none (likely never reached a recorded vote)"
    why[reason.split(":")[0]] += 1
    issue("E4", "ontario", k, "", "no outcome", reason)
for r, n in why.most_common():
    say(f"      {n:>4}  {r}")
missing_sessions = Counter(k.rsplit("-Bill", 1)[0] for k in on_missing)
say(f"      missing by session: {dict(sorted(missing_sessions.items()))}")
say(f"      fsob records by session: {dict(sorted(fsob_nrec.items()))}")

# Quebec
qc_keys = {}
for e in qc_health:
    try:
        qc_keys[f"{e.get('session', '')}-Bill{int(e.get('bill_number'))}"] = e
    except (TypeError, ValueError):
        pass
qc_pred_keys = sorted({p["bill_key"] for p in preds["quebec"]})
qc_out_field = Counter()
qc_no_outcome = []
for k in qc_pred_keys:
    e = qc_keys.get(k)
    if e is None:
        qc_no_outcome.append((k, "not in quebec_health_bills_combined.json"))
        continue
    val = e.get("outcome", e.get("result", ""))
    qc_out_field[(e.get("source", ""), bool(val))] += 1
    if not val:
        qc_no_outcome.append((k, f"no outcome field (source={e.get('source', '')})"))
info("E5 quebec predicated bills with an outcome in the combined bill list (raw file; see E6)",
        f"{len(qc_pred_keys) - len(qc_no_outcome)} found, {len(qc_no_outcome)} missing")
say(f"      (source, has_outcome) counts: {dict(qc_out_field)}")
say(f"      quebec combined-file keys: {examples(list(qc_keys)[:1], 1)} ; available fields: "
    f"{sorted(set().union(*[set(e.keys()) for e in qc_health])) if qc_health else []}")
for k, why_ in qc_no_outcome:
    issue("E5", "quebec", k, "", "no outcome", why_)

# ============================================================ F. health list membership
say("\n" + "-" * 78 + "\nF. every predicated bill is on the health bill list\n" + "-" * 78)
us_not = sorted(us_pred_keys - set(by_bk))
verdict("F1 us predicated bills in plan.json", not us_not, f"{len(us_not)} not in plan" + (f" e.g. {examples(us_not)}" if us_not else ""))
on_not = [k for k in on_pred_keys if k not in on_segs]
verdict("F2 ontario predicated bills in hansard_segments_v3.json", not on_not, f"{len(on_not)} not in segments")
# The v3 rebuild defines Ontario health bills in bills_master.json (lexicon and/or
# old index). ontario_bill_index.json's health_tag is the older definition.
on_master = load(ROOT / "data" / "canada" / "ontario" / "v3" / "bills_master.json", required=False) or {}
health_on = {k for k, v in on_master.items() if v.get("health")}
if on_master:
    not_h = [k for k in on_pred_keys if k in on_master and not on_master[k].get("health")]
    not_in = [k for k in on_pred_keys if k not in on_master]
    verdict("F3 ontario predicated bills are health=True in bills_master.json (v3 definition)",
            not not_h and not not_in, f"{len(not_h)} health=False, {len(not_in)} not in master")
    info("F3b health_basis of predicated Ontario bills",
         dict(Counter(on_master[k].get("health_basis", "") for k in on_pred_keys if k in on_master)))
    for k in not_h + not_in:
        issue("F3", "ontario", k, "", "not health=True in bills_master.json")
else:
    verdict("F3 ontario bills_master.json", False, "file not found")
qc_not = [k for k in qc_pred_keys if k not in qc_keys]
verdict("F4 quebec predicated bills in quebec_health_bills_combined.json", not qc_not,
        f"{len(qc_not)} not in list" + (f" e.g. {examples(qc_not)}" if qc_not else ""))
for k in us_not: issue("F1", "us", k, "", "not in plan.json")
for k in on_not: issue("F2", "ontario", k, "", "not in hansard_segments_v3.json")
for k in qc_not: issue("F4", "quebec", k, "", "not in health list")

# ============================================================ G. coverage
say("\n" + "-" * 78 + "\nG. health bills with no transcript at all\n" + "-" * 78)
us_idx_keys = {k for k, _ in idx["us"]}
info("G1 us plan bills with no debate transcript", f"{len(set(by_bk) - us_idx_keys)} of {len(by_bk)}; "
     f"segments_missing.json has {len(us_missing)} entries")
qc_idx_keys = {k for k, _ in idx["quebec"]}
info("G2 quebec health bills with no journal transcript", f"{len(set(qc_keys) - qc_idx_keys)} of {len(qc_keys)}")
if health_on:
    info("G3 ontario health bills (bills_master) with no Hansard segments",
         f"{len(health_on - set(on_segs))} of {len(health_on)}")
for k in sorted(set(by_bk) - us_idx_keys):
    issue("G1", "us", k, "", "no transcript found")
for k in sorted(set(qc_keys) - qc_idx_keys):
    issue("G2", "quebec", k, "", "no transcript found", qc_keys[k].get("source", ""))

# ============================================================ E6. unified outcomes
say("\n" + "-" * 78 + "\nE6. unified outcomes (data/v3_outcomes.json from outcomes_v3.py)\n" + "-" * 78)
uo = load(ROOT / "data" / "v3_outcomes.json", required=False)
if uo is None:
    info("E6", "data/v3_outcomes.json not found. Run scripts/v3/outcomes_v3.py first.")
else:
    for j, pk in (("us", us_pred_keys), ("ontario", set(on_pred_keys)), ("quebec", set(qc_pred_keys))):
        t = uo.get(j, {})
        have = [k for k in pk if t.get(k, {}).get("passed") is not None]
        dis = [k for k in pk if "DISAGREE" in str(t.get(k, {}).get("check", ""))]
        pend = [k for k in pk if k not in have and "running" in str(t.get(k, {}).get("outcome_raw", ""))]
        verdict(f"E6 {j} predicated bills with a pass/fail outcome (or pending: session still running)",
                len(have) + len(pend) == len(pk),
                f"{len(have)} of {len(pk)}, pending {len(pend)} (passed {sum(t[k]['passed'] == 1 for k in have)}, "
                f"not passed {sum(t[k]['passed'] == 0 for k in have)}); sources "
                f"{dict(Counter(t[k].get('source', '') for k in have))}")
        verdict(f"E7 {j} outcome agrees with its second source", not dis,
                f"{len(dis)} disagree" + (f" e.g. {examples(sorted(dis))}" if dis else ""))
        for k in sorted(set(pk) - set(have) - set(pend)):
            issue("E6", j, k, "", "no pass/fail outcome in v3_outcomes.json", t.get(k, {}).get("outcome_raw", ""))
        for k in dis:
            issue("E7", j, k, "", "outcome sources disagree", t[k].get("check", ""))

# ============================================================ H. US text readability
say("\n" + "-" * 78 + "\nH. US debate text: readable English or scrambled columns? (per 150-word window)\n" + "-" * 78)
# Method 1: the pipeline's own record of where each bound day's text came from
#           (data/us/v3/cache/bound_text/{day}.json: source + interleave_rate).
# Method 2 (independent): in each 150-word window, the share of adjacent word pairs
#           that are common Congressional Record pairs ("of the", "I yield"), divided by
#           the same share after shuffling that window's own words. Real prose scores
#           several times its shuffle; scrambled text scores about the same as its
#           shuffle (ratio near 1). Lists and bill text keep their word order, so they
#           are not penalised for unusual vocabulary.
import random as _rnd
WORD = re.compile(r"[A-Za-z]+")
WIN, CUT = 150, 1.5


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _dehyph(s):   # PATCHED_SENTENCE_JOINS_2026_10_06: words joined again across a column break (para_join.py)
    return re.sub(r"(?<=[A-Za-z])- (?=[a-z])", "", s)


def file_text(fp):
    try:
        return norm_ws(Path(fp).read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return ""


us_files = [(e.get("bill_key", ""), e.get("debate_date", ""), e.get("edition", ""),
             ROOT / "data" / "us" / str(e.get("file", ""))) for e in us_index]
daily = sorted([x for x in us_files if x[2] != "bound" and x[1] >= "1995-01-01"], key=lambda x: str(x[3]))
ref, ctl = daily[0::2][:80], daily[1::2]
bc = Counter()
for _, _, _, fp in ref:
    w = [m.group(0).lower() for m in WORD.finditer(file_text(fp))][:40_000]
    bc.update(zip(w, w[1:]))
common = {b for b, _ in bc.most_common(3000)}


def share(words):
    pairs = list(zip(words, words[1:]))
    return sum(p in common for p in pairs) / len(pairs) if pairs else 0.0


def windows(text):
    """Yields (char_start, char_end, ratio or None)."""
    toks = [(m.start(), m.end(), m.group(0).lower()) for m in WORD.finditer(text)]
    rng = _rnd.Random(13)
    for i in range(0, len(toks) - 40, WIN):
        chunk = toks[i:i + WIN]
        words = [t[2] for t in chunk]
        obs = share(words)
        shuf = 0.0
        for _ in range(3):
            s = words[:]
            rng.shuffle(s)
            shuf += share(s) / 3
        ratio = None if (obs < 0.03 and shuf < 0.03) else obs / max(shuf, 0.005)
        yield chunk[0][0], chunk[-1][1], ratio


if not common:
    info("H", "no daily-edition files found to build the reference; check skipped")
else:
    ctl_r = sorted(r for _, _, _, fp in ctl for _, _, r in windows(file_text(fp)) if r is not None)
    if ctl_r:
        pc = lambda q: ctl_r[min(len(ctl_r) - 1, int(len(ctl_r) * q))]
        fp_rate = sum(r < CUT for r in ctl_r) / len(ctl_r)
        say(f"  clean control windows ({len(ctl_r):,} from {len(ctl)} daily files): 1st pct {pc(0.01):.2f}, "
            f"5th pct {pc(0.05):.2f}, median {pc(0.5):.2f}. Cutoff {CUT} flags {fp_rate:.2%} of clean windows "
            f"(expected false-positive rate).")
    # synthetic check that the method catches scrambling: shuffle a clean file's words
    if ctl:
        t0 = file_text(ctl[0][3])
        w0 = t0.split()
        _rnd.Random(5).shuffle(w0)
        rs = [r for _, _, r in windows(" ".join(w0)) if r is not None]
        say(f"  self-test: a clean file with its words shuffled -> {sum(r < CUT for r in rs)} of {len(rs)} windows flagged")
    bt_dir = ROOT / "data" / "us" / "v3" / "cache" / "bound_text"
    preds_by_bd = defaultdict(list)
    for p in preds["us"]:
        preds_by_bd[(p.get("bill_key"), p.get("date"))].append(p)
    qrows, prow, tab = [], [], Counter()
    for bk, d, ed, fp in us_files:
        text = file_text(fp)
        wins = list(windows(text))
        bad = [(a, b) for a, b, r in wins if r is not None and r < CUT]
        scored = [r for _, _, r in wins if r is not None]
        src, rate_ = "", ""
        if ed == "bound":
            c = load(bt_dir / f"{d}.json", required=False)
            src, rate_ = (c.get("source", ""), c.get("interleave_rate", "")) if c else ("no cache record", "")
        n_in, n_nf = 0, 0
        for p in preds_by_bd.get((bk, d), []):
            key = norm_ws(p.get("full_text", ""))[:80]
            pos = text.find(key) if key else -1
            if pos < 0 and key:
                pos = _dehyph(text).find(_dehyph(key))
            if pos < 0:
                flag = "?"
                n_nf += 1
            else:
                flag = "Y" if any(a <= pos <= b for a, b in bad) else "N"
                n_in += flag == "Y"
            prow.append({"sentence_id": p.get("sentence_id", ""), "bill_key": bk, "date": d, "edition": ed,
                         "in_scrambled_text": flag})
        pct = len(bad) / len(scored) if scored else 0.0
        qrows.append({"bill_key": bk, "debate_date": d, "edition": ed, "pipeline_text_source": src,
                      "pipeline_interleave_rate": rate_, "windows_scored": len(scored), "windows_scrambled": len(bad),
                      "pct_scrambled": round(pct, 3), "predications": len(preds_by_bd.get((bk, d), [])),
                      "predications_in_scrambled_text": n_in, "predications_not_located": n_nf,
                      "flag_scrambled": "Y" if pct >= 0.10 else ("?" if not scored else "N")})
        tab[(ed or "?", src or "-", "10%+ scrambled" if pct >= 0.10 else ("some" if bad else ("none" if scored else "unscored")))] += 1
    for ed in sorted({r["edition"] for r in qrows}):
        rs = [r for r in qrows if r["edition"] == ed]
        n_p = sum(r["predications"] for r in rs)
        n_b = sum(r["predications_in_scrambled_text"] for r in rs)
        n_nf = sum(r["predications_not_located"] for r in rs)
        # pass when no bill-day is 10%+ scrambled, every predication is found in its text, and the
        # share of predications in flagged windows is within twice the test's false-alarm rate on
        # known-clean text (0.10%): at that level the flags are the test's own noise
        ok_h = (sum(r['flag_scrambled'] == 'Y' for r in rs) == 0 and n_nf == 0
                and (n_b / n_p if n_p else 0) <= 0.002)
        verdict(f"H1 us {ed or '?'} edition: text readable (flags at or below the test's false-alarm rate)", ok_h,
                f"{n_b:,} of {n_p:,} ({(n_b / n_p if n_p else 0):.1%}); bill-days 10%+ scrambled: "
                f"{sum(r['flag_scrambled'] == 'Y' for r in rs)} of {len(rs)}; predications not located in text: {n_nf:,}")
    say("  cross-check, (edition, pipeline text source, method-2 result) -> bill-days:")
    for k, n in sorted(tab.items()):
        say(f"      {n:>4}  {k}")
    for name, rows in (("us_text_quality.csv", qrows), ("us_predication_text_flags.csv", prow)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    say(f"  wrote {OUT / 'us_text_quality.csv'} (per bill-day) and {OUT / 'us_predication_text_flags.csv'} (per predication)")
    for r in qrows:
        if r["flag_scrambled"] == "Y":
            issue("H1", "us", r["bill_key"], r["debate_date"], "10%+ of text scrambled",
                  f"{r['pct_scrambled']:.0%} of windows; {r['predications_in_scrambled_text']} predications affected")

# ============================================================ I. each section names its own bill
say("\n" + "-" * 78 + "\nI. each bill-day section names its own bill (number, or title words in the heading)\n" + "-" * 78)
STOP = {"an", "act", "acts", "to", "the", "of", "and", "amend", "amending", "respecting", "certain", "in", "for",
        "a", "on", "with", "by", "its", "their", "other", "matters", "related", "concernant", "loi", "la", "le",
        "les", "de", "des", "du", "et", "sur", "modifiant", "projet", "no", "bill", "2", "diverses", "dispositions"}


def content_words(s):
    s = strip_accents(s or "")
    return {w for w in re.findall(r"[a-z]{3,}", s) if w not in STOP}


def title_match(title, headings):
    """title may be one title or a list (long title, short title); any one matching is enough."""
    h = content_words(" ".join(headings))
    for one in (title if isinstance(title, (list, tuple)) else [title]):
        t = content_words(one)
        if t and len(t & h) / len(t) >= 0.6:
            return True
    return False


def ola_short_title(bk):
    """Short title from the <title> of the bill's cached OLA status page (an official source separate
    from bills_master), e.g. 'Fair Municipal Finance Act, 1997 (No. 2)'. Hansard headings use it."""
    p = ROOT / "data" / "v3_status_cache" / "ontario" / f"{bk}.html"
    if not p.exists():
        return ""
    m = re.search(r"<title>\s*Bill\s+\d+\s*,\s*(.+?)\s+-\s+Legislative Assembly",
                  p.read_text(encoding="utf-8", errors="ignore"), re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


EXCL = []
if (ROOT / "outputs/audit/exclusions_confirmed.json").exists():
    with open(ROOT / "outputs/audit/exclusions_confirmed.json", encoding="utf-8") as _f:
        EXCL = json.load(_f)


SECTION_OK = {}
if (ROOT / "data/v3_section_checks.json").exists():
    with open(ROOT / "data/v3_section_checks.json", encoding="utf-8") as _f:
        SECTION_OK = {(c["jurisdiction"], c["bill_key"], c["date"]): c["finding"] for c in json.load(_f)}


def mention_check(jur, rows):
    """rows: list of (bill_key, date, text, headings, title, number_regex)."""
    rows = [r for r in rows if not any(e["jurisdiction"] == jur and e["bill_key"] == r[0]
                                       and e.get("date", "*") in ("*", r[1]) for e in EXCL)]
    ok_num = ok_title = ok_hand = bad = 0
    bad_rows = []
    per_bill = defaultdict(list)
    for bk, d, text, heads, title, rx in rows:
        if rx.search(text):
            ok_num += 1
            per_bill[bk].append(True)
        elif title_match(title, heads):
            ok_title += 1
            per_bill[bk].append(True)
        elif (jur, bk, d) in SECTION_OK:
            ok_hand += 1
            per_bill[bk].append(True)
        else:
            bad += 1
            per_bill[bk].append(False)
            hl = [heads] if isinstance(heads, str) else list(heads or [])
            others = Counter(re.findall(r"\b(?:Bill|H\.\s?R\.|projet de loi(?: n\S{0,3})?)\s*(\d+)", text, re.I))
            bad_rows.append((bk, d, f"title: {str(title[0] if isinstance(title, list) else title)[:70]} | headings: {' / '.join(map(str, hl[:3]))[:150]} | "
                                    f"bill numbers named instead: {dict(others.most_common(5))} | "
                                    f"starts: {' '.join(str(text).split())[:160]}"))
    never = sorted(k for k, v in per_bill.items() if not any(v))
    n = ok_num + ok_title + ok_hand + bad
    verdict(f"I1 {jur} bill-day sections that name their bill", bad == 0,
            f"{n - bad} of {n} ({ok_num} by number, {ok_title} by title words in the heading"
            f"{' (long title or OLA short title)' if jur == 'ontario' else ''}, "
            f"{ok_hand} checked by hand, see data/v3_section_checks.json); {bad} name neither")
    verdict(f"I2 {jur} bills where NO section names the bill", not never,
            f"{len(never)} of {len(per_bill)}" + (f" e.g. {examples(never)}" if never else ""))
    for bk, d, why in bad_rows:
        issue("I1", jur, bk, d, "section names neither the bill number nor its title", why)
    for bk in never:
        issue("I2", jur, bk, "", "no section for this bill names it: likely assigned to the wrong bill")


try:
    rows = []
    for bk, days in on_segs.items():
        n = bk.rsplit("-Bill", 1)[1]
        rx = re.compile(r"\bBill\s+(?:No\.\s*)?" + n + r"\b", re.I)
        title = [(on_master.get(bk) or {}).get("long_title", ""), ola_short_title(bk)]
        for d, paras in days.items():
            text = " ".join(str(p.get("text", "")) for p in paras)
            heads = sorted({str(p.get("topic", "")) for p in paras if p.get("topic")})
            rows.append((bk, d, text, heads, title, rx))
    mention_check("ontario", rows)
except Exception as ex:
    verdict("I ontario", False, f"check could not run: {ex}")

try:
    rows = []
    qc_titles = {k: v.get("title", "") for k, v in qc_keys.items()}
    for e in qc_index:
        bk, d = e.get("bill_key", ""), ymd8_to_iso(e.get("date", ""))
        n = str(e.get("bill_number", ""))
        rx = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[o°º]?\.?\s*)?" + n + r"\b|\bbill\s+" + n + r"\b", re.I)
        try:
            text = strip_accents((ROOT / "data" / "canada" / "quebec_assembly" / e["file"]).read_text(encoding="utf-8"))
        except (OSError, KeyError):
            text = ""
        heads = [e.get("title", "")] + [str(x) for x in (e.get("stages") or {})]
        rows.append((bk, d, text, heads, qc_titles.get(bk, e.get("title", "")), rx))
    mention_check("quebec", rows)
except Exception as ex:
    verdict("I quebec", False, f"check could not run: {ex}")

try:
    rows = []
    PFX = {"hr": r"H\.\s?R\.", "s": r"S\.", "hres": r"H\.\s?Res\.", "hjres": r"H\.\s?J\.\s?Res\.",
           "hconres": r"H\.\s?Con\.\s?Res\.", "sjres": r"S\.\s?J\.\s?Res\.", "sconres": r"S\.\s?Con\.\s?Res\.",
           "sres": r"S\.\s?Res\."}
    for e in us_index:
        t, n = str(e.get("type", "")).lower(), str(e.get("number", ""))
        rx = re.compile(PFX.get(t, re.escape(t)) + r"\s?" + n + r"\b", re.I)
        try:
            text = (ROOT / "data" / "us" / e["file"]).read_text(encoding="utf-8", errors="ignore")
        except (OSError, KeyError):
            text = ""
        rows.append((e.get("bill_key", ""), e.get("debate_date", ""), text, [], "", rx))
    mention_check("us", rows)
except Exception as ex:
    verdict("I us", False, f"check could not run: {ex}")

# ============================================================ write
say("\n" + "=" * 78 + "\nSUMMARY\n" + "=" * 78)
for c, s, d in results:
    if s != "INFO":
        say(f"  {s}  {c}")
nfail = sum(1 for _, s, _ in results if s == "FAIL")
say(f"\n{nfail} FAIL, {sum(1 for _, s, _ in results if s == 'PASS')} PASS, "
    f"{sum(1 for _, s, _ in results if s == 'INFO')} INFO. {len(issues):,} issue rows.")

(OUT / "audit_report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
with open(OUT / "audit_issues.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["check", "jurisdiction", "bill_key", "date", "problem", "detail"])
    w.writeheader()
    w.writerows(issues)
say(f"Wrote {OUT/'audit_report.txt'} and {OUT/'audit_issues.csv'}")
