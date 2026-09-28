#!/usr/bin/env python3
"""
check_links.py   (reads the sheet, changes nothing in it)
Opens every distinct link in outputs/health_bills_review.xlsx, the way a browser
would, and records what each site answered.
  OK          the page or PDF opened (HTTP 200)
  BROKEN      the site says it does not exist (404/410) -> must be fixed
  BLOCKED     the site refused an automated check (403/429); open by hand to confirm
  ERROR       no answer (network) -> rerun later
Each site is checked one request at a time with a pause (sites differ), and the
sites run side by side. Writes outputs/audit/link_check.csv and prints a summary.
Run from project root:  python3 scripts/v3/check_links.py
"""
import csv, sys, threading, time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import openpyxl
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
SHEET = ROOT / "outputs" / "health_bills_review.xlsx"
OUT = ROOT / "outputs" / "audit" / "link_check.csv"
PAUSE = {"www.ola.org": 1.5, "www.assnat.qc.ca": 1.0, "www.congress.gov": 1.5, "www.govinfo.gov": 0.3}
HEAD = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/17.5 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-CA,en-US;q=0.9,fr-CA;q=0.8",
}


def collect():
    import re
    wb = openpyxl.load_workbook(SHEET, read_only=True)
    where = defaultdict(set)
    for name in wb.sheetnames:
        if name == "All Predications":
            continue                      # same links as Bills + Sitting Days, far more rows
        ws = wb[name]
        rows = ws.iter_rows(values_only=True)
        cols = list(next(rows, []) or [])
        for row in rows:
            key = f"{name}: {row[1] if len(row) > 1 else ''} {row[4] if len(row) > 4 else ''}".strip()
            for i, v in enumerate(row):
                if not isinstance(v, str) or "http" not in v:
                    continue
                for url in re.findall(r"https?://[^\s;,|)]+", v):
                    col = cols[i] if i < len(cols) else ""
                    where[url.split("#")[0]].add(f"{col} | {key}")
    return where


def check_site(host, urls, results):
    s = requests.Session()
    s.headers.update(HEAD)
    try:
        s.get(f"https://{host}/", timeout=30)
    except requests.RequestException:
        pass
    for i, u in enumerate(urls, 1):
        status, code = "ERROR", ""
        for attempt in range(3):
            try:
                if u.lower().endswith(".pdf"):
                    r = s.head(u, timeout=60, allow_redirects=True)
                    if r.status_code in (403, 405):
                        r = s.get(u, timeout=120, stream=True)
                        r.close()
                else:
                    r = s.get(u, timeout=60)
                code = r.status_code
                status = ("OK" if code == 200 else "BROKEN" if code in (404, 410) else
                          "BLOCKED" if code in (401, 403, 429) else f"HTTP {code}")
                if code == 429:
                    time.sleep(30)
                    continue
                break
            except requests.RequestException as e:
                code = type(e).__name__
                time.sleep(5)
        results[u] = (status, code)
        if i % 100 == 0:
            print(f"  {host}: {i}/{len(urls)}", flush=True)
        time.sleep(PAUSE.get(host, 1.0))


def main():
    if not SHEET.exists():
        sys.exit(f"{SHEET} not found; build the sheet first")
    where = collect()
    by_host = defaultdict(list)
    for u in sorted(where):
        by_host[urlparse(u).netloc].append(u)
    print("distinct links: " + ", ".join(f"{h} {len(v)}" for h, v in sorted(by_host.items())))
    est = max(len(v) * (PAUSE.get(h, 1.0) + 0.5) for h, v in by_host.items()) / 60
    print(f"estimated time: about {est:.0f} min (sites are checked side by side)")
    results = {}
    threads = [threading.Thread(target=check_site, args=(h, v, results)) for h, v in by_host.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["status", "http", "site", "url", "used_in (column | sheet row)"])
        for u in sorted(results, key=lambda u: (results[u][0] == "OK", u)):
            w.writerow([results[u][0], results[u][1], urlparse(u).netloc, u, "; ".join(sorted(where[u]))[:500]])
    tally = Counter((urlparse(u).netloc, results[u][0]) for u in results)
    print("\nRESULT by site:")
    for h in sorted(by_host):
        print(f"  {h}: " + ", ".join(f"{st} {n}" for (hh, st), n in sorted(tally.items()) if hh == h))
    bad = [u for u in results if results[u][0] != "OK"]
    print(f"\n{len(results) - len(bad)} of {len(results)} links opened OK; {len(bad)} need attention -> {OUT}")


if __name__ == "__main__":
    main()
