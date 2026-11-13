#!/usr/bin/env python3
"""
check_fix8.py   (reads only; a minute or two)

Checks after fix8, each one independent of the code that made the change:
  1. US section text: only the two repaired files changed (H.R. 483 1995-04-06, H.R. 1590 1995-05-16)
  2. US page markers: every line printed after a page marker on a saved Record page used by a section is in that
     section now (it was 11 lines missing)
  3. US "notbill" text: 15,063 paragraphs tagged, and no sentence or claim from them counts
  4. US: the kept text of H.R. 5716 on 2002-11-14 is only its own part (the bill's heading and text and
     Mr. Boehner's statement)
  5. Ontario: no sentence or claim left for 33-1 Bill 52 on 1985-12-17 or 33-3 Bill 79 on 1987-06-29
  6. the audit has no FAIL
Writes outputs/audit/fix8_check.txt. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix8.py <copy folder from before fix8>
"""
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "data" / "us" / "v3" / "segments_index.json").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT)
B = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if B is None or not (B / "cr_segments_v3").is_dir():
    sys.exit("Give the copy folder from before fix8 (data/_before_fix8_*). Nothing checked.")
OUT = Path("outputs/audit/fix8_check.txt")
LINES, RES = [], []
SID = re.compile(r"\|p(\d+)\|s(\d+)$")


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def check(name, ok, detail=""):
    RES.append(ok)
    say(f"CHECK {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return d


def N(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


md5 = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()
cur = Path("data/us/v3/cr_segments_v3")
changed = sorted(f for f in os.listdir(cur) if f.endswith(".txt") and (
    not (B / "cr_segments_v3" / f).exists() or md5(cur / f) != md5(B / "cr_segments_v3" / f)))
gone = sorted(f for f in os.listdir(B / "cr_segments_v3") if f.endswith(".txt") and not (cur / f).exists())
check("1. only the two repaired US section files changed", changed == ["104-HR1590_1995-05-16.txt", "104-HR483_1995-04-06.txt"]
      and not gone, f"changed {changed}; missing {gone}")

idx = load("data/us/v3/segments_index.json", [])
miss, n_lines = [], 0
for e in idx:
    sec = None
    for u, _ in e["para_units"]:
        if not u.startswith("CREC-"):
            continue
        raw = open(f"data/us/v3/cache/daily/CREC-{u[5:15]}/{u}.txt", encoding="utf-8", errors="ignore").read()
        for line in raw.splitlines():
            m = re.match(r"\s*\[\[Page [^\]]*\]\]\s*(\S.*)$", line)
            if m and len(N(m.group(1))) >= 8:
                if sec is None:
                    sec = N(Path("data/us", e["file"]).read_text(encoding="utf-8"))
                n_lines += 1
                if N(m.group(1)) not in sec:
                    miss.append((e["bill_key"], e["debate_date"], m.group(1)[:60]))
check("2. every line printed after a page marker is in its section", not miss, f"{n_lines} such lines; missing {len(miss)} {miss[:3]}")

tags_of, nb = {}, 0
for e in idx:
    t = [x for x, n in e["para_tags"] for _ in range(n)]
    tags_of[(e["bill_key"], e["debate_date"])] = t
    nb += sum(1 for x in t if x.startswith("notbill"))
sents = load("data/dbpedia_pipeline/us/sentences_v3.json", [])
preds = load("data/dbpedia_pipeline/us/predications_v3.json", [])
aside = load("data/dbpedia_pipeline/us/predications_v3_set_aside.json", [])


def tag(r):
    m = SID.search(str(r.get("sentence_id", "")))
    t = tags_of.get((r.get("bill_key"), r.get("date")))
    return t[int(m.group(1))] if (m and t and int(m.group(1)) < len(t)) else ""


kept_nb_s = sum(1 for r in sents if tag(r).startswith("notbill"))
kept_nb_p = sum(1 for r in preds if tag(r).startswith("notbill"))
aside_nb = sum(1 for r in aside if str(r.get("_set_aside", "")).startswith("notbill"))
check("3. no sentence or claim from notbill text counts", nb == 15063 and kept_nb_s == 0 and kept_nb_p == 0 and aside_nb > 0,
      f"notbill paragraphs {nb:,} (expected 15,063); counted sentences {kept_nb_s}, claims {kept_nb_p}; claims set aside {aside_nb:,}")

k = ("107-HR5716", "2002-11-14")
e5 = next(e for e in idx if (e["bill_key"], e["debate_date"]) == k)
ps = [p for p in Path("data/us", e5["file"]).read_text(encoding="utf-8").split("\n\n") if p.strip()]
kept = sorted({int(SID.search(r["sentence_id"]).group(1)) for r in sents if (r.get("bill_key"), r.get("date")) == k})
ok = bool(kept) and all(120 <= q <= 141 for q in kept) and any("BOEHNER" in ps[q] for q in kept)
check("4. H.R. 5716 on 2002-11-14 keeps only its own part", ok, f"paragraphs with counted sentences: {kept[:12]}")

left = Counter()
for kind in ("sentences_v3.json", "predications_v3.json"):
    for r in load(f"data/dbpedia_pipeline/ontario/{kind}", []):
        if (r.get("bill_key"), str(r.get("date"))[:10]) in {("33-1-Bill52", "1985-12-17"), ("33-3-Bill79", "1987-06-29")}:
            left[kind] += 1
check("5. the two Ontario bill-days of another bill are out", not left, dict(left) or "0 rows")

rep = Path("outputs/audit/audit_report.txt")
fails = [l for l in rep.read_text(encoding="utf-8").splitlines() if "[FAIL]" in l] if rep.exists() else ["no audit report"]
check("6. the audit has no FAIL", not fails, "; ".join(fails[:3]) or "0 FAIL")

before = {j: len(load(B / f"{j}_predications_v3.json", []) or []) for j in ("us", "ontario")}
say(f"\nclaims that count: US {before['us']:,} -> {len(preds):,}; Ontario {before['ontario']:,} -> "
    f"{len(load('data/dbpedia_pipeline/ontario/predications_v3.json', [])):,}")
say(f"CHECKS: {sum(RES)} passed, {len(RES) - sum(RES)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
sys.exit(2 if not all(RES) else 0)
