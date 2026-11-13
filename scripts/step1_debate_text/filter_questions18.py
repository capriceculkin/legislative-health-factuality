#!/usr/bin/env python3
"""filter_questions18.py   Removes, from the claims already extracted, every claim whose sentence is itself a
question (the same rule the patched extractor now applies), so no 90-minute re-extraction is needed.
Writes outputs/audit/fix18_removed_questions.csv. Run from the project folder."""
import csv, importlib.util, json, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("x18", "scripts/step1_debate_text/extract_predications_v3.py")
X = importlib.util.module_from_spec(spec)
sys.modules.setdefault("spacy", type(sys)("spacy"))
sys.path.insert(0, "scripts/step1_debate_text")
spec.loader.exec_module(X)
if not hasattr(X, "is_question"):
    sys.exit("the extractor has no question rule; run patch_extractor18.py first")
rows = []
for j in ("us", "ontario", "quebec"):
    for name in ("predications_v3.json", "predications_v3_set_aside.json"):
        p = Path("data/dbpedia_pipeline") / j / name
        if not p.exists():
            continue
        claims = json.loads(p.read_text(encoding="utf-8"))
        keep = []
        for c in claims:
            if X.is_question(c.get("full_text", ""), c.get("language", "en")):
                rows.append({"jurisdiction": j, "file": name, "sentence_id": c.get("sentence_id"),
                             "claim": f"{c.get('subject')} | {c.get('verb')} | {c.get('object')}",
                             "sentence": c.get("full_text", "")[:400]})
            else:
                keep.append(c)
        p.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   {j} {name}: {len(claims):,} -> {len(keep):,} claims ({len(claims) - len(keep):,} from questions removed)")
out = Path("outputs/audit/fix18_removed_questions.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["jurisdiction", "file", "sentence_id", "claim", "sentence"])
    w.writeheader(); w.writerows(rows)
print(f"   {len(rows):,} claims removed in all; listed in {out}")
