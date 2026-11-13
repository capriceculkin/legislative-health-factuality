#!/usr/bin/env python3
"""check_fix18.py  <copy folder from before fix18>
Two different checks that only question claims were removed:
  A. no claim left comes from a question (the rule applied again to every claim now)
  B. sentence by sentence against the copy: every claim now is identical to the one before, and every claim that
     is gone came from a question (nothing else was lost, nothing was changed or added)
Writes outputs/audit/fix18_check.txt; exit code 2 on any FAIL. Run from the project folder."""
import importlib.util, json, sys
from pathlib import Path

B = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("x18c", "scripts/step1_debate_text/extract_predications_v3.py")
X = importlib.util.module_from_spec(spec); sys.modules.setdefault("spacy", type(sys)("spacy"))
sys.path.insert(0, "scripts/step1_debate_text"); spec.loader.exec_module(X)
L, ok = [], True
def say(s): print(s); L.append(s)
left = changed = added = lost_other = gone_q = 0
for j in ("us", "ontario", "quebec"):
    for name in ("predications_v3.json", "predications_v3_set_aside.json"):
        before_p, now_p = B / f"{j}_{name}", Path("data/dbpedia_pipeline") / j / name
        if not before_p.exists() and not now_p.exists():
            continue
        before = {c["sentence_id"]: c for c in json.loads(before_p.read_text(encoding="utf-8"))} if before_p.exists() else {}
        now = {c["sentence_id"]: c for c in json.loads(now_p.read_text(encoding="utf-8"))} if now_p.exists() else {}
        left += sum(X.is_question(c.get("full_text", ""), c.get("language", "en")) for c in now.values())
        added += len(set(now) - set(before))
        changed += sum(now[k] != before[k] for k in set(now) & set(before))
        for k in set(before) - set(now):
            if X.is_question(before[k].get("full_text", ""), before[k].get("language", "en")): gone_q += 1
            else: lost_other += 1
        say(f"   {j} {name}: {len(before):,} -> {len(now):,}")
a = left == 0
b = changed == 0 and added == 0 and lost_other == 0
say(f"CHECK {'PASS' if a else 'FAIL'}  A. no claim left comes from a question  ({left} left)")
say(f"CHECK {'PASS' if b else 'FAIL'}  B. only question claims removed, nothing else changed  "
    f"(removed from questions {gone_q:,}; other claims lost {lost_other}; changed {changed}; added {added})")
Path("outputs/audit").mkdir(parents=True, exist_ok=True)
Path("outputs/audit/fix18_check.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
sys.exit(0 if a and b else 2)
