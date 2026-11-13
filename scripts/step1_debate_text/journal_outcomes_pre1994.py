#!/usr/bin/env python3
"""
journal_outcomes_pre1994.py   (reads the saved Journal pages; updates data/canada/quebec_bills/quebec_pre1994_vote_outcomes.json)

The outcome of every 1985-1994 health bill, from the Journal des debats itself: the vote on the bill's final adoption
("Est-ce que le projet de loi 74 ... est adopte? Adopte", a recorded vote "pour: 74 contre: 27 ... la motion est
adoptee", a supply bill's single motion), a rejection ("ce projet de loi a ete rejete"), or no final vote before the
end of its session. The vote is looked for between the bill's first debate day and 60 days after its last one, on
the pages of its session and of the next session of the same legislature (a bill reinstated after prorogation).

The vote-outcomes file that came with the library list marked 26 bills "died_in_session"; the Journal shows 24 of
them adopted (every 33-1 bill with no vote date in that file was marked dead). The file's outcome and vote date are
kept as file_outcome / file_vote_date; outcome and vote_date now come from the Journal.
Writes outputs/audit/quebec_pre1994_journal_outcomes.txt.  Run from the project folder:
  python3 scripts/step1_debate_text/journal_outcomes_pre1994.py
"""
import datetime
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
import quebec_rebuild as Q   # noqa: E402

QC = ROOT / "data" / "canada" / "quebec_assembly"
PO = ROOT / "data" / "canada" / "quebec_bills" / "quebec_pre1994_vote_outcomes.json"
OUT = ROOT / "outputs" / "audit" / "quebec_pre1994_journal_outcomes.txt"
NEXT = {"33-1": "33-2", "34-1": "34-2", "34-2": "34-3"}
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


idx = [e for e in json.load(open(QC / "v3" / "segments_index.json", encoding="utf-8")) if e.get("source") == "bibliotheque_pre1994"]
days = json.load(open(QC / "v3" / "pre1994" / "sitting_days.json", encoding="utf-8"))
by_sess = defaultdict(list)
for d in days:
    by_sess[d["session"]].append(d)
for s in by_sess:
    by_sess[s].sort(key=lambda d: d["date"])
bdays = defaultdict(list)
for e in idx:
    bdays[e["bill_key"]].append(e["date"])
N = lambda n: rf"projet\s+(?:de\s+loi|d['’]interet\s+prive)\s+(?:n[o°]?\s*)?{n}\b"
TALLY = re.compile(r"pour\s*:\s*(\d+)\s*contre\s*:\s*(\d+)")
pages = {}


def page(d):
    p = Q.cache_path(d["url"])
    if p not in pages:
        if not os.path.exists(p):
            pages[p] = None
        else:
            out, who = [], "chair"
            for b in Q.parse_page(open(p, encoding="utf-8", errors="ignore").read(), old_format=True)[1]:
                t = Q._norm(b["text"])
                if b["heading"]:
                    who = "member" if re.match(r"^(?:m|mm|mme|mmes|mlle)\.?\s+[a-z]", t) else "chair"
                elif re.match(r"^(?:le|la)\s+(?:vice-)?president", t) or re.match(r"^(?:des|une)\s+voix\s*:", t) or t.startswith("le secretaire"):
                    who = "chair"
                elif re.match(r"^(?:m|mme|mlle)\.?\s+[a-z][^:]{0,40}:", t):
                    who = "member"
                out.append((t, who))
            pages[p] = out
    return pages[p]


def plus(d, n):
    return (datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])) + datetime.timedelta(days=n)).strftime("%Y%m%d")


results = {}
for key in sorted(bdays):
    s, n = key.split("-Bill")
    n = int(n)
    ds = sorted(bdays[key])
    lo, hi = ds[0], plus(ds[-1], 60)
    if s == "33-1" and lo < "19870101":          # numbering started again in 1987: stop where the number is re-used
        rx_present = re.compile(r"presente\s+le\s+" + N(n))
        for d in by_sess[s]:
            if d["date"] >= "19870101" and d["date"] > ds[-1] and page(d) and any(rx_present.search(t) for t, w in page(d)):
                hi = min(hi, d["date"])
                break
    rx_final = re.compile(
        r"(?:propose\s+que\s+l['’]assemblee\s+soit\s+saisie\s+du\s+" + N(n)
        + r"|" + N(n) + r"[^.]{0,160}?en\s+soit\s+saisie[^.]{0,120}?adopte\s+le\s+projet"
        + r"|" + N(n) + r"[^.]{0,300}?adoption\s+de\s+ce\s+projet\s+de\s+loi"
        + r"|adoption\s+(?:finale\s+)?(?:du\s+" + N(n) + r"|de\s+la\s+loi\s+(?:n[o°]?\s*)?" + str(n) + r"\b)"
        + r"|" + N(n) + r"[^?!]{0,300}?\best(?:[- ](?:il|elle))?\s*(?:donc\s+|maintenant\s+)?adopte"      # a title may hold "inc."
        + r"|" + N(n) + r"\s+presentation,?\s+adoption\s+du\s+principe\s+et\s+adoption"
        + r"|que\s+le\s+" + N(n) + r"[^.]{0,200}?soit\s+adopte)")
    ev = []
    for d in sorted(by_sess[s] + by_sess.get(NEXT.get(s, ""), []), key=lambda d: d["date"]):
        if not (lo <= d["date"] <= hi):
            continue
        bl = page(d)
        if not bl:
            continue
        for i, (t, who) in enumerate(bl):
            if re.search(r"a\s+ete\s+(?:egalement\s+)?rejete", t) and re.search(N(n), t):
                ev.append((d["date"], "rejected", False, t[:160]))
            m = rx_final.search(t)
            if not m:
                continue
            # the vote is put by the Chair (or printed as a heading, or is the one motion on a supply bill); a member
            # who speaks of the adoption of the bill does not carry the vote
            if who != "chair" and not ("soit saisie" in t or "en propose" in t):
                continue
            before = t[max(0, m.start() - 90):m.start()].split(".")[-1]      # the same sentence, before the match
            if re.search(r"principe|rapport|amendement|motion\s+de\s+report|scission|renvoi|defere", before):
                continue           # the vote on the principle, on the committee's report or on an amendment, not the final one
            if re.search(r"principe\s+(?:du|de\s+la)\s+" + N(n), t[m.start():m.end() + 5]):
                continue
            win = " ".join(x[0] for x in bl[i:i + 12])      # a recorded vote lists the members before the tally
            after = win[m.end() - m.start():]
            tal = TALLY.search(win)
            if tal:
                ev.append((d["date"], "recorded vote", int(tal.group(1)) > int(tal.group(2)), t[:160]))
            elif re.search(r"\brejet", after):
                ev.append((d["date"], "rejected", False, t[:160]))
            elif re.search(r"(?:^|[:.?!]\s*|voix\s*:\s*)adopte|\bmotion\s+est\s+(?:donc\s+)?adoptee|\best\s+(?:donc\s+|maintenant\s+)?adopte|adopte\s+sur\s+division", after):
                ev.append((d["date"], "adopted", True, t[:160]))      # the vote itself, not a mention of the adoption
    passed = [e for e in ev if e[2]]
    rej = [e for e in ev if not e[2]]
    if passed:
        votes = [e for e in passed if e[1] == "recorded vote"]
        best = max(votes or passed, key=lambda e: e[0])      # a recorded vote outranks a mention of the adoption
        oc, when, how = "passed", best[0], best[1]
    elif rej:
        oc, when, how = "rejected", max(e[0] for e in rej), "rejected"
    else:
        oc, when, how = "no final vote found", None, ""
    results[key] = {"journal_outcome": oc, "journal_vote_date": when, "how": how, "days": ds, "evidence": ev}

po = json.load(open(PO, encoding="utf-8"))
items = po if isinstance(po, dict) else {f"{v['session']}-Bill{int(v['bill_number'])}": v for v in po}
backup = PO.with_name(PO.stem + "_before_journal_" + time.strftime("%Y%m%d-%H%M%S") + ".json")
shutil.copy2(PO, backup)
tab, changed = Counter(), []
for key, r in results.items():
    v = items.get(key)
    if v is None:
        s, n = key.split("-Bill")
        v = items[key] = {"bill_number": n, "session": s, "title": ""}
    if "file_outcome" not in v:
        v["file_outcome"], v["file_vote_date"] = v.get("outcome", ""), v.get("vote_date")
    new_oc = "passed" if r["journal_outcome"] == "passed" else "died_in_session"
    tab[(v["file_outcome"] or "blank", r["journal_outcome"])] += 1
    if (v.get("outcome"), v.get("vote_date")) != (new_oc, r["journal_vote_date"]):
        changed.append((key, v["file_outcome"], v["file_vote_date"], r["journal_outcome"], r["journal_vote_date"]))
    v["outcome"], v["vote_date"] = new_oc, r["journal_vote_date"]
    v["journal_outcome"], v["journal_how"] = r["journal_outcome"], r["how"]
    v["source"] = "Journal des debats, vote on the final adoption (journal_outcomes_pre1994.py)"
json.dump(items if isinstance(po, dict) else list(items.values()), open(PO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

say("=" * 100)
say("Outcomes of the 1985-1994 health bills from the Journal des debats")
say("=" * 100)
say(f"bills with debate days: {len(results)}; outcome from the Journal: {dict(Counter(r['journal_outcome'] for r in results.values()))}")
say("file outcome -> Journal outcome:")
for (a, b), k in sorted(tab.items()):
    say(f"   {a:<16} -> {b:<22} {k}")
say(f"\nbills whose outcome or vote date changed: {len(changed)}")
for key, fo, fd, jo, jd in changed:
    say(f"   {key:<14} file {fo or 'blank':<16} {str(fd):<10} -> Journal {jo:<22} {jd}")
say("\nbills with no final vote found in the Journal (left as died_in_session):")
for key, r in sorted(results.items()):
    if r["journal_outcome"] != "passed":
        say(f"   {key:<14} {r['journal_outcome']:<22} days {r['days'][0]}..{r['days'][-1]} ({len(r['days'])})")
say("\nevery bill, with the sentence the outcome rests on:")
for key, r in sorted(results.items()):
    last = next((e for e in sorted(r["evidence"], key=lambda e: e[0], reverse=True) if (e[2] if r["journal_outcome"] == "passed" else not e[2])), None)
    say(f"   {key:<14} {r['journal_outcome']:<22} {str(r['journal_vote_date']):<10} {r['how']:<14} | {last[3] if last else ''}")
say(f"\nwritten: {PO.relative_to(ROOT)} (backup {backup.name})")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
print(f"Saved {OUT}")
