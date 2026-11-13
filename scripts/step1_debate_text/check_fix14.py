#!/usr/bin/env python3
"""
check_fix14.py   (reads only; a few minutes)

Checks after the US rebuild with the three words Apple's engine settled (fix14):
  1. Ontario and Quebec sentences are byte for byte what they were (only the US is rebuilt)
  2. every US sentence is in its own bill-day's text read with the listed corrections, so nothing else changed
  3. no joined US sentence crosses two tags or two source units
  4. in the 1985-1993 sentences that count, fewer words that neither the daily Record nor the sentences of
     1994+ use (a different measure from the rules that made the list)
  5. every listed correction found its text; every US sentence placed by apply_us_text_choices.py; the audit,
     which reads the text with the same corrections, has no FAIL
Writes outputs/audit/fix14_check.txt. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix14.py <copy folder from before fix14>
"""
import filecmp
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "build_sentences_v3.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
import para_join as PJ  # noqa: E402

B = Path(sys.argv[1]) if len(sys.argv) > 1 else None
OUT = Path("outputs/audit/fix14_check.txt")
LINES, RES = [], []
OUT_TAGS = {"printed", "votelist", "rule", "notbill"}
FIXES = Path("data/us/v3/ocr_word_fixes.json")
PIPE = Path("data/dbpedia_pipeline")


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def check(name, ok, detail=""):
    RES.append(bool(ok))
    say(f"CHECK {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def load(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def squash(s):
    return re.sub(r"[^0-9a-z]", "", str(s).lower())


def pnum(sid):
    m = re.search(r"\|p(\d+)\|s\d+$", sid)
    return int(m.group(1)) if m else 0


same = [j for j in ("ontario", "quebec") if B and (B / f"{j}_sentences_v3.json").exists()
        and load(B / f"{j}_sentences_v3.json") == load(PIPE / j / "sentences_v3.json")]
check("1. Ontario and Quebec sentences unchanged", len(same) == 2, f"unchanged: {same}")

sent = (load(PIPE / "us" / "sentences_v3.json", []) or []) + (load(PIPE / "us" / "sentences_v3_set_aside.json", []) or [])
bsent = ((load(B / "us_sentences_v3.json", []) or []) + (load(B / "us_sentences_v3_set_aside.json", []) or [])) if B else []
idx = {(e["bill_key"], e["debate_date"]): e for e in load("data/us/v3/segments_index.json", [])}
tally = {}
texts = {}
for k, e in idx.items():
    t = Path("data/us", e["file"]).read_text(encoding="utf-8")
    texts[k] = PJ.apply_fixes(t, PJ.fixes_for(FIXES, e["file"]), tally, "us_ocr_fixed")

by_day = {}
for s in sent:
    by_day.setdefault((s["bill_key"], s["date"]), []).append(s)
miss, mixed = [], []
for k, rows in by_day.items():
    e = idx.get(k)
    if not e:
        miss += [r["sentence_id"] for r in rows]
        continue
    paras = [p.strip() for p in texts[k].split("\n\n") if p.strip()]
    keys = PJ.us_keys(e, len(paras)) or [(None, None)] * len(paras)
    sq = [squash(p) for p in paras]
    whole = "".join(sq)
    for r in rows:
        t = squash(r["text"])
        if t not in whole:
            miss.append(r["sentence_id"])
            continue
        p = q = pnum(r["sentence_id"])
        acc = ""
        while q < len(sq) and t not in acc:
            acc += sq[q]
            q += 1
        if t not in acc or len(set(keys[p:q])) > 1:
            mixed.append(r["sentence_id"])
check("2. every US sentence is in its bill-day's corrected text", not miss,
      f"{len(sent):,} sentences, {len(miss)} not found {miss[:2]}")
check("3. no joined US sentence crosses two tags or two source units", not mixed, f"{len(mixed)} {mixed[:3]}")

W = re.compile(r"[A-Za-z]{3,}")
vocab = Counter()
bound_rows = lambda rows: [r for r in rows if idx.get((r["bill_key"], r["date"]), {}).get("edition") == "bound"]
for r in sent:
    if idx.get((r["bill_key"], r["date"]), {}).get("edition") != "bound":
        vocab.update(w.lower() for w in W.findall(r["text"]))


def unknown_share(rows):
    n = u = 0
    for r in bound_rows(rows):
        e = idx[(r["bill_key"], r["date"])]
        tags = PJ.expand_runs(e["para_tags"])
        p = pnum(r["sentence_id"])
        if p < len(tags) and set(tags[p].split("+")) & OUT_TAGS:
            continue
        ws = W.findall(r["text"])
        n += len(ws)
        u += sum(vocab[w.lower()] < 2 for w in ws)
    return n, u


nb, ub = unknown_share(bsent)
na, ua = unknown_share(sent)
check("4. no more unknown words in the 1985-1993 sentences that count than before", nb and ua <= ub,
      f"before {ub:,} of {nb:,} ({ub / max(nb, 1):.2%}); now {ua:,} of {na:,} ({ua / max(na, 1):.2%})")

n_list = len(load(FIXES, []) or [])
rep = Path("outputs/audit/us_text_choices.txt")
placed = rep.exists() and "every sentence placed" in rep.read_text(encoding="utf-8")
arep = Path("outputs/audit/audit_report.txt")
fails = [ln for ln in arep.read_text(encoding="utf-8").splitlines() if "[FAIL]" in ln] if arep.exists() else ["no audit"]
check("5. every listed correction applied, every US sentence placed, audit has no FAIL",
      tally.get("us_ocr_fixed") == n_list and not tally.get("us_ocr_not_found") and placed and not fails,
      f"corrections {tally.get('us_ocr_fixed', 0):,} of {n_list:,} (not found {tally.get('us_ocr_not_found', 0)}); "
      f"US placed {placed}; audit {fails[:2] or '0 FAIL'}")
before = len(load(B / "us_predications_v3.json", []) or []) if B else 0
say(f"US claims that count: {before:,} -> {len(load(PIPE / 'us' / 'predications_v3.json', []) or []):,}")
say(f"CHECKS: {sum(RES)} passed, {len(RES) - sum(RES)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
sys.exit(2 if not all(RES) else 0)
