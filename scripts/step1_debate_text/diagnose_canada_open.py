#!/usr/bin/env python3
"""
diagnose_canada_open.py   (reads only; changes no data; about 3 minutes, about 60 small downloads)

Collects what the next Ontario and Quebec fixes need, from files on this machine and from the
Assemblee nationale site:

ONTARIO
  O1  the bill-day the rebuild's own CHECK 1 marks FAIL (no procedural line behind it)
  O2  headings claimed by two bills of one session (topic_conflicts.csv): the bills, their titles,
      and how many paragraphs of the health bills' downloaded rows sit under each heading
  O3  old health-list bills the rebuild did not find again (old_health_bills_not_rediscovered.csv),
      each with what the rebuild knows about the same session and number, and why it was missed
  O4  the carry-over pairs among health bills (outputs/audit/carry_over_bills.csv)
QUEBEC 1985-1994
  Q1  the 117 health-list records with placeholder numbers: file name, the bill numbers written in
      their text, and how they line up with quebec_pre1994_vote_outcomes.json
  Q2  how the Assemblee site lists the sitting days and bills of sessions 33-1 to 34-3 (session
      pages, Journal des debats indexes, a known sitting page): link patterns and text around
      "projet de loi", so the debate days can be found

Run from the project folder:   python3 scripts/step1_debate_text/diagnose_canada_open.py
Writes outputs/audit/canada_open_diag.txt and keeps the downloaded pages in
data/canada/quebec_assembly/v3/pre1994/probe/
"""
import ast
import csv
import json
import re
import sys
import time
import traceback
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
AUD = ROOT / "outputs" / "audit"
ON = ROOT / "data" / "canada" / "ontario" / "v3"
QB = ROOT / "data" / "canada" / "quebec_bills"
PROBE = ROOT / "data" / "canada" / "quebec_assembly" / "v3" / "pre1994" / "probe"
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def short(s, n=150):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 3] + "..."


def section(name, fn):
    say("\n" + "=" * 100 + f"\n{name}\n" + "=" * 100)
    try:
        fn()
    except Exception:                                   # noqa: BLE001
        say("this part stopped with an error (the other parts still ran):")
        say(traceback.format_exc()[-1500:])


def csv_rows(p):
    try:
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return None


def norm_topic(t):
    return re.sub(r"\s+", " ", re.sub(r"\(CONTINUED\)", "", str(t or "").upper())).strip()


# ============================================================================ ONTARIO
def o1():
    rows = csv_rows(ON / "ontario_running_table.csv")
    if rows is None:
        say("ontario_running_table.csv not found")
        return
    bad = [r for r in rows if r.get("check1_procedural_evidence") == "FAIL"]
    say(f"bill-days: {len(rows)}; CHECK 1 FAIL: {len(bad)}")
    seg = load(ON / "hansard_segments_v3.json", {}) or {}
    for r in bad:
        say(f"   {r['bill_key']} {r['debate_date']}  {r['n_paragraphs']} paragraphs  headings: {short(r['headings'], 120)}")
        say(f"      methods {r['methods']}  title: {short(r.get('long_title'), 100)}")
        say(f"      url {r.get('hansard_url')}")
        paras = (seg.get(r["bill_key"]) or {}).get(r["debate_date"], [])
        for p in paras[:4]:
            say(f"      [{p.get('topic', '')[:40]}] {p.get('speaker', '')[:30]}: {short(p.get('text'), 200)}")
        master = load(ON / "bills_master.json", {}) or {}
        b = master.get(r["bill_key"], {})
        say(f"      anchor days of this bill: {b.get('anchor_dates')}; stages {b.get('stages')}; headings {b.get('topics')}")


def o2():
    rows = csv_rows(ON / "topic_conflicts.csv")
    if rows is None:
        say("topic_conflicts.csv not found")
        return
    master = load(ON / "bills_master.json", {}) or {}
    health = {k: v for k, v in master.items() if v.get("health")}
    say(f"headings claimed by two or more bills of one session: {len(rows)}")
    # paragraphs of the health bills' downloaded rows under each conflicted heading
    under = Counter()
    days_under = defaultdict(set)
    keys = {(r["session"], norm_topic(r["heading"])) for r in rows}
    raw = ON / "raw"
    for k, b in health.items():
        data = load(raw / f"{k}.json", []) or []
        for x in data:
            t = norm_topic(x.get("topic"))
            if (b["session"], t) in keys:
                under[(b["session"], t, k)] += 1
                days_under[(b["session"], t, k)].add(str(x.get("date", ""))[:10])
    tot = Counter()
    for (s, t, k), n in under.items():
        tot[(s, t)] += n
    say(f"paragraphs of health bills' downloaded rows under these headings (not used for any bill now): "
        f"{sum(tot.values()):,} under {len(tot)} headings")
    for r in sorted(rows, key=lambda r: -tot[(r["session"], norm_topic(r["heading"]))])[:60]:
        s, t = r["session"], norm_topic(r["heading"])
        try:
            votes = ast.literal_eval(r["anchor_votes_by_bill"])   # the csv holds a printed dict
        except (ValueError, SyntaxError):
            votes = {}
        say(f"   {s}  {short(r['heading'], 70)}  votes {r['anchor_votes_by_bill']}  rows under it: {tot[(s, t)]}")
        for num in votes:
            k = f"{s}-Bill{num}"
            b = master.get(k, {})
            say(f"        Bill {num}: health={b.get('health')}  {short(b.get('long_title'), 90)}  anchors on {b.get('anchor_dates', [])[:8]}"
                + (f"  | rows here: {under.get((s, t, k), 0)} on {sorted(days_under.get((s, t, k), []))[:6]}" if k in health else ""))


def o3():
    rows = csv_rows(ON / "old_health_bills_not_rediscovered.csv")
    if rows is None:
        say("old_health_bills_not_rediscovered.csv not found")
        return
    master = load(ON / "bills_master.json", {}) or {}
    anchors = load(ON / "anchors.json", []) or []
    old = load(ROOT / "data" / "canada" / "ontario" / "ontario_bill_index.json", {}) or {}
    fsob = load(ROOT / "data" / "canada" / "ontario" / "ontario_fsob_votes.json", {}) or {}
    status = ROOT / "data" / "v3_status_cache" / "ontario"
    an = defaultdict(lambda: Counter())
    for a in anchors:
        if a.get("session"):
            an[f"{a['session']}-Bill{a['bill_number']}"]["strong" if a.get("strong") else "weak"] += 1
    try:
        from v3_common import content_tokens, jaccard, health_hits
    except Exception:                                   # noqa: BLE001
        content_tokens = lambda s, lang="en": re.findall(r"[a-z]{4,}", str(s).lower())   # noqa: E731
        jaccard = lambda a, b: len(set(a) & set(b)) / max(1, len(set(a) | set(b)))       # noqa: E731
        health_hits = lambda s: []                                                          # noqa: E731
    why = Counter()
    out = []
    for r in rows:
        ok = r["old_key"]
        m = re.match(r"^(\d+-\d+)-Bill(\d+)$", ok)
        s, n = (m.group(1), int(m.group(2))) if m else ("", 0)
        same = master.get(f"{s}-Bill{n}")
        ov = old.get(ok, {})
        if same:
            j = jaccard(content_tokens(same.get("long_title", "")), content_tokens(ov.get("title", "")))
            reason = ("found, title differs (word overlap %.2f), and no health word in its title or headings" % j
                      if not same.get("health") else "found and health (should have matched)")
        elif an.get(f"{s}-Bill{n}"):
            reason = "only weak procedural lines found (no 'moved ... reading of Bill N')"
        else:
            reason = "no procedural line found for this session and number"
        why[reason.split(" (")[0]] += 1
        st = (status / f"{s}-Bill{n}.html").exists()
        out.append((reason, ok, ov.get("title", "") or r.get("old_title", ""), r.get("old_dates", ""),
                    same.get("long_title", "") if same else "", st, health_hits(ov.get("title", "") or "")))
    say(f"old health-list bills not found again: {len(rows)}")
    for k, v in why.most_common():
        say(f"   {v:>4}  {k}")
    for reason, ok, ot, od, nt, st, hh in sorted(out):
        say(f"   {ok:<14} {short(ot, 80)}")
        say(f"        old dates: {short(od, 90)} | OLA status page saved: {st} | health words in old title: {hh}")
        say(f"        {reason}" + (f" | rebuild title: {short(nt, 80)}" if nt else ""))


def o4():
    rows = csv_rows(AUD / "carry_over_bills.csv")
    if rows is None:
        say("outputs/audit/carry_over_bills.csv not found")
        return
    say(f"carry-over pairs: {len(rows)}; columns: {list(rows[0].keys()) if rows else []}")
    for r in rows:
        if any(str(v).lower() in ("true", "yes", "y") for k, v in r.items() if "health" in k.lower()):
            say("   " + " | ".join(f"{k}={short(v, 60)}" for k, v in r.items()))


# ============================================================================ QUEBEC
def q1():
    recs = load(QB / "quebec_health_bills_combined.json", []) or []
    pre = [r for r in recs if str(r.get("source", "")).startswith("bibliotheque")]
    say(f"health-list records from the library (1985-1994): {len(pre)}; fields: {sorted(set(k for r in pre for k in r))}")
    po = load(QB / "quebec_pre1994_vote_outcomes.json", {}) or {}
    po_keys = {(v.get("session"), str(v.get("bill_number"))): v for v in (po.values() if isinstance(po, dict) else po)}
    say(f"quebec_pre1994_vote_outcomes.json: {len(po_keys)} bills; fields of one: {sorted(next(iter(po_keys.values())).keys()) if po_keys else []}")
    found = Counter()
    for r in pre:
        txt = " ".join(str(r.get(k, "")) for k in ("title", "filename"))
        nums = re.findall(r"[Pp]rojet\s+de\s+loi\s*(?:n\s*[°ºo]\.?\s*)?(\d{1,3})", txt)
        fn_nums = re.findall(r"(\d{1,3})", str(r.get("filename", "")))
        s = r.get("session", "")
        hit = [n for n in nums if (s, n) in po_keys]
        found["number in text" if nums else "no number in text"] += 1
        found["matches an outcome record" if hit else "no outcome match"] += 1
        say(f"   {s:<5} placeholder {str(r.get('bill_number')):<4} file {short(r.get('filename'), 60):<60} "
            f"numbers in text {nums[:4]} | outcome match {hit[:3]}")
        say(f"        {short(r.get('title'), 170)}")
    say(f"summary: {dict(found)}")
    sess = Counter(v.get("session") for v in po_keys.values())
    say(f"outcome records by session: {dict(sorted(sess.items()))}")
    for (s, n), v in sorted(po_keys.items())[:12]:
        say(f"   outcome {s} Bill {n}: {short(json.dumps(v, ensure_ascii=False), 200)}")


BASE = "https://www.assnat.qc.ca"
DAY = re.compile(r"assemblee-nationale/(\d{2}-\d)/journal-debats/(\d{8})/(\d+)\.html")


def fam(u):
    u = re.sub(r"\d{8}", "<date>", u)
    u = re.sub(r"\d+", "N", u)
    return u.split("#")[0][:120]


def fetch(url, name):
    try:
        import requests
    except ImportError:
        say("pip install requests")
        return None
    PROBE.mkdir(parents=True, exist_ok=True)
    p = PROBE / name
    if p.exists() and p.stat().st_size > 500:
        return p.read_text(encoding="utf-8", errors="ignore")
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (research; Yale School of Public Health)"}, timeout=60)
            time.sleep(1.5)
            say(f"   GET {url} -> HTTP {r.status_code}, {len(r.content):,} bytes")
            if r.status_code == 200:
                p.write_bytes(r.content)
                return r.content.decode("utf-8", errors="ignore")
            return None
        except Exception as e:                          # noqa: BLE001
            say(f"   GET {url} failed ({type(e).__name__}); retrying")
            time.sleep(5 * (attempt + 1))
    return None


def describe(html, url, label):
    if not html:
        return []
    links = [urljoin(url, m.group(1)) for m in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", html, re.I)]
    fams = Counter(fam(u) for u in links)
    days = sorted({DAY.search(u).groups() for u in links if DAY.search(u)})
    text = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", html))
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text))
    say(f"   {label}: {len(links)} links; sitting-page links: {len(days)}" + (f" (first {days[:3]}, last {days[-2:]})" if days else ""))
    for f, n in fams.most_common(14):
        say(f"      {n:>4}x {f}")
    for m in list(re.finditer(r"[Pp]rojet\s+de\s+loi", text))[:6]:
        say(f"      text: ...{text[max(0, m.start() - 80): m.start() + 160]}...")
    return links


def q2():
    say("(links are shown as patterns: a run of digits is N, an 8-digit date is <date>)")
    s = "34-1"
    tries = [
        (f"{BASE}/fr/travaux-parlementaires/assemblee-nationale/{s}/index.html", f"session_{s}.html"),
        (f"{BASE}/fr/travaux-parlementaires/journaux-debats/index-jd/{s}.html", f"indexjd_{s}.html"),
        (f"{BASE}/fr/travaux-parlementaires/journaux-debats/index-jd/recherche.html?cat=v&Session=jd34l1se&Section=sujets&Requete=s",
         f"indexjd_{s}_sujets_s.html"),
        (f"{BASE}/fr/travaux-parlementaires/journaux-debats/index-jd/recherche.html?cat=v&Session=jd34l1se&Section=sujets&Requete=p",
         f"indexjd_{s}_sujets_p.html"),
        (f"{BASE}/fr/travaux-parlementaires/assemblee-nationale/{s}/journal-debats/19910619/63423.html", "sitting_19910619.html"),
        (f"{BASE}/fr/travaux-parlementaires/projets-loi/projets-loi-{s}.html", f"projets_loi_{s}.html"),
        (f"{BASE}/fr/travaux-parlementaires/projets-loi/index.html", "projets_loi_index.html"),
        (f"{BASE}/fr/travaux-parlementaires/journaux-debats.html", "journaux_debats.html"),
        (f"{BASE}/fr/travaux-parlementaires/assemblee-nationale/{s}/journal-debats.html", f"jd_{s}.html"),
        (f"{BASE}/fr/travaux-parlementaires/assemblee-nationale/{s}/journaux-debats.html", f"jds_{s}.html"),
    ]
    got = {}
    for url, name in tries:
        html = fetch(url, name)
        got[name] = (url, html)
        describe(html, url, name)
    # follow the first few index-jd search sections and bill links found on these pages
    more = set()
    for name, (url, html) in got.items():
        for m in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", html or "", re.I):
            u = urljoin(url, m.group(1)).split("#")[0]
            if re.search(r"index-jd/recherche\.html\?.*Section=(?!sujets)", u) or re.search(r"projet-loi-\d+-3[34]-\d\.html", u) \
                    or re.search(r"Section=sujets&(?:amp;)?Requete=s\b", u):
                more.add(u.replace("&amp;", "&"))
    say(f"\nfollowing {min(len(more), 12)} more links (other index sections and bill pages) of {len(more)} found:")
    for i, u in enumerate(sorted(more)[:12]):
        html = fetch(u, f"more_{i}.html")
        describe(html, u, u.replace(BASE, "")[:100])
    # previous / next sitting from a known sitting page, and other sessions' pages
    for s2 in ("33-1", "33-2", "34-2", "34-3"):
        html = fetch(f"{BASE}/fr/travaux-parlementaires/journaux-debats/index-jd/{s2}.html", f"indexjd_{s2}.html")
        describe(html, f"{BASE}/fr/travaux-parlementaires/journaux-debats/index-jd/{s2}.html", f"indexjd_{s2}.html")


def main():
    section("O1 Ontario: the bill-day with no procedural line behind it (CHECK 1 FAIL)", o1)
    section("O2 Ontario: headings claimed by two bills of one session", o2)
    section("O3 Ontario: old health-list bills the rebuild did not find again", o3)
    section("O4 Ontario: carry-over pairs among health bills", o4)
    section("Q1 Quebec 1985-1994: health-list records with placeholder numbers", q1)
    section("Q2 Quebec 1985-1994: how the Assemblee site lists sittings and bills", q2)
    AUD.mkdir(parents=True, exist_ok=True)
    (AUD / "canada_open_diag.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    say(f"\nwrote outputs/audit/canada_open_diag.txt")


if __name__ == "__main__":
    main()
