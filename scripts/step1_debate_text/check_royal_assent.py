#!/usr/bin/env python3
"""
check_royal_assent.py   (reads only; changes nothing in data/)

Why: Bill 50 (35-3) is labelled "not passed" because it is missing from the FSOB
vote file, but the Hansard of 1993-12-14 lists it under ROYAL ASSENT. The same
"bill absent" rule labels about 70 pre-1995 Ontario bills, and the FSOB royal
assent field labels about 50 more. This checks all of them against a second,
independent source: the ROYAL ASSENT sections of the Hansard itself.

Steps
  1. Downloads every paragraph filed under a ROYAL ASSENT heading from the OLA
     Hansard API, 1985 to 2003 (not saved into data/).
  2. Reads the bill numbers named in those paragraphs, with the session taken
     from each paragraph's own Hansard page address.
  3. Benchmark: for bills with an OLA bill status page (1995 on), compares
     "named in a royal assent list" with the OLA page. This says how far the
     method can be trusted before it is used on older bills.
  4. For every bill whose outcome came from the FSOB file (the bills before
     1995), compares the current outcome with the royal assent lists.
  5. Lists possible carry-overs: the same bill number in two sessions of one
     Parliament under the same debate heading (like Bill 94 in 33-1 and 33-2).

Run from the project folder:
  python3 scripts/step1_debate_text/check_royal_assent.py
Writes outputs/audit/royal_assent_check.csv, outputs/audit/carry_over_bills.csv
and outputs/audit/royal_assent_check.txt
"""
import csv
import os
import re
import sys
from collections import defaultdict

os.environ.setdefault("OLA_SLEEP", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ontario_rebuild as ob  # noqa: E402

START, END = "1985-05-01", "2003-12-31"
TOPICS = ["ROYAL ASSENT", "ROYAL ASSENT / SANCTION ROYALE", "SANCTION ROYALE / ROYAL ASSENT", "SANCTION ROYALE"]
BILL_RX = re.compile(r"\bBill\s+(\d+)\b")

lines = []


def say(s=""):
    print(s, flush=True)
    lines.append(s)


def parl(key):
    m = re.match(r"^(\d+)-(\d+)-Bill(\d+)$", key)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (None, None, None)


probe = ob.load_probe()
if not probe["decisions"].get("use_topic_filter"):
    say("The probe found the API's topic filter unreliable, so this check cannot pull ROYAL ASSENT "
        "sections by heading. Nothing was checked.")
    sys.exit(1)

# 1-2. royal assent paragraphs -> assented bill keys
rows, capped = [], []
for t in TOPICS:
    got = ob.query_complete("*", "topic eq '" + t.replace("'", "''") + "'", START, END, capped)
    say(f"ROYAL ASSENT heading '{t}': {len(got)} paragraphs")
    rows += got
assent = {}          # key -> first assent date
no_session = 0
for r in rows:
    sess = ob.row_session(r)
    if not sess:
        no_session += 1
        continue
    d = ob.row_date(r)
    for n in BILL_RX.findall(ob.row_text(r)):
        k = f"{sess}-Bill{int(n)}"
        if k not in assent or d < assent[k]:
            assent[k] = d
say(f"bills named in royal assent lists: {len(assent)} (paragraphs with no session in their page address: {no_session})")
cache = {"range": [START, END], "sessions_covered": sorted({ob.row_session(r) for r in rows if ob.row_session(r)}),
         "bills": {k: {"date": d} for k, d in sorted(assent.items())}}
ob.save_json(cache, ob.rp("data", "canada", "ontario", "v3", "royal_assent_lists.json"))
say("saved data/canada/ontario/v3/royal_assent_lists.json (read by apply_royal_assent.py)")
if capped:
    say(f"WARNING: {len(capped)} single days reached the API row cap; see output for dates: {capped[:5]}")

outcomes = (ob.load_json(ob.rp("data", "v3_outcomes.json"), {}) or {}).get("ontario", {})
covered = {ob.row_session(r) for r in rows if ob.row_session(r)}

# 3. benchmark against OLA bill pages
bench = []
for k, o in outcomes.items():
    p, s, _ = parl(k)
    if p is None or o.get("source") != "OLA bill status page" or o.get("passed") not in (0, 1, True, False):
        continue
    if f"{p}-{s}" not in covered:
        continue
    bench.append((k, int(bool(o["passed"])), int(k in assent)))
agree = sum(a == b for _, a, b in bench)
say()
say("BENCHMARK (bills with an OLA status page, sessions that have a royal assent section in the API):")
if bench:
    fp = [k for k, a, b in bench if a == 0 and b == 1]
    fn = [k for k, a, b in bench if a == 1 and b == 0]
    say(f"  royal assent list vs OLA page: {agree}/{len(bench)} agree ({agree / len(bench):.1%})")
    named = [(k, a) for k, a, b in bench if b == 1]
    if named:
        ok = sum(a for _, a in named)
        say(f"  of bills NAMED in a list, OLA says passed: {ok}/{len(named)} ({ok / len(named):.1%})  <- how far 'named = passed' can be trusted")
    notn = [(k, a) for k, a, b in bench if b == 0]
    if notn:
        z = sum(1 for _, a in notn if a == 0)
        say(f"  of bills NOT named, OLA says not passed: {z}/{len(notn)} ({z / len(notn):.1%})  <- 'not named = not passed' is NOT used")
    say(f"  named in a list but OLA says not passed: {len(fp)} {fp[:10]}")
    say(f"  OLA says passed but not named in a list: {len(fn)} {fn[:10]}")
else:
    say("  no overlap (the API has no royal assent sections for 1995 to 2003, or no OLA pages were fetched)")

# 4. FSOB-based outcomes
say()
say("BILLS WHOSE OUTCOME CAME FROM THE FSOB FILE:")
out_rows = []
by_src = defaultdict(lambda: [0, 0])
for k in sorted(outcomes, key=lambda x: parl(x)):
    o = outcomes[k]
    src = str(o.get("source") or "")
    if "fsob" not in src.lower():
        continue
    p, s, n = parl(k)
    cur = {1: 1, True: 1, 0: 0, False: 0}.get(o.get("passed"))
    ra = int(k in assent)
    sess_has_list = f"{p}-{s}" in covered
    verdict = ("agrees" if cur == ra else "DISAGREES") if sess_has_list else "no royal assent section found for this session"
    if sess_has_list and cur is not None:
        by_src[src][0 if cur == ra else 1] += 1
    out_rows.append({"bill_key": k, "current_outcome": {1: "passed", 0: "not passed"}.get(cur, "none"),
                     "current_source": src, "named_in_royal_assent_list": "yes" if ra else "no",
                     "royal_assent_date": assent.get(k, ""), "verdict": verdict,
                     "official_hansard": (f"https://www.ola.org/en/legislative-business/house-documents/"
                                          f"parliament-{p}/session-{s}/{assent[k]}/hansard") if ra else ""})
for src, (a, d) in sorted(by_src.items()):
    say(f"  {src}: {a} agree, {d} disagree")
dis = [r for r in out_rows if r["verdict"] == "DISAGREES"]
say(f"  disagreements ({len(dis)}):")
for r in dis:
    say(f"    {r['bill_key']:<14} now: {r['current_outcome']:<11} royal assent list: {r['named_in_royal_assent_list']:<3} "
        f"{r['royal_assent_date']}  ({r['current_source']})")
nolist = [r["bill_key"] for r in out_rows if r["verdict"].startswith("no royal")]
if nolist:
    say(f"  sessions with no royal assent section in the API ({len(nolist)} bills, not judged): {nolist[:15]}")

# 5. carry-overs
say()
say("POSSIBLE CARRY-OVERS (same number, same Parliament, next session, same debate heading):")
master = ob.load_json(ob.MASTER, {}) or {}
GENERIC = {"", "ORDERS OF THE DAY", "THIRD READINGS", "SECOND READINGS", "INTRODUCTION OF BILLS", "FIRST READINGS",
           "DEFERRED VOTES", "ORAL QUESTIONS", "COMMITTEE OF THE WHOLE HOUSE", "ROYAL ASSENT"}
carry = []
for k, v in master.items():
    p, s, n = parl(k)
    if p is None:
        continue
    k2 = f"{p}-{s + 1}-Bill{n}"
    if k2 not in master:
        continue
    t1 = {ob.norm_topic(t) for t in (v.get("topics") or [])} - GENERIC
    t2 = {ob.norm_topic(t) for t in (master[k2].get("topics") or [])} - GENERIC
    shared = sorted(t for t in t1 & t2 if not t.startswith(("STANDING COMMITTEE", "SELECT COMMITTEE", "THIRD READING",
                                                             "SECOND READING", "FIRST READING", "COMMITTEE OF THE WHOLE")))
    if shared and n != 1:
        o1, o2 = outcomes.get(k, {}), outcomes.get(k2, {})
        carry.append({"first_session_key": k, "next_session_key": k2, "shared_heading": shared[0],
                      "health_first": v.get("health"), "health_next": master[k2].get("health"),
                      "outcome_first": {1: "passed", 0: "not passed"}.get(o1.get("passed"), "none"),
                      "outcome_next": {1: "passed", 0: "not passed"}.get(o2.get("passed"), "none")})
carry.sort(key=lambda r: parl(r["first_session_key"]))
say(f"  {len(carry)} pairs; health bills among them: "
    f"{sum(1 for r in carry if r['health_first'] or r['health_next'])}")
for r in carry[:25]:
    say(f"    {r['first_session_key']:<13} -> {r['next_session_key']:<13} {r['shared_heading'][:60]:<60} "
        f"outcomes: {r['outcome_first']} / {r['outcome_next']}")

os.makedirs(ob.rp("outputs", "audit"), exist_ok=True)
for name, data in (("royal_assent_check.csv", out_rows), ("carry_over_bills.csv", carry)):
    path = ob.rp("outputs", "audit", name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        if data:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    say(f"wrote {path}")
with open(ob.rp("outputs", "audit", "royal_assent_check.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
