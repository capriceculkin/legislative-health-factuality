#!/usr/bin/env python3
"""
us_sections_report.py   (reads only)

What the US section fix changed, checked two independent ways.

  1. totals before and after, by tag
  2. every removal, with the line in the Record that brings up the other measure and the checks
  3. text held for a look (kept in the data), every one listed with its text
  4. text added because a line in the Record brings the bill up
  5. bill-days and bills that left the data, and bill-days with no debate
  6. CHECK A, by headings: the Sept 29 hand reading of the 195 flagged Record items
     (outputs/audit/us_unit_flags.csv) against what the new rule did with each item
  7. CHECK B, by Congress.gov: share of bill-days with debate text on a day Congress.gov lists
     House floor action on the bill (day before or after allowed), before and after; and for
     every bill-day that left the data, whether Congress.gov lists House action that day
  8. against the previous pass (round 4): totals by tag and the bill-days that changed; what the round-5 rules took
     out or tagged companion
  9. CHECK D, by the files alone: the same Record paragraph in two bills' files on the same day
 10. OPEN ITEMS: every decision on the bill-days still in question, with the Record line behind each

Run from the project folder:  python3 scripts/step1_debate_text/us_sections_report.py data/_before_us_sections_<stamp> [previous pass]
Writes outputs/audit/us_sections_report.txt, us_sections_removed.csv, us_sections_held.csv
"""
import csv
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
AUD = ROOT / "outputs" / "audit"
US = ROOT / "data" / "us"
LINES = []
import us_sections as SEC  # noqa: E402


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def short(s, n=160):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 3] + "..."


def pct(a, b):
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


# the Sept 29 hand reading of Record item headings (us_hand_class.py), one method: headings only
OWN = [("111-HR3470", "NATIONALLY ENHANCING"), ("113-HR2668", "FAIRNESS FOR AMERICAN FAMILIES"),
       ("115-HR5797", "INDIVIDUALS IN MEDICAID"), ("111-HR5756", "TRAINING AND RESEARCH FOR AUTISM"),
       ("116-HR4764", "TIMELY REAUTHORIZATION"), ("117-HR941", "TIMELY REAUTHORIZATION"), ("118-HR7213", "AUTISM COLLABORATION"),
       ("117-HR5487", "STILLBIRTH HEALTH"), ("114-HR5613", "CONTINUING ACCESS TO HOSPITALS"), ("117-S578", "FOOD ALLERGY SAFETY"),
       ("115-HR7217", "IMPROVING MEDICAID PROGRAMS"), ("111-HR3199", "EMERGENCY MEDIC TRANSITION"),
       ("114-HR5659", "EXPANDING SENIORS RECEIVING DIALYSIS"), ("116-HR3253", "EMPOWERING BENEFICIARIES"),
       ("115-S3029", "PREMATURITY RESEARCH"), ("109-HR864", "SOBER TRUTH"), ("106-HR2498", "CARDIAC ARREST SURVIVAL"),
       ("111-HR1256", "FAMILY SMOKING PREVENTION"), ("114-HR3762", "RESTORING AMERICANS"), ("116-HR1425", "STATE HEALTH CARE PREMIUM"),
       ("108-HR1", "MEDICARE PRESCRIPTION DRUG AND MODERNIZATION"), ("110-HR6331", "MEDICARE IMPROVEMENTS FOR PATIENTS"),
       ("100-HR3361", "AMENDMENT IN THE NATURE"), ("101-HR3968", "ORGAN TRANSPLANT"), ("100-S1158", "NATIONAL HEALTH SERVICE CORPS"),
       ("104-S641", "RYAN WHITE"), ("104-S641", "CONFERENCE REPORT ON S. 641"), ("104-HR3103", "HEALTH COVERAGE AVAILABILITY"),
       ("101-HR3607", "MEDICARE CATASTROPHIC COVERAGE REPEAL"), ("101-HR3607", "MEDICARE CATASTROPHIC COVERAGE REFORM"),
       ("110-HR3963", "CHILDREN'S HEALTH INSURANCE"), ("108-HR1", "MOTION TO INSTRUCT CONFEREES ON H.R. 1"),
       ("104-HR2425", "MEDICARE PRESERVATION ACT"), ("109-HRES802", "ENCOURAGING ALL ELIGIBLE"), ("103-S1", "IN THE COMMITTEE OF THE WHOLE"),
       ("102-HR6182", "MAMMOGRAPHY"), ("112-HR1216", "REPEALING MANDATORY FUNDING"), ("117-HR1667", "DR. LORNA BREEN"),
       ("100-HR5560", "TECHNICAL CORRECTIONS"), ("106-HRES535", "SENSE OF THE HOUSE CONCERNING"), ("108-HR2122", "MAKING IN ORDER")]
VEHICLE = [("111-HR3590", "SERVICE MEMBERS HOME"), ("114-HR34", "TSUNAMI WARNING")]
UNSURE = [("101-HR4487", "CONFERENCE REPORT (H. REPT. 101-945)"), ("103-HR670", "AUTHORIZING THE CLERK"),
          ("103-HR4", "ALIENS INFECTED"), ("100-HR5142", "MODELING THE AIDS PANDEMIC")]
SPEECH_TITLES = ["THE TIME TO ACT IS NOW", "THE HEALTH ACT OF 2011", "LET'S NOT PLAY POLITICS", "30-SOMETHING", "THE DEMOCRATIC AGENDA",
                 "ISSUES OF THE DAY", "MEDICARE DECEPTION", "THE HEALTH CARE CRISIS", "MEDICARE PART D PRESCRIPTION",
                 "PRESCRIPTION DRUG COVERAGE UNDER", "HEALTH CARE"]


def hand_class(r):
    def hit(lst):
        return any(r["bill_key"] == k and r["title"].upper().startswith(t) for k, t in lst)
    k = r["kind"]
    if k == "ok":
        return "ok (not flagged)"
    if k == "procedural":
        return "procedural"
    if k.startswith("speech"):
        return "speech"
    if hit(VEHICLE):
        return "vehicle"
    if hit(OWN):
        return "own debate"
    if hit(UNSURE):
        return "unsure"
    if k in ("long, names the bill 3 times or fewer", "other bill's debate") and hit([(r["bill_key"], t) for t in SPEECH_TITLES]):
        return "speech"
    return "other bill's debate"


def floor_days(bk):
    try:
        from compare_debate_days import house_floor
    except Exception:                                   # noqa: BLE001
        return None
    acts = (load(ROOT / "data" / "v3_status_cache" / "us" / f"{bk}.actions.json", {}) or {}).get("actions")
    return None if acts is None else set(house_floor(acts))


def near(day, days):
    d0 = dt.date.fromisoformat(day)
    return any(abs((dt.date.fromisoformat(x) - d0).days) <= 1 for x in days)


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: us_sections_report.py data/_before_us_sections_<stamp> [data/_before_us_sections3_<stamp>]")
    before = ROOT / sys.argv[1] if not Path(sys.argv[1]).is_absolute() else Path(sys.argv[1])
    prev = None if len(sys.argv) < 3 else (ROOT / sys.argv[2] if not Path(sys.argv[2]).is_absolute() else Path(sys.argv[2]))
    old = load(before / "segments_index.json", []) or []
    new = load(US / "v3" / "segments_index.json", []) or []
    emptied = load(US / "v3" / "segments_emptied.json", []) or []
    say("=" * 100 + "\nUS SECTIONS: what the new rule changed\n" + "=" * 100)

    def file_words(base, e):
        try:
            return len((base / Path(e["file"]).name).read_text(encoding="utf-8").split()) if base else \
                len((US / e["file"]).read_text(encoding="utf-8").split())
        except OSError:
            return 0
    ow = {(e["bill_key"], e["debate_date"]): file_words(before / "cr_segments_v3", e) for e in old}
    tag_w, per_unit = Counter(), defaultdict(Counter)
    for e in new:
        paras = [p.strip() for p in (US / e["file"]).read_text(encoding="utf-8").split("\n\n") if p.strip()]
        tags = [t for t, n in e["para_tags"] for _ in range(n)]
        units = [u for u, n in e.get("para_units", []) for _ in range(n)]
        for p, t, u in zip(paras, tags, units):
            w = len(p.split())
            tag_w[t] += w
            per_unit[(e["bill_key"], e["debate_date"], u)][t] += w
    removed_rows = []
    for e in new:
        for r in e.get("removed", []):
            removed_rows.append({**r, "bill_key": e["bill_key"], "day": e["debate_date"], "whole_day": False})
    for x in emptied:
        for r in x.get("removed", []):
            removed_rows.append({**r, "bill_key": x["bill_key"], "day": x["debate_date"], "whole_day": True})
    for r in removed_rows:
        per_unit[(r["bill_key"], r["day"], r["unit"])]["removed: " + r["kind"]] += r["words"]
    total_old, total_new = sum(ow.values()), sum(tag_w.values())
    rem_w = sum(r["words"] for r in removed_rows)
    say(f"bill-days: {len(old)} -> {len(new)}   bills: {len({e['bill_key'] for e in old})} -> {len({e['bill_key'] for e in new})}")
    say(f"words in the bill-day files: {total_old:,} -> {total_new:,}; taken out: {rem_w:,} "
        f"({pct(rem_w, total_old)} of before)")
    say("\nwords now, by tag (the choices file decides which tags count; see apply_us_text_choices.py):")
    for t, w in tag_w.most_common():
        say(f"   {t:<34}{w:>12,}  {pct(w, total_new):>6}")

    say("\n" + "-" * 100 + f"\nREMOVED: {len(removed_rows)} pieces of Record items, {rem_w:,} words")
    kinds = Counter()
    for r in removed_rows:
        kinds[r["kind"]] += r["words"]
    for k, w in kinds.most_common():
        say(f"   {k:<14}{w:>12,} words")
    say("\nlargest 40 (the line is the Record's own line that brings up the other measure):")
    for r in sorted(removed_rows, key=lambda r: -r["words"])[:40]:
        say(f"   {r['bill_key']:<13}{r['day']}  {r['words']:>8,} words  {r['kind']:<11}{r.get('measure', ''):<12}"
            f"{'(whole day)' if r['whole_day'] else ''}  title: {short(r['title'], 60)}")
        if r["kind"] == "other":
            say(f"        checks: A line {r.get('A_line_brings_up_other')}, B title not this bill "
                f"{r.get('B_heading_not_this_bill', r.get('B_title_not_this_bill'))}, C no House action on Congress.gov {r.get('C_no_house_floor_action')}, "
                f"D other named as often {r.get('D_other_named_as_often')} ({r.get('mentions_other')} vs "
                f"{r.get('mentions_this_bill')})")
            say(f"        line: {short(r.get('line'), 200)}")
            if r.get("why_removed"):
                say(f"        {r['why_removed']}")
    AUD.mkdir(parents=True, exist_ok=True)
    cols = ["bill_key", "day", "whole_day", "kind", "measure", "unit", "title", "words", "paragraphs", "line",
            "A_line_brings_up_other", "B_title_not_this_bill", "C_no_house_floor_action", "D_other_named_as_often",
            "mentions_other", "mentions_this_bill", "member_speaks_40_words", "first", "url"]
    with open(AUD / "us_sections_removed.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(removed_rows, key=lambda r: -r["words"]))

    r3 = [r for r in removed_rows if "(round 3)" in str(r.get("why_removed", ""))]
    say("\n" + "-" * 100 + f"\nTAKEN OUT BY THE ROUND-3 RULES: {len(r3)} pieces, {sum(r['words'] for r in r3):,} words "
        "(the Record's own line inside the piece, or an omnibus list, or the same item title continued)")
    for r in sorted(r3, key=lambda r: -r["words"])[:60]:
        say(f"   {r['bill_key']:<13}{r['day']}  {r['words']:>8,} words  {r.get('measure', ''):<12}title: {short(r['title'], 60)}")
        say(f"        why: {short(r.get('why_removed'), 200)}")
        if r.get("line"):
            say(f"        line: {short(r.get('line'), 200)}")
    held = [{**h, "bill_key": e["bill_key"], "day": e["debate_date"]} for e in new for h in e.get("held", [])]
    hw = Counter()
    for h in held:
        hw[h["why"][:70]] += h.get("words", len(str(h.get("text", "")).split()))
    say("\n" + "-" * 100 + f"\nHELD (kept in the data, tagged 'held', to read): {len(held)} pieces, "
        f"{tag_w.get('held', 0) + sum(w for t, w in tag_w.items() if t.startswith('held+')):,} words")
    for k, w in hw.most_common():
        say(f"   {w:>10,} words  {k}")
    for h in sorted(held, key=lambda h: -h.get("words", 0))[:60]:
        say(f"   {h['bill_key']:<13}{h['day']}  {h.get('words', 0):>7,} words  {short(h.get('title', ''), 55)}  [{short(h['why'], 70)}]")
        say(f"        text: {short(h.get('text', ''), 260)}")
        for ln in (h.get("lines") or [])[:3]:
            say(f"        line naming a measure: {short(ln, 200)}  -> read as {SEC.consideration(ln)}")
    with open(AUD / "us_sections_held.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bill_key", "day", "unit", "title", "kind", "measure", "words", "why", "text", "url"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(held)

    added = [(e["bill_key"], e["debate_date"], e.get("added_paragraphs", 0)) for e in new if e.get("added_paragraphs")]
    say("\n" + "-" * 100 + f"\nADDED: {len(added)} bill-days gained paragraphs from a line in the Record that brings the bill up")
    for bk, d, n in sorted(added, key=lambda x: -x[2])[:30]:
        say(f"   {bk:<13}{d}  {n} paragraphs")
    new_days = {(e["bill_key"], e["debate_date"]) for e in new}
    gone_days = sorted(set(ow) - new_days)
    gone_bills = sorted({e["bill_key"] for e in old} - {e["bill_key"] for e in new})
    say("\n" + "-" * 100 + f"\nBILL-DAYS THAT LEFT THE DATA: {len(gone_days)}")
    why = {(x["bill_key"], x["debate_date"]): x for x in emptied}
    for k in gone_days:
        rs = why.get(k, {}).get("removed", [])
        say(f"   {k[0]:<13}{k[1]}  {ow[k]:>8,} words before; "
            + ("; ".join(f"{r['kind']} {r.get('measure', '')} ({r['words']:,} w, {short(r['title'], 40)})" for r in rs[:3])
               if rs else "no text kept"))
    say(f"BILLS THAT LEFT THE US DATA: {len(gone_bills)} {', '.join(gone_bills)}")
    nd = [e for e in new if e.get("no_debate")]
    bills_nd = sorted({e["bill_key"] for e in nd} - {e["bill_key"] for e in new if not e.get("no_debate")})
    say(f"\nbill-days with no member speaking 40+ words beyond motions and requests: {len(nd)}")
    say(f"bills with no such debate on any of their days (passed without debate): {len(bills_nd)} {', '.join(bills_nd)}")
    veh = [e for e in new if any(t.startswith("vehicle") for t, _ in e["para_tags"])]
    if veh:
        say("\nvehicle days (question 9; tagged, kept unless the choices file says out):")
        for e in veh:
            say(f"   {e['bill_key']} {e['debate_date']}: {e.get('tag_words', {})}")

    # ---------------------------------------------------------------- bills, additions, rule and companion tags
    new_bills = sorted({e["bill_key"] for e in new} - {e["bill_key"] for e in old})
    say(f"\nBILLS NOW IN THE US DATA THAT WERE NOT BEFORE: {len(new_bills)} {', '.join(new_bills)}")
    say("\nlargest additions, by tag (words):")
    for e in sorted((e for e in new if e.get("added_paragraphs")), key=lambda e: -e["added_paragraphs"])[:15]:
        say(f"   {e['bill_key']:<13}{e['debate_date']}  {e['added_paragraphs']} paragraphs added; now {e.get('tag_words', {})}")
    notes = [{**h, "bill_key": e["bill_key"], "day": e["debate_date"]} for e in new for h in e.get("notes", [])]
    for tag in ("rule", "companion"):
        sub = [h for h in notes if h.get("tag") == tag]
        say(f"\n{tag.upper()} tags: {len(sub)} pieces, {sum(h.get('words', 0) for h in sub):,} words")
        if tag == "rule":
            both = sum(1 for h in sub if h.get("rule_on_congress_gov") is True)
            say(f"   rule also listed for the bill on Congress.gov: {both} of {len(sub)} "
                f"(the Record's own rule text names the bill in every one)")
        for h in sorted(sub, key=lambda h: -h.get("words", 0))[:25]:
            say(f"   {h['bill_key']:<13}{h['day']}  {h.get('words', 0):>7,} w  {h.get('measure', ''):<11} {short(h.get('title'), 50)}"
                + (f"  [companion in data: {h.get('companion_in_data')}]" if tag == "companion" else ""))
    iss = AUD / "audit_issues.csv"
    if iss.exists():
        rows_i = [r for r in csv.DictReader(open(iss, encoding="utf-8")) if r["check"] == "I1" and r["jurisdiction"] == "us"]
        say(f"\naudit check I1 (US bill-day text names its bill) rows: {len(rows_i)}")
        for r in rows_i[:10]:
            say(f"   {r['bill_key']} {r['date']}: {short(r['detail'], 300)}")

    # ---------------------------------------------------------------- against the previous pass
    if prev is not None:
        pidx = load(prev / "segments_index.json", []) or []
        say("\n" + "=" * 100 + f"\nAGAINST THE PREVIOUS PASS ({prev.name})\n" + "=" * 100)

        def tag_words(index, base):
            out, per = Counter(), {}
            for e in index:
                try:
                    paras = [x.strip() for x in (base / Path(e["file"]).name).read_text(encoding="utf-8").split("\n\n") if x.strip()]
                except OSError:
                    continue
                tg = [t for t, n in e["para_tags"] for _ in range(n)]
                c = Counter()
                for x, t in zip(paras, tg):
                    c[t.split("+")[0]] += len(x.split())
                out.update(c)
                per[(e["bill_key"], e["debate_date"])] = c
            return out, per
        pw, pper = tag_words(pidx, prev / "cr_segments_v3")
        nw, nper = tag_words(new, US / "v3" / "cr_segments_v3")
        say(f"bill-days: {len(pidx)} -> {len(new)}; bills: {len({e['bill_key'] for e in pidx})} -> {len({e['bill_key'] for e in new})}")
        say(f"{'tag':<12}{'previous':>14}{'now':>14}{'change':>14}")
        for t in sorted(set(pw) | set(nw), key=lambda t: -(pw.get(t, 0) + nw.get(t, 0))):
            say(f"{t:<12}{pw.get(t, 0):>14,}{nw.get(t, 0):>14,}{nw.get(t, 0) - pw.get(t, 0):>+14,}")
        ch = []
        for k in set(pper) | set(nper):
            a, b2 = pper.get(k, Counter()), nper.get(k, Counter())
            d = sum(abs(b2.get(t, 0) - a.get(t, 0)) for t in set(a) | set(b2))
            if d:
                ch.append((d, k, dict(a), dict(b2)))
        say(f"bill-days whose text or tags changed: {len(ch)}; largest 40:")
        for d, k, a, b2 in sorted(ch, key=lambda x: -x[0])[:40]:
            say(f"   {k[0]:<13}{k[1]}  previous {a or 'not in the data'}  ->  now {b2 or 'not in the data'}")
    else:
        pper = {}

    # ---------------------------------------------------------------- round 5: what its rules took out or re-tagged
    r5 = [r for r in removed_rows if "(round 5)" in str(r.get("why_removed", ""))]
    say("\n" + "-" * 100 + f"\nTAKEN OUT BY THE ROUND-5 RULES: {len(r5)} pieces, {sum(r['words'] for r in r5):,} words")
    for r in sorted(r5, key=lambda r: -r["words"])[:60]:
        say(f"   {r['bill_key']:<13}{r['day']}  {r['words']:>8,} words  {r['kind']:<11}{r.get('measure', ''):<12}"
            f"{'(whole day) ' if r['whole_day'] else ''}title: {short(r['title'], 55)}")
        say(f"        why: {short(r.get('why_removed'), 220)}")
        if r.get("line"):
            say(f"        line: {short(r.get('line'), 200)}")
    c5 = [h for h in notes if "round 5" in str(h.get("why", ""))]
    say(f"TAGGED COMPANION BY THE ROUND-5 RULE (same title, other chamber, not in the data): {len(c5)} pieces, "
        f"{sum(h.get('words', 0) for h in c5):,} words")
    for h in sorted(c5, key=lambda h: -h.get("words", 0))[:30]:
        say(f"   {h['bill_key']:<13}{h['day']}  {h.get('words', 0):>8,} w  {h.get('measure', ''):<11} title: {short(h.get('title'), 55)}")

    # ---------------------------------------------------------------- CHECK D: one Record paragraph under two bills
    # independent of the section rule: it only compares the files. A one-minute speech naming two bills is in both
    # (tagged speech); the ACA debate read by hand counts for both bills; anything else in two bills' files is one
    # debate counted twice.
    hand = load(US / "v3" / "section_hand_checks.json", {}) or {}
    joint_keys = {(j[0], j[1]) for j in hand.get("joint_debates", [])}

    def shared(index, base):
        seen = defaultdict(set)
        for e in index:
            try:
                paras = [x.strip() for x in (base / Path(e["file"]).name).read_text(encoding="utf-8").split("\n\n") if x.strip()]
            except OSError:
                continue
            tg = [t for t, n in e["para_tags"] for _ in range(n)]
            for x, t in zip(paras, tg):
                if len(x.split()) >= 40:
                    seen[(e["debate_date"], x)].add((e["bill_key"], t.split("+")[0]))
        cats, groups = Counter(), Counter()
        for (day, x), s in seen.items():
            bills = tuple(sorted({b for b, _ in s}))
            if len(bills) < 2:
                continue
            tags = {t for _, t in s}
            cat = ("a speech naming both bills" if tags == {"speech"} else
                   "a rule that brings up both bills" if tags == {"rule"} else
                   "the joint debate read by hand" if all((b, day) in joint_keys for b in bills) else
                   "one debate kept under two bills")
            cats[cat] += len(x.split())
            if cat == "one debate kept under two bills":
                groups[(day, bills, tuple(sorted(tags)))] += len(x.split())
        return cats, groups
    say("\n" + "=" * 100 + "\nCHECK D: the same Record paragraph (40+ words) in two bills' files for the same day "
        "(compares the files only; does not use the section rule)\n" + "=" * 100)
    cats_now, groups_now = shared(new, US / "v3" / "cr_segments_v3")
    if prev is not None:
        cats_prev, _ = shared(pidx, prev / "cr_segments_v3")
    for cat in ("a speech naming both bills", "a rule that brings up both bills", "the joint debate read by hand",
                "one debate kept under two bills"):
        say(f"   {cat:<34} now {cats_now.get(cat, 0):>9,} words" +
            (f"   previous pass {cats_prev.get(cat, 0):>9,} words" if prev is not None else ""))
    for (day, bills, tags), w in groups_now.most_common(25):
        say(f"   {day}  {' & '.join(bills):<34} {w:>8,} words  tags {', '.join(tags)}")

    # ---------------------------------------------------------------- open items: every decision on each, to read
    OPEN = [("103-S1", "1993-03-10", "H.R. 4's Committee of the Whole debate was held under S. 1 (H.R. 4 is in the data that day)"),
            ("109-HR810", "2006-07-18", "S. 3504 and S. 2754 debates held under H.R. 810 the day before its veto debate"),
            ("111-HR3962", "2009-11-06", "a resolution on Chinese activists held under H.R. 3962 the day before its debate"),
            ("103-S1569", "1994-05-23", "H.R. 3869 (same title, House bill, not in the data) was taken out in round 4"),
            ("100-HR3361", "1988-07-12", "Sept 29 hand reading: own debate; the Record's line takes up S. 2385"),
            ("101-HR3968", "1990-04-04", "Sept 29 hand reading: own debate; the Record's line takes up H.R. 2015"),
            ("100-S1158", "1987-09-09", "Sept 29 hand reading: own debate; companion H.R. 1327 is in the data"),
            ("101-HR3607", "1989-11-21", "Sept 29 hand reading: speech; a long procedural stretch was taken out"),
            ("108-HR2122", "2003-07-15", "10,857 words held under 'MAKING IN ORDER AT ANY TIME CONSIDERATION OF H.R. 2122'"),
            ("111-HR577", "2009-03-31", "own debate shrank against round 2"),
            ("111-HR1256", "2009-06-12", "rule text read as the bill's line before round 5"),
            ("114-HR3762", "2016-01-06", "rule text read as the bill's line before round 5"),
            ("114-HR34", "2016-11-30", "rule text read as the bill's line before round 5")]
    say("\n" + "=" * 100 + "\nOPEN ITEMS: every decision on each bill-day still in question, with the Record line behind it\n" + "=" * 100)
    by_key = {(e["bill_key"], e["debate_date"]): e for e in new}
    gone = {(x["bill_key"], x["debate_date"]): x for x in emptied}
    for bk, day, about in OPEN:
        k = (bk, day)
        e = by_key.get(k) or gone.get(k)
        state = "in the data" if k in by_key else "left the data (every piece taken out)" if k in gone else "not read by the segment step"
        say(f"\n{bk} {day}: {state}.  ({about})")
        if k in by_key:
            say(f"   tags now: {by_key[k].get('tag_words', {})}" + (f"; previous pass: {dict(pper[k])}" if k in pper else ""))
        if e is None:
            continue
        for r in sorted(e.get("removed", []), key=lambda r: -r.get("words", 0))[:8]:
            say(f"   taken out {r.get('words', 0):,} w  {r.get('kind', '')} {r.get('measure', '')}  title: {short(r.get('title'), 60)}")
            default = {"other": "the Record's line brings up the other measure and two checks agree",
                       "procedural": "procedural: no line brings this bill up, and no member speaks 40+ words in it (or it is a "
                                     "long stretch naming the bill at most twice)",
                       "unexplained": "no line brings any measure up, and it names many other measures and this bill rarely"}
            say(f"        why: {short(r.get('why_removed') or default.get(r.get('kind'), ''), 200)}")
            if r.get("kind") == "other":
                say(f"        line: {short(r.get('line'), 220)}")
                say(f"        heading: {short(r.get('heading'), 80)} | names other {r.get('mentions_other')} x, this bill "
                    f"{r.get('mentions_this_bill')} x | other bill in the data that day: {r.get('other_in_data_that_day')} | "
                    f"heading shares this bill's title: {r.get('heading_title_share')} | companion in data: {r.get('companion_in_data', '')}")
            say(f"        starts: {short(r.get('first'), 220)}")
            for x in r.get("member_paragraphs", []) or []:
                say(f"        a member speaking in it: {short(x, 220)}")
            for x in r.get("paragraphs_naming_bill", []) or []:
                say(f"        naming this bill: {short(x, 220)}")
        for h in sorted(e.get("held", []), key=lambda h: -h.get("words", 0))[:6]:
            say(f"   held {h.get('words', 0):,} w  {h.get('measure', '')}  title: {short(h.get('title'), 60)}")
            say(f"        why: {short(h.get('why'), 200)}")
            say(f"        starts: {short(h.get('text'), 220)}")
        for h in e.get("notes", [])[:6]:
            say(f"   tagged {h.get('tag')} {h.get('words', 0):,} w  {h.get('measure', '')}  title: {short(h.get('title'), 60)}")
            say(f"        why: {short(h.get('why'), 200)}")

    # ---------------------------------------------------------------- CHECK C: printed text, read two ways
    say("\n" + "=" * 100 + "\nCHECK C: is text tagged printed really printed? Two tests that do not use the tagging rule\n"
        "   speech test: a paragraph addresses the Chair ('Mr. Speaker', 'Madam Chair') or yields time\n"
        "   statute test: a paragraph reads like bill text ('SEC. 2.', '(a) In general', 'is amended', 'by striking')\n" + "=" * 100)
    VOC = re.compile(r"\b(?:Mr\.|Madam)\s+(?:Speaker|Chair(?:man|woman)?)\b|\bI\s+yield\b|\bmy\s+colleagues\b")
    STAT = re.compile(r"^(?:\(?[a-zA-Z0-9]{1,5}\)\s|SEC(?:TION)?\.?\s+\d|Sec\.\s+\d|TITLE\s+[IVX]+|Subtitle\s+[A-Z])|"
                      r"\bis\s+amended\b|\bby\s+striking\b|\bby\s+inserting\b|\bBe\s+it\s+enacted\b|This\s+Act\s+may\s+be\s+cited")
    ATTR = re.compile(r"^((?:Mr|Mrs|Ms|Miss)\.\s+[^.]{2,60})\.\s+(?:Mr\.|Madam)\s+(?:Speaker|Chair)")
    grp = defaultdict(lambda: [0, 0, 0, 0])          # tag group -> paragraphs, words, speech-test, statute-test
    runs, missed = [], Counter()
    for e in new:
        paras = [p.strip() for p in (US / e["file"]).read_text(encoding="utf-8").split("\n\n") if p.strip()]
        tags = [t for t, n in e["para_tags"] for _ in range(n)]
        cur = None
        for p, t in zip(paras, tags):
            g = "printed" if "+printed" in t else "votelist" if "+votelist" in t else t.split("+")[0]
            a = grp[g]
            a[0] += 1
            a[1] += len(p.split())
            v, st = bool(VOC.search(p)), bool(STAT.search(p))
            a[2] += v
            a[3] += st
            if ATTR.match(p) and not (SEC.MEMBER.match(p) or SEC.CHAIR.match(p)):
                missed[ATTR.match(p).group(1)] += 1
            if g == "printed":
                if cur is None:
                    cur = {"bill_key": e["bill_key"], "day": e["debate_date"], "n": 0, "voc": 0, "first_voc": "", "first": p}
                cur["n"] += 1
                if v:
                    cur["voc"] += 1
                    cur["first_voc"] = cur["first_voc"] or p
            elif cur is not None:
                runs.append(cur)
                cur = None
        if cur is not None:
            runs.append(cur)
    say(f"{'tag':<12}{'paragraphs':>12}{'words':>13}{'speech test':>13}{'statute test':>14}")
    for g in ("debate", "printed", "votelist", "speech", "held", "rule", "companion", "vehicle"):
        a = grp.get(g)
        if a:
            say(f"{g:<12}{a[0]:>12,}{a[1]:>13,}{pct(a[2], a[0]):>13}{pct(a[3], a[0]):>14}")
    bad = sorted((r for r in runs if r["voc"] >= 2), key=lambda r: -r["voc"])
    say(f"printed runs: {len(runs):,}; runs with 2+ paragraphs that pass the speech test: {len(bad)} "
        f"(these may have run past the end of the printed text)")
    for r in bad[:25]:
        say(f"   {r['bill_key']:<13}{r['day']}  {r['n']:>5} paragraphs, {r['voc']:>4} address the Chair; first: {short(r['first_voc'], 170)}")
    say(f"paragraphs that look like a member speaking but are not read as one: {sum(missed.values())}")
    for k, n in missed.most_common(12):
        say(f"   {n:>6}  {k}")

    # ---------------------------------------------------------------- CHECK A: Sept 29 hand reading
    say("\n" + "=" * 100 + "\nCHECK A: the Sept 29 reading of item headings (by hand) against the new rule (Record lines)\n" + "=" * 100)
    flags = AUD / "us_unit_flags.csv"
    if not flags.exists():
        say("outputs/audit/us_unit_flags.csv (from check_open_items.py, Sept 29) not found; check A skipped")
    else:
        rows = list(csv.DictReader(open(flags, encoding="utf-8")))
        table = defaultdict(Counter)
        disagree = []
        for r in rows:
            hc = hand_class(r)
            fate = per_unit.get((r["bill_key"], r["day"], r["unit"]), Counter())
            if not fate and (r["bill_key"], r["day"]) not in new_days:
                fate = Counter({"removed: whole day": int(r["words"])})
            if not fate:
                fate = Counter({"not kept (no longer chosen)": int(r["words"])})
            top = fate.most_common(1)[0][0].split("+")[0]
            top = "removed" if top.startswith("removed") or top.startswith("not kept") else top
            table[hc][top] += 1
            expect = {"other bill's debate": "removed", "procedural": "removed", "own debate": "debate",
                      "speech": "speech", "vehicle": "vehicle"}.get(hc)
            if expect and top != expect and not (expect == "debate" and top == "companion") \
                    and not (expect == "removed" and top == "rule"):
                disagree.append((hc, top, r))
        cols2 = ["debate", "companion", "rule", "speech", "held", "vehicle", "removed"]
        say(f"{'hand reading (Sept 29)':<26}" + "".join(f"{c:>10}" for c in cols2) + "   (Record items; largest share of each item's words)")
        for hc in ["other bill's debate", "procedural", "own debate", "speech", "vehicle", "unsure", "ok (not flagged)"]:
            if table[hc]:
                say(f"{hc:<26}" + "".join(f"{table[hc][c]:>10}" for c in cols2))
        agree = sum(table[h][e] for h, e in (("other bill's debate", "removed"), ("other bill's debate", "rule"),
                                              ("procedural", "removed"), ("own debate", "debate"),
                                              ("own debate", "companion"), ("speech", "speech")))
        n_cmp = sum(sum(table[h].values()) for h in ("other bill's debate", "procedural", "own debate", "speech"))
        say(f"agreement on items the hand reading settled: {agree} of {n_cmp} ({pct(agree, n_cmp)})")
        say(f"items the Sept 29 check left as 'ok' that the new rule tags speech: {table['ok (not flagged)']['speech']} "
            f"(the Sept 29 speech check missed one-minutes whose marker was split across two lines)")
        say("\nevery disagreement (hand reading -> new rule), to read:")
        for hc, top, r in sorted(disagree, key=lambda x: -int(x[2]["words"])):
            say(f"   {hc:<20} -> {top:<9} {r['bill_key']:<13}{r['day']} {int(r['words']):>8,} w  {short(r['title'], 60)}")

    # ---------------------------------------------------------------- CHECK B: Congress.gov
    say("\n" + "=" * 100 + "\nCHECK B: Congress.gov House floor actions (an official record independent of the Record text)\n" + "=" * 100)
    fd_cache = {}

    def fd(bk):
        if bk not in fd_cache:
            fd_cache[bk] = floor_days(bk)
        return fd_cache[bk]
    for name, idx in (("before", old), ("after", new)):
        n = yes = nolist = 0
        for e in idx:
            if name == "after" and not any(t.split("+")[0] in ("debate", "vehicle") for t, _ in e["para_tags"]):
                continue
            days = fd(e["bill_key"])
            if days is None:
                nolist += 1
                continue
            n += 1
            yes += near(e["debate_date"], days)
        say(f"   {name:<7} bill-days{' with debate text' if name == 'after' else ''}: {n + nolist}; "
            f"House floor action on Congress.gov that day (or the day before/after): {yes} of {n} ({pct(yes, n)}); "
            f"no action list: {nolist}")
    DEB = re.compile(r"DEBATE\s*-|Considered under suspension|Considered under the provisions of rule|Committee of the Whole|"
                     r"GENERAL DEBATE|moved to suspend the rules|moved that the House suspend|Called up by|Considered as privileged|"
                     r"proceeded with|Considered as unfinished business", re.I)
    n = none = nodeb = 0
    deb_listed = []
    for k in gone_days:
        days = fd(k[0])
        if days is None:
            continue
        n += 1
        if not near(k[1], days):
            none += 1
            continue
        acts = (load(ROOT / "data" / "v3_status_cache" / "us" / f"{k[0]}.actions.json", {}) or {}).get("actions") or []
        house = [a for a in acts if "Senate" not in str((a.get("sourceSystem") or {}).get("name", ""))
                 and not (re.search(r"\bSenate\b", str(a.get("text", ""))) and not re.search(r"\bHouse\b", str(a.get("text", ""))))]
        deb_acts = [a for a in house if DEB.search(str(a.get("text", "")))]
        deb = {str(a.get("actionDate", ""))[:10] for a in deb_acts}
        if near(k[1], deb):
            same = k[1] in deb
            deb_listed.append((k, same, [f"{str(a.get('actionDate', ''))[:10]}: {short(a.get('text', ''), 110)}" for a in deb_acts
                                         if near(k[1], {str(a.get('actionDate', ''))[:10]})][:3]))
        nodeb += not near(k[1], deb)
    say(f"   bill-days that left the data: {len(gone_days)}; with a Congress.gov action list: {n}; of those, no House action "
        f"that day: {none}; House action but no debate (passed by unanimous consent): {nodeb}; House debate listed: "
        f"{n - none - nodeb} (that exact day: {sum(1 for x in deb_listed if x[1])}; only the day before or after: "
        f"{sum(1 for x in deb_listed if not x[1])})")
    for k, same, acts_txt in deb_listed:
        say(f"   {k[0]:<13}{k[1]}  {'debate listed that day' if same else 'debate listed the day before or after'}; to read:")
        for a in acts_txt:
            say(f"        {a}")
    (AUD / "us_sections_report.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    say(f"\nwrote outputs/audit/us_sections_report.txt, us_sections_removed.csv, us_sections_held.csv")


if __name__ == "__main__":
    main()
