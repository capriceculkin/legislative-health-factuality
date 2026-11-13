#!/usr/bin/env python3
"""
ontario_rebuild.py

Rebuilds the Ontario bill-to-debate assignment from the OLA Hansard API using
procedural anchors plus a per-session topic hash table (David, Sept 24:
"assign by similarity of the hash table").

Why the old approach failed (each one is measured by audit_pipeline.py):
  1. Session keys came from a hand-written date table that was wrong. The archived
     OLA Hansard index and a York University archive both put 33-1 at
     June 4 1985 to Feb 12 1986 and the start of 33-2 at April 22 1986, and the
     API's own session field agreed. Bill numbers restart every session, so a
     wrong session merges two different bills that share a number
     (33-2-Bill124 picked up the Wellington County teachers dispute debate).
  2. Candidate dates came from the old bill index, whose dates were days the
     bill number was MENTIONED. The scraper only fetched those days, so real
     debate days outside the index were never collected, and index days with no
     debate (1986-01-17 for Bill 94) produced nothing.
  3. "Bill N appears somewhere in the paragraph" was accepted as proof of debate,
     so Business of the House statements and Third Readings lists were assigned
     to whichever bill they mentioned.
  4. Three dates per request against a 500-row cap could silently drop paragraphs.

New approach (every step is resumable; rerunning skips finished work):
  probe     about 10 requests that test what the API supports; saves decisions
  discover  finds every procedural anchor ("X moved second reading of Bill 94",
            "Resuming the adjourned debate ... Bill 94", "committee of the whole on
            Bill 94") from 1985 to today, labelling each by the session in its URL
  master    builds the per-session bill list from anchors and flags health bills
            (writes health_bills_review.csv for Joanie and David to confirm)
  fetch     pulls every paragraph under each health bill's own debate headings
  assign    builds the topic hash table per session and assigns paragraphs;
            nothing is ever assigned because a bill number was merely mentioned.
            Only BILL headings (with ACT / LOI / CODE / BILL / STATUTE in them) are
            assigned through the hash. A heading like HOSPITAL RESTRUCTURING can enter
            the hash when the API files an anchor under the wrong heading (Bill 149 on
            1997-09-25), which pulled in weeks of members' statements. Such headings are
            now handled like procedural ones: a paragraph is kept only from a line that
            names the bill ("moved second reading of Bill 149") until the next anchor.
  official-days
            for every official debate or vote day on the bill's OLA status page that has
            no text yet, downloads that day (paragraphs naming the bill, the full day,
            and every heading that day that is this bill's own heading, including year
            and spelling variants) into raw_official/. The next assign run uses them.
  verify    two independent checks per bill-date, plus the running table
  all       runs every step in order (official-days is run separately, then assign again)

Usage (from the repo root, with the venv active):
  python3 scripts/v3/ontario_rebuild.py probe
  python3 scripts/v3/ontario_rebuild.py all
Environment knobs: OLA_SLEEP (seconds between requests, default 12),
OLA_START / OLA_END (default 1985-05-01 to today).
"""
import ast
import csv
import datetime as dt
import os
import re
import sys
import time
from collections import Counter, OrderedDict, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import (rp, load_json, save_json, sha, clean_html, norm_topic, is_procedural_topic, url_session,
                       api_session, find_anchors_en, health_hits, content_tokens, jaccard, github_url, dates_in,
                       lang_heuristic)

try:
    import requests
except ImportError:
    requests = None

SLEEP = float(os.environ.get("OLA_SLEEP", "12"))
START = os.environ.get("OLA_START", "1985-05-01")
END = os.environ.get("OLA_END", dt.date.today().isoformat())

OUT = rp("data", "canada", "ontario", "v3")
PROBE = os.path.join(OUT, "probe.json")
ANCHORS = os.path.join(OUT, "anchors.json")
MASTER = os.path.join(OUT, "bills_master.json")
RAW_DIR = os.path.join(OUT, "raw")
DAY_DIR = os.path.join(OUT, "raw_days")
SEGMENTS = os.path.join(OUT, "hansard_segments_v3.json")
TEXT_DIR = os.path.join(OUT, "bill_texts")
OFFICIAL_DIR = os.path.join(OUT, "raw_official")
STATUS_DIR = rp("data", "v3_status_cache", "ontario")
TABLE = os.path.join(OUT, "ontario_running_table.csv")
OLD_INDEX = rp("data", "canada", "ontario", "ontario_bill_index.json")
FSOB = rp("data", "canada", "ontario", "ontario_fsob_votes.json")
OLD_SCRAPER = rp("scripts", "fetch_ontario_hansard_via_api.py")

CAP = 500  # replaced by the probe's measured cap


# --------------------------------------------------------------------------- API plumbing

def load_api_config():
    """Reuse the endpoint and headers already in scripts/fetch_ontario_hansard_via_api.py."""
    url, headers = os.environ.get("OLA_API_URL"), None
    if os.path.exists(OLD_SCRAPER):
        tree = ast.parse(open(OLD_SCRAPER, encoding="utf-8").read())
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)):
                continue
            try:
                val = ast.literal_eval(node.value)
            except Exception:
                continue
            name = node.targets[0].id.upper()
            if isinstance(val, dict) and "HEADER" in name:
                headers = val
            elif isinstance(val, str) and val.startswith("http") and not url and (
                    "URL" in name or "ENDPOINT" in name or "API" in name):
                url = val
    if not url or not isinstance(headers, dict):
        sys.exit("Could not read API_URL and HEADERS from scripts/fetch_ontario_hansard_via_api.py.\n"
                 "Set OLA_API_URL and make sure HEADERS is a plain dict literal in that file.")
    return url, headers


API_URL, HEADERS = None, None


def _rows_from(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("value", "results", "items", "documents", "hits", "data"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def api(keyword, filt, rows=None, extra=None, _attempt=0):
    global API_URL, HEADERS
    if requests is None:
        sys.exit("pip install requests")
    if API_URL is None:
        API_URL, HEADERS = load_api_config()
    payload = {"keyword": keyword, "filter": filt, "rows": rows or CAP}
    if extra:
        payload.update(extra)
    try:
        r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=120)
    except requests.RequestException as e:
        if _attempt >= 5:
            raise
        wait = 30 * (_attempt + 1)
        print(f"    network error ({e.__class__.__name__}); retry in {wait}s", flush=True)
        time.sleep(wait)
        return api(keyword, filt, rows, extra, _attempt + 1)
    if r.status_code == 429 or r.status_code >= 500:
        if _attempt >= 6:
            r.raise_for_status()
        wait = min(900, 60 * (2 ** _attempt))
        print(f"    HTTP {r.status_code}; waiting {wait}s", flush=True)
        time.sleep(wait)
        return api(keyword, filt, rows, extra, _attempt + 1)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} for filter {filt!r}: {r.text[:300]}")
    time.sleep(SLEEP)
    return _rows_from(r.json())


def window(lo, hi):
    return f"date ge {lo}T00:00:00Z and date le {hi}T23:59:59Z"


def row_text(r):
    return clean_html(r.get("paragraph") or r.get("text") or r.get("content") or "")


def row_date(r):
    return str(r.get("date") or r.get("hansardDate") or "")[:10]


def row_para_url(r):
    return r.get("paraUrl") or r.get("para_url") or ""


def row_session(r):
    return url_session(r.get("url") or "") or url_session(row_para_url(r)) or api_session(r.get("session"))


def row_id(r):
    # PATCHED_ROWID_2026_10_01: the API's own paragraph id. The paraUrl used before is shared by
    # every paragraph of a sitting on many 1993-1997 pages ('.../hansard-1#'), so de-duplication
    # kept one paragraph per page part (check_row_ids.py).
    if r.get("id"):
        return "id:" + str(r["id"])
    return sha(f"{row_para_url(r)}|{r.get('url')}|{row_date(r)}|{row_order(r)}|{row_text(r)}")


def row_order(r):
    # PATCHED_ORDER_2026_10_02: the API id ('19931208-0000512') gives the paragraph's place in the day;
    # paraUrl has no number on pages where every paragraph shares '...#'
    m = re.match(r"^\d{8}-(\d+)$", str(r.get("id") or ""))
    if m:
        return int(m.group(1))
    for k in ("paragraphNumber", "paragraphIndex", "sequence", "order", "position"):
        v = r.get(k)
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            return int(v)
    nums = re.findall(r"\d+", row_para_url(r).split("#")[-1])
    return int(nums[-1]) if nums else 0


def query_complete(keyword, base_filter, lo, hi, capped):
    """Returns every row matching the query between lo and hi. If a window hits the
    row cap, the window is split in half until each piece is under the cap, so
    nothing is silently dropped. A single day that alone exceeds the cap is logged."""
    f = window(lo, hi) if not base_filter else f"({base_filter}) and {window(lo, hi)}"
    rows = api(keyword, f)
    if len(rows) < CAP:
        return rows
    lo_d, hi_d = dt.date.fromisoformat(lo), dt.date.fromisoformat(hi)
    if lo_d >= hi_d:
        capped.append({"date": lo, "keyword": keyword, "filter": base_filter, "rows": len(rows)})
        print(f"    WARNING: {lo} alone reaches the {CAP}-row cap for {keyword!r}; logged", flush=True)
        return rows
    mid = lo_d + (hi_d - lo_d) // 2
    return (query_complete(keyword, base_filter, lo, mid.isoformat(), capped)
            + query_complete(keyword, base_filter, (mid + dt.timedelta(days=1)).isoformat(), hi, capped))


def load_probe():
    global CAP
    p = load_json(PROBE)
    if not p:
        sys.exit("Run the probe step first:  python3 scripts/v3/ontario_rebuild.py probe")
    CAP = int(p["decisions"]["rows_cap"])
    return p


# --------------------------------------------------------------------------- probe

def cmd_probe():
    global CAP
    os.makedirs(OUT, exist_ok=True)
    res = {}

    def attempt(name, fn):
        try:
            res[name] = fn()
        except Exception as e:
            res[name] = {"error": str(e)[:300]}
        print(f"  {name}: {str(res[name])[:700]}\n", flush=True)

    def day_profile(day):
        rows = api("*", window(day, day))
        return {"rows": len(rows), "fields": sorted(rows[0].keys()) if rows else [],
                "typeOfBusiness": Counter(str(r.get("typeOfBusiness")) for r in rows).most_common(8),
                "api_session": Counter(str(r.get("session")) for r in rows).most_common(4),
                "url_session": Counter(str(row_session(r)) for r in rows).most_common(4),
                "topics": Counter(r.get("topic") for r in rows).most_common(12)}

    print("Probing the OLA API (about 10 requests)\n")
    attempt("day_1986_01_14", lambda: day_profile("1986-01-14"))
    attempt("day_2020_03_02", lambda: day_profile("2020-03-02"))
    attempt("row_cap", lambda: {"asked": 1000, "returned": len(api("*", window("1986-01-01", "1986-06-30"),
                                                                     rows=1000))})

    def topic_filter():
        rows = api("*", "topic eq 'HEALTH CARE ACCESSIBILITY ACT'", rows=100)
        return {"rows": len(rows),
                "all_match": bool(rows) and all(norm_topic(r.get("topic")) == "HEALTH CARE ACCESSIBILITY ACT"
                                                for r in rows),
                "dates": sorted({row_date(r) for r in rows})[:25],
                "url_sessions": Counter(str(row_session(r)) for r in rows).most_common(4)}
    attempt("topic_filter", topic_filter)

    def session_filter():
        rows = api("*", "session eq '33-1'", rows=100)
        ds = sorted(row_date(r) for r in rows)
        return {"rows": len(rows), "url_sessions": Counter(str(row_session(r)) for r in rows).most_common(4),
                "date_range": [ds[0], ds[-1]] if ds else None}
    attempt("session_filter", session_filter)

    def phrase():
        rows = api('"second reading of Bill 94"', window("1985-06-04", "1986-02-12"), rows=100)
        hits = sum(bool(re.search(r"second\s+reading\s+of\s+Bill\s+94\b", row_text(r), re.I)) for r in rows)
        return {"rows": len(rows), "containing_phrase": hits}
    attempt("phrase_search", phrase)

    def anchors_week():
        rows = api("reading", window("1986-01-13", "1986-01-21"), rows=500)
        found = []
        for r in rows:
            for a in find_anchors_en(row_text(r), r.get("speaker"), r.get("topic"), r.get("typeOfBusiness")):
                found.append((row_date(r), a["stage"], a["bill_number"], a["strong"], r.get("topic")))
        return {"rows": len(rows), "anchors": sorted(set(found))[:25]}
    attempt("anchors_jan_1986", anchors_week)

    def paging():
        base = api("*", window("1986-01-14", "1986-01-14"), rows=50)
        ids1 = {row_id(r) for r in base}
        out = {}
        for param, val in (("skip", 50), ("start", 50), ("offset", 50), ("page", 2)):
            try:
                pg = api("*", window("1986-01-14", "1986-01-14"), rows=50, extra={param: val})
                out[param] = {"rows": len(pg), "overlap_with_first_page": len(ids1 & {row_id(r) for r in pg})}
            except Exception as e:
                out[param] = {"error": str(e)[:120]}
        return out
    attempt("paging", paging)

    cap = res.get("row_cap", {}).get("returned") if isinstance(res.get("row_cap"), dict) else None
    rows_cap = 1000 if cap and cap >= 1000 else (cap if cap and cap > 0 else 500)
    tf = res.get("topic_filter", {})
    ph = res.get("phrase_search", {})
    phrase_ok = bool(ph.get("rows")) and ph.get("containing_phrase", 0) / max(ph.get("rows", 1), 1) >= 0.8
    decisions = {
        "rows_cap": rows_cap,
        "use_topic_filter": bool(tf.get("all_match")),
        "discovery_keywords": (['"reading of Bill"', '"reading of the following bill"', '"committee of the whole"']
                               if phrase_ok else ["reading", "committee"]),
    }
    res["decisions"] = decisions
    save_json(res, PROBE, indent=1)
    print("DECISIONS")
    print(f"  row cap used for bisection: {rows_cap}")
    print(f"  topic filter works: {decisions['use_topic_filter']} "
          f"({'fetch pulls each heading directly' if decisions['use_topic_filter'] else 'fetch pulls full anchor days instead'})")
    print(f"  discovery keywords: {decisions['discovery_keywords']}")
    d86 = res.get("day_1986_01_14", {})
    if isinstance(d86, dict) and d86.get("url_session"):
        print(f"  1986-01-14 session by URL: {d86['url_session']}  by API field: {d86.get('api_session')}"
              "  (both should say 33-1)")
    print(f"\nSaved {PROBE}. Read the anchors_jan_1986 line: Bill 94 second reading should appear on 1986-01-14.")


# --------------------------------------------------------------------------- discover

def cmd_discover():
    probe = load_probe()
    keywords = probe["decisions"]["discovery_keywords"]
    state = load_json(ANCHORS + ".state", {"done": [], "capped": []})
    anchors = load_json(ANCHORS, [])
    seen = {f"{a['row_id']}|{a['bill_number']}" for a in anchors}
    y0, y1 = int(START[:4]), int(END[:4])
    for kw in keywords:
        for y in range(y0, y1 + 1):
            tag = f"{kw}|{y}"
            if tag in state["done"]:
                continue
            lo, hi = max(START, f"{y}-01-01"), min(END, f"{y}-12-31")
            capped = []
            rows = query_complete(kw, None, lo, hi, capped)
            new = 0
            for r in rows:
                text = row_text(r)
                for a in find_anchors_en(text, r.get("speaker"), r.get("topic"), r.get("typeOfBusiness")):
                    rid = row_id(r)
                    k = f"{rid}|{a['bill_number']}"
                    if k in seen:
                        continue
                    seen.add(k)
                    anchors.append({
                        "row_id": rid, "session": row_session(r),
                        "session_from_url": url_session(r.get("url") or ""),
                        "session_api": api_session(r.get("session")),
                        "bill_number": a["bill_number"], "stage": a["stage"], "strong": a["strong"],
                        "date": row_date(r), "topic": r.get("topic") or "", "topic_norm": norm_topic(r.get("topic")),
                        "long_title": a["long_title"], "url": r.get("url") or "", "para_url": row_para_url(r),
                        "speaker": r.get("speaker") or "", "type_of_business": r.get("typeOfBusiness") or "",
                        "text": text[:500]})
                    new += 1
            state["done"].append(tag)
            state["capped"].extend(capped)
            save_json(anchors, ANCHORS)
            save_json(state, ANCHORS + ".state")
            print(f"  {tag}: {len(rows)} rows, {new} new anchors, total {len(anchors)}", flush=True)
    strong = sum(a["strong"] for a in anchors)
    disagree = sum(1 for a in anchors if a["session_from_url"] and a["session_api"]
                   and a["session_from_url"] != a["session_api"])
    print(f"\nAnchors: {len(anchors):,} ({strong:,} strong). URL vs API session disagreements: {disagree}")
    print(f"Single days that exceeded the row cap: {len(state['capped'])} (listed in {ANCHORS}.state)")


# --------------------------------------------------------------------------- master bill list + health flag

def cmd_master():
    anchors = load_json(ANCHORS, [])
    if not anchors:
        sys.exit("No anchors yet. Run discover first.")
    old = load_json(OLD_INDEX, {}) or {}
    bills = {}
    for a in anchors:
        if not a["session"]:
            continue
        key = f"{a['session']}-Bill{a['bill_number']}"
        b = bills.setdefault(key, {"titles": Counter(), "topics": Counter(), "dates": set(), "stages": Counter(),
                                   "strong": 0, "weak": 0, "session": a["session"], "num": a["bill_number"]})
        if a["long_title"]:
            b["titles"][a["long_title"]] += 1
        if a["strong"]:
            b["strong"] += 1
            b["dates"].add(a["date"])
            b["stages"][a["stage"]] += 1
            if not is_procedural_topic(a["topic_norm"]):
                b["topics"][a["topic"]] += 1
        else:
            b["weak"] += 1

    old_health = defaultdict(list)
    for k, v in old.items():
        if v.get("health_tag"):
            old_health[str(v.get("bill_number"))].append((k, v.get("title") or ""))

    out, matched_old = {}, set()
    for key, b in bills.items():
        title = b["titles"].most_common(1)[0][0] if b["titles"] else ""
        topics = [t for t, _ in b["topics"].most_common()]
        lex = health_hits(title + " " + " ".join(topics))
        prior = [ok for ok, ot in old_health.get(str(b["num"]), [])
            if title
            and ok.split('-Bill')[0] == b["session"]
            and jaccard(content_tokens(title), content_tokens(ot)) >= 0.5]
        matched_old.update(prior)
        out[key] = {"bill_key": key, "session": b["session"], "bill_number": b["num"], "long_title": title,
                    "topics": topics, "anchor_dates": sorted(b["dates"]), "stages": dict(b["stages"]),
                    "strong_anchors": b["strong"], "weak_anchors": b["weak"], "health_terms": lex,
                    "old_index_keys": prior, "health": bool(lex) or bool(prior),
                    "health_basis": "both" if lex and prior else "lexicon" if lex else "old_index" if prior else ""}
    save_json(out, MASTER, indent=1)

    review = os.path.join(OUT, "health_bills_review.csv")
    with open(review, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bill_key", "long_title", "debate_headings", "health_basis", "health_terms", "old_index_keys",
                    "anchor_dates", "keep_yes_no"])
        for k, v in sorted(out.items()):
            if v["health"]:
                w.writerow([k, v["long_title"], " | ".join(v["topics"]), v["health_basis"],
                            ", ".join(v["health_terms"]), ", ".join(v["old_index_keys"]),
                            ", ".join(v["anchor_dates"]), ""])
    lost = sorted(k for ks in old_health.values() for k, _ in ks if k not in matched_old)
    lost_path = os.path.join(OUT, "old_health_bills_not_rediscovered.csv")
    with open(lost_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["old_key", "old_title", "old_dates"])
        for k in lost:
            w.writerow([k, old[k].get("title", ""), ", ".join(old[k].get("dates", [])[:10])])
    basis = Counter(v["health_basis"] for v in out.values() if v["health"])
    print(f"Bills with anchors: {len(out):,}. Flagged health: {sum(v['health'] for v in out.values())} {dict(basis)}")
    print(f"Old health-index bills with no matching anchored bill: {len(lost)} (see {lost_path})")
    print(f"Review list for Joanie and David: {review}")


# --------------------------------------------------------------------------- fetch

def fetch_day(d, capped):
    p = os.path.join(DAY_DIR, f"{d}.json")
    if os.path.exists(p):
        return load_json(p, [])
    rows = query_complete("*", None, d, d, capped)
    save_json(rows, p)
    return rows


def cmd_fetch():
    probe = load_probe()
    use_topic = probe["decisions"]["use_topic_filter"]
    master = load_json(MASTER) or sys.exit("Run master first.")
    anchors = load_json(ANCHORS, [])
    proc_days = defaultdict(set)
    all_dates = defaultdict(set)
    for a in anchors:
        if a["strong"] and a["session"] and is_procedural_topic(a["topic_norm"]):
            proc_days[f"{a['session']}-Bill{a['bill_number']}"].add(a["date"])
        if a["session"] and a.get("date"):
            all_dates[f"{a['session']}-Bill{a['bill_number']}"].add(a["date"])
    os.makedirs(RAW_DIR, exist_ok=True)
    health = sorted((k, v) for k, v in master.items() if v["health"])
    capped = []
    for i, (key, b) in enumerate(health, 1):
        path = os.path.join(RAW_DIR, f"{key}.json")
        if os.path.exists(path):
            continue
        rows, dates = [], b["anchor_dates"]
        if dates:
            # window: first to last day the bill is moved or named in a reading, weak lines included,
            # plus 45 days (before 2026-10-01: last FIRM stage + 45 days)
            every = sorted(set(dates) | all_dates.get(key, set()))
            lo = every[0]
            hi = min(END, (dt.date.fromisoformat(every[-1]) + dt.timedelta(days=45)).isoformat())
            if use_topic and b["topics"]:
                # every heading with and without "(CONTINUED)" (before: only "X" -> "X (CONTINUED)")
                variants = set()
                for t in b["topics"]:
                    base = re.sub(r"\s*\(CONTINUED\)\s*$", "", t)
                    variants.update({base, base + " (CONTINUED)"})
                for t in sorted(variants):
                    rows += query_complete("*", "topic eq '" + t.replace("'", "''") + "'", lo, hi, capped)
            else:
                for d in dates:
                    rows += fetch_day(d, capped)
            for d in sorted(proc_days.get(key, ())):
                rows += fetch_day(d, capped)
        uniq = OrderedDict((row_id(r), r) for r in rows)
        save_json(list(uniq.values()), path)
        print(f"  [{i}/{len(health)}] {key}: {len(uniq)} paragraphs from {len(dates)} anchor dates", flush=True)
    save_json(capped, os.path.join(OUT, "fetch_capped_days.json"))
    print(f"Days that alone exceeded the cap during fetch: {len(capped)}")


# --------------------------------------------------------------------------- bill headings

BILL_WORDS = re.compile(r"\b(ACTS?|LOIS?|CODE|BILL|STATUTES?)\b")
_CORE_STOP = {"ACT", "AN", "THE", "OF", "TO", "AND", "FOR", "IN", "ON", "A", "LOI", "DE", "LA", "LE", "LES", "DES", "DU",
              "SUR", "ET", "CONTINUED"}


def bill_like(topic):
    """True for a bill's own debate heading (TOBACCO CONTROL ACT, 2004 / LOI DE 2004 ...), false for
    statement and question headings (HOSPITAL RESTRUCTURING, ABORTION, HEALTH CARE)."""
    return bool(BILL_WORDS.search(str(topic or "").upper()))


def title_core(t):
    """Words of a heading or title that identify the bill: English half only, no year (the year
    changes when a bill is reprinted), no (CONTINUED). Keeps NO. 2 so (No. 2) bills stay distinct."""
    s = str(t or "").upper().split(" / ")[0]
    s = re.sub(r"\(CONTINUED\)", " ", s)
    s = re.sub(r",?\s*\b(?:19|20)\d{2}\b", " ", s)
    return set(re.findall(r"[A-Z0-9]+", s)) - _CORE_STOP


def ola_short_title(key):
    """The bill's short title from the <title> of its cached OLA status page, if any."""
    p = os.path.join(STATUS_DIR, f"{key}.html")
    if not os.path.exists(p):
        return ""
    m = re.search(r"<title>\s*Bill\s+\d+\s*,\s*(.+?)\s+-\s+Legislative Assembly", 
                  open(p, encoding="utf-8", errors="ignore").read(), re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def own_heading(topic, key, b, topic_hash):
    """Is this heading the bill's own debate heading, allowing year and spelling variants?
    Compared with the bill's anchored bill headings and its OLA short title; never a heading
    the topic hash gives to another bill."""
    if not bill_like(topic):
        return False
    o = topic_hash.get((b["session"], norm_topic(topic)))
    if o is not None and str(o) != str(b["bill_number"]):
        return False
    core = title_core(topic)
    if not core:
        return False
    refs = [t for t in b.get("topics", []) if bill_like(t)] + [ola_short_title(key)]
    return any(r and jaccard(core, title_core(r)) >= 0.8 for r in refs)


def official_days(key):
    """date -> (kind, stage text) of House debate and vote days on the bill's OLA status page,
    read by the same parser as compare_debate_days_canada.py."""
    p = os.path.join(STATUS_DIR, f"{key}.html")
    if not os.path.exists(p):
        return {}
    from pathlib import Path
    import compare_debate_days_canada as CC
    return CC.ola_days(Path(p))


# --------------------------------------------------------------------------- official days

def cmd_official_days():
    probe = load_probe()
    use_topic = probe["decisions"]["use_topic_filter"]
    master = load_json(MASTER) or sys.exit("Run master first.")
    seg = load_json(SEGMENTS) or {}
    anchors = load_json(ANCHORS, [])
    topic_hash, _ = build_topic_hash(anchors)
    todo = []
    for key, b in sorted(master.items()):
        if not b["health"]:
            continue
        have = set(seg.get(key, {}))
        for d, (kind, stage) in sorted(official_days(key).items()):
            if d not in have and START <= d <= END:
                todo.append((key, b, d, kind))
    print(f"Official OLA debate/vote days with no text yet: {len(todo)} "
          f"(about {len(todo) * 4 * SLEEP / 60:.0f} min at OLA_SLEEP={SLEEP:g}s)", flush=True)
    capped, found = [], Counter()
    os.makedirs(DAY_DIR, exist_ok=True)
    for i, (key, b, d, kind) in enumerate(todo, 1):
        path = os.path.join(OFFICIAL_DIR, key, f"{d}.json")
        if os.path.exists(path):
            continue
        num = b["bill_number"]
        rows = query_complete(f'"Bill {num}"', None, d, d, capped)
        rows += fetch_day(d, capped)
        mine = sorted({r.get("topic") or "" for r in rows if own_heading(r.get("topic"), key, b, topic_hash)})
        if use_topic:
            for t in mine:
                rows += query_complete("*", "topic eq '" + t.replace("'", "''") + "'", d, d, capped)
        uniq = OrderedDict((row_id(r), r) for r in rows if row_date(r) == d)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        save_json(list(uniq.values()), path)
        named = sum(1 for r in uniq.values() if re.search(r"\bBill\s+(?:No\.\s*)?" + str(num) + r"\b", row_text(r), re.I))
        found["own heading that day" if mine else ("named, no own heading" if named else "not named that day")] += 1
        print(f"  [{i}/{len(todo)}] {key} {d} ({kind}): {len(uniq)} paragraphs that day, {named} name Bill {num}; "
              f"own heading: {mine[:2] or 'none'}", flush=True)
    save_json(capped, os.path.join(OUT, "official_days_capped.json"))
    print(f"Official days fetched: {dict(found)}. Days that alone exceeded the row cap: {len(capped)}")
    print("Now run:  python3 scripts/v3/ontario_rebuild.py assign")


# --------------------------------------------------------------------------- assign

def build_topic_hash(anchors):
    votes = defaultdict(Counter)
    for a in anchors:
        if a["strong"] and a["session"] and not is_procedural_topic(a["topic_norm"]):
            votes[(a["session"], a["topic_norm"])][a["bill_number"]] += 1
    topic_hash, conflicts = {}, []
    for k, c in votes.items():
        (num, n), total = c.most_common(1)[0], sum(c.values())
        if n / total >= 2 / 3:
            topic_hash[k] = num
        else:
            conflicts.append({"session": k[0], "topic": k[1], "votes": dict(c)})
    return topic_hash, conflicts


def fuzzy_owner(nt, sess, keys_by_session, topic_hash):
    toks = set(nt.split())
    scored = sorted(((jaccard(toks, set(k.split())), k) for k in keys_by_session.get(sess, [])), reverse=True)
    if not scored:
        return None, 0.0
    best_s, best_k = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_s >= 0.8 and best_s - second >= 0.1:
        return topic_hash[(sess, best_k)], best_s
    return None, best_s


def cmd_assign():
    master = load_json(MASTER) or sys.exit("Run master first.")
    anchors = load_json(ANCHORS, [])
    topic_hash, conflicts = build_topic_hash(anchors)
    keys_by_session = defaultdict(list)
    for (s, t) in topic_hash:
        keys_by_session[s].append(t)
    segments, stats, unassigned = {}, Counter(), Counter()

    def add(key, day, r, method):
        segments.setdefault(key, {}).setdefault(day, []).append({
            "text": row_text(r), "speaker": r.get("speaker") or "", "topic": r.get("topic") or "",
            "session": row_session(r), "session_api": api_session(r.get("session")),
            "url": r.get("url") or row_para_url(r).split("#")[0],
            "para_url": row_para_url(r), "type_of_business": r.get("typeOfBusiness") or "",
            "assignment_method": method})
        stats[method.split(":")[0]] += 1

    for key, b in sorted(master.items()):
        if not b["health"]:
            continue
        rows = load_json(os.path.join(RAW_DIR, f"{key}.json"))
        if rows is None:
            stats["bills_not_fetched"] += 1
            continue
        num, sess = b["bill_number"], b["session"]
        off_days = set()
        odir = os.path.join(OFFICIAL_DIR, key)
        if os.path.isdir(odir):
            seen_ids = {row_id(r) for r in rows}
            for fn in sorted(os.listdir(odir)):
                if fn.endswith(".json"):
                    off_days.add(fn[:-5])
                    for r in load_json(os.path.join(odir, fn), []) or []:
                        if row_id(r) not in seen_ids:
                            seen_ids.add(row_id(r))
                            rows.append(r)
        rows.sort(key=lambda r: (row_date(r), r.get("url") or row_para_url(r).split("#")[0], row_order(r)))
        groups = OrderedDict()
        for r in rows:
            groups.setdefault((row_date(r), r.get("topic") or ""), []).append(r)
        for (day, topic), group in groups.items():
            nt = norm_topic(topic)
            official = day in off_days
            if is_procedural_topic(nt) or not bill_like(topic):
                # procedural headings, and statement headings such as HOSPITAL RESTRUCTURING: keep a
                # paragraph only from a line that names this bill until the next such line. On an
                # official OLA day for this bill, weak anchors ("Mr Caplan has moved third reading of
                # Bill 8") count too.
                current = None
                for r in group:
                    here = find_anchors_en(row_text(r), r.get("speaker"), topic, r.get("typeOfBusiness"))
                    procedural = is_procedural_topic(nt)
                    # under a non-bill heading, a bill only LISTED in a committee report ("Bill 176, An Act
                    # to amend the Nursing Homes Act.") does not start its debate; a line naming another
                    # bill still ends the current one
                    found = [a for a in here if (a["strong"] or official)
                             and (procedural or a.get("stage") != "list_item")]
                    if found:
                        current = found[0]["bill_number"]
                    elif not procedural and any(str(a["bill_number"]) != str(num) for a in here):
                        current = None
                    if current == num and row_session(r) == sess:
                        add(key, day, r, "anchor_split" + ("" if is_procedural_topic(nt) else ":other_heading")
                            + (":official_day" if official else ""))
                continue
            for r in group:
                rs = row_session(r)
                if rs != sess:
                    stats["dropped_other_session"] += 1
                    continue
                owner, method = topic_hash.get((rs, nt)), "topic_hash_exact"
                if owner is None:
                    owner, score = fuzzy_owner(nt, rs, keys_by_session, topic_hash)
                    method = f"topic_hash_fuzzy:{score:.2f}"
                if owner == num:
                    add(key, day, r, method)
                elif owner is None and official and own_heading(topic, key, b, topic_hash):
                    add(key, day, r, "official_day_heading")
                elif owner is None:
                    stats["unassigned_heading_not_in_hash"] += 1
                    unassigned[(rs, topic)] += 1
                else:
                    stats["heading_belongs_to_other_bill"] += 1

    save_json(segments, SEGMENTS)
    for key, days in segments.items():
        for day, paras in days.items():
            p = os.path.join(TEXT_DIR, key, f"{day}.txt")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n\n".join(x["text"] for x in paras) + "\n")
    with open(os.path.join(OUT, "topic_conflicts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["session", "heading", "anchor_votes_by_bill"])
        for c in conflicts:
            w.writerow([c["session"], c["topic"], c["votes"]])
    with open(os.path.join(OUT, "unassigned_headings.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["session", "heading", "paragraphs"])
        for (s, t), n in unassigned.most_common():
            w.writerow([s, t, n])
    n_days = sum(len(v) for v in segments.values())
    print(f"Assigned bills: {len(segments)}, bill-dates: {n_days}, paragraphs: {sum(stats[k] for k in stats if k in ('anchor_split', 'topic_hash_exact', 'topic_hash_fuzzy', 'official_day_heading'))}")
    print(f"Method counts: {dict(stats)}")
    print(f"Headings claimed by two bills (not used): {len(conflicts)}  -> topic_conflicts.csv")
    print(f"Wrote {SEGMENTS} and per bill-date text files under {TEXT_DIR}")


# --------------------------------------------------------------------------- verify + running table

def cmd_verify():
    master = load_json(MASTER) or {}
    anchors = load_json(ANCHORS, [])
    seg = load_json(SEGMENTS) or sys.exit("Run assign first.")
    old = load_json(OLD_INDEX, {}) or {}
    fsob = load_json(FSOB, {}) or {}

    anchor_days = defaultdict(lambda: defaultdict(set))
    anchored_headings = defaultdict(set)
    for a in anchors:
        if a["strong"] and a["session"]:
            key = f"{a['session']}-Bill{a['bill_number']}"
            anchor_days[key][a["date"]].add(a["stage"])
            if not is_procedural_topic(a["topic_norm"]):
                anchored_headings[key].add(a["topic_norm"])
    fsob_dates = defaultdict(set)
    if isinstance(fsob, dict):
        for ps, data in fsob.items():
            sess = api_session(ps)
            for rec in (data.get("records", []) if isinstance(data, dict) else []):
                n = str(rec.get("bill_number", "")).strip()
                if sess and n.isdigit():
                    fsob_dates[f"{sess}-Bill{int(n)}"] |= dates_in(rec)
    have_fsob_dates = any(fsob_dates.values())

    rows, c = [], Counter()
    for key in sorted(seg):
        b = master.get(key, {})
        old_dates = set()
        for ok in b.get("old_index_keys", []):
            old_dates |= set(old.get(ok, {}).get("dates", []))
        for day in sorted(seg[key]):
            paras = seg[key][day]
            headings = Counter(p["topic"] for p in paras)
            methods = Counter(p["assignment_method"].split(":")[0] for p in paras)
            anchor_today = day in anchor_days[key]
            shared_heading = any(norm_topic(h) in anchored_headings[key] for h in headings)
            check1 = "anchor_on_date" if anchor_today else ("anchored_heading" if shared_heading else "FAIL")
            in_fsob = (day in fsob_dates.get(key, set())) if have_fsob_dates else None
            fr = sum(1 for p in paras if lang_heuristic(p["text"])[0] == "fr")
            c[check1] += 1
            c["in_old_index" if day in old_dates else "not_in_old_index"] += 1
            if in_fsob is not None:
                c["in_fsob" if in_fsob else "not_in_fsob"] += 1
            first = next((p for p in paras if find_anchors_en(p["text"], p["speaker"], p["topic"])), paras[0])
            txt_path = os.path.join(TEXT_DIR, key, f"{day}.txt")
            rows.append({
                "session": b.get("session", key.rsplit("-Bill", 1)[0]), "bill_key": key,
                "bill_number": b.get("bill_number"), "long_title": b.get("long_title", ""),
                "health_basis": b.get("health_basis", ""), "debate_date": day, "n_paragraphs": len(paras),
                "french_paragraphs": fr, "headings": " | ".join(headings), "methods": dict(methods),
                "check1_procedural_evidence": check1,
                "anchor_stages_on_date": ", ".join(sorted(anchor_days[key].get(day, set()))),
                "check2_in_fsob": "" if in_fsob is None else ("Y" if in_fsob else "N"),
                "in_old_index": "Y" if day in old_dates else "N",
                "hansard_url": paras[0]["url"], "first_para_url": first["para_url"],
                "github_text": github_url(txt_path), "excerpt": first["text"][:220]})
    with open(TABLE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bill_key"])
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    print(f"Bill-dates: {n}")
    print(f"CHECK 1 (procedural evidence from the discovery queries, independent of the heading fetch):")
    print(f"   anchor on that date: {c['anchor_on_date']}   shares an anchored heading: {c['anchored_heading']}   "
          f"FAIL: {c['FAIL']}")
    if have_fsob_dates:
        print(f"CHECK 2 (FSOB dates, an outside source): in FSOB {c['in_fsob']}, not in FSOB {c['not_in_fsob']}")
    else:
        print("CHECK 2 unavailable: the FSOB file has no dates in it. Only CHECK 1 has been run, so treat "
              "assignments as checked ONE way until the reading dates are compared by hand for a sample.")
    print(f"Old index overlap (information only): {c['in_old_index']} in, {c['not_in_old_index']} new")
    print(f"Running table: {TABLE}")


def cmd_all():
    cmd_probe()
    cmd_discover()
    cmd_master()
    cmd_fetch()
    cmd_assign()
    cmd_verify()


if __name__ == "__main__":
    cmds = {"probe": cmd_probe, "discover": cmd_discover, "master": cmd_master, "fetch": cmd_fetch,
            "assign": cmd_assign, "verify": cmd_verify, "all": cmd_all, "official-days": cmd_official_days}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit("usage: ontario_rebuild.py " + "|".join(cmds))
    cmds[sys.argv[1]]()
