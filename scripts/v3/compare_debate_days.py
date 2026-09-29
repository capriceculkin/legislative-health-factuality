#!/usr/bin/env python3
"""
compare_debate_days.py   (reads only; changes nothing)
For every US bill, compares the sitting days in our data with the House floor days in
the bill's own Congress.gov action list (data/v3_status_cache/us/{bill}.actions.json,
already downloaded). Congress.gov records the day a bill was debated ("DEBATE - The
House proceeded with forty minutes of debate", "Considered under suspension of the
rules", Committee of the Whole) separately from the day it was voted on, so a debate
held days before the vote shows up here even when our search window missed it.

Rules Committee actions (reporting the rule) are not counted as debate.
  MISSING: debate days before the vote, outside the search window
        the pipeline searched only the vote day and 1 day before (pre-1994) or 3 days
        before (1994 on); this debate was earlier (H.R. 2454 on 10/28/1991)
  MISSING: in the search window but not kept
        the day was searched, but no section for the bill was kept
  MISSING: earlier House action with no vote in our list
        e.g. first House passage by voice vote when our vote is a later one
  MISSING: after the outcome vote
        later House debate (Senate amendments, conference report); in scope only if
        the outcome is "became law"
  CHECK: one day from a day we have
        Congress.gov lists debate the day before or after a day we have. Often the same
        sitting (the Record prints a sitting under its legislative day, so debate past
        midnight is dated a day apart), but it can be a second day of debate.
  NOT LISTED on Congress.gov
        a day we have that Congress.gov does not list as a House floor day (worth a look)

Writes outputs/audit/debate_days_vs_congress.csv and prints a summary.
Run from project root:  python3 scripts/v3/compare_debate_days.py
"""
import csv, datetime as dt, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "v3_status_cache" / "us"
OUT = ROOT / "outputs" / "audit" / "debate_days_vs_congress.csv"

DEBATE = re.compile(r"DEBATE\s*-|Considered under suspension|Considered under the provisions of rule|"
                    r"Considered by unanimous consent|Committee of the Whole|"
                    r"GENERAL DEBATE|moved to suspend the rules|moved that the House suspend|Called up by|"
                    r"Considered as privileged|proceeded with", re.I)
RULES = re.compile(r"^\s*(Rules\s*Committee|Committee on Rules|Rule\s+H\.?\s*Res)", re.I)   # the rule, not the bill
VOTE = re.compile(r"Considered as unfinished business|On passage|On motion to suspend|On motion that the House|Passed/agreed to in House|"
                  r"Motion to reconsider|On agreeing to the conference report|Resolving differences -- House|"
                  r"motion to recommit|Agreed to by", re.I)


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def house_floor(actions):
    """date -> ('debate' | 'vote', [texts]) for House floor actions."""
    days = defaultdict(lambda: [set(), []])
    for a in actions:
        t = str(a.get("text", ""))
        d = str(a.get("actionDate", ""))[:10]
        src = str((a.get("sourceSystem") or {}).get("name", ""))
        if not d or (re.search(r"\bSenate\b", t) and not re.search(r"\bHouse\b", t)) or "Senate" in src:
            continue
        if RULES.search(t):
            continue
        kind = "debate" if DEBATE.search(t) else ("vote" if VOTE.search(t) else None)
        if kind:
            days[d][0].add(kind)
            if t not in days[d][1]:
                days[d][1].append(t)
    return {d: ("debate" if "debate" in k else "vote", txt) for d, (k, txt) in days.items()}


def near(d, days):
    """True when one of days is the day before or after d (the Record prints a sitting
    under its legislative day, so a debate that ran past midnight can be dated a day apart)."""
    x = dt.date.fromisoformat(d)
    return any(abs((dt.date.fromisoformat(y) - x).days) == 1 for y in days)


def main():
    idx = load(ROOT / "data/us/v3/segments_index.json", []) or []
    preds = load(ROOT / "data/dbpedia_pipeline/us/predications_v3.json", []) or []
    outc = (load(ROOT / "data/v3_outcomes.json", {}) or {}).get("us", {})
    ours = defaultdict(lambda: defaultdict(lambda: [0, 0]))      # bill -> day -> [text files, predications]
    for e in idx:
        ours[e["bill_key"]][e["debate_date"]][0] += 1
    for p in preds:
        ours[p.get("bill_key", "")][p.get("date", "")][1] += 1
    plan = load(ROOT / "data/us/v3/plan.json", []) or []
    bills = sorted(({p.get("bill_key", "") for p in preds} | set(ours) | {e.get("bill_key", "") for e in plan}
                    | set(outc)) - {""})
    rows, cover = [], Counter()
    no_actions = []
    for bk in bills:
        acts = (load(CACHE / f"{bk}.actions.json", {}) or {}).get("actions")
        cong = bk.split("-")[0]
        if acts is None:
            no_actions.append(bk)
            continue
        floor = house_floor(acts)
        cover[(cong, bool(any(k == "debate" for k, _ in floor.values())))] += 1
        vote_day = str(outc.get(bk, {}).get("outcome_date", ""))[:10]
        votes = sorted({str(e.get("vote_date", ""))[:10] for e in plan if e.get("bill_key") == bk} - {""})
        mine = {d for d, (f_, p_) in ours.get(bk, {}).items() if f_ or p_}
        for d in sorted(set(floor) | set(ours.get(bk, {}))):
            kind, txt = floor.get(d, ("", []))
            files, npred = ours.get(bk, {}).get(d, [0, 0])
            have = files > 0 or npred > 0
            if kind == "debate" and not have:
                if near(d, mine):
                    status = "CHECK: one day from a day we have (same sitting dated differently, or a 2nd debate day)"
                elif vote_day and d > vote_day and not any(v >= d for v in votes):
                    status = "MISSING: after the outcome vote"
                else:
                    nxt = min((v for v in votes if v >= d), default=vote_day or d)
                    gap = (dt.date.fromisoformat(nxt) - dt.date.fromisoformat(d)).days
                    look = 1 if nxt < "1994-01-01" else 3
                    if gap <= look:
                        status = "MISSING: in the search window but not kept"
                    elif gap <= 14:
                        status = "MISSING: debate days before the vote, outside the search window"
                    else:
                        status = "MISSING: earlier House action with no vote in our list"
            elif have and not kind:
                status = ("ok (one day from a Congress.gov floor day)" if near(d, {x for x, (k_, _) in floor.items() if k_})
                          else "NOT LISTED on Congress.gov")
            elif have:
                status = f"ok ({kind} day)"
            else:
                status = "vote-only day, no text (fine)"
            rows.append({"status": status, "bill_key": bk, "date": d, "outcome_vote_date": vote_day,
                         "our_text_files": files, "our_predications": npred,
                         "congress_gov_floor": kind or "not listed",
                         "congress_gov_actions": " | ".join(txt)[:400]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    order = {"MISSING: debate days before the vote, outside the search window": 0,
             "MISSING: in the search window but not kept": 1,
             "MISSING: earlier House action with no vote in our list": 2,
             "MISSING: after the outcome vote": 3,
             "CHECK: one day from a day we have (same sitting dated differently, or a 2nd debate day)": 4,
             "NOT LISTED on Congress.gov": 5}
    rows.sort(key=lambda r: (order.get(r["status"], 9), r["bill_key"], r["date"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["status"])
        w.writeheader()
        w.writerows(rows)

    tally = Counter(r["status"] for r in rows)
    print(f"{len(bills)} US bills; {len(no_actions)} without a Congress.gov action list"
          + (f" (e.g. {no_actions[:5]})" if no_actions else ""))
    print("Congress.gov records House debate days for (by congress):")
    for c in sorted({c for c, _ in cover}, key=int):
        y, n = cover[(c, True)], cover[(c, False)]
        n_ = int(c)
        suf = "th" if 10 <= n_ % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n_ % 10, "th")
        print(f"  {c}{suf} Congress: {y} of {y + n} bills")
    print("\nbill-days by result:")
    for s, n in sorted(tally.items(), key=lambda x: order.get(x[0], 9)):
        print(f"  {n:>5}  {s}")
    for s in [k for k, v in sorted(order.items(), key=lambda x: x[1]) if k.startswith(("MISSING", "CHECK"))]:
        miss = [r for r in rows if r["status"] == s]
        if miss:
            print(f"\n{s} ({len(miss)}), first 12:")
            for r in miss[:12]:
                print(f"  {r['bill_key']:<14} {r['date']}  (vote {r['outcome_vote_date']})  {r['congress_gov_actions'][:80]}")
    print(f"\nfull list: {OUT}")


if __name__ == "__main__":
    main()
