#!/usr/bin/env python3
"""
check_quebec_pages.py

Word accounting for every cached Quebec journal page. For each page it counts
  * the words inside <contenu> (the whole debate text of the day),
  * the words the old paragraph reading missed (text sitting outside any <p>),
  * whether the fix 6 repair applied, and the words still missed after it.
This checks fix 6 a different way from the bill-day before/after report: it does not
look at bills at all, only at whether every word on every page is read.

Writes outputs/audit/quebec_page_coverage.csv and prints a summary by legislature.
Run from the project folder:  python3 scripts/step1_debate_text/check_quebec_pages.py
"""
import csv
import glob
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quebec_rebuild as Q
from v3_common import rp

pages = sorted(glob.glob(os.path.join(Q.CACHE, "*.html")))
print(f"cached pages: {len(pages)}")
rows = []
by_leg = defaultdict(lambda: [0, 0, 0, 0, 0])   # pages, repaired, words, missed before, missed after
for i, path in enumerate(pages, 1):
    name = os.path.basename(path)
    html = open(path, encoding="utf-8", errors="ignore").read()
    total, before = Q.words_outside_p(html)
    fixed, changed = Q.repair_selfclosed_paragraphs(html)
    after = Q.words_outside_p(fixed)[1] if changed else before
    leg = name.split("_")[0]
    s = by_leg[leg]
    s[0] += 1; s[1] += int(changed); s[2] += total; s[3] += before; s[4] += after
    rows.append({"page": name, "legislature": leg, "words": total, "missed_before": before,
                 "repaired": int(changed), "missed_after": after,
                 "pct_missed_before": round(100 * before / total, 1) if total else 0.0,
                 "pct_missed_after": round(100 * after / total, 1) if total else 0.0})
    if i % 200 == 0:
        print(f"  {i}/{len(pages)} pages", flush=True)

out = rp("outputs", "audit", "quebec_page_coverage.csv")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["page"])
    w.writeheader()
    w.writerows(rows)

print(f"\n{'legislature':<12}{'pages':>7}{'repaired':>10}{'words':>12}{'missed before':>16}{'missed after':>15}")
T = [0, 0, 0, 0, 0]
for leg in sorted(by_leg, key=lambda k: [int(x) for x in k.split("-") if x.isdigit()]):
    s = by_leg[leg]
    T = [a + b for a, b in zip(T, s)]
    pb = f"{s[3]:,} ({100*s[3]/s[2]:.1f}%)" if s[2] else "0"
    pa = f"{s[4]:,} ({100*s[4]/s[2]:.1f}%)" if s[2] else "0"
    print(f"{leg:<12}{s[0]:>7}{s[1]:>10}{s[2]:>12,}{pb:>16}{pa:>15}")
print(f"{'ALL':<12}{T[0]:>7}{T[1]:>10}{T[2]:>12,}{T[3]:>12,} ({100*T[3]/max(T[2],1):.1f}%){T[4]:>11,} ({100*T[4]/max(T[2],1):.1f}%)")

still = sorted((r for r in rows if r["pct_missed_after"] >= 2.0), key=lambda r: -r["pct_missed_after"])
print(f"\npages still missing 2% or more of their words after the repair: {len(still)}")
for r in still[:15]:
    print(f"  {r['page']:<34} {r['missed_after']:>6,} of {r['words']:>7,} words ({r['pct_missed_after']}%)")
print(f"\nper-page table: {out}")
