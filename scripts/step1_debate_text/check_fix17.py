#!/usr/bin/env python3
"""
check_fix17.py   (reads only; a few minutes)

Checks after every claim was extracted again with the v17 claim rules (compared with the claims before):
  1. the sentences of all three jurisdictions are the same as before (only the claims were redone)
  2. no subject or object has words that are not in its sentence, and none is empty or the same as the other
  3. forms of address as subject ("Mr. Speaker", "M. le President"): at most 20 in all
  4. subjects followed by a colon in the sentence (speaker labels): at most 1 in 200 claims
  5. no object is the French filler "la" or the pronoun "l'", and none ends with "ago"
  6. the 1,380 sentences Claude tested have exactly the claims Claude got (wherever they are in the data)
  7. every claim has its sentence, every US sentence placed by apply_us_text_choices.py, the audit has no FAIL
  8. no sentence broke a claim rule during the run (outputs/audit/extract_errors.txt is empty)
Writes outputs/audit/fix17_check.txt. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix17.py <copy folder from before fix17> <expected_claims.json>
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
OUT = Path("outputs/audit/fix17_check.txt")
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
    text = p.get("full_text", "") or ""
    subj, obj = p.get("subject", "") or "", p.get("object", "") or ""
    out = set()
    if any(w not in text for f in (subj, obj) for w in WORD.findall(f)):
        out.add("glued")
    if ADDRESS.match(subj):
        out.add("address")
    elif re.search(re.escape(subj) + r"\s*(?:\([^)]*\))?\s*:", text):
        out.add("label")
    if obj.lower() in {"là", "l'", "l’"} or obj.lower().endswith(" ago"):
        out.add("filler")
    if not subj.strip() or not obj.strip() or subj.lower() == obj.lower():
        out.add("glued")
    return out


same = []
for j in ("us", "ontario", "quebec"):
    a = (load(B / f"{j}_sentences_v3.json", []) or []) + (load(B / f"{j}_sentences_v3_set_aside.json", []) or [])
    b = (load(f"data/dbpedia_pipeline/{j}/sentences_v3.json", []) or []) + \
        (load(f"data/dbpedia_pipeline/{j}/sentences_v3_set_aside.json", []) or [])
    if a and sorted(x["sentence_id"] for x in a) == sorted(x["sentence_id"] for x in b):
        same.append(j)
check("1. the sentences are the same as before", len(same) == 3, f"same: {same}")
K = ("glued", "address", "label", "filler")
tot = {w: dict.fromkeys(K + ("n",), 0) for w in ("before", "now")}
for j in ("us", "ontario", "quebec"):
    for when, rows in (("before", load(B / f"{j}_predications_v3.json", []) or []),
                       ("now", load(f"data/dbpedia_pipeline/{j}/predications_v3.json", []) or [])):
        c = dict.fromkeys(K, 0)
        for p in rows:
            for k in kinds(p):
                c[k] += 1
        for k in c:
            tot[when][k] += c[k]
        tot[when]["n"] += len(rows)
        say(f"   {j} {when}: {len(rows):,} claims; glued words {c['glued']:,}; address as subject {c['address']:,}; "
            f"label as subject {c['label']:,}; 'la' or l' as object {c['filler']:,}")
b_, n_ = tot["before"], tot["now"]
check("2. no words missing from the sentence, no empty subject or object", n_["glued"] == 0,
      f"{b_['glued']:,} -> {n_['glued']:,}")
check("3. forms of address as subject: at most 20", n_["address"] <= 20, f"{b_['address']:,} -> {n_['address']:,}")
check("4. speaker labels as subject: at most 1 in 200", n_["label"] * 200 <= max(n_["n"], 1),
      f"{b_['label']:,} -> {n_['label']:,} of {n_['n']:,}")
check("5. no French filler or l' as object, none ending in 'ago'", n_["filler"] == 0, f"{b_['filler']:,} -> {n_['filler']:,}")
E = load(sys.argv[2], {}) or {}
have = {}
for j in ("us", "ontario", "quebec"):
    for f in ("predications_v3.json", "predications_v3_set_aside.json"):
        for p in load(f"data/dbpedia_pipeline/{j}/{f}", []) or []:
            have[p.get("sentence_id")] = p
F = ("subject", "verb", "verb_lemma", "object", "hedged", "negated")
miss = []
for r in E.get("sentences", []):
    p = have.get(r["sentence_id"])
    got = {k: p.get(k) for k in F} if p else None
    if got != r["expected"]:
        miss.append(r["sentence_id"])
check("6. the 1,380 tested sentences have exactly the claims Claude tested", E.get("sentences") and not miss,
      f"{len(E.get('sentences', []))} sentences, {len(miss)} differ {miss[:3]}")
sids = set()
for j in ("us", "ontario", "quebec"):
    sids |= {s["sentence_id"] for s in load(f"data/dbpedia_pipeline/{j}/sentences_v3.json", []) or []}
orph = sum(1 for j in ("us", "ontario", "quebec") for p in load(f"data/dbpedia_pipeline/{j}/predications_v3.json", []) or []
           if p.get("sentence_id") not in sids)
rep = Path("outputs/audit/us_text_choices.txt")
placed = rep.exists() and "every sentence placed" in rep.read_text(encoding="utf-8")
arep = Path("outputs/audit/audit_report.txt")
fails = [l for l in arep.read_text(encoding="utf-8").splitlines() if "[FAIL]" in l] if arep.exists() else ["no audit"]
check("7. every claim has its sentence, every US sentence placed, audit has no FAIL", orph == 0 and placed and not fails,
      f"claims without their sentence {orph}; US placed {placed}; audit {fails[:2] or '0 FAIL'}")
errf = Path("outputs/audit/extract_errors.txt")
errs = [l for l in (errf.read_text(encoding="utf-8").splitlines() if errf.exists() else []) if l.strip()]
check("8. no sentence broke a claim rule during the run", not errs,
      f"{len(errs)} in outputs/audit/extract_errors.txt" + (f"; first: {errs[0][:160]}" if errs else ""))
for j in ("us", "ontario", "quebec"):
    say(f"{j} claims that count: {len(load(B / f'{j}_predications_v3.json', []) or []):,} -> "
        f"{len(load(f'data/dbpedia_pipeline/{j}/predications_v3.json', []) or []):,}")
say(f"CHECKS: {sum(RES)} passed, {len(RES) - sum(RES)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
sys.exit(2 if not all(RES) else 0)
