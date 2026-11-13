#!/usr/bin/env python3
"""
patch_dbpedia_v3.py

Two edits to scripts/dbpedia_batch_pipeline.py, stage extract_v2:
  1. Spotlight language comes from each predication (pred["language"]) instead of the
     jurisdiction-wide SPOTLIGHT_LANG, so French Ontario predications go to the
     French Spotlight on port 2223 and English Quebec predications to port 2222.
  2. Each triple keeps bill_key, session, date and language, so scores can be joined
     per bill.

It also swaps in the v3 predications file:
  predications.json      -> predications_v2_backup.json   (kept, not deleted)
  predications_v3.json   -> predications.json
and removes a stale triples_v2.json.checkpoint so extract_v2 starts clean.

A backup of the pipeline script is written first. The script prints exactly what it
changed and stops without writing if a pattern is not found.

    python3 scripts/step1_debate_text/patch_dbpedia_v3.py            # patch the script only
    python3 scripts/step1_debate_text/patch_dbpedia_v3.py ontario    # patch + swap files for one jurisdiction
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import rp

SCRIPT = rp("scripts", "dbpedia_batch_pipeline.py")


def patch_script():
    with open(SCRIPT, encoding="utf-8") as f:
        src = f.read()
    if "pred.get(\"language\") or SPOTLIGHT_LANG" in src:
        print("dbpedia_batch_pipeline.py is already patched")
        return
    new, n1 = re.subn(r'spotlight_string\(\s*pred\["(subject|object)"\]\s*,\s*SPOTLIGHT_LANG\s*\)',
                      r'spotlight_string(pred["\1"], pred.get("language") or SPOTLIGHT_LANG)', src)
    new, n2 = re.subn(r'("sentence_id"\s*:\s*pred\["sentence_id"\]\s*,)',
                      r'\1 "bill_key": pred.get("bill_key"), "session": pred.get("session"), '
                      r'"date": pred.get("date"), "language": pred.get("language"),', new, count=1)
    print(f"  Spotlight language lines changed: {n1} (expected 2)")
    print(f"  triple metadata lines changed: {n2} (expected 1)")
    if n1 != 2 or n2 != 1:
        sys.exit("Patterns not found as expected. Nothing written. Run: grep -n 'spotlight_string\\|sentence_id' "
                 "scripts/dbpedia_batch_pipeline.py  and send the output.")
    shutil.copy2(SCRIPT, SCRIPT + ".bak_before_v3")
    with open(SCRIPT, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"  patched {SCRIPT} (backup: {SCRIPT}.bak_before_v3)")


def swap(j):
    d = rp("data", "dbpedia_pipeline", j)
    v3 = os.path.join(d, "predications_v3.json")
    cur = os.path.join(d, "predications.json")
    bak = os.path.join(d, "predications_v2_backup.json")
    if not os.path.exists(v3):
        sys.exit(f"{v3} not found. Run extract_predications_v3.py {j} first.")
    if os.path.exists(cur) and not os.path.exists(bak):
        os.replace(cur, bak)
        print(f"  {cur} -> {bak}")
    shutil.copy2(v3, cur)
    print(f"  {v3} -> {cur}")
    ck = os.path.join(d, "triples_v2.json.checkpoint")
    if os.path.exists(ck):
        os.remove(ck)
        print(f"  removed stale {ck}")


if __name__ == "__main__":
    patch_script()
    for j in sys.argv[1:]:
        swap(j)
