#!/usr/bin/env python3
"""
find_quebec_pre1994.py

Quebec health bills from 1985 to 1994 (32nd to 34th legislatures) have no debate text in the
data: their Assnat bill pages have no "cheminement", so the rebuild never learns which Journal
des debats pages to read. The Journal pages themselves are online in the same HTML format as
later years (for example 34-1 on 19 June 1991, "Projet de loi 156 Adoption du principe").

This finds those debates directly:
  1. lists the pre-1994 health bills and their sessions, and how they line up with
     quebec_pre1994_vote_outcomes.json
  2. finds every sitting-day page of each session (the session's Journal index, and if that
     gives nothing, by following links between sitting pages)
  3. downloads the pages into the normal Journal cache (only pages not saved yet)
  4. reads every page with the same parser as quebec_rebuild.py and records, for each health
     bill, the days where it has its own numbered heading or procedural anchor, in its own
     session (bill numbers restart every session, so a page of another session never counts)
  5. checks each found day a second, different way: how many of the bill title's words appear
     in the section text

Changes nothing in the existing data. New files only:
  data/canada/quebec_assembly/v3/journal_cache/<session>_<date>_<page>.html   (pages)
  data/canada/quebec_assembly/v3/pre1994/sitting_days.json
  data/canada/quebec_assembly/v3/pre1994/bill_days_found.json
  outputs/audit/quebec_pre1994_scan.txt                                         (the report)
Safe to run while other runs are going. Safe to stop and start again (saved pages are kept).
Run from the project folder (about 30 to 45 minutes, mostly polite pauses between downloads):
  caffeinate -i python3 scripts/v3/find_quebec_pre1994.py
"""
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import quebec_rebuild as Q      # noqa: E402  (same paths, cache names and page parser as the rebuild)

if Q.requests is None or Q.BeautifulSoup is None:
    sys.exit("pip install requests beautifulsoup4")
requests = Q.requests

ROOT = HERE.parent.parent
OUT = Path(Q.OUT) / "pre1994"
REPORT = ROOT / "outputs" / "audit" / "quebec_pre1994_scan.txt"
PRE_OUTCOMES = ROOT / "data" / "canada" / "quebec_bills" / "quebec_pre1994_vote_outcomes.json"
BASE = "https://www.assnat.qc.ca"
DAY = re.compile(r"assemblee-nationale/(\d{2}-\d)/journal-debats/(\d{8})/(\d+)\.html")
INDEX_TRIES = ["/fr/travaux-parlementaires/assemblee-nationale/{s}/journal-debats/index.html",
               "/fr/travaux-parlementaires/assemblee-nationale/{s}/journal-debats/",
               "/fr/travaux-parlementaires/assemblee-nationale/{s}/index.html",
               "/fr/travaux-parlementaires/journaux-debats/index-jd/{s}.html"]
# pages known to exist (found by web search), used to start the link-following route
SEEDS = {"33-1": ["19851216/122661"], "34-1": ["19910619/63423"], "34-2": ["19930607/63721"]}
DEFAULT_SESSIONS = ["32-5", "33-1", "33-2", "34-1", "34-2", "34-3"]
CRAWL_CAP = 700          # most pages followed per session on the link-following route
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def canon(s, date, pid):
    return f"{BASE}/fr/travaux-parlementaires/assemblee-nationale/{s}/journal-debats/{date}/{pid}.html"


def get(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=Q.UA, timeout=60)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
        except requests.RequestException:
            pass
        time.sleep(8 * (attempt + 1))
    return None


def harvest(html, base, sessions):
    found = {}
    for m in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", html or "", re.I):
        d = DAY.search(urljoin(base, m.group(1).strip()))
        if d and d.group(1) in sessions:
            found[canon(*d.groups())] = d.groups()
    for d in DAY.finditer(html or ""):
        if d.group(1) in sessions:
            found[canon(*d.groups())] = d.groups()
    return found


def page(url, stats):
    """Saved copy if there is one, otherwise download and save it. Returns the HTML or None."""
    p = Q.cache_path(url)
    if os.path.exists(p) and os.path.getsize(p) > 2000:
        with open(p, encoding="utf-8", errors="ignore") as f:
            return f.read()
    r = get(url)
    time.sleep(Q.SLEEP)
    if r is None or r.status_code != 200 or len(r.content) < 2000:
        stats["failed"] += 1
        return None
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(r.content)
    stats["downloaded"] += 1
    return r.content.decode("utf-8", errors="ignore")


def session_of(rec):
    s = str(rec.get("session") or "")
    m = re.match(r"^(\d{2})-(\d)$", s) or re.search(r"(\d{2})\D{1,20}?(\d)\s*(?:re|e|er)?\s*session", s, re.I)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"projet-loi-\d+-(\d{2})-(\d)\.html", rec.get("bill_url") or "")
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # ------------------------------------------------------------------ 1. which bills
    _, no_urls = Q.expected_debates()
    pre, no_session = {}, []
    for rec in no_urls:
        s = session_of(rec)
        n = str(rec.get("bill_number", "")).strip()
        if not s:
            no_session.append(rec)
            continue
        if int(s.split("-")[0]) <= 34 and n.isdigit():
            pre[(s, int(n))] = rec
    later = len(no_urls) - len(pre) - len(no_session)
    say(f"Health bills with no Assembly debate links: {len(no_urls)}")
    say(f"   from 1985-1994 (legislature 34 or earlier): {len(pre)}; later sessions: {later}; "
        f"no usable session: {len(no_session)}")
    say(f"   by session: {dict(sorted(Counter(s for s, _ in pre).items()))}")
    if pre:
        k0 = sorted(pre)[0]
        say(f"   example record fields: {sorted(pre[k0].keys())}")
    for rec in no_session[:5]:
        say(f"   no session: {rec.get('bill_number')} {str(rec.get('title', ''))[:70]} | fields {sorted(rec.keys())}")
    try:
        po = json.load(open(PRE_OUTCOMES, encoding="utf-8"))
    except (OSError, ValueError):
        po = {}
    items = po.items() if isinstance(po, dict) else enumerate(po or [])
    po_keys = set()
    for k, v in items:
        rec = v if isinstance(v, dict) else {"outcome": v}
        url = k if isinstance(k, str) and "assnat" in k else (rec.get("bill_url") or rec.get("url") or "")
        m = re.search(r"projet-loi-(\d+)-(\d+-\d+)\.html", url or "")
        s = rec.get("session") or (m.group(2) if m else "")
        n = str(rec.get("bill_number") or (m.group(1) if m else "")).strip()
        if s and n.isdigit():
            po_keys.add((s, int(n)))
    say(f"quebec_pre1994_vote_outcomes.json: {len(po_keys)} bills with a session and number; "
        f"{len(po_keys & set(pre))} of the {len(pre)} pre-1994 health bills have an outcome there")
    sessions = sorted({s for s, _ in pre}) or DEFAULT_SESSIONS
    if not pre:
        say(f"   no pre-1994 bills found by session, so scanning the default sessions {sessions}")

    # ------------------------------------------------------------------ 2-3. sitting days and pages
    stats = Counter()
    days = {}
    for s in sessions:
        got, how = {}, ""
        for tpl in INDEX_TRIES:
            url = BASE + tpl.format(s=s)
            r = get(url)
            time.sleep(Q.SLEEP)
            if r is None:
                say(f"   {s}: {url} did not answer")
                continue
            html = r.content.decode("utf-8", errors="ignore")
            with open(OUT / f"index_{s}_{INDEX_TRIES.index(tpl)}.html", "w", encoding="utf-8") as f:
                f.write(html)
            found = harvest(html, url, {s})
            say(f"   {s}: {url} -> HTTP {r.status_code}, {len(found)} sitting-page links")
            if len(found) >= 5:
                got, how = found, f"session index ({url})"
                break
        if len(got) < 5:
            queue = [canon(s, *x.split("/")) for x in SEEDS.get(s, [])] + list(got)
            seen = set()
            while queue and len(seen) < CRAWL_CAP:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                html = page(url, stats)
                d = DAY.search(url)
                if html and d:
                    got[url] = d.groups()
                for u in harvest(html, url, {s}):
                    if u not in seen:
                        queue.append(u)
            how = f"following links between sitting pages from {len(SEEDS.get(s, []))} known page(s)"
        say(f"{s}: {len(got)} sitting pages found by {how or 'nothing'}")
        days.update(got)
    todo = [u for u in sorted(days) if not (os.path.exists(Q.cache_path(u)) and os.path.getsize(Q.cache_path(u)) > 2000)]
    say(f"Sitting pages found: {len(days)}; already saved: {len(days) - len(todo)}; downloading: {len(todo)}")
    for i, u in enumerate(todo, 1):
        page(u, stats)
        if i % 25 == 0 or i == len(todo):
            print(f"   {i}/{len(todo)} downloaded, {stats['failed']} failed", flush=True)
    with open(OUT / "sitting_days.json", "w", encoding="utf-8") as f:
        json.dump([{"session": s, "date": d, "page_id": p, "url": u} for u, (s, d, p) in sorted(days.items())],
                  f, indent=1)

    # ------------------------------------------------------------------ 4-5. read every page
    found, pages_read, pages_with_bills = [], 0, 0
    other_bills = Counter()
    for u, (s, d, pid) in sorted(days.items()):
        p = Q.cache_path(u)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="ignore") as f:
            segs, _ = Q.parse_page(f.read())
        pages_read += 1
        pages_with_bills += bool(segs)
        for n, paras in segs.items():
            rec = pre.get((s, n))
            if rec is None:
                other_bills[s] += 1
                continue
            text = " ".join(x["text"] for x in paras)
            t_toks = set(Q.content_tokens(rec.get("title", ""), "fr"))
            overlap = len(t_toks & set(Q.content_tokens(text, "fr"))) / len(t_toks) if t_toks else 0.0
            found.append({"bill_key": f"{s}-Bill{n}", "bill_session": s, "bill_number": n,
                          "title": rec.get("title", ""), "date": d, "page_id": pid, "url": u,
                          "n_paragraphs": len(paras), "words": len(text.split()),
                          "stages": dict(Counter(x["stage"] for x in paras if x.get("stage"))),
                          "methods": dict(Counter(x["method"].split(":")[0] for x in paras)),
                          "title_overlap": round(overlap, 2), "first_paragraph": paras[0]["text"][:200]})
    with open(OUT / "bill_days_found.json", "w", encoding="utf-8") as f:
        json.dump(found, f, indent=1, ensure_ascii=False)

    by_bill = defaultdict(list)
    for x in found:
        by_bill[(x["bill_session"], x["bill_number"])].append(x)
    say("")
    say(f"Pages read: {pages_read}; pages where the parser found at least one bill: {pages_with_bills}")
    say(f"Downloads this run: {stats['downloaded']}; failed: {stats['failed']}")
    say(f"Pre-1994 health bills with at least one debate day found: {len(by_bill)} of {len(pre)}; "
        f"bill-days found: {len(found)}")
    low = [x for x in found if x["title_overlap"] < 0.5]
    say(f"Second check (title words in the section): {len(found) - len(low)} bill-days share at least half "
        f"the title's words; {len(low)} share less (listed below, these need a look before they are used)")
    say(f"Stages seen: {dict(Counter(k for x in found for k in x['stages']).most_common())}")
    say(f"Found by: {dict(Counter(k for x in found for k in x['methods']).most_common())}")
    say("\nFound, first 25 bills:")
    for (s, n) in sorted(by_bill)[:25]:
        xs = by_bill[(s, n)]
        say(f"   {s}-Bill{n:<5} {str(xs[0]['title'])[:60]:<60} days {len(xs)}: "
            + ", ".join(f"{x['date']}({x['title_overlap']})" for x in xs[:6]))
    say("\nLow title overlap (a different bill with the same number, or a short procedural section):")
    for x in low[:30]:
        say(f"   {x['bill_key']:<13} {x['date']} overlap {x['title_overlap']} {x['n_paragraphs']} paras | "
            f"{x['first_paragraph'][:110]}")
    missing = sorted(set(pre) - set(by_bill))
    say(f"\nPre-1994 health bills with no debate day found in their session: {len(missing)}")
    for (s, n) in missing[:40]:
        rec = pre[(s, n)]
        say(f"   {s}-Bill{n:<5} {str(rec.get('title', ''))[:80]}"
            + ("   (has an outcome)" if (s, n) in po_keys else ""))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    print(f"\nSaved {REPORT}\n      {OUT / 'bill_days_found.json'}")


if __name__ == "__main__":
    main()
