#!/usr/bin/env python3
"""
compare_debate_days_canada.py   (reads only; changes nothing)
The Ontario and Quebec version of compare_debate_days.py: for every predicated bill,
compares our sitting days with the debate days the legislature's own bill page lists.

  Ontario  OLA bill status page (data/v3_status_cache/ontario/{bill}.html; exists from
           the 36th Parliament, 1995, on). A row counts as a House debate day when its
           stage is Second Reading, Third Reading or Committee of the Whole House.
           Bills before 1995 have no status page and are reported as not checkable.
  Quebec   (1) the Assembly debate list in quebec_health_bills_combined.json
           (2) the Assemblee nationale bill page (data/v3_status_cache/quebec/{bill}.html):
               dates under Adoption du principe, Prise en considération du rapport and
               Adoption (Assembly stages; committee study is not in the Journal).

  MISSING     the official page lists a debate day we have no text for
  ok          we have it
  not debated that day (Hansard checked)
              Ontario only: the full Hansard of that day was downloaded (raw_official) and the
              bill appears only in a committee report or a procedural line, never in a debate.
              The status page lists the day because the bill was reported from committee.
  official date outside the bill's legislature
              Quebec only: the bill page gives a date before its legislature began or after the
              next one began (e.g. "17 juin 1996" for a 1999 bill), which cannot be right.
  ok (debate, in the previous day's sitting)
              Quebec only: the Journal page for that date never names the bill, the Journal
              page of the day before does, and we have the bill's text from that day. Long
              end-of-session sittings run past midnight, so the bill page lists both dates
              (Bill 116: both stages are in the 18 June 1996 Journal; the 19 June Journal
              never names it, checked on the cached page and on assnat.qc.ca).
Writes outputs/audit/debate_days_vs_official_canada.csv and prints a summary with
examples, including how many pages could not be read, so a parsing problem shows.
Run from project root:  python3 scripts/step1_debate_text/compare_debate_days_canada.py
"""
import csv, datetime as dt, html as htmlmod, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STATUS = ROOT / "data" / "v3_status_cache"
OUT = ROOT / "outputs" / "audit" / "debate_days_vs_official_canada.csv"
EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
      "November", "December"]
FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
      "novembre", "décembre"]
EN_DATE = re.compile(r"\b(" + "|".join(EN) + r")\s+(\d{1,2}),\s+(\d{4})")
FR_DATE = re.compile(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(FR) + r")\s+(\d{4})", re.I)
YMD8 = re.compile(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)")
ISO = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def page_text(path):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def valid(y, m, d):
    try:
        return dt.date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def iso_any(s):
    s = str(s)
    out = set()
    for m in YMD8.finditer(s):
        v = valid(*m.groups())
        if v:
            out.add(v)
    for m in ISO.finditer(s):
        v = valid(*m.groups())
        if v:
            out.add(v)
    for m in FR_DATE.finditer(s):
        v = valid(m.group(3), FR.index(m.group(2).lower()) + 1, m.group(1))
        if v:
            out.add(v)
    return out


# Quebec general elections: legislature L sits between election L and election L+1
QC_ELECTIONS = {"33": "1985-12-02", "34": "1989-09-25", "35": "1994-09-12", "36": "1998-11-30", "37": "2003-04-14",
                "38": "2007-03-26", "39": "2008-12-08", "40": "2012-09-04", "41": "2014-04-07", "42": "2018-10-01",
                "43": "2022-10-03", "44": "2026-10-05"}


def outside_legislature_dates(lg, d):
    if not str(lg).isdigit():
        return False
    lo, hi = QC_ELECTIONS.get(str(lg)), QC_ELECTIONS.get(str(int(lg) + 1))
    return bool(lo and hi) and not (lo <= d < hi)


OLA_DEBATE = re.compile(r"\b(Second|Third) Reading\s*[-\u2013\u2014|]?\s*Debate\b|"
                        r"Committee of the Whole House\s*[-\u2013\u2014|]?\s*(Debate|Considered|In Committee)\b")
OLA_VOTE = re.compile(r"\b(Second|Third) Reading\s*[-\u2013\u2014|]?\s*(Carried|Lost|Negatived|Defeated|Vote)\b")


def ola_days(path):
    """date -> (kind, row text) for House stages on an OLA status page. Each table row
    starts with its date; the text up to the next date is that row (several events on one
    date share it). 'debate' = a Second/Third Reading or Committee of the Whole House
    debate; 'vote' = a reading carried or lost. Procedural rows (ordered for third reading,
    time allocated, referral, royal assent, committee reports) are not counted."""
    t = page_text(path)
    ms = list(EN_DATE.finditer(t))
    days = {}
    for i, m in enumerate(ms):
        win = t[m.end(): ms[i + 1].start() if i + 1 < len(ms) else m.end() + 200][:200]
        d = valid(m.group(3), EN.index(m.group(1)) + 1, m.group(2))
        if not d:
            continue
        w = re.sub(r"Ordered for Third Reading[^|]*", " ", win)
        if OLA_DEBATE.search(w):
            days[d] = ("debate", win.strip()[:90])
        elif OLA_VOTE.search(w) and days.get(d, ("",))[0] != "debate":
            days[d] = ("vote", win.strip()[:90])
    return days


QC_HEAD = re.compile(r"(Présentation|Consultations particulières|Consultation générale|"
                     r"Dépôt du rapport de commission|Adoption du principe|Étude détaillée en commission|"
                     r"Prise en considération du rapport de commission|Adoption(?! du principe)|Sanction|"
                     r"Date de la dernière modification)")
QC_ASSEMBLY = {"Adoption du principe": "debate", "Prise en considération du rapport de commission": "debate",
               "Adoption": "debate", "Présentation": "presentation"}
QC_OTHER = {"Dépôt du rapport de commission": "report tabled, no debate",
            "Consultations particulières": "committee sitting", "Consultation générale": "committee sitting",
            "Étude détaillée en commission": "committee sitting", "Sanction": "royal assent"}
QC_RANK = {"debate": 0, "presentation": 1, "report tabled, no debate": 2, "committee sitting": 3, "royal assent": 4}
SEANCE = re.compile(r"Séances?\s+du\s+(\d{1,2})(?:er)?\s+(" + "|".join(FR) + r")\s+(\d{4})", re.I)


def assnat_days(path):
    """date -> (kind, stage) from the stage list on an Assemblee nationale bill page.
    Only 'Séance du ...' dates under Assembly stages count; committee stages (consultations,
    étude détaillée) are held in commission, not in the Assembly's Journal des débats."""
    return assnat_all(path, assembly_only=True)


def assnat_all(path, assembly_only=False):
    """Every dated stage on the page, keeping the most debate-like stage for each date."""
    t = page_text(path)
    parts = QC_HEAD.split(t)
    days = {}
    for i in range(1, len(parts) - 1, 2):
        kind = QC_ASSEMBLY.get(parts[i]) or (None if assembly_only else QC_OTHER.get(parts[i]))
        if not kind:
            continue
        for m in SEANCE.finditer(parts[i + 1]):
            d = valid(m.group(3), FR.index(m.group(2).lower()) + 1, m.group(1))
            if d and (d not in days or QC_RANK[kind] < QC_RANK[days[d][0]]):
                days[d] = (kind, parts[i])
    return days


def why_summary(rows, jur):
    miss = [r for r in rows if r["jurisdiction"] == jur and r["status"].startswith("MISSING") and r.get("why")]
    if not miss:
        return
    print(f"  why the {len(miss)} missing debate days are missing:")
    groups = defaultdict(list)
    for r in miss:
        groups[re.sub(r"\d+", "N", r["why"])].append(r)
    for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"    {len(v):>4}  {k}")
        for r in v[:3]:
            print(f"            {r['bill_key']} {r['date']}  ({r['official_stage'][:40]}): {r['why']}")


def main():
    rows = []
    summary = {}
    # ---------------- Ontario
    segs = load(ROOT / "data/canada/ontario/v3/hansard_segments_v3.json", {}) or {}
    preds = load(ROOT / "data/dbpedia_pipeline/ontario/predications_v3.json", []) or []
    ours = defaultdict(set)
    for bk, dmap in segs.items():
        ours[bk] |= set(dmap)
    for p in preds:
        ours[p.get("bill_key", "")].add(p.get("date", ""))
    bills = sorted({p.get("bill_key", "") for p in preds} - {""})
    tally, unread, nopage = Counter(), [], 0
    nodebate = defaultdict(list)
    for bk in bills:
        m = re.match(r"^(\d+)-", bk)
        page = STATUS / "ontario" / f"{bk}.html"
        if not page.exists():
            nopage += 1
            continue
        off = ola_days(page)
        if not off:
            t = page_text(page).split("Debates and Progress")[0]
            ms = list(EN_DATE.finditer(t))
            rows_txt = [t[m.start(): ms[i + 1].start() if i + 1 < len(ms) else m.end() + 120][:120].strip()
                        for i, m in enumerate(ms)]
            if not ms:
                unread.append(bk)
            elif any(re.search(r"(Second|Third) Reading|Committee of the Whole", r) for r in rows_txt):
                nodebate["has 2nd/3rd reading rows, none a debate or vote (check)"].append((bk, rows_txt[:4]))
            else:
                nodebate["first reading only (never debated)"].append((bk, rows_txt[:2]))
            continue
        for d, (kind, stage) in sorted(off.items()):
            st = ("ok" if d in ours[bk] else "MISSING") + f" ({kind} day)"
            if st.startswith("MISSING") and (ROOT / "data/canada/ontario/v3/raw_official" / bk / f"{d}.json").exists():
                st = f"not debated that day (Hansard checked, {kind} day on the status page)"
            tally[st] += 1
            rows.append({"jurisdiction": "ontario", "status": st, "bill_key": bk, "date": d,
                         "official_source": "OLA bill status page", "official_stage": stage})
    summary["ontario"] = (len(bills), nopage, unread, tally)
    summary["ontario_nodebate"] = nodebate

    # ---------------- Quebec
    idx = load(ROOT / "data/canada/quebec_assembly/v3/segments_index.json", []) or []
    qpreds = load(ROOT / "data/dbpedia_pipeline/quebec/predications_v3.json", []) or []
    qours = defaultdict(set)
    for e in idx:
        for d in iso_any(e.get("date", "")):
            qours[e["bill_key"]].add(d)
    for p in qpreds:
        qours[p.get("bill_key", "")].add(p.get("date", ""))
    comb = {}
    for e in load(ROOT / "data/canada/quebec_bills/quebec_health_bills_combined.json", []) or []:
        n = str(e.get("bill_number", "")).strip()
        if n.isdigit():
            comb[f"{e.get('session', '')}-Bill{int(n)}"] = e
    qbills = sorted({p.get("bill_key", "") for p in qpreds} - {""})
    qt, qunread, qnopage, qlist_empty = Counter(), [], 0, 0
    jc = ROOT / "data/canada/quebec_assembly/v3/journal_cache"
    jfiles = defaultdict(list)
    if jc.exists():
        for f in jc.iterdir():
            m = re.search(r"_((?:19|20)\d{6})_", f.name)
            if m:
                jfiles[valid(m.group(1)[:4], m.group(1)[4:6], m.group(1)[6:])].append(f)
    _txt = {}

    def names_bill(files, n):
        rx = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[o\u00b0\u00ba]?\.?\s*|num[e\u00e9]ro\s+)?" + str(n) + r"(?!\d)", re.I)
        for f in files:
            if f not in _txt:
                _txt[f] = page_text(f).replace("\u00a0", " ")
            if rx.search(_txt[f]):
                return True
        return False

    def outside_legislature(bk, d):
        return outside_legislature_dates(bk.split("-")[0], d)

    def previous_sitting(bk, d):
        n = int(bk.rsplit("-Bill", 1)[1])
        if not jfiles.get(d) or names_bill(jfiles[d], n):
            return False
        prev = (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()
        return prev in qours[bk] and names_bill(jfiles.get(prev, []), n)

    for bk in qbills:
        lst = iso_any(json.dumps((comb.get(bk) or {}).get("assembly_debates", ""), ensure_ascii=False))
        if not lst:
            qlist_empty += 1
        page = STATUS / "quebec" / f"{bk}.html"
        official, every = {}, {}
        if page.exists():
            official = assnat_days(page)
            every = assnat_all(page)
            if not official:
                qunread.append(bk)
        else:
            qnopage += 1
        for d in lst:
            if d in official:
                continue
            if d in every:              # on the page, but under a stage that is not a debate
                official[d] = (f"listed, {every[d][0]}", every[d][1])
            else:
                official[d] = ("listed only", "in assembly_debates, date not on bill page")
        for d, (kind, stage) in sorted(official.items()):
            if d not in qours[bk] and kind == "debate" and previous_sitting(bk, d):
                st = "ok (debate, in the previous day's sitting)"
            elif d not in qours[bk] and outside_legislature(bk, d):
                st = f"official date outside the bill's legislature ({kind})"
            else:
                st = ("ok" if d in qours[bk] else "MISSING") + f" ({kind})"
            qt[st] += 1
            rows.append({"jurisdiction": "quebec", "status": st, "bill_key": bk, "date": d,
                         "official_source": "Assemblee nationale bill page", "official_stage": stage})
    summary["quebec"] = (len(qbills), qnopage, qunread, qt, qlist_empty)

    # ---------------- why each missing debate day is missing
    on_all = defaultdict(set)                 # date -> Ontario bills we have text for that day
    for bk, dmap in segs.items():
        for d, paras in dmap.items():
            if paras:
                on_all[d].add(bk)
    qc_all = defaultdict(set)
    for e in idx:
        for d in iso_any(e.get("date", "")):
            qc_all[d].add(e["bill_key"])
    for r in rows:
        if r["status"] not in ("MISSING (debate day)", "MISSING (debate)"):
            continue
        bk, d = r["bill_key"], r["date"]
        n = re.search(r"Bill(\d+)$", bk).group(1)
        if r["jurisdiction"] == "ontario":
            others = on_all.get(d, set()) - {bk}
            r["why"] = (f"we have that day's Hansard (text for {len(others)} other bill(s)); this bill was not found in it"
                        if others else "no bill has text from that day: the day's Hansard was not downloaded or not read")
        else:
            others = qc_all.get(d, set()) - {bk}
            fs = jfiles.get(d, [])
            if fs:
                txt = " ".join(page_text(f) for f in fs).replace("\u00a0", " ")
                hits = len(re.findall(r"projet\s+de\s+loi\s+(?:n\s*[o°º]?\.?\s*)?" + n + r"(?!\d)", txt, re.I))
                r["why"] = (f"that day's Journal is downloaded ({len(fs)} file(s)) and names projet de loi {n} "
                            f"{hits} time(s); the bill was not cut out of it" if hits else
                            f"that day's Journal is downloaded ({len(fs)} file(s)) but never names projet de loi {n}")
            elif others:
                r["why"] = f"no Journal file for that day, yet {len(others)} other bill(s) have text from it"
            else:
                r["why"] = "that day's Journal was never downloaded"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["jurisdiction"], not r["status"].startswith("MISSING"), r["bill_key"], r["date"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["jurisdiction", "status", "bill_key", "date", "official_source",
                                          "official_stage", "why"])
        w.writeheader()
        w.writerows(rows)

    nb, nopage, unread, tally = summary["ontario"]
    print(f"ONTARIO: {nb} predicated bills; {nopage} have no OLA status page (before 1995, not checkable); "
          f"{len(unread)} pages with no dated rows at all" + (f" e.g. {unread[:5]}" if unread else ""))
    for k, v in summary["ontario_nodebate"].items():
        print(f"  {len(v):>5}  bills with no debate or vote day on the page: {k}")
        for bk_, rr in v[:3]:
            print(f"           {bk_}: " + " || ".join(rr))
    for k in sorted(tally):
        print(f"  {tally[k]:>5}  {k}")
    why_summary(rows, "ontario")
    nb, nopage, unread, qt, empty = summary["quebec"]
    print(f"\nQUEBEC: {nb} predicated bills; {nopage} without a cached bill page; {len(unread)} pages had no "
          f"readable Assembly stages" + (f" e.g. {unread[:5]}" if unread else ""))
    for k in sorted(qt):
        print(f"  {qt[k]:>5}  {k}")
    why_summary(rows, "quebec")
    print(f"\nfull list: {OUT}")


if __name__ == "__main__":
    main()
