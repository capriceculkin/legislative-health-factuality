#!/usr/bin/env python3
"""
sept24_before_after.py   (reads the data, changes nothing)

One sheet with every example shown at the September 24 meeting, what it showed then,
David's comment, and what the rebuilt data holds now for the same bill and dates.
For every old date that is no longer in the data it looks inside that day's saved raw
Hansard (Ontario) and reports where the bill is named, so the reason is shown, not assumed.

Run from the project folder:
  python3 scripts/step1_debate_text/sept24_before_after.py
Writes outputs/audit/sept24_before_after.xlsx (and .csv copies of each sheet).
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "audit"


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------ what Sept 24 showed
ONTARIO = [
    # key, title as shown, session label shown, dates shown, David's comment
    ("33-2-Bill94", "An Act regulating Amounts charged for Insured Services (extra billing)", "33-2 (Nov 1985 to Oct 1986)",
     ["1985-12-20", "1986-01-14", "1986-01-17", "1986-01-20"], "\"starts in april?\" / \"jan 17 not there\""),
    ("34-2-Bill52", "An Act to amend certain Statutes re Municipal Act", "34-2 (Mar 1989 to Aug 1990)",
     ["1989-07-20", "1989-10-10", "1989-12-06"], "\"the session is right, bill isnt exact but dates are better\""),
    ("42-2-Bill175", "An Act to amend Acts respecting home care and community services", "42-2 (Feb 2020 to May 2022)",
     ["2020-02-25", "2020-02-26", "2020-02-27", "2020-03-02", "2020-03-03"],
     "\"Back to the drawing board. Instead, sign by text similarity assign by similarity of the hash table\""),
    ("35-3-Bill50", "An Act to implement Government expenditure control plan", "35-3 (Nov 1993 to Feb 1995)",
     ["1993-11-15", "1993-11-16", "1993-11-17"], ""),
    ("33-2-Bill113", "An Act to amend the Homemakers and Nurses Services Act", "33-2", ["1986-07-03"], ""),
]
QUEBEC = [
    # bill number, title, legislature shown, dates shown (YYYY-MM-DD), file shown, David's comment
    ("2", "Loi modifiant diverses lois fiscales", "33rd, 1st session", ["1985-12-17", "1985-12-18"], "19851218_bill2.txt", ""),
    ("28", "Loi visant a mettre fin a l'etat d'urgence sanitaire", "42nd, 1st session", ["2022-04-13"], "20220413_bill28.txt",
     "\"yes this exists but the bill is not mentioned\""),
    ("130", "Loi sur les services de sante et les services sociaux", "35th, 1st session", ["1995-12-04"], "19951204_bill130.txt",
     "\"it should be 116... 130 is about justice\" / \"date is right but the bill number is the one that is wrong\""),
]
US = [
    # old file, topic shown, date shown, David's comment
    ("2006-12-09.txt", "SCHIP reauthorization", "2006-12-09",
     "\"this is the 8th!!!!\" / Friday December 8th is Vol. 152, No. 135 / \"parsing paragraph wrong, combining first and middle column\""),
    ("1985-06-18.txt", "Earliest health bill in corpus (mental health)", "1985-06-18", ""),
]
PREDICATION_EXAMPLES = [
    ("Ontario", "19850708-api-1985b32 (Bill 32, Workers Compensation)", "1985-07-08", "32"),
    ("Ontario", "19860319-bill14 (French spoken in the Ontario legislature)", "1986-03-19", "14"),
    ("Quebec", "19851219-bill3", "1985-12-19", "3"),
    ("Quebec", "19860319-bill14", "1986-03-19", "14"),
    ("Quebec", "20220413-bill28", "2022-04-13", "28"),
    ("US", "2006-12-09 (Congress passed an omnibus veterans bill)", "2006-12-09", ""),
    ("US", "2009-07-30 (The House gave its approval)", "2009-07-30", ""),
]
OLD_TOTALS = {  # as printed on Sept 24
    "Ontario": {"text units": "212 bills, 63,615 paragraphs", "sentences": 1942246, "claims": 197316},
    "Quebec": {"text units": "11,369 files", "sentences": 923634, "claims": 41718},
    "US": {"text units": "448 files", "sentences": 584111, "claims": 141186},
}

# ------------------------------------------------------------------ current data
on_segs = load(ROOT / "data/canada/ontario/v3/hansard_segments_v3.json", {}) or {}
on_master = load(ROOT / "data/canada/ontario/v3/bills_master.json", {}) or {}
on_index = load(ROOT / "data/canada/ontario/ontario_bill_index.json", {}) or {}
qc_idx = load(ROOT / "data/canada/quebec_assembly/v3/segments_index.json", []) or []
us_idx = load(ROOT / "data/us/v3/segments_index.json", []) or []
outcomes = load(ROOT / "data/v3_outcomes.json", {}) or {}
proposals = {(p.get("jurisdiction"), p.get("bill_key")): p for p in (load(ROOT / "data/v3_health_proposals.json", []) or [])}
RAW_DAYS = ROOT / "data/canada/ontario/v3/raw_days"


def hansard_url(session, day):
    p, s = session.split("-")
    return f"https://www.ola.org/en/legislative-business/house-documents/parliament-{p}/session-{s}/{day}/hansard"


_RANGES = {}
for _k, _days in on_segs.items():
    _s = _k.split("-Bill")[0]
    for _d in _days:
        lo, hi = _RANGES.get(_s, (_d, _d))
        _RANGES[_s] = (min(lo, _d), max(hi, _d))


def on_session_of(day):
    """The session a date falls in: the session whose rebuilt sitting days span that date
    (sessions in the rebuild come from the OLA API)."""
    for s, (lo, hi) in sorted(_RANGES.items()):
        if lo <= day <= hi:
            return s
    return ""


def raw_mentions(day, num):
    """Where Bill <num> is named in the saved raw Hansard of that day: heading, business type, first words."""
    rows = load(RAW_DAYS / f"{day}.json", None)
    if rows is None:
        return None
    rx = re.compile(rf"\bBill\s+{num}\b")
    found = []
    for r in rows:
        t = str(r.get("paragraph") or r.get("text") or r.get("content") or "")
        if rx.search(t):
            t = re.sub(r"<[^>]+>", " ", t)
            t = re.sub(r"\s+", " ", t).strip()
            found.append(f"[{r.get('topic') or '?'} | {r.get('typeOfBusiness') or '?'}] {t[:160]}")
    return found


def on_outcome(k):
    o = (outcomes.get("ontario") or {}).get(k) or {}
    return {1: "passed", True: "passed", 0: "not passed", False: "not passed"}.get(o.get("passed"), "no outcome") + \
        (f" ({o.get('source')})" if o.get("source") else "")


ON_ANCHOR = r"(moved (?:first|second|third) reading of (?:the following bill: )?Bill\s+{n}\b|motion for (?:first|second|third) reading of (?:the following bill: )?Bill\s+{n}\b|Bill\s+{n}\b[^.]{{0,80}}(?:read a (?:first|second|third) time|referred to))"


def clean(t, n=260):
    t = re.sub(r"<[^>]+>", " ", str(t or ""))
    return re.sub(r"\s+", " ", t).strip()[:n]


def on_how(paras, num):
    """Plain-language account of how the day's paragraphs were separated for the bill."""
    out = []
    by = {}
    for p in paras:
        m = str(p.get("assignment_method") or "")
        by.setdefault((m.split(":")[0], m, str(p.get("topic") or "")), 0)
        by[(m.split(":")[0], m, str(p.get("topic") or ""))] += 1
    for (kind, m, topic), n in sorted(by.items(), key=lambda x: -x[1]):
        if kind == "topic_hash_exact":
            out.append(f"{n} paragraphs under the bill's own heading '{topic}' (that heading is tied to Bill {num} "
                       f"by the line that moved it)")
        elif kind == "topic_hash_fuzzy":
            out.append(f"{n} paragraphs under '{topic}', a near-exact match of the bill's heading ({m.split(':')[-1]})")
        elif kind == "anchor_split":
            out.append(f"{n} paragraphs under the heading '{topic}', which is not the bill's own, kept from the line that "
                       f"moves Bill {num} until another bill is named")
        elif kind == "official_day_heading":
            out.append(f"{n} paragraphs under the bill's heading '{topic}' on a day the OLA bill page lists")
        else:
            out.append(f"{n} paragraphs, method {m}, heading '{topic}'")
    return "; ".join(out)


def on_anchor_line(paras, num):
    rx = re.compile(ON_ANCHOR.format(n=num), re.I)
    for p in paras:
        t = clean(p.get("text"), 2000)
        mm = rx.search(t)
        if mm:
            a = max(0, mm.start() - 80)
            return t[a:a + 260]
    return ""


QC_HOW = {
    "heading": "under the bill's own heading in the Journal (for example 'Projet de loi no 116')",
    "heading_line": "under a short line that names the bill, printed without heading formatting",
    "heading_then_stage": "a bill heading followed by a debate stage heading (Adoption du principe, Adoption, ...)",
    "text_anchor": "from the procedural line that opens the debate ('propose l'adoption du principe du projet de loi no N')",
    "chair_anchor": "from the chair's line that calls the bill ('L'Assemblee prend en consideration le rapport ... projet de loi no N')",
}
US_HOW = {
    "bill_number": "a Congressional Record section that names the bill (H.R./S. number) as its subject",
    "title_hash": "a Record section with the same heading as a section that names the bill, on the same day",
}

bill_rows, date_rows = [], []

# ---- Ontario
for key, title, sess_label, old_dates, comment in ONTARIO:
    sess, num = key.split("-Bill")
    # the same bill number in any session, so days that moved to another session are found
    same_num = {k: v for k, v in on_segs.items() if k.split("-Bill")[1] == num and k.split("-Bill")[0][:2] == sess[:2]}
    now_days = sorted(on_segs.get(key, {}))
    idx = on_index.get(key) or {}
    m = on_master.get(key) or {}
    health = "yes" if m.get("health") else ("no" if m else "not found in Hansard procedural lines")
    prop = proposals.get(("ontario", key))
    bill_rows.append({
        "jurisdiction": "Ontario", "example (Sept 24)": key, "title shown": title, "session shown": sess_label,
        "dates shown": ", ".join(old_dates), "David's comment": comment,
        "now: in study data": "yes" if key in on_segs else "no",
        "now: sitting days": ", ".join(now_days),
        "now: same bill number, other session": "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in sorted(same_num.items()) if k != key),
        "now: old index health tag": str(idx.get("health_tag", "not in index")),
        "now: rebuild health check": health + (f" ({m.get('health_basis')})" if m.get("health_basis") else ""),
        "now: health-list proposal": (prop or {}).get("decision", ""),
        "now: outcome": on_outcome(key) if key in on_segs else "",
        "old index dates": ", ".join(idx.get("dates", [])),
    })
    for d in sorted(set(old_dates) | set(now_days)):
        where = [k for k, v in same_num.items() if d in v]
        paras = (on_segs.get(where[0], {}) or {}).get(d, []) if where else []
        heads = sorted({str(p.get("topic") or "") for p in paras})[:3]
        meth = sorted({str(p.get("assignment_method") or "").split(":")[0] for p in paras})
        if where:
            status = "in data under " + ", ".join(where)
            why = f"{len(paras)} paragraphs under: {' | '.join(heads)}; assigned by {', '.join(meth)}"
        else:
            status = "not in data"
            mentions = raw_mentions(d, num)
            if mentions is None:
                why = "that day's raw Hansard is not saved (only days needed for health bills are downloaded); read the Hansard link"
            elif not mentions:
                why = f"the saved raw Hansard of that day never names Bill {num}"
            else:
                why = f"Bill {num} is only named here (heading | business): " + " || ".join(mentions[:3])
        s_guess = where[0].split("-Bill")[0] if where else (on_session_of(d) or sess)
        gov = next((str(p.get("url")) for p in paras if p.get("url")), "") or hansard_url(s_guess, d)
        tfile = ROOT / "data/canada/ontario/v3/bill_texts" / where[0] / f"{d}.txt" if where else None
        date_rows.append({"jurisdiction": "Ontario", "example": key, "date": d,
                          "shown on Sept 24": "yes" if d in old_dates else "no (new)",
                          "now": status, "detail": why,
                          "how it was separated": on_how(paras, num) if paras else "",
                          "line that ties it to the bill": on_anchor_line(paras, num) if paras else "",
                          "text starts": clean(paras[0].get("text")) if paras else "",
                          "our text file": str(tfile.relative_to(ROOT)) if tfile and tfile.exists() else "",
                          "government source": gov})

# ---- Quebec
for num, title, leg, old_dates, fname, comment in QUEBEC:
    ents = [e for e in qc_idx if str(e.get("bill_key", "")).split("Bill")[-1] == num]
    near = [e for e in qc_idx if str(e.get("date", "")) in {d.replace("-", "") for d in old_dates}]
    now = sorted({f"{e.get('bill_key')} {e.get('date')}" for e in ents if int(str(e.get('date', '0'))[:4] or 0) - int(old_dates[0][:4]) in (-1, 0, 1)})
    bill_rows.append({
        "jurisdiction": "Quebec", "example (Sept 24)": f"Bill {num} ({old_dates[0][:4]}), file {fname}", "title shown": title,
        "session shown": leg, "dates shown": ", ".join(old_dates), "David's comment": comment,
        "now: in study data": "yes" if now else "no",
        "now: sitting days": "; ".join(now),
        "now: same bill number, other session": "",
        "now: old index health tag": "",
        "now: rebuild health check": "",
        "now: health-list proposal": "",
        "now: outcome": "",
        "old index dates": "",
    })
    for d in old_dates:
        dd = d.replace("-", "")
        here = sorted({str(e.get("bill_key")) for e in near if str(e.get("date")) == dd})
        if int(d[:4]) < 1994:
            why = "Quebec before 1994 is not rebuilt yet: those health-list records carry placeholder bill numbers (open item)"
        elif here:
            why = "sections on this date now: " + ", ".join(here)
        else:
            why = "no section on this date"
        es = [e for e in near if str(e.get("date")) == dd]
        own = [e for e in es if str(e.get("bill_key")).endswith("Bill" + num)] or es
        e0 = own[0] if own else {}
        qfile = ROOT / "data/canada/quebec_assembly" / str(e0.get("file", "")) if e0.get("file") else None
        text0 = ""
        if qfile and qfile.exists():
            text0 = clean(qfile.read_text(encoding="utf-8", errors="ignore"))
        how = "; ".join(f"{n} paragraphs {QC_HOW.get(m, m)}" for m, n in (e0.get("methods") or {}).items())
        date_rows.append({"jurisdiction": "Quebec", "example": f"Bill {num}", "date": d, "shown on Sept 24": "yes",
                          "now": "in data" if any(h.endswith("Bill" + num) for h in here) else "not in data",
                          "detail": why,
                          "how it was separated": (f"{e0.get('bill_key')}: " + how) if how else "",
                          "line that ties it to the bill": "",
                          "text starts": text0,
                          "our text file": str(qfile.relative_to(ROOT)) if qfile and qfile.exists() else "",
                          "government source": str(e0.get("url", ""))})

# ---- US
for fname, topic, day, comment in US:
    d0 = day
    days = {d0}
    if d0 == "2006-12-09":
        days.add("2006-12-08")
    ents = [e for e in us_idx if e.get("debate_date") in days]
    parts = []
    for e in ents:
        p = ROOT / "data/us/v3/cr_segments_v3" / f"{e.get('bill_key')}_{e.get('debate_date')}.txt"
        schip = ""
        if p.exists() and "SCHIP" in topic:
            schip = f", names SCHIP {p.read_text(encoding='utf-8', errors='ignore').count('SCHIP')}x"
        issues = sorted({f"Vol. {u.get('printed', {}).get('volume')}, No. {u.get('printed', {}).get('number')}"
                         for u in e.get("units", []) if (u.get("printed") or {}).get("volume")})
        parts.append(f"{e.get('bill_key')} {e.get('debate_date')} ({len(e.get('units', []))} units{schip}; {', '.join(issues) or e.get('edition', '')})")
    bill_rows.append({
        "jurisdiction": "US", "example (Sept 24)": fname, "title shown": topic, "session shown": "",
        "dates shown": day, "David's comment": comment,
        "now: in study data": "yes" if ents else "no",
        "now: sitting days": "; ".join(parts),
        "now: same bill number, other session": "", "now: old index health tag": "", "now: rebuild health check": "",
        "now: health-list proposal": "", "now: outcome": "", "old index dates": "",
    })
    for e in ents:
        p = ROOT / "data/us/v3/cr_segments_v3" / f"{e.get('bill_key')}_{e.get('debate_date')}.txt"
        units = e.get("units", [])
        how = "; ".join(f"'{u.get('title', '')}': {US_HOW.get(str(u.get('method')), u.get('method'))}" for u in units[:4])
        issues = sorted({f"Vol. {(u.get('printed') or {}).get('volume')}, No. {(u.get('printed') or {}).get('number')}, "
                         f"printed date {(u.get('printed') or {}).get('date')}" for u in units if (u.get("printed") or {}).get("volume")})
        date_rows.append({"jurisdiction": "US", "example": fname, "date": e.get("debate_date"),
                          "shown on Sept 24": "shown as " + day,
                          "now": f"in data under {e.get('bill_key')}",
                          "detail": "; ".join(issues) or f"{e.get('edition', '')} edition",
                          "how it was separated": how,
                          "line that ties it to the bill": "",
                          "text starts": clean(p.read_text(encoding="utf-8", errors="ignore")) if p.exists() else "",
                          "our text file": str(p.relative_to(ROOT)) if p.exists() else "",
                          "government source": next((str(u.get("url")) for u in units if u.get("url")), "")})

# ---- predication examples
pred_rows = []
for jur, ex, day, num in PREDICATION_EXAMPLES:
    if jur == "Ontario":
        hit = sorted(k for k, v in on_segs.items() if k.split("-Bill")[1] == num and day in v)
        now = ", ".join(hit) if hit else "no Ontario bill " + num + " has text on this date now"
    elif jur == "Quebec":
        if int(day[:4]) < 1994:
            now = "Quebec before 1994 is not rebuilt yet (open item)"
        else:
            hit = sorted({str(e.get("bill_key")) for e in qc_idx if str(e.get("date")) == day.replace("-", "")
                          and str(e.get("bill_key")).endswith("Bill" + num)})
            now = ", ".join(hit) if hit else "no section on this date"
    else:
        dd = {day, "2006-12-08"} if day == "2006-12-09" else {day}
        hit = sorted({f"{e.get('bill_key')} {e.get('debate_date')}" for e in us_idx if e.get("debate_date") in dd})
        now = ", ".join(hit) if hit else "no US bill-day on this date"
    pred_rows.append({"jurisdiction": jur, "example claim (Sept 24)": ex, "date": day, "now": now,
                      "note": "claims are re-extracted from the rebuilt text; the claim step itself is today's decision"})

# ---- totals
tot_rows = []
for jur, key in (("Ontario", "ontario"), ("Quebec", "quebec"), ("US", "us")):
    s = load(ROOT / f"data/dbpedia_pipeline/{key}/sentences_v3.json", []) or []
    p = load(ROOT / f"data/dbpedia_pipeline/{key}/predications_v3.json", []) or []
    if jur == "Ontario":
        units = f"{len(on_segs)} bills, {sum(len(v) for d in on_segs.values() for v in d.values()):,} paragraphs, " \
                f"{sum(len(d) for d in on_segs.values()):,} bill-days"
    elif jur == "Quebec":
        units = f"{len(qc_idx):,} bill-day sections"
    else:
        units = f"{len(us_idx):,} bill-days"
    o = OLD_TOTALS[jur]
    tot_rows.append({"jurisdiction": jur, "Sept 24: text": o["text units"], "now: text": units,
                     "Sept 24: sentences": f"{o['sentences']:,}", "now: sentences": f"{len(s):,}",
                     "Sept 24: claims": f"{o['claims']:,}", "now: claims": f"{len(p):,}",
                     "Sept 24: claim rate": f"{100 * o['claims'] / o['sentences']:.1f}%",
                     "now: claim rate": f"{100 * len(p) / max(len(s), 1):.1f}%"})

# ------------------------------------------------------------------ write
OUT.mkdir(parents=True, exist_ok=True)
RULES = [
    {"jurisdiction": "Ontario", "step": "Which bills", "rule": "A bill is found in Hansard by a procedural line that moves it ('moved second reading of Bill 94, An Act ...'). It is kept as health if its title or debate heading has a health word, or it matches an old health-list bill (same session, same number, half the title words shared).", "script": "ontario_rebuild.py discover, master"},
    {"jurisdiction": "Ontario", "step": "Which session", "rule": "Sessions come from the OLA's own API (33-2 starts April 22, 1986), not a hand-made table.", "script": "ontario_rebuild.py"},
    {"jurisdiction": "Ontario", "step": "How text is separated", "rule": "Under a heading that belongs to the bill (the heading is tied to the bill by the line that moved it, per session), every paragraph goes to the bill. Under any other heading (Oral Questions topics, THIRD READING, statements), a paragraph goes to the bill only from a line that formally moves the bill until another bill is named. A bill number that is only mentioned never assigns text.", "script": "ontario_rebuild.py assign"},
    {"jurisdiction": "Ontario", "step": "Example: Dec 20, 1985", "rule": "Bill 94 is named only in Question Period, under the heading EXTRA BILLING, when Mr. Timbrell asks whether it will go to committee after second reading in January. That is a question about the bill, not a motion, so no text is assigned.", "script": "OLA Hansard 1985-12-20"},
    {"jurisdiction": "Quebec", "step": "Which days", "rule": "The debates listed on each bill's own Assemblee nationale page.", "script": "quebec_rebuild.py"},
    {"jurisdiction": "Quebec", "step": "How text is separated", "rule": "Each Journal des debats page is read paragraph by paragraph: a bill heading or a procedural line ('propose l'adoption du principe du projet de loi no N') starts the bill, and the next section heading ends it.", "script": "quebec_rebuild.py segment"},
    {"jurisdiction": "US", "step": "Which days", "rule": "The vote date and the days before it, plus every House floor day Congress.gov lists for the bill.", "script": "us_rebuild.py"},
    {"jurisdiction": "US", "step": "How text is separated", "rule": "The Congressional Record is already split into sections with headings. A section is kept if it names the bill (H.R./S. number), plus sections under the same heading on the same day. Rule debates and procedural notices are left out. From 1994 the daily edition is used; before 1994 the bound-edition PDF is read column by column.", "script": "us_rebuild.py segment"},
]
sheets = [("Bills shown Sept 24", bill_rows), ("Every date", date_rows), ("How it was separated", RULES),
          ("Claim examples", pred_rows), ("Totals", tot_rows)]
for name, rows in sheets:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    with open(OUT / f"sept24_before_after_{slug}.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name[:31])
        if not rows:
            continue
        cols = list(rows[0].keys())
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append([r.get(c, "") for c in cols])
        for i, c in enumerate(cols, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(60, max(12, len(c) + 2))
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
    path = OUT / "sept24_before_after.xlsx"
    wb.save(path)
    print(f"wrote {path}")
except ImportError:
    print("openpyxl not installed: wrote the CSV files only")

for name, rows in sheets[:2]:
    print(f"\n== {name}")
    for r in rows:
        print("  " + " | ".join(str(v)[:110] for v in r.values()))
