#!/usr/bin/env python3
"""
diagnose_canada_days.py   (reads only; changes nothing; no internet)

Explains three Canada problems in one run, so they can be fixed together.

  1. ONTARIO, extra paragraphs. Bill 149's sections on 1997-09-29 and 1997-10-07 hold
     paragraphs filed under HOSPITAL RESTRUCTURING and ABORTION. ontario_rebuild.py gives
     a paragraph to a bill when its Hansard heading is in the "topic hash", and a heading
     enters the hash when discovery anchors ("moved second reading of Bill 149") were
     found under it. This counts every paragraph that reached a bill through a heading
     that is not a bill heading (no ACT / LOI / CODE / BILL in it), and prints the
     anchors that tied each such heading to the bill.
  2. ONTARIO, missing days. For each MISSING day in debate_days_vs_official_canada.csv:
     was an anchor found that day, was the day inside the fetch window, were paragraphs
     fetched, and where did assign send them.
  3. QUEBEC, missing days. For each MISSING day: is the day in the bill's
     assembly_debates list, is the page cached, and what quebec_rebuild.py's own parser
     saw where the page names the bill (heading it skipped, heading it did not
     recognise, or text it filed under another bill).

Run from the project folder (takes a few minutes):
    python3 scripts/step1_debate_text/diagnose_canada_days.py
Prints a report and saves the same text to outputs/audit/canada_diagnosis.txt
"""
import csv
import datetime as dt
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ontario_rebuild as ON      # noqa: E402  (paths and helpers exactly as the pipeline uses them)
import quebec_rebuild as QR       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
AUDIT = os.path.join(ROOT, "outputs", "audit")
CMP = os.path.join(AUDIT, "debate_days_vs_official_canada.csv")
REPORT = os.path.join(AUDIT, "canada_diagnosis.txt")
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def short(s, n=110):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 3] + "..."


BILL_WORDS = re.compile(r"\b(ACTS?|LOIS?|CODE|BILL|STATUTES?)\b")


def bill_like(topic):
    return bool(BILL_WORDS.search(str(topic or "").upper()))


def missing_rows(jur, statuses):
    if not os.path.exists(CMP):
        sys.exit(f"{CMP} not found. Run  python3 scripts/step1_debate_text/compare_debate_days_canada.py  first.")
    with open(CMP, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["jurisdiction"] == jur and r["status"] in statuses]


# =============================================================================== ONTARIO
def ontario():
    seg = ON.load_json(ON.SEGMENTS, {}) or {}
    anchors = ON.load_json(ON.ANCHORS, []) or []
    master = ON.load_json(ON.MASTER, {}) or {}
    topic_hash, _conf = ON.build_topic_hash(anchors)
    keys_by_session = defaultdict(list)
    for (s, t) in topic_hash:
        keys_by_session[s].append(t)
    by_heading = defaultdict(list)               # (session, topic_norm) -> strong anchors under it
    for a in anchors:
        if a.get("strong") and a.get("session"):
            by_heading[(a["session"], a.get("topic_norm", ""))].append(a)

    # ---------------------------------------------------------------- 1. extra paragraphs
    say("=" * 78)
    say("ONTARIO 1. paragraphs that reached a bill through a heading that is not a bill heading")
    say("=" * 78)
    tot_p = tot_w = sus_p = sus_w = 0
    method_tab = Counter()
    days_any, days_all, bills_any = 0, 0, set()
    per = defaultdict(lambda: {"paras": 0, "words": 0, "days": set(), "methods": Counter()})
    for bk, days in seg.items():
        for d, paras in days.items():
            n_sus = 0
            for p in paras:
                w = len(str(p.get("text", "")).split())
                m = str(p.get("assignment_method", "")).split(":")[0]
                t = p.get("topic", "")
                kind = ("bill heading" if bill_like(t) else
                        "procedural heading" if ON.is_procedural_topic(ON.norm_topic(t)) else "other heading")
                method_tab[(m, kind)] += 1
                tot_p += 1
                tot_w += w
                if m.startswith("topic_hash") and kind == "other heading":
                    n_sus += 1
                    sus_p += 1
                    sus_w += w
                    k = (bk, t)
                    per[k]["paras"] += 1
                    per[k]["words"] += w
                    per[k]["days"].add(d)
                    per[k]["methods"][m] += 1
            if n_sus:
                days_any += 1
                bills_any.add(bk)
                days_all += n_sus == len(paras)
    n_days = sum(len(v) for v in seg.values())
    say(f"All Ontario paragraphs: {tot_p:,} in {n_days:,} bill-days of {len(seg)} bills")
    say("How paragraphs were assigned (method, kind of heading) -> paragraphs:")
    for (m, kind), n in sorted(method_tab.items(), key=lambda x: -x[1]):
        say(f"   {n:>8,}  {m:<18} {kind}")
    say(f"SUSPECT (topic hash, heading is not a bill heading): {sus_p:,} paragraphs "
        f"({(sus_p / tot_p if tot_p else 0):.1%} of paragraphs, {(sus_w / tot_w if tot_w else 0):.1%} of words), "
        f"in {days_any:,} bill-days of {len(bills_any)} bills; {days_all:,} bill-days are made ONLY of these")
    heads = Counter()
    for (bk, t), v in per.items():
        heads[t] += v["paras"]
    say(f"Distinct suspect headings: {len(heads)}. Largest 30 (bill, heading, paragraphs, days, and the anchors "
        "that tied the heading to the bill):")
    for (bk, t), v in sorted(per.items(), key=lambda kv: -kv[1]["paras"])[:30]:
        sess, num = bk.rsplit("-Bill", 1)
        nt = ON.norm_topic(t)
        tied = [a for a in by_heading.get((sess, nt), []) if str(a.get("bill_number")) == num]
        other = Counter(str(a.get("bill_number")) for a in by_heading.get((sess, nt), [])
                        if str(a.get("bill_number")) != num)
        say(f"   {v['paras']:>5} paras {len(v['days']):>3} days  {bk:<14} '{short(t, 50)}'  "
            f"method {dict(v['methods'])}")
        if tied:
            dates = sorted({a.get('date', '') for a in tied})
            say(f"          tied by {len(tied)} anchor(s) on {', '.join(dates[:4])}{' ...' if len(dates) > 4 else ''}"
                + (f"; anchors for other bills under it: {dict(other)}" if other else ""))
            say(f"          e.g. {tied[0].get('date', '')} [{tied[0].get('type_of_business', '')}] "
                f"\"{short(tied[0].get('text', ''), 150)}\"")
        else:
            say("          no anchor under this exact heading (reached by fuzzy heading match)")
    for bk in ("36-1-Bill149",):
        if bk in seg:
            say(f"\n   {bk}, every heading in its sections (paragraphs per day):")
            for d in sorted(seg[bk]):
                c = Counter(p.get("topic", "") for p in seg[bk][d])
                say(f"      {d}: " + "; ".join(f"{short(t, 45)} {n}" for t, n in c.most_common()))

    # ---------------------------------------------------------------- 2. missing days
    say("\n" + "=" * 78)
    say("ONTARIO 2. why each missing day is missing")
    say("=" * 78)
    rows = missing_rows("ontario", ("MISSING (debate day)", "MISSING (vote day)"))
    cats = Counter()
    for r in rows:
        bk, d = r["bill_key"], r["date"]
        sess, num = bk.rsplit("-Bill", 1)
        m = master.get(bk) or {}
        A = [a for a in anchors if a.get("session") == sess and str(a.get("bill_number")) == num]
        a_day = [a for a in A if a.get("date") == d]
        ad = m.get("anchor_dates") or []
        if ad:
            lo, hi = ad[0], (dt.date.fromisoformat(ad[-1]) + dt.timedelta(days=45)).isoformat()
            in_win = lo <= d <= hi
            win = f"{lo} to {hi}"
        else:
            in_win, win = False, "none (no dated strong anchors)"
        raw = ON.load_json(os.path.join(ON.RAW_DIR, f"{bk}.json"), None)
        raw_day = [x for x in (raw or []) if ON.row_date(x) == d]
        dayp = os.path.join(ON.DAY_DIR, f"{d}.json")
        full = ON.load_json(dayp, None) if os.path.exists(dayp) else None
        rx = re.compile(r"\bBill\s+(?:No\.\s*)?" + num + r"\b", re.I)
        full_named = [x for x in (full or []) if rx.search(ON.row_text(x))]
        if not m:
            why = "bill is not in bills_master.json"
        elif not m.get("health"):
            why = "bill is not flagged health in bills_master.json"
        elif raw is None:
            why = "the bill's raw fetch file does not exist"
        elif raw_day:
            owners = Counter()
            for x in raw_day:
                t = x.get("topic") or ""
                nt = ON.norm_topic(t)
                if ON.is_procedural_topic(nt):
                    owners[f"procedural heading '{short(t, 30)}' (anchor split)"] += 1
                    continue
                if ON.row_session(x) != sess:
                    owners["dropped: other session"] += 1
                    continue
                o = topic_hash.get((sess, nt))
                if o is None:
                    o, _s = ON.fuzzy_owner(nt, sess, keys_by_session, topic_hash)
                owners[f"'{short(t, 30)}' -> " + ("no bill (heading not in hash)" if o is None
                                                  else f"Bill {o}" + (" (this bill)" if str(o) == num else ""))] += 1
            why = "fetched, but assign did not keep them"
            detail = "; ".join(f"{k}: {n}" for k, n in owners.most_common(4))
        elif a_day:
            why = "anchor found that day, but no paragraphs of that day were fetched"
        elif not in_win:
            why = "no anchor found that day, and the day is outside the fetch window"
        else:
            why = "inside the fetch window, but no paragraph that day was under the bill's headings"
        cats[why] += 1
        say(f"\n{bk} {d} [{r['status']}] {short(r.get('official_stage', ''), 60)}")
        say(f"   -> {why}")
        if raw_day:
            say(f"      {len(raw_day)} paragraphs fetched that day; {detail}")
        say(f"      bill headings from anchors: {', '.join(short(t, 40) for t in (m.get('topics') or [])[:4]) or 'none'}"
            f" | fetch window: {win}")
        for a in a_day[:3]:
            say(f"      anchor that day: strong={a.get('strong')} stage={a.get('stage')} heading='{short(a.get('topic'), 40)}'"
                f" \"{short(a.get('text'), 100)}\"")
        if full is None:
            say("      full day file: not on disk (this day was never downloaded in full)")
        else:
            tops = Counter(x.get("topic") or "" for x in full_named)
            say(f"      full day file on disk: {len(full)} paragraphs, {len(full_named)} name Bill {num}; their headings: "
                + ("; ".join(f"{short(t, 35)} {n}" for t, n in tops.most_common(4)) or "none"))
    say("\nONTARIO missing days by reason:")
    for k, n in cats.most_common():
        say(f"   {n:>4}  {k}")


# =============================================================================== QUEBEC
FR_DAY = re.compile(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})(?:er)?\s+"
                    r"(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\s+(\d{4})")


def quebec():
    say("\n" + "=" * 78)
    say("QUEBEC 3. why each missing debate day is missing")
    say("=" * 78)
    debates, _ = QR.expected_debates()
    listed = defaultdict(list)
    for d in debates:
        iso = f"{d['date'][:4]}-{d['date'][4:6]}-{d['date'][6:]}"
        listed[(f"{d['bill_session']}-Bill{d['bill_number']}", iso)].append(d)
    missing = {}
    for m in QR.load_json(os.path.join(QR.OUT, "segments_missing.json"), []) or []:
        missing[(f"{m.get('bill_session')}-Bill{m.get('bill_number')}", str(m.get("date")))] = m
    failed = set(QR.load_json(os.path.join(QR.OUT, "fetch_failed.json"), []) or [])
    cache_by_date = defaultdict(list)
    if os.path.isdir(QR.CACHE):
        for f in os.listdir(QR.CACHE):
            mm = re.search(r"_(\d{8})_", f)
            if mm:
                cache_by_date[mm.group(1)].append(f)
    parsed = {}
    cats = defaultdict(list)
    moved = Counter()          # (this bill-day, other bill) -> paragraphs about this bill filed under the other
    for r in missing_rows("quebec", ("MISSING (debate)",)):
        bk, d = r["bill_key"], r["date"]
        num = int(bk.rsplit("-Bill", 1)[1])
        ymd = d.replace("-", "")
        ds = listed.get((bk, d), [])
        if not ds:
            cats["the date is on the bill page but not in the bill's assembly_debates list, so the pipeline "
                 "never looked at it"].append((r, None, f"Journal pages cached for that date: "
                                                        f"{cache_by_date.get(ymd, []) or 'none'}"))
            continue
        for x in ds:
            p = QR.cache_path(x["url"])
            if not os.path.exists(p):
                cats["listed, but the page was never downloaded"].append(
                    (r, None, f"url {x['url']}" + (" (in fetch_failed.json)" if x["url"] in failed else "")))
                continue
            if p not in parsed:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    parsed[p] = QR.parse_page(f.read())
            segs, blocks = parsed[p]
            reason = (missing.get((bk, ymd)) or {}).get("reason", "")
            if segs.get(num):
                cats["the parser finds the bill on this page now (the index may be older than the parser)"].append(
                    (r, None, f"{len(segs[num])} paragraphs"))
                continue
            hits = [i for i, b in enumerate(blocks) if str(num) in QR._BILL_HEAD_TXT.findall(QR._norm(b["text"]))]
            if not hits:
                page_day = next((" ".join(mm.groups()) for b in blocks[:80]
                                 for mm in [FR_DAY.search(QR._norm(b["text"]))] if mm), "not found")
                run, score = QR.title_fallback(blocks, num, x["title"])
                cats["the page never names 'projet de loi N'"].append(
                    (r, None, f"page {os.path.basename(p)}, {len(blocks)} paragraphs, page's own date: {page_day}; "
                              f"bills the parser found: {sorted(segs)}; title overlap {score:.2f}; "
                              f"other pages cached that date: {[f for f in cache_by_date.get(ymd, []) if f != os.path.basename(p)]}"))
                continue
            kinds = Counter()
            for i in hits:
                b = blocks[i]
                if b["heading"] and b["section"].startswith(QR._NO_DEBATE_SECTIONS):
                    kinds[f"a heading inside a section the parser skips ('{short(b['section'], 40)}')"] += 1
                elif b["heading"]:
                    kinds["a heading the parser read, but the next heading reset it"] += 1
                elif len(b["text"]) <= 250:
                    kinds["a short line the parser did not treat as a heading"] += 1
                else:
                    kinds["speech text only"] += 1
                if b["bill"] is not None and b["bill"] != num:
                    moved[(bk, d, b["bill"])] += 1
            first = hits[0]
            fb = blocks[first]
            lab = ("heading, skipped section" if fb["heading"] and fb["section"].startswith(QR._NO_DEBATE_SECTIONS)
                   else "heading, reset" if fb["heading"]
                   else "short line not treated as a heading" if len(fb["text"]) <= 250 else "speech text")
            on = f"bill {fb['bill']}" if fb["bill"] is not None else "no bill"
            key = f"first place the page names the bill: {lab}; the parser was on {('ANOTHER BILL' if fb['bill'] not in (None, num) else on)}"
            ctx = []
            for j in range(max(0, first - 3), min(len(blocks), first + 5)):
                b = blocks[j]
                ctx.append(f"{'>>' if j == first else '  '} {'H' if b['heading'] else 'p'} "
                           f"sec='{short(b['section'], 28)}' bill={b['bill']} | {short(b['text'], 110)}")
            cats[key].append((r, ctx, f"{len(hits)} places name it: {dict(kinds)}; pipeline reason: {short(reason, 90)}"))
    total = sum(len(v) for v in cats.values())
    say(f"Missing Quebec debate days examined: {total}")
    for k, v in sorted(cats.items(), key=lambda kv: -len(kv[1])):
        say(f"\n  {len(v):>4}  {k}")
        for r, ctx, info in v[:3]:
            say(f"        {r['bill_key']} {r['date']} ({short(r.get('official_stage', ''), 40)}): {info}")
            for c in (ctx or []):
                say(f"             {c}")
        if len(v) > 3:
            say("        others: " + ", ".join(f"{r['bill_key']} {r['date']}" for r, _, _ in v[3:]))
    if moved:
        say("\nParagraphs that name a missing bill but were filed under ANOTHER bill (possible mix-ups):")
        for (bk, d, other), n in moved.most_common(20):
            say(f"   {bk} {d}: {n} paragraph(s) naming it went to Bill {other}")

    # every existing Quebec section: does it contain a short "Projet de loi n N" line for a DIFFERENT
    # bill? That is a heading the parser did not recognise, and the text after it belongs to bill N.
    say("\nQUEBEC 4. existing sections that contain another bill's heading line (text after it is that bill's)")
    idx = QR.load_json(QR.INDEX, []) or []
    head_line = re.compile(r"^projet de loi\s+(?:n\s*[o°º]?\.?\s*|numero\s+)?(\d+)\b")
    hit_secs, hit_paras, tot_paras, ex = 0, 0, 0, []
    for e in idx:
        try:
            with open(os.path.join(QR.QC, e["file"]), encoding="utf-8") as f:
                paras = [p for p in f.read().split("\n\n") if p.strip()]
        except (OSError, KeyError):
            continue
        tot_paras += len(paras)
        own = int(e.get("bill_number", -1))
        cut = next((i for i, p in enumerate(paras)
                    if len(p) <= 250 and (m := head_line.match(QR._norm(p))) and int(m.group(1)) != own), None)
        if cut is not None:
            hit_secs += 1
            hit_paras += len(paras) - cut
            if len(ex) < 6:
                ex.append(f"   {e.get('bill_key')} {e.get('date')}: from paragraph {cut + 1} of {len(paras)}, "
                          f"'{short(paras[cut], 60)}'")
    say(f"   sections checked: {len(idx)}; with another bill's heading line inside: {hit_secs}; "
        f"paragraphs from that line on: {hit_paras:,} of {tot_paras:,}")
    for x in ex:
        say(x)


if __name__ == "__main__":
    t0 = dt.datetime.now()
    say(f"CANADA DIAGNOSIS {t0:%Y-%m-%d %H:%M}  (reads only)")
    for part in (ontario, quebec):
        try:
            part()
        except Exception as ex:                        # keep going so one part's problem does not hide the other
            import traceback
            say(f"\n!! {part.__name__} part stopped: {ex!r}")
            say(traceback.format_exc())
    os.makedirs(AUDIT, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    print(f"\nSaved {REPORT}  ({(dt.datetime.now() - t0).seconds}s)")
