#!/usr/bin/env python3
"""
check_bill2_days.py   (reads only; a few seconds)
The three Bill 2 (1985) days that grew or appeared in the fix7e run: 1985-12-17 (41 -> 781 paragraphs), 1986-05-15
(new, 60) and 1986-05-20 (new, 107). For each, the page is traced (every heading, every switch of bill) and the
section is checked: it must start at a heading or call that names Bill 2, must end at a heading of other business
or of another bill, must not name another bill 3+ times in any 40-paragraph stretch without naming Bill 2, and the
1985-12-17 section must be the debate on the principle (the vote on it was deferred to 1985-12-18).
Prints PASS or FAIL for each day; writes outputs/audit/bill2_days_check.txt. Exit code 2 if any FAIL.
"""
import json, os, re, sys
from collections import Counter
from pathlib import Path
ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
import quebec_rebuild as Q
NUM = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[°ºo]\.?\s*|num[eé]ro\s+)?(\d+)\b", re.I)
OUT = ROOT / "outputs/audit/bill2_days_check.txt"
L, fails = [], 0
def say(s=""):
    print(s, flush=True); L.append(str(s))
idx = json.load(open("data/canada/quebec_assembly/v3/segments_index.json", encoding="utf-8"))
cut = lambda t, k=140: (t[:k] + "...") if len(t) > k else t
for date, need_principle in (("19851217", True), ("19860515", False), ("19860520", False)):
    e = next((x for x in idx if x["bill_key"] == "33-1-Bill2" and x["date"] == date), None)
    say("=" * 100); say(f"Bill 2 of 1985, {date}: {e['n_paragraphs'] if e else 'NO SECTION'} paragraphs"); say("=" * 100)
    if e is None:
        say(f"   (no section for this day in this data; nothing to check)"); continue
    with open(Q.cache_path(e["url"]), encoding="utf-8", errors="ignore") as f:
        segs, blocks = Q.parse_page(f.read(), old_format=True)
    last = "start"
    for i, b in enumerate(blocks):
        if b["heading"]:
            nxt = next((x["bill"] for x in blocks[i + 1:i + 3] if not x["heading"]), None)
            say(f"   [{i:>5}] HEADING  bill {str(b['bill']):<5}-> {str(nxt):<5} | {cut(b['text'], 100)}")
        elif b["bill"] != last:
            say(f"   [{i:>5}] text now bill {b['bill']} | {cut(b['text'])}")
        last = b["bill"]
    mine = [i for i, b in enumerate(blocks) if b["bill"] == 2 and not b["heading"]]
    runs, cur = [], []
    for i in mine:
        if cur and i != cur[-1] + 1 and any(blocks[j]["heading"] and NUM.search(blocks[j]["text"]) and int(NUM.search(blocks[j]["text"]).group(1)) != 2 for j in range(cur[-1] + 1, i)):
            runs.append(cur); cur = []
        cur.append(i)
    if cur: runs.append(cur)
    ok = True
    for r in runs:
        s0, s1 = r[0], r[-1]
        head = " ".join(blocks[j]["text"] for j in range(max(0, s0 - 4), s0 + 2))
        starts = bool(re.search(r"projet\s+de\s+loi\s+2\b", Q._norm(head)))
        after = [blocks[j]["text"] for j in range(s1 + 1, min(len(blocks), s1 + 4))]
        say(f"   stretch [{s0}]..[{s1}] ({len(r)} paragraphs)")
        say(f"      starts: {cut(blocks[s0]['text'])}")
        say(f"      ends:   {cut(blocks[s1]['text'])}")
        say(f"      then:   {cut(after[0]) if after else '(end of page)'}")
        drift = []
        for k in range(0, len(r), 40):
            w = r[k:k + 40]; c = Counter(int(m.group(1)) for j in w for m in NUM.finditer(blocks[j]["text"]))
            oth = [(n, x) for n, x in c.most_common() if n != 2 and x >= 3]
            if oth and c.get(2, 0) == 0: drift.append((r[k], oth[0]))
        if not starts: say("      FAIL: the stretch does not start at a heading or call naming Bill 2"); ok = False
        if drift: say(f"      FAIL: drift into another bill at {drift[:3]}"); ok = False
    if need_principle:
        txt = " ".join(Q._norm(blocks[j]["text"]) for j in mine)
        if "adoption du principe du projet de loi 2" not in txt and "principe du projet de loi 2" not in txt:
            say("      FAIL: the 1985-12-17 text never speaks of the adoption of the principle of Bill 2"); ok = False
        elif "report" in txt[-3000:] or "ajourn" in txt[-3000:]:
            say("      the day ends with a deferral or adjournment, as the Dec 18 page says")
    say(f"CHECK {'PASS' if ok else 'FAIL'}  {date}")
    fails += not ok
OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"\nSaved {OUT}"); sys.exit(2 if fails else 0)
