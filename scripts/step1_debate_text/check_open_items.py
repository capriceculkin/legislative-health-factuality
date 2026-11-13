#!/usr/bin/env python3
"""
check_open_items.py   (reads only, about a minute)

Four checks on what the Sept 29 runs turned up, so the next fixes are made on evidence:

  A. US: every Record unit inside every US bill-day, sorted into
       procedural   notices that slipped past the procedural list ("Constitutional Authority
                    Statement for H.R. N", "Reports of Committee on Public Bills", Rules announcements)
       speech       one-minute speeches and special-order hours that mention the bill but are not
                    its consideration on the floor
       other bill   a named Act that is not this bill and names it only in passing
                    (104-HR483: 104,225 words of the American Overseas Interests Act)
       long, rare   5,000+ words that name the bill 3 times or fewer
     with the words each class holds, so the rule change can be sized before it is made.
  B. Quebec: the two sections fix 3 created or grew that need a look (37-1 Bill 56 on
     2004-10-19, 36-1 Bill 170 on 2000-12-19), and why the parser finds no bill at all on
     three Journal pages (38-1 2007-06-05, 39-1 2009-09-23 and 24).
  C. Quebec 1985 to 1994: what bill lists exist, and how the saved session pages link to
     sitting days, so the 1985 to 1994 debates can be found.
  D. Canada sample: bills whose only stage is first reading (Ontario) or presentation (Quebec),
     counted two ways (the official status page, and our own text), with their claims and
     outcomes. Their text is the sponsor's introduction, not a debate.

Run from the project folder:   python3 scripts/step1_debate_text/check_open_items.py
Writes outputs/audit/open_items_check.txt and outputs/audit/us_unit_flags.csv
"""
import csv
import glob
import json
import os
import re
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent.parent
AUD = ROOT / "outputs" / "audit"
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


STOP = set("that this with from have been which their there about into other such under shall more "
           "purposes provide provides amend amendment title united states section sections code public "
           "law laws year years certain respect relating related american".split())


def toks(s):
    return {w for w in re.findall(r"[a-z]{4,}", str(s or "").lower()) if w not in STOP and w not in ("bill", "act")}


# ============================================================================ A. US units
EXTRA_PROC = re.compile(r"^(CONSTITUTIONAL AUTHORITY STATEMENT|REPORTS? OF COMMITTEES? ON (PUBLIC|PRIVATE) BILLS|"
                        r"ANNOUNCEMENT BY (THE )?COMMITTEE ON RULES|AMENDMENT PROCESS FOR|TIME LIMITATIONS? OF REFERRED|"
                        r"AUTHORIZING (THE )?SPEAKER|REPORT ON RESOLUTION|DISCHARGE OF COMMITTEE|"
                        r"SUBMISSION OF|CORRECTING ENROLLMENT)")
SPEECH = re.compile(r"asked and was given permission to address the House for 1 minute|"
                    r"Under the Speaker'?s announced policy of|Under (?:a|the) previous order of the House, the "
                    r"(?:gentle|following)|MORNING[- ]HOUR DEBATE|morning-hour debate", re.I)


def section_a():
    import us_rebuild as U
    idx = load(ROOT / "data/us/v3/segments_index.json", []) or []
    say("=" * 90 + "\nA. US: what each Record unit inside the 788 bill-days is\n" + "=" * 90)
    titles = {}
    for p in (ROOT / "data/v3_status_cache/us").glob("*.bill.json"):
        titles[p.name[:-len(".bill.json")]] = ((load(p, {}) or {}).get("bill") or {}).get("title", "")
    bound_cache = {}
    rows, tally_units, tally_words, tally_days = [], Counter(), Counter(), defaultdict(set)
    total_words = 0
    for e in idx:
        bk, day = e["bill_key"], e["debate_date"]
        rx = U.us_bill_mention_re(e["type"], e["number"])
        own_toks = toks(titles.get(bk, ""))
        for u in e.get("units", []):
            text = ""
            if u.get("source") == "daily_edition":
                f = ROOT / "data/us/v3/cache/daily" / f"CREC-{day}" / f"{u['id']}.txt"
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    text = ""
            else:
                if day not in bound_cache:
                    try:
                        bound_cache[day] = {x["id"]: x["text"] for x in U.bound_units(day, set())}
                    except Exception:                       # noqa: BLE001
                        bound_cache[day] = {}
                text = bound_cache[day].get(u["id"], "")
            words = len(text.split())
            total_words += words
            hits = len(rx.findall(text))
            nt = U.norm_title(u.get("title", ""))
            title_own = bool(rx.search(u.get("title", "")))
            ov = (len(toks(u.get("title", "")) & own_toks) / len(toks(u.get("title", ""))) if toks(u.get("title", "")) else 0.0)
            if U.is_proc_title(nt) or EXTRA_PROC.search(nt):
                kind = "procedural"
            elif SPEECH.search(text[:2500]):
                kind = "speech (one-minute or special order)"
            elif re.search(r"\bACT\b", nt) and not title_own and ov < 0.25 and hits <= 3:
                kind = "other bill's debate"
            elif words >= 5000 and hits <= 3:
                kind = "long, names the bill 3 times or fewer"
            else:
                kind = "ok"
            tally_units[kind] += 1
            tally_words[kind] += words
            tally_days[kind].add((bk, day))
            rows.append({"kind": kind, "bill_key": bk, "day": day, "unit": u["id"], "title": u.get("title", ""),
                         "words": words, "names_bill": hits, "title_names_bill": title_own,
                         "title_overlap": round(ov, 2), "method": u.get("method", ""),
                         "bill_title": titles.get(bk, "")[:120], "starts": short(text, 200)})
    say(f"units: {len(rows):,} in {len(idx)} bill-days; words: {total_words:,}")
    for k in ["ok", "procedural", "speech (one-minute or special order)", "other bill's debate",
              "long, names the bill 3 times or fewer"]:
        say(f"   {k:<40} units {tally_units[k]:>5}   bill-days {len(tally_days[k]):>4}   words {tally_words[k]:>10,}"
            f"   ({100.0 * tally_words[k] / max(total_words, 1):.1f}% of US words)")
    days_all = defaultdict(list)
    for r in rows:
        days_all[(r["bill_key"], r["day"])].append(r["kind"])
    only_flagged = [k for k, v in days_all.items() if all(x != "ok" for x in v)]
    say(f"bill-days where every unit is flagged (the whole day would go): {len(only_flagged)}")
    flagged = sorted((r for r in rows if r["kind"] != "ok"), key=lambda r: -r["words"])
    for k in ["other bill's debate", "long, names the bill 3 times or fewer", "procedural",
              "speech (one-minute or special order)"]:
        sub = [r for r in flagged if r["kind"] == k]
        say(f"\n--- {k}: {len(sub)} units (largest 40)")
        for r in sub[:40]:
            say(f"   {r['bill_key']:<14} {r['day']}  {r['words']:>7,} words  names bill {r['names_bill']:>3}x  "
                f"title overlap {r['title_overlap']:.2f}  {short(r['title'], 70)}")
            if k in ("other bill's debate", "long, names the bill 3 times or fewer"):
                say(f"        bill: {short(r['bill_title'], 110)}")
    out = AUD / "us_unit_flags.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["kind"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["kind"] == "ok", -r["words"])))
    say(f"\nevery unit with its class: {out}")


# ============================================================================ B. Quebec
def section_b():
    say("\n" + "=" * 90 + "\nB. Quebec: sections to look at, and pages the parser cannot read\n" + "=" * 90)
    qc = ROOT / "data/canada/quebec_assembly"
    idx = load(qc / "v3/segments_index.json", []) or []
    qs = load(ROOT / "data/dbpedia_pipeline/quebec/sentences_v3.json", []) or []
    say(f"Quebec now: {len(qs):,} sentences, {len(idx):,} bill-day sections")
    for bk, d in (("37-1-Bill56", "20041019"), ("36-1-Bill170", "20001219")):
        for e in idx:
            if e.get("bill_key") != bk:
                continue
            mark = "  <== look" if e.get("date") == d else ""
            say(f"{bk} {e.get('date')}  {e.get('n_paragraphs')} paras  label '{e.get('label', '')}'  "
                f"methods {e.get('methods')}  stages {e.get('stages')}{mark}")
            if e.get("date") == d:
                try:
                    paras = [p for p in (qc / e["file"]).read_text(encoding="utf-8").split("\n\n") if p.strip()]
                except OSError:
                    paras = []
                for p in paras[:5]:
                    say(f"      first: {short(p, 170)}")
                for p in paras[-2:]:
                    say(f"      last:  {short(p, 170)}")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None
    for name in ("38-1_20070605_3039.html", "39-1_20090923_11099.html", "39-1_20090924_11101.html"):
        p = qc / "v3/journal_cache" / name
        say(f"\n{name}: ", )
        if not p.exists():
            say("   not in the cache")
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        say(f"   {len(raw):,} characters; <contenu> tag: {'<contenu' in raw.lower()}; "
            f"<title>: {short(re.search(r'(?is)<title>(.*?)</title>', raw).group(1) if re.search(r'(?is)<title>(.*?)</title>', raw) else '', 110)}")
        low = raw.lower()
        for pat in ("projet de loi", "projet&nbsp;de&nbsp;loi", "projet de\nloi", "n<sup>o</sup>", "n&#176;", "n&deg;", "journal des d"):
            say(f"   '{pat}': {low.count(pat)}")
        for m in list(re.finditer(r"(?i)projet(?:\s|&nbsp;)+de(?:\s|&nbsp;)+loi", raw))[:3]:
            say(f"   context: {short(raw[max(0, m.start() - 80): m.end() + 120], 220)}")
        if BeautifulSoup:
            soup = BeautifulSoup(raw, "html.parser")
            body = soup.find("contenu") or soup.body or soup
            ps = body.find_all("p")
            say(f"   <p> in the main body: {len(ps)}; most common tags there: "
                f"{Counter(t.name for t in body.find_all(True)).most_common(8)}")
            shown = 0
            for tag in body.find_all(["p", "h1", "h2", "h3", "h4", "div", "span"]):
                txt = tag.get_text(" ", strip=True)
                if len(txt) < 3 or tag.find(["p", "div"]):
                    continue
                say(f"   <{tag.name} {dict(list(tag.attrs.items())[:3])}> {short(txt, 110)}")
                shown += 1
                if shown >= 25:
                    break


# ============================================================================ C. Quebec 1985-1994
def section_c():
    say("\n" + "=" * 90 + "\nC. Quebec 1985 to 1994: bill lists and how the session pages link to sittings\n" + "=" * 90)
    qb = ROOT / "data/canada/quebec_bills"
    for f in sorted(qb.glob("*")):
        if f.is_file():
            say(f"   {f.name:<55} {f.stat().st_size:>12,} bytes")
    po = load(qb / "quebec_pre1994_vote_outcomes.json")
    items = list(po.items()) if isinstance(po, dict) else list(enumerate(po or []))
    say(f"quebec_pre1994_vote_outcomes.json: {type(po).__name__} with {len(items)} records")
    for k, v in items[:4]:
        say(f"   {short(k, 90)} -> {short(json.dumps(v, ensure_ascii=False), 300)}")
    sess = Counter()
    for k, v in items:
        rec = v if isinstance(v, dict) else {}
        s = str(rec.get("session") or "")
        m = re.search(r"projet-loi-\d+-(\d+-\d+)", str(k) + json.dumps(rec))
        sess[s or (m.group(1) if m else "?")] += 1
    say(f"   by session: {dict(sorted(sess.items()))}")
    comb = load(qb / "quebec_health_bills_combined.json", []) or []
    old = [r for r in comb if re.match(r"^(\d+)-", str(r.get("session", ""))) and
           int(str(r.get("session")).split("-")[0]) <= 34]
    say(f"health list records from the 34th legislature or earlier: {len(old)}")
    for r in old[:8]:
        say(f"   {r.get('session')} Bill {r.get('bill_number')}: source {r.get('source')} | {short(r.get('title'), 100)}")
    say(f"health list records by source: {dict(Counter(str(r.get('source')) for r in comb))}")
    pre = ROOT / "data/canada/quebec_assembly/v3/pre1994"
    for f in sorted(pre.glob("index_*.html")):
        raw = f.read_text(encoding="utf-8", errors="ignore")
        hrefs = re.findall(r"""href\s*=\s*["']([^"']+)["']""", raw, re.I)
        pats = Counter(re.sub(r"\d+", "N", h.split("?")[0]) for h in hrefs)
        jd = [h for h in hrefs if re.search(r"journal|debat|seance|jd", h, re.I)]
        say(f"\n   {f.name}: {len(raw):,} chars, {len(hrefs)} links, {len(jd)} mention journal/debat/seance/jd")
        for h, n in Counter(re.sub(r"\d{5,}", "N", h) for h in jd).most_common(10):
            say(f"      {n:>3}x {short(h, 140)}")
        for h, n in pats.most_common(6):
            say(f"      pattern {n:>3}x {short(h, 120)}")


# ============================================================================ D. Canada sample
def section_d():
    import compare_debate_days_canada as CC
    say("\n" + "=" * 90 + "\nD. Canada: bills whose only stage is first reading / presentation\n" + "=" * 90)
    outc = load(ROOT / "data/v3_outcomes.json", {}) or {}
    # --- Ontario
    preds = load(ROOT / "data/dbpedia_pipeline/ontario/predications_v3.json", []) or []
    claims = Counter(p.get("bill_key", "") for p in preds)
    segs = load(ROOT / "data/canada/ontario/v3/hansard_segments_v3.json", {}) or {}
    later = re.compile(r"(second|third) reading|resuming the adjourned debate|committee of the whole", re.I)
    ola_first, ola_page = set(), set()
    for bk in claims:
        page = CC.STATUS / "ontario" / f"{bk}.html"
        if not page.exists():
            continue
        ola_page.add(bk)
        if CC.ola_days(page):
            continue
        t = CC.page_text(page).split("Debates and Progress")[0]
        rows = [m.group(0) for m in CC.EN_DATE.finditer(t)]
        if rows and not re.search(r"(Second|Third) Reading|Committee of the Whole", t):
            ola_first.add(bk)
    text_first, words = set(), {}
    for bk in claims:
        paras = [p for d in (segs.get(bk) or {}).values() for p in d]
        words[bk] = sum(len(str(p.get("text", "")).split()) for p in paras)
        if paras and not any(later.search(str(p.get("text", ""))) for p in paras):
            text_first.add(bk)
    both = ola_first & text_first
    say(f"ONTARIO: {len(claims)} bills with claims; {len(ola_page)} have an OLA status page")
    say(f"   first reading only, by the OLA page:                  {len(ola_first)}")
    say(f"   no second/third reading or adjourned debate in our text: {len(text_first)}")
    say(f"   both ways agree:                                      {len(both)}   "
        f"(OLA only {len(ola_first - text_first)}, text only among OLA-page bills {len((text_first & ola_page) - ola_first)})")

    def describe(group, name):
        o = outc.get("ontario", {})
        pas = Counter({1: "passed", 0: "not passed", None: "pending/none"}.get(o.get(b, {}).get("passed"), "?") for b in group)
        c = sum(claims[b] for b in group)
        med = sorted(words[b] for b in group)[len(group) // 2] if group else 0
        say(f"   {name}: {len(group)} bills, {c:,} claims ({100.0 * c / max(sum(claims.values()), 1):.1f}% of Ontario claims), "
            f"median {med:,} words of text per bill, outcomes {dict(pas)}")
    describe(both, "first reading only (both ways)")
    describe(set(claims) - text_first, "debated beyond first reading (our text)")
    for b in sorted(both)[:5]:
        first = next((p for d in (segs.get(b) or {}).values() for p in d), {})
        say(f"      e.g. {b}: {words[b]} words | {short(first.get('text'), 140)}")
    # --- Quebec
    qpreds = load(ROOT / "data/dbpedia_pipeline/quebec/predications_v3.json", []) or []
    qclaims = Counter(p.get("bill_key", "") for p in qpreds)
    qidx = load(ROOT / "data/canada/quebec_assembly/v3/segments_index.json", []) or []
    labels = defaultdict(set)
    for e in qidx:
        labels[e.get("bill_key", "")].add(str(e.get("label", "")))
    q_page_pres, q_text_pres = set(), set()
    for bk in qclaims:
        page = CC.STATUS / "quebec" / f"{bk}.html"
        if page.exists():
            kinds = {k for k, _ in CC.assnat_days(page).values()}
            if kinds and "debate" not in kinds:
                q_page_pres.add(bk)
        if labels[bk] and all(re.match(r"(?i)pr[ée]sentation", x) for x in labels[bk]):
            q_text_pres.add(bk)
    qb = q_page_pres & q_text_pres
    say(f"\nQUEBEC: {len(qclaims)} bills with claims")
    say(f"   only a presentation, by the Assemblee page: {len(q_page_pres)}; by our sections' labels: {len(q_text_pres)}; "
        f"both: {len(qb)}")
    o = outc.get("quebec", {})
    pas = Counter({1: "passed", 0: "not passed", None: "pending/none"}.get(o.get(b, {}).get("passed"), "?") for b in qb)
    c = sum(qclaims[b] for b in qb)
    say(f"   those bills: {c:,} claims ({100.0 * c / max(sum(qclaims.values()), 1):.1f}% of Quebec claims), outcomes {dict(pas)}")


def main():
    AUD.mkdir(parents=True, exist_ok=True)
    for fn in (section_a, section_b, section_c, section_d):
        try:
            fn()
        except Exception:                                   # noqa: BLE001
            say(f"\n!! {fn.__name__} stopped with an error (the other checks still ran):")
            say(traceback.format_exc(limit=3))
    with open(AUD / "open_items_check.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    print(f"\nSaved {AUD / 'open_items_check.txt'}")


if __name__ == "__main__":
    main()
