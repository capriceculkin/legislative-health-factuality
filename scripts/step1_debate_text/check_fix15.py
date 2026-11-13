#!/usr/bin/env python3
"""
check_fix15.py   (reads only; a few minutes)

Checks after every claim was extracted again with the corrected extractor:
  1. the sentences of all three jurisdictions are the same as before (only the claims were redone)
  2. subjects and objects with words that are not in their sentence (glued words): far fewer than before
  3. objects taken from an opening phrase before the verb: far fewer than before
  4. subjects that are a speaker label or a form of address: far fewer than before
  5. every claim has its sentence, every US sentence placed by apply_us_text_choices.py, the audit has no FAIL
"Far fewer" is a third or less of the count before, for all three jurisdictions together.
Writes outputs/audit/fix15_check.txt. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix15.py <copy folder from before fix15>
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
B = Path(sys.argv[1])
OUT = Path("outputs/audit/fix15_check.txt")
LINES, RES = [], []
ADDRESS = re.compile(r"^(?:(?:Mr|Mrs|Ms|Madam|Madame)\.?\s+(?:Speaker|Chairman|Chairwoman|Chair|President|Clerk)"
                     r"(?:\s+pro\s+tempore)?|(?:M\.|Mme|Monsieur|Madame)\s+(?:le|la)\s+(?:Présidente?|"
                     r"Vice-Présidente?))$", re.I)
WORD = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*", re.U)


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


def kinds(p):
    text = p.get("full_text", "")
    out = set()
    if any(w not in text for f in ("subject", "object") for w in WORD.findall(p.get(f, ""))):
        out.add("glued")
    io, iv = text.find(p.get("object", "")), text.find(p.get("verb", ""))
    if io >= 0 and iv >= 0 and io < iv and not text.rstrip().endswith("?"):
        out.add("opening")
    if re.search(re.escape(p.get("subject", "")) + r"\s*:", text) or ADDRESS.match(p.get("subject", "")):
        out.add("label")
    return out


same = []
for j in ("us", "ontario", "quebec"):
    a = (load(B / f"{j}_sentences_v3.json", []) or []) + (load(B / f"{j}_sentences_v3_set_aside.json", []) or [])
    b = (load(f"data/dbpedia_pipeline/{j}/sentences_v3.json", []) or []) + \
        (load(f"data/dbpedia_pipeline/{j}/sentences_v3_set_aside.json", []) or [])
    if a and sorted(x["sentence_id"] for x in a) == sorted(x["sentence_id"] for x in b):
        same.append(j)
check("1. the sentences are the same as before", len(same) == 3, f"same: {same}")
tot = {"before": {"glued": 0, "opening": 0, "label": 0, "n": 0}, "now": {"glued": 0, "opening": 0, "label": 0, "n": 0}}
for j in ("us", "ontario", "quebec"):
    for when, rows in (("before", load(B / f"{j}_predications_v3.json", []) or []),
                       ("now", load(f"data/dbpedia_pipeline/{j}/predications_v3.json", []) or [])):
        c = {"glued": 0, "opening": 0, "label": 0}
        for p in rows:
            for k in kinds(p):
                c[k] += 1
        for k in c:
            tot[when][k] += c[k]
        tot[when]["n"] += len(rows)
        say(f"   {j} {when}: {len(rows):,} claims; glued words {c['glued']:,}; object from an opening phrase "
            f"{c['opening']:,}; label or address as subject {c['label']:,}")
for n, k, name in ((2, "glued", "subjects and objects with words not in the sentence"),
                   (3, "opening", "objects from an opening phrase before the verb"),
                   (4, "label", "speaker labels and forms of address as subject")):
    check(f"{n}. far fewer {name}", tot["now"][k] * 3 <= tot["before"][k] and tot["before"][k] > 0,
          f"{tot['before'][k]:,} -> {tot['now'][k]:,}")
sids = set()
for j in ("us", "ontario", "quebec"):
    sids |= {s["sentence_id"] for s in load(f"data/dbpedia_pipeline/{j}/sentences_v3.json", []) or []}
orph = sum(1 for j in ("us", "ontario", "quebec") for p in load(f"data/dbpedia_pipeline/{j}/predications_v3.json", []) or []
           if p.get("sentence_id") not in sids)
rep = Path("outputs/audit/us_text_choices.txt")
placed = rep.exists() and "every sentence placed" in rep.read_text(encoding="utf-8")
arep = Path("outputs/audit/audit_report.txt")
fails = [l for l in arep.read_text(encoding="utf-8").splitlines() if "[FAIL]" in l] if arep.exists() else ["no audit"]
check("5. every claim has its sentence, every US sentence placed, audit has no FAIL", orph == 0 and placed and not fails,
      f"claims without their sentence {orph}; US placed {placed}; audit {fails[:2] or '0 FAIL'}")
for j in ("us", "ontario", "quebec"):
    say(f"{j} claims that count: {len(load(B / f'{j}_predications_v3.json', []) or []):,} -> "
        f"{len(load(f'data/dbpedia_pipeline/{j}/predications_v3.json', []) or []):,}")
say(f"CHECKS: {sum(RES)} passed, {len(RES) - sum(RES)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
sys.exit(2 if not all(RES) else 0)
