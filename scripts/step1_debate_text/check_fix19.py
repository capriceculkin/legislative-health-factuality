#!/usr/bin/env python3
"""check_fix19.py  <copy folder from before fix19>
Checks on the v19 claims that do not depend on how the parser read each sentence:
  A. no claim comes from a question (v18 rule)
  B. no claim breaks a v19 text rule: statute text, statute number or heading as subject, relative pronoun as subject,
     a quoted word inside the verb, a French clause as object
  C. claims did not collapse: the total is at least 90% of the count before fix19, in every jurisdiction
  D. at most 15% of sentences changed claim (the rules are targeted; more would mean something went wrong)
Writes outputs/audit/fix19_check.txt; exit code 2 on any FAIL. Run from the project folder."""
import importlib.util, json, re, sys
from pathlib import Path

B = Path(sys.argv[1])
sys.modules.setdefault("spacy", type(sys)("spacy")); sys.path.insert(0, "scripts/step1_debate_text")
spec = importlib.util.spec_from_file_location("x19c", "scripts/step1_debate_text/extract_predications_v3.py")
X = importlib.util.module_from_spec(spec); spec.loader.exec_module(X)
L, res = [], []
def say(s): print(s); L.append(s)
def check(name, ok, detail): res.append(ok); say(f"CHECK {'PASS' if ok else 'FAIL'}  {name}  ({detail})")
def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
q = t = 0; low = []; changed = total = 0; examples = []
for j in ("us", "ontario", "quebec"):
    now = load(Path("data/dbpedia_pipeline") / j / "predications_v3.json")
    before = load(B / f"{j}_predications_v3.json")
    for c in now:
        L_ = c.get("language", "en"); s, v, o, txt = c["subject"], c["verb"], c["object"], c.get("full_text", "")
        q += X.is_question(txt, L_)
        bad = ((L_ == "en" and (X.LEGAL_EN.search(txt) or X.LEGAL_EN_CS.search(txt))) or X.STATUTE_SUBJ.search(s)
               or X.CAPS_RUN.search(s) or X.REL_SUBJ[L_].search(s) or any(w[:1].isupper() for w in v.split()[1:])
               or (L_ == "fr" and re.match(r"^(?:on|lorsqu|quand|si|parce)\b", o, re.I)))
        if bad:
            t += 1; examples.append(f"{s} | {v} | {o}")
    if before and len(now) < 0.9 * len(before):
        low.append(f"{j} {len(before):,} -> {len(now):,}")
    a = {c["sentence_id"]: (c["subject"], c["verb"], c["object"]) for c in before}
    b = {c["sentence_id"]: (c["subject"], c["verb"], c["object"]) for c in now}
    ids = set(a) | set(b)
    total += len(ids); changed += sum(a.get(k) != b.get(k) for k in ids)
    say(f"   {j}: {len(before):,} claims before fix19 -> {len(now):,} now")
check("A. no claim comes from a question", q == 0, f"{q} left")
check("B. no claim breaks a v19 text rule", t == 0, f"{t} found" + (f"; e.g. {examples[0][:120]}" if examples else ""))
check("C. claims did not collapse (each jurisdiction keeps at least 90%)", not low, "; ".join(low) or "all kept 90% or more")
check("D. at most 15% of sentences changed claim", changed <= 0.15 * max(total, 1), f"{changed:,} of {total:,} ({100 * changed / max(total, 1):.1f}%)")
say(f"CHECKS: {sum(res)} passed, {len(res) - sum(res)} failed")
Path("outputs/audit/fix19_check.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
sys.exit(0 if all(res) else 2)
