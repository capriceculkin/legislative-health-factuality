#!/usr/bin/env python3
"""
check_qc_sections.py   (reads only; about a minute)

Checks the Quebec sections, above all the new 1985-1994 ones, for text that runs past the end of its bill's
debate into other business. Bill 2 of 1985 now has 1,140 paragraphs on 1985-12-18; that is a whole sitting's
worth, so before it goes on the sheet it is checked three different ways:
  A. size: paragraphs per section, 1985-1994 against 1994 on (the same parser and rules)
  B. drift: in every section, stretches of 40 paragraphs that never name the section's own bill but name
     another bill three times or more
  C. the page itself: every heading the parser saw on the 1985-12-18 page (and on the largest 1985-1994
     sections), with the bill it was following after each one
  D. the days found for Bill 2 of 1985: the title printed on each day and the stages
  E. on the 1985-1994 pages that print no "Affaires courantes" or "Affaires du jour" (read with the stricter rules
     of patch_quebec_oldformat.py): every heading that ended a bill's text, how often, with an example
Writes outputs/audit/qc_section_check.txt
Run from the project folder:  python3 ~/Desktop/check_qc_sections.py   (or wherever the file landed)
"""
import inspect
import json
import os
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
os.chdir(ROOT)
import quebec_rebuild as Q   # noqa: E402

QC = ROOT / "data" / "canada" / "quebec_assembly"
OUT = ROOT / "outputs" / "audit" / "qc_section_check.txt"
NUM = re.compile(r"projet\s+de\s+loi\s+(?:n\s*[°ºo]\.?\s*|num[eé]ro\s+)?(\d+)\b", re.I)
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def paras_of(e):
    try:
        return [p.strip() for p in open(QC / e["file"], encoding="utf-8").read().split("\n\n") if p.strip()]
    except OSError:
        return []


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0


idx = json.load(open(QC / "v3" / "segments_index.json", encoding="utf-8"))
pre = [e for e in idx if e.get("source") == "bibliotheque_pre1994"]
post = [e for e in idx if e.get("source") != "bibliotheque_pre1994"]

say("=" * 100)
say("A. Paragraphs per section")
say("=" * 100)
for name, es in (("1994 on", post), ("1985-1994", pre)):
    n = [e["n_paragraphs"] for e in es]
    if n:
        say(f"   {name:<10} sections {len(n):>5}   median {statistics.median(n):>6.0f}   90th pct {pct(n, .9):>5}   "
            f"99th pct {pct(n, .99):>5}   largest {max(n)}")
cut = pct([e["n_paragraphs"] for e in post], .99) if post else 400
big = sorted((e for e in idx if e["n_paragraphs"] > cut), key=lambda e: -e["n_paragraphs"])
say(f"   sections above the 1994-on 99th percentile ({cut} paragraphs): {len(big)} "
    f"(1985-1994: {sum(1 for e in big if e in pre)}, 1994 on: {sum(1 for e in big if e not in pre)})")
for e in big[:25]:
    say(f"      {e['bill_key']:<14} {e['date']}  {e['n_paragraphs']:>5} paragraphs  methods {e.get('methods')}  "
        f"stages {e.get('stages')}")

say("")
say("=" * 100)
say("B. Drift: 40-paragraph stretches that never name their own bill and name another bill 3+ times")
say("=" * 100)
drift = []
for e in idx:
    ps = paras_of(e)
    own = int(e["bill_number"])
    for i in range(0, len(ps), 40):
        nums = Counter(int(m.group(1)) for p in ps[i:i + 40] for m in NUM.finditer(p))
        other = [(n, k) for n, k in nums.most_common() if n != own and k >= 3]
        if other and nums.get(own, 0) == 0:
            drift.append((e, i, other[0], next((p for p in ps[i:i + 40] if NUM.search(p) and
                                                 int(NUM.search(p).group(1)) == other[0][0]), "")))
            break
say(f"sections with such a stretch: {len(drift)} of {len(idx)} "
    f"(1985-1994: {sum(1 for d in drift if d[0] in pre)} of {len(pre)}; 1994 on: {sum(1 for d in drift if d[0] not in pre)} of {len(post)})")
for e, i, (n, k), p in sorted(drift, key=lambda d: -d[0]["n_paragraphs"])[:40]:
    say(f"   {e['bill_key']:<14} {e['date']} ({e['n_paragraphs']} paras) from paragraph {i}: Bill {n} named {k}x | "
        f"{p[:150]}")


def trace(e, around=None):
    """every heading the parser saw on the page, and the bill it was following after it"""
    p = Q.cache_path(e["url"])
    if not os.path.exists(p):
        say(f"   page not saved: {p}")
        return
    with open(p, encoding="utf-8", errors="ignore") as f:
        html = f.read()
    if e.get("source") == "bibliotheque_pre1994" and "old_format" in inspect.signature(Q.parse_page).parameters:
        segs, blocks = Q.parse_page(html, old_format=True)
    else:
        segs, blocks = Q.parse_page(html)
    say(f"   page {os.path.basename(p)}: {len(blocks)} paragraphs; paragraphs per bill on this page: "
        f"{ {k: len(v) for k, v in sorted(segs.items())} }")
    last = None
    for i, b in enumerate(blocks):
        if b["heading"]:
            nxt = next((x["bill"] for x in blocks[i + 1:i + 3] if not x["heading"]), None)
            say(f"      [{i:>5}] HEADING  section={b['section'][:28]!r:<31} bill after={nxt!s:<5} | {b['text'][:110]}")
        elif b["bill"] != last:
            say(f"      [{i:>5}] bill {last} -> {b['bill']} at: {b['text'][:110]}")
        last = b["bill"]
    own = e["bill_number"]
    mine = [i for i, b in enumerate(blocks) if b["bill"] == own]
    if mine:
        say(f"   this bill's paragraphs run from [{mine[0]}] to [{mine[-1]}] of {len(blocks)}")
        for i in (mine[0], mine[0] + 1, mine[len(mine) // 2], mine[-2] if len(mine) > 1 else mine[-1], mine[-1]):
            say(f"      [{i:>5}] {blocks[i]['text'][:200]}")
        others = Counter(int(m.group(1)) for i in mine for m in NUM.finditer(blocks[i]["text"]))
        say(f"   bill numbers named inside this bill's paragraphs: {dict(others.most_common(12))}")


say("")
say("=" * 100)
say("C. The page behind the largest 1985-1994 sections")
say("=" * 100)
b2 = [e for e in pre if e["bill_key"] == "33-1-Bill2"]
targets = [e for e in b2 if e["date"] == "19851218"] + sorted(pre, key=lambda e: -e["n_paragraphs"])[:3]
seen = set()
for e in targets:
    if (e["bill_key"], e["date"], e["page_id"]) in seen:
        continue
    seen.add((e["bill_key"], e["date"], e["page_id"]))
    say(f"\n-- {e['bill_key']} {e['date']} ({e['n_paragraphs']} paragraphs, methods {e.get('methods')})")
    trace(e)

say("")
say("=" * 100)
say("D. Days found for Bill 2 of 1985")
say("=" * 100)
found = json.load(open(QC / "v3" / "pre1994" / "bill_days_found.json", encoding="utf-8"))
for x in found:
    if x.get("bill_key") == "33-1-Bill2":
        say(f"   {x['date']} page {x['page_id']}  accepted {x['accepted']}  {x['n_paragraphs']} paras  stages {x['stages']}  "
            f"title: {x.get('title', '')[:90]}")
        say(f"        first paragraph: {x.get('first_paragraph', '')[:160]}")

say("")
say("=" * 100)
say("E. Headings that ended a bill's text on 1985-1994 pages read with the stricter rules")
say("=" * 100)
if "old_format" not in inspect.signature(Q.parse_page).parameters or not hasattr(Q, "_OLD_STRUCT"):
    say("   quebec_rebuild.py does not have the stricter rules yet (patch_quebec_oldformat.py); nothing to show")
else:
    ended, n_pages, n_strict = {}, 0, 0
    for path in sorted({Q.cache_path(e["url"]) for e in pre}):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="ignore") as f:
            segs, blocks = Q.parse_page(f.read(), old_format=True)
        n_pages += 1
        if any(b["heading"] and Q._OLD_STRUCT.match(Q._norm(b["text"])) for b in blocks):
            continue
        n_strict += 1
        for i in range(len(blocks) - 1):
            b = blocks[i]
            if b["heading"] and b["bill"] is not None and blocks[i + 1]["bill"] is None:
                k = Q._norm(b["text"])[:60]
                c = ended.setdefault(k, [0, b["text"][:90], os.path.basename(path), b["bill"]])
                c[0] += 1
    say(f"   pages of the 1985-1994 bills: {n_pages}; read with the stricter rules (no Affaires courantes or "
        f"Affaires du jour): {n_strict}")
    say(f"   headings that ended a bill's text ({sum(c[0] for c in ended.values())} times, {len(ended)} different):")
    for k, (n, text, page, bill) in sorted(ended.items(), key=lambda kv: -kv[1][0])[:80]:
        say(f"      {n:>4}x  {text:<90}  e.g. {page} (bill {bill})")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
print(f"\nSaved {OUT}")
