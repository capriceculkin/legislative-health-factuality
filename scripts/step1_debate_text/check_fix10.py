#!/usr/bin/env python3
"""
check_fix10.py   (reads only; a few minutes)

Checks after the sentence rebuild with para_join.py:
  1. Ontario sentences are byte for byte what they were (Ontario is not touched)
  2. every US and Quebec sentence is in its own bill-day's text (Quebec 1985-1994: with the OCR word corrections),
     so the joins add no word and lose none
  3. no joined US sentence crosses two tags or two source units (walked paragraph by paragraph, a different method
     from the one the builder uses)
  4. sentence fragments (no . ! ? : ; at the end) are far fewer: US text that counts and Quebec 1985-1994
  5. all 477 Quebec OCR corrections found their word; every US sentence placed by apply_us_text_choices.py;
     the audit has no FAIL
Writes outputs/audit/fix10_check.txt. Exit code 2 on any FAIL.
Run from the project folder:  python3 scripts/step1_debate_text/check_fix10.py <copy folder from before fix10>
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
OUT = Path("outputs/audit/fix10_check.txt")
LINES, RES = [], []
TERM = re.compile(r"[.!?:;…][\"'»”’)\]]*$")
OUT_TAGS = {"printed", "votelist", "rule", "notbill"}
N_OCR = 477


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


PIPE = Path("data/dbpedia_pipeline")
# 1
o_old, o_new = (load(B / "ontario_test" / f, None) if B else None for f in ("old_builder.json", "new_builder.json"))
ok1 = bool(o_old) and o_old == o_new and load(B / "ontario_sentences_v3.json", None) == load(PIPE / "ontario" / "sentences_v3.json", None)
check("1. Ontario sentences unchanged (old and new builder give the same; saved file kept)", ok1,
      f"{len(o_old or []):,} sentences from each builder")

# sentences: kept + set aside (US)
sent = {j: (load(PIPE / j / "sentences_v3.json", []) or []) + (load(PIPE / j / "sentences_v3_set_aside.json", []) or [])
        for j in ("us", "quebec")}
bsent = {j: (load(B / f"{j}_sentences_v3.json", []) or []) + (load(B / f"{j}_sentences_v3_set_aside.json", []) or [])
         for j in ("us", "quebec")} if B else {"us": [], "quebec": []}

# texts
qbase = Path("data/canada/quebec_assembly")
qidx = load(qbase / "v3" / "segments_index.json", [])
fixes = PJ.load_ocr_fixes(qbase / "v3" / "ocr_word_fixes.json")
vocab = PJ.quebec_vocab(str(qbase), qidx)
tally = {}
qtext, qera = {}, {}
for e in qidx:
    t = (qbase / e["file"]).read_text(encoding="utf-8")
    d = f"{e['date'][:4]}-{e['date'][4:6]}-{e['date'][6:]}"
    pre = e.get("source") == "bibliotheque_pre1994"
    if pre:
        t = PJ.fix_quebec_text(t, fixes.get(e["file"]), vocab, tally)
    k = (e["bill_key"], d)
    qtext[k] = qtext.get(k, "") + squash(t)
    qera[k] = "1985-1994" if pre else "1994+"
uidx = load("data/us/v3/segments_index.json", [])
uinfo = {}
for e in uidx:
    uinfo[(e["bill_key"], e["debate_date"])] = e

# 2 and 3
miss = {"us": [], "quebec": []}
for s in sent["quebec"]:
    if squash(s["text"]) not in qtext.get((s["bill_key"], s["date"]), ""):
        miss["quebec"].append(s["sentence_id"])
by_day = {}
for s in sent["us"]:
    by_day.setdefault((s["bill_key"], s["date"]), []).append(s)
mixed, spans, frag = [], 0, Counter()
for k, rows in by_day.items():
    e = uinfo.get(k)
    if not e:
        miss["us"] += [r["sentence_id"] for r in rows]
        continue
    paras = [p.strip() for p in Path("data/us", e["file"]).read_text(encoding="utf-8").split("\n\n") if p.strip()]
    keys = PJ.us_keys(e, len(paras)) or [(None, None)] * len(paras)
    sq = [squash(p) for p in paras]
    whole = "".join(sq)
    for r in rows:
        t = squash(r["text"])
        if t not in whole:
            miss["us"].append(r["sentence_id"])
            continue
        p, q, acc = pnum(r["sentence_id"]), pnum(r["sentence_id"]), ""
        while q < len(sq) and t not in acc:
            acc += sq[q]
            q += 1
        if t not in acc or len(set(keys[p:q])) > 1:
            mixed.append(r["sentence_id"])
        spans += q - p > 1
check("2. every US and Quebec sentence is in its bill-day's text", not miss["us"] and not miss["quebec"],
      f"US {len(sent['us']):,} sentences, {len(miss['us'])} not found {miss['us'][:2]}; Quebec "
      f"{len(sent['quebec']):,}, {len(miss['quebec'])} not found {miss['quebec'][:2]}")
check("3. no joined US sentence crosses two tags or two source units", not mixed,
      f"{spans:,} sentences join 2+ paragraphs; {len(mixed)} cross {mixed[:3]}")


# 4
def frag_share(rows, j):
    c = Counter()
    for r in rows:
        k = (r["bill_key"], r["date"])
        if j == "us":
            e = uinfo.get(k)
            tags = PJ.expand_runs(e["para_tags"]) if e else []
            p = pnum(r["sentence_id"])
            t = tags[p] if p < len(tags) else "?"
            if set(t.split("+")) & OUT_TAGS:
                continue
            g = "US text that counts"
        else:
            g = "Quebec " + qera.get(k, "?")
        c[(g, 0)] += 1
        c[(g, 1)] += not TERM.search(r["text"].strip())
    return c


fa = frag_share(sent["us"], "us") + frag_share(sent["quebec"], "quebec")
fb = frag_share(bsent["us"], "us") + frag_share(bsent["quebec"], "quebec")
ok4 = True
for g in ("US text that counts", "Quebec 1985-1994", "Quebec 1994+"):
    a_n, a_f, b_n, b_f = fa[(g, 0)], fa[(g, 1)], fb[(g, 0)], fb[(g, 1)]
    say(f"   {g}: sentences {b_n:,} -> {a_n:,}; without a sentence end {b_f:,} "
        f"({b_f / max(b_n, 1):.1%}) -> {a_f:,} ({a_f / max(a_n, 1):.1%})")
    if g != "Quebec 1994+" and not (a_f / max(a_n, 1) < 0.5 * b_f / max(b_n, 1)):
        ok4 = False
check("4. sentence fragments at least halved (US text that counts, Quebec 1985-1994)", ok4 and bool(fb))

# 5
rep = Path("outputs/audit/us_text_choices.txt")
placed = rep.exists() and "every sentence placed" in rep.read_text(encoding="utf-8")
arep = Path("outputs/audit/audit_report.txt")
fails = [ln for ln in arep.read_text(encoding="utf-8").splitlines() if "[FAIL]" in ln] if arep.exists() else ["no audit"]
check("5. Quebec OCR corrections all applied, every US sentence placed, audit has no FAIL",
      tally.get("ocr_fixed") == N_OCR and not tally.get("ocr_not_found") and placed and not fails,
      f"OCR {tally.get('ocr_fixed', 0)} of {N_OCR} (not found {tally.get('ocr_not_found', 0)}); line-end hyphen joins inside paragraphs "
      f"{tally.get('hyphen_joined', 0)}; US placed {placed}; audit {fails[:2] or '0 FAIL'}")

for j in ("us", "quebec"):
    before = len(load(B / f"{j}_predications_v3.json", []) or []) if B else 0
    now = len(load(PIPE / j / "predications_v3.json", []) or [])
    say(f"{'US' if j == 'us' else 'Quebec'} claims that count: {before:,} -> {now:,}")
say(f"CHECKS: {sum(RES)} passed, {len(RES) - sum(RES)} failed")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
sys.exit(2 if not all(RES) else 0)
