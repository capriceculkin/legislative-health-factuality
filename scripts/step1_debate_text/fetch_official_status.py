#!/usr/bin/env python3
"""
fetch_official_status.py
Downloads the official record for each predicated bill so outcomes can be
checked against the legislature itself. Raw pages are cached; nothing is
parsed here (outcomes_v3.py parses, so a parser fix never needs a refetch).
Safe to stop and rerun: cached pages are skipped.

  ontario   OLA bill status pages (exist from the 36th Parliament, 1995, on)
            https://www.ola.org/en/legislative-business/bills/parliament-P/session-S/bill-N
            -> data/v3_status_cache/ontario/{bill_key}.html
  quebec    Assemblee nationale bill pages (bill_url in the health bill list)
            -> data/v3_status_cache/quebec/{bill_key}.html
  us-congress  Congress.gov bill record + actions (House passage incl. voice votes,
            became law) -> data/v3_status_cache/us/{bill_key}.bill.json / .actions.json
  us-bound  GovInfo granule lists for bound-edition years, to find the House
            granule (full-day PDF) for each pre-1994 debate date.
            Needs:  export GOVINFO_API_KEY=...   (never written to any file)
            -> data/us/v3/cache/granule_lists/GPO-CRECB-YYYY-ptN.json

Run from project root:
    python3 scripts/step1_debate_text/fetch_official_status.py ontario
    python3 scripts/step1_debate_text/fetch_official_status.py quebec
    python3 scripts/step1_debate_text/fetch_official_status.py us-bound
"""
import json, os, re, sys, time
import urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "v3_status_cache"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36 (research; Yale School of Public Health legislative study)",
      "Accept-Language": "en-CA,en;q=0.9,fr-CA;q=0.8"}


def mask(e):
    """Error text with any API key removed."""
    return re.sub(r"api_key=[^&\s]+", "api_key=***", str(e))


def get(url, timeout=40):
    """requests (with its own certificate bundle, as the pipeline used) when available;
    otherwise urllib with the certifi bundle."""
    try:
        import requests
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            return r.status_code, r.content
        except requests.RequestException as e:
            print("    network error: " + mask(e))
            return None, b""
    except ImportError:
        pass
    import ssl
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = None
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        print("    network error: " + mask(e))
        return None, b""


def pred_keys(j):
    with open(ROOT / "data" / "dbpedia_pipeline" / j / "predications_v3.json", encoding="utf-8") as f:
        return sorted({p["bill_key"] for p in json.load(f)})


BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/17.5 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}
_SESSION = None


def browser_get(url, referer="https://www.ola.org/en/legislative-business/bills", timeout=40):
    """A session that behaves like a person's browser: visits the site's bills page
    first (to receive its cookies), then asks for each bill page with a referer."""
    global _SESSION
    import requests
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update(BROWSER)
        for warm in ("https://www.ola.org/en", "https://www.ola.org/en/legislative-business/bills"):
            try:
                _SESSION.get(warm, timeout=timeout)
            except requests.RequestException:
                pass
            time.sleep(2)
    try:
        r = _SESSION.get(url, headers={"Referer": referer}, timeout=timeout)
        return r.status_code, r.content
    except requests.RequestException as e:
        print("    network error: " + mask(e))
        return None, b""


def fetch_pages(jur, targets, sleep, marker, getter=None):
    getter = getter or get
    out = CACHE / jur
    out.mkdir(parents=True, exist_ok=True)
    todo = [(bk, u) for bk, u in targets if not (out / f"{bk}.html").exists()]
    print(f"{jur}: {len(targets)} bills, {len(targets) - len(todo)} already cached, {len(todo)} to fetch "
          f"(~{len(todo) * sleep / 60:.0f} min)")
    blocked = 0
    for i, (bk, url) in enumerate(todo, 1):
        code, body = getter(url)
        if code == 200 and marker.encode() in body:
            (out / f"{bk}.html").write_bytes(body)
            blocked = 0
        elif code == 404:
            (out / f"{bk}.404").write_text(url)          # recorded so it is not retried
        else:
            print(f"  [{i}/{len(todo)}] {bk}: HTTP {code}, {len(body)} bytes  {url}")
            if code in (403, 429, None):
                blocked += 1
                if blocked >= 3:
                    sys.exit("Stopped: the site refused 3 requests in a row. Wait a while and rerun; "
                             "cached pages are kept.")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}")
        time.sleep(sleep)
    have = len(list(out.glob("*.html")))
    print(f"{jur}: done. {have} pages cached, {len(list(out.glob('*.404')))} not found (404).")


def cmd_ontario():
    targets = []
    for bk in pred_keys("ontario"):
        m = re.match(r"^(\d+)-(\d+)-Bill(\d+)$", bk)
        if m and int(m.group(1)) >= 36:
            p, s, n = m.groups()
            targets.append((bk, f"https://www.ola.org/en/legislative-business/bills/parliament-{p}/session-{s}/bill-{n}"))
    print(f"(Ontario bills before the 36th Parliament have no status page and are handled from the Hansard.)")
    import random
    base = float(os.environ.get("OLA_SLEEP", "5"))
    code, body = browser_get(targets[0][1]) if targets else (None, b"")
    if code == 403:
        sys.exit("OLA still refuses automated requests (HTTP 403) even as a browser session.\n"
                 "Nothing to fix on your side: Ontario outcomes will use the vote file (FSOB) plus the\n"
                 "Hansard check, and outcomes_v3.py reports how well those two agree.")
    fetch_pages("ontario", targets, base + random.random() * 2, "Bill", getter=browser_get)


def cmd_quebec():
    with open(ROOT / "data/canada/quebec_bills/quebec_health_bills_combined.json", encoding="utf-8") as f:
        combined = json.load(f)
    url_of = {}
    for e in combined:
        n = str(e.get("bill_number", "")).strip()
        if n.isdigit() and e.get("bill_url"):
            url_of[f"{e.get('session', '')}-Bill{int(n)}"] = e["bill_url"]
    keys = pred_keys("quebec")
    missing = [k for k in keys if k not in url_of]
    if missing:
        print(f"  {len(missing)} predicated Quebec bills have no bill_url: {missing[:10]}")
    fetch_pages("quebec", [(k, url_of[k]) for k in keys if k in url_of],
                float(os.environ.get("ASSNAT_SLEEP", "1.5")), "projet")


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def title_date(t):
    m = re.search(r"(" + "|".join(MONTHS) + r") (\d{1,2}), (\d{4})", t or "")
    if not m:
        return ""
    return f"{m.group(3)}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"


def cmd_us_bound():
    key = os.environ.get("GOVINFO_API_KEY", "")
    if not key:
        sys.exit("export GOVINFO_API_KEY=... first (it is read from the shell only, never saved).")
    # every pre-1994 vote date in the plan and the day before it (not only days where
    # a bill was already found, so missing vote days get searched too)
    import datetime as dt
    with open(ROOT / "data/us/v3/plan.json", encoding="utf-8") as f:
        plan = json.load(f)
    need = set()
    for b in plan:
        if b.get("vote_date", "") < "1994-01-01":
            d0 = dt.date.fromisoformat(b["vote_date"])
            need |= {b["vote_date"], (d0 - dt.timedelta(days=1)).isoformat()}
    # plus the House debate days from Congress.gov (us_rebuild.py floor-days)
    fl = ROOT / "data/us/v3/floor_days.json"
    if fl.exists():
        for days in json.loads(fl.read_text(encoding="utf-8")).values():
            need |= {d for d in days if d < "1994-01-01"}
    need = sorted(need)
    gl_dir = ROOT / "data/us/v3/cache/granule_lists"
    gl_dir.mkdir(parents=True, exist_ok=True)
    found = {}
    for p in gl_dir.glob("GPO-CRECB-*.json"):
        for g in (json.loads(p.read_text(encoding="utf-8")).get("granules") or []):
            if str(g.get("title", "")).startswith("House of Representatives"):
                found.setdefault(title_date(g["title"]), g["granuleId"])
    todo_years = sorted({d[:4] for d in need if d not in found})
    print(f"bound debate dates: {len(need)}; already mapped: {sum(d in found for d in need)}; years to scan: {todo_years}")
    for y in todo_years:
        want = {d for d in need if d[:4] == y and d not in found}
        misses = 0
        for part in range(1, 46):
            pkg = f"GPO-CRECB-{y}-pt{part}"
            path = gl_dir / f"{pkg}.json"
            if path.exists():
                grans = json.loads(path.read_text(encoding="utf-8")).get("granules") or []
            else:
                grans, url = [], f"https://api.govinfo.gov/packages/{pkg}/granules?offsetMark=*&pageSize=1000&api_key={key}"
                while url:
                    code, body = get(url)
                    if code in (401, 403):
                        sys.exit(f"GovInfo refused the API key (HTTP {code}). Set your real key: "
                                 f"export GOVINFO_API_KEY=<the key from api.data.gov>  and run again.")
                    if code != 200:
                        break
                    data = json.loads(body)
                    grans += data.get("granules") or []
                    nxt = data.get("nextPage")
                    url = (nxt + ("&" if "?" in nxt else "?") + f"api_key={key}") if nxt else None
                    time.sleep(0.4)
                if not grans:
                    misses += 1
                    if misses >= 3:
                        break
                    continue
                path.write_text(json.dumps({"granules": grans}), encoding="utf-8")
            misses = 0
            for g in grans:
                if str(g.get("title", "")).startswith("House of Representatives"):
                    d = title_date(g["title"])
                    found.setdefault(d, g["granuleId"])
                    want.discard(d)
            if not want:
                break
        print(f"  {y}: still unmapped {sorted(want) if want else 'none'}")
    print(f"bound dates mapped to a House granule: {sum(d in found for d in need)} of {len(need)}")


def cmd_us_congress():
    """Congress.gov bill record and full action list for every predicated US bill.
    Uses the same api.data.gov key as GovInfo (read from the shell, never saved)."""
    key = os.environ.get("GOVINFO_API_KEY", "") or os.environ.get("CONGRESS_API_KEY", "")
    if not key:
        sys.exit("export GOVINFO_API_KEY=... first (the api.data.gov key also works for api.congress.gov).")
    out = CACHE / "us"
    out.mkdir(parents=True, exist_ok=True)
    keys = pred_keys("us")
    todo = [k for k in keys if not (out / f"{k}.actions.json").exists() or not (out / f"{k}.bill.json").exists()]
    print(f"US bills with predications: {len(keys)}; to fetch: {len(todo)} (~{len(todo) * 2 * 0.8 / 60:.0f} min)")
    bad = []
    for i, bk in enumerate(todo, 1):
        m = re.match(r"^(\d+)-([A-Z]+)(\d+)$", bk)
        if not m:
            bad.append(bk)
            continue
        c, t, n = m.group(1), m.group(2).lower(), m.group(3)
        base = f"https://api.congress.gov/v3/bill/{c}/{t}/{n}"
        for suffix, fname in (("", f"{bk}.bill.json"), ("/actions", f"{bk}.actions.json")):
            if (out / fname).exists():
                continue
            items, url, ok = [], f"{base}{suffix}?format=json&limit=250", True
            data = None
            while url:
                code, body = get(url + f"&api_key={key}")
                if code in (401, 403):
                    sys.exit(f"api.congress.gov refused the key (HTTP {code}). If your GovInfo key is not accepted, "
                             f"get a free key at https://api.congress.gov/sign-up/ and: export CONGRESS_API_KEY=...")
                if code == 429:
                    print("  rate limited; waiting 60 s")
                    time.sleep(60)
                    continue
                if code != 200:
                    print(f"  [{i}/{len(todo)}] {bk}{suffix}: HTTP {code}")
                    ok = False
                    break
                data = json.loads(body)
                if suffix == "/actions":
                    items += data.get("actions") or []
                    nxt = (data.get("pagination") or {}).get("next")
                    url = (nxt + ("&" if "?" in nxt else "?") + "format=json") if nxt else None
                    if url:
                        url = re.sub(r"[&?]api_key=[^&]*", "", url)
                else:
                    url = None
                time.sleep(0.8)
            if ok:
                payload = {"actions": items} if suffix == "/actions" else data
                (out / fname).write_text(json.dumps(payload), encoding="utf-8")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}")
    have = len(list(out.glob("*.actions.json")))
    print(f"us-congress: done. action lists cached: {have} of {len(keys)}" + (f"; bad keys {bad[:5]}" if bad else ""))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"ontario": cmd_ontario, "quebec": cmd_quebec, "us-bound": cmd_us_bound, "us-congress": cmd_us_congress}.get(
        cmd, lambda: sys.exit("usage: fetch_official_status.py ontario|quebec|us-bound|us-congress"))()
