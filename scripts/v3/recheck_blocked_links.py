#!/usr/bin/env python3
"""
recheck_blocked_links.py
Second check of every link check_links.py could not open (BLOCKED means the site refused
an automated request with HTTP 403/429; it says nothing about whether the page exists).
Each one is checked again by a different route:

  www.ola.org       opened again the way the Ontario status-page download succeeded: a
                    session that first visits the OLA home and bills pages and then asks
                    with a referer, one page every few seconds (OLA_SLEEP, default 4).
                    Bill status pages the pipeline already downloaded from that exact URL
                    with HTTP 200 (data/v3_status_cache/ontario/{bill}.html) count as
                    confirmed without asking again.
  www.congress.gov  Congress.gov does not allow scripts on its bill pages (robots.txt), so
                    the page is not opened. The link is checked against the Congress.gov API
                    record already downloaded for the bill (data/v3_status_cache/us/
                    {bill}.bill.json): the congress, bill type and number in the link must be
                    the ones in that record, and the link must follow the Congress.gov bill
                    page pattern (/bill/113th-congress/house-bill/2668/all-actions).

  CONFIRMED    opened with HTTP 200 and the expected content, or matched the official record
  BROKEN       the site says the page does not exist (404/410), or the link contradicts the record
  UNCONFIRMED  still could not be checked (reason given)

Writes outputs/audit/link_check_2.csv. Safe to stop and rerun: finished checks are kept in
outputs/audit/link_recheck_cache.json and skipped; unconfirmed ones are tried again.
Run from project root:  python3 scripts/v3/recheck_blocked_links.py
"""
import csv, json, os, random, re, sys, time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch_official_status as F      # the browser-like session that downloaded the OLA pages

ROOT = HERE.parent.parent
AUD = ROOT / "outputs" / "audit"
IN = AUD / "link_check.csv"
OUT = AUD / "link_check_2.csv"
CACHE = AUD / "link_recheck_cache.json"
STATUS = ROOT / "data" / "v3_status_cache"
SLEEP = float(os.environ.get("OLA_SLEEP", "4"))

SLUG = {"house-bill": "HR", "senate-bill": "S", "house-resolution": "HRES", "house-joint-resolution": "HJRES",
        "house-concurrent-resolution": "HCONRES", "senate-resolution": "SRES",
        "senate-joint-resolution": "SJRES", "senate-concurrent-resolution": "SCONRES"}
CG_RE = re.compile(r"^https://www\.congress\.gov/bill/(\d+)(st|nd|rd|th)-congress/([a-z-]+)/(\d+)(/all-actions)?/?$")
OLA_BILL = re.compile(r"^https://www\.ola\.org/en/legislative-business/bills/parliament-(\d+)/session-(\d+)/bill-(\d+)/?$")
OLA_HANSARD = re.compile(r"^https://www\.ola\.org/en/legislative-business/house-documents/"
                         r"parliament-(\d+)/session-(\d+)/(\d{4}-\d{2}-\d{2})/hansard(-\d+)?/?$")


def ordinal(n):
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def congress(url):
    m = CG_RE.match(url)
    if not m:
        return "UNCONFIRMED", "not the Congress.gov bill page pattern"
    c, suf, slug, n = int(m.group(1)), m.group(2), m.group(3), int(m.group(4))
    if suf != ordinal(c):
        return "BROKEN", f"'{c}{suf}' is not how Congress.gov writes the {c}{ordinal(c)} Congress"
    if slug not in SLUG:
        return "UNCONFIRMED", f"bill type '{slug}' not recognised"
    bk = f"{c}-{SLUG[slug]}{n}"
    p = STATUS / "us" / f"{bk}.bill.json"
    if not p.exists():
        return "UNCONFIRMED", f"no Congress.gov API record downloaded for {bk}"
    try:
        b = json.loads(p.read_text(encoding="utf-8")).get("bill") or {}
    except ValueError:
        return "UNCONFIRMED", f"API record for {bk} could not be read"
    got = (str(b.get("congress")), str(b.get("type", "")).upper(), str(b.get("number")))
    if got != (str(c), SLUG[slug], str(n)):
        return "BROKEN", f"the API record for {bk} is {' '.join(got)}"
    page = b.get("legislationUrl") or ""
    if page and page.rstrip("/") != re.sub(r"/all-actions/?$", "", url).rstrip("/"):
        return "BROKEN", f"Congress.gov gives the page as {page}"
    return "CONFIRMED", (f"Congress.gov API record {b.get('type')} {b.get('number')}, {c}{suf} Congress"
                         + (" (page URL given by the API matches)" if page else "")
                         + f": {str(b.get('title', ''))[:70]}")


def hansard_paragraphs():
    p = ROOT / "data/canada/ontario/v3/hansard_segments_v3.json"
    n = Counter()
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for dmap in json.load(f).values():
                for paras in dmap.values():
                    for x in paras:
                        if x.get("url"):
                            n[x["url"].split("#")[0]] += 1
    return n


def ola_live(url, state):
    """One polite request through the browser-like session. Returns (status, how) or None
    when the site is refusing and live checks have been stopped."""
    if state["refused"] >= 3:
        return None
    ref = ("https://www.ola.org/en/legislative-business/bills" if OLA_BILL.match(url)
           else "https://www.ola.org/en/legislative-business/house-documents")
    code, body = F.browser_get(url, referer=ref)
    time.sleep(SLEEP + random.random() * 2)
    if code in (403, 429, None):
        state["refused"] += 1
        if code == 429:
            time.sleep(60)
        return "UNCONFIRMED", f"OLA refused this request too (HTTP {code})"
    state["refused"] = 0
    if code in (404, 410):
        return "BROKEN", f"OLA answered HTTP {code} (page not found)"
    if code == 200:
        marker = b"Bill" if OLA_BILL.match(url) else b"Hansard"
        if marker.lower() in (body or b"").lower():
            return "CONFIRMED", f"opened (HTTP 200) and the page is an OLA {marker.decode()} page"
        return "UNCONFIRMED", f"opened (HTTP 200) but the page does not look like an OLA {marker.decode()} page"
    return "UNCONFIRMED", f"OLA answered HTTP {code}"


def main():
    if not IN.exists():
        sys.exit(f"{IN} not found; run check_links.py first")
    with open(IN, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    todo = [r for r in rows if r["status"] != "OK"]
    done = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    paras = hansard_paragraphs()
    state = {"refused": 0}
    results = dict(done)          # only CONFIRMED and BROKEN are kept for a rerun; the rest are tried again
    live = [r for r in todo if r["site"] == "www.ola.org" and r["url"] not in done]
    print(f"{len(todo)} links to check again; {len(done)} already done earlier. "
          f"OLA pages to open: up to {len(live)} (about {len(live) * (SLEEP + 1.5) / 60:.0f} min)", flush=True)
    for i, r in enumerate(todo, 1):
        u = r["url"]
        if u in done:
            continue
        if r["site"] == "www.congress.gov":
            res = congress(u)
        elif r["site"] == "www.ola.org":
            m = OLA_BILL.match(u)
            page = STATUS / "ontario" / (f"{m.group(1)}-{m.group(2)}-Bill{m.group(3)}.html" if m else "_")
            if m and page.exists() and b"Bill" in page.read_bytes():
                res = ("CONFIRMED", "the pipeline downloaded this exact URL with HTTP 200 on "
                       + time.strftime("%Y-%m-%d", time.localtime(page.stat().st_mtime)))
            else:
                res = ola_live(u, state)
                if res is None:
                    res = ("UNCONFIRMED", "not opened: OLA refused 3 requests in a row, live checks stopped")
                if res[0] == "UNCONFIRMED" and OLA_HANSARD.match(u) and paras.get(u):
                    res = (res[0], res[1] + f"; the pipeline took {paras[u]} paragraph(s) of Hansard text from this URL")
        else:
            res = ("UNCONFIRMED", f"first check said {r['status']} {r['http']}; no second route for this site")
        results[u] = list(res)
        if res[0] != "UNCONFIRMED":
            done[u] = list(res)
        if i % 25 == 0:
            CACHE.write_text(json.dumps(done), encoding="utf-8")
            print(f"  {i}/{len(todo)}", flush=True)
    CACHE.write_text(json.dumps(done), encoding="utf-8")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["second_check", "how", "first_check", "site", "url", "used_in (column | sheet row)"])
        order = {"BROKEN": 0, "UNCONFIRMED": 1, "CONFIRMED": 2}
        for r in sorted(rows, key=lambda r: (order.get(results.get(r["url"], ["OK"])[0], 3), r["site"], r["url"])):
            if r["status"] == "OK":
                w.writerow(["OK (first check)", f"opened, HTTP {r['http']}", r["status"], r["site"], r["url"],
                            r.get("used_in (column | sheet row)", "")])
            else:
                s, how = results[r["url"]]
                w.writerow([s, how, f"{r['status']} {r['http']}", r["site"], r["url"],
                            r.get("used_in (column | sheet row)", "")])
    tally = Counter((r["site"], "OK" if r["status"] == "OK" else results[r["url"]][0]) for r in rows)
    print("\nALL LINKS, after both checks:")
    for site in sorted({r["site"] for r in rows}):
        print(f"  {site}: " + ", ".join(f"{s} {n}" for (h, s), n in sorted(tally.items()) if h == site))
    bad = sum(n for (h, s), n in tally.items() if s == "BROKEN")
    unk = sum(n for (h, s), n in tally.items() if s == "UNCONFIRMED")
    print(f"\n{len(rows) - bad - unk} of {len(rows)} links confirmed; {bad} broken; {unk} unconfirmed -> {OUT}")


if __name__ == "__main__":
    main()
