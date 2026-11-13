#!/bin/bash
# run_ontario_order_fix.sh   (about 25 minutes, no downloads)
# Puts Ontario paragraphs in Hansard order on pages where they all share one address (Bill 50 on
# 1993-12-08 started with "How much heat?" instead of the third-reading motion), fills a missing page
# address (audit check D1), rebuilds Ontario sentences, claims, outcomes, audit and workbook, then
# prints everything the Sept 24 before-and-after sheet needs.
# Run from the project folder AFTER run_ontario_variants_fix.sh has printed "== DONE":
#   caffeinate -i bash scripts/step1_debate_text/run_ontario_order_fix.sh 2>&1 | tee outputs/audit/ontario_order_fix.log
set -eo pipefail

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_ontario_order_fix_$STAMP"
echo "== keeping a copy of the current data in $B"
mkdir -p "$B"
cp data/canada/ontario/v3/hansard_segments_v3.json "$B/"
cp data/canada/quebec_assembly/v3/segments_index.json "$B/"
cp -R data/canada/quebec_assembly/v3/bill_segments_v3 "$B/quebec_bill_segments_v3"
cp data/dbpedia_pipeline/ontario/sentences_v3.json "$B/ontario_sentences_v3.json"
if [ -f data/dbpedia_pipeline/ontario/predications_v3.json ]; then
  cp data/dbpedia_pipeline/ontario/predications_v3.json "$B/ontario_predications_v3.json"; fi
cp data/v3_outcomes.json "$B/"

echo "== patch: paragraph order from the API id, page address from paraUrl when missing"
python3 scripts/step1_debate_text/patch_ontario_order.py
python3 scripts/step1_debate_text/ontario_rebuild.py assign
python3 scripts/step1_debate_text/ontario_rebuild.py verify

echo "== order check: first paragraph of each Bill 50 and Bill 94 day (a debate opens with its motion or the Speaker)"
python3 -c "
import json
s = json.load(open('data/canada/ontario/v3/hansard_segments_v3.json'))
for k in ('35-3-Bill50', '33-1-Bill94', '33-2-Bill94'):
    for d, ps in sorted((s.get(k) or {}).items()):
        print(f'  {k} {d} {len(ps):>4}  {ps[0][\"text\"][:110]}')
"

echo "== what changed (paragraphs matched by address and text, so only a change in WHICH paragraphs shows here)"
python3 scripts/step1_debate_text/canada_before_after.py "$B"

echo "== Ontario sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py ontario
mkdir -p data/dbpedia_pipeline/ontario/_old_resume
if [ -f data/dbpedia_pipeline/ontario/predications_v3.json ]; then
  mv -f data/dbpedia_pipeline/ontario/predications_v3.json \
        data/dbpedia_pipeline/ontario/_old_resume/predications_v3_before_order_fix.json; fi
python3 scripts/step1_debate_text/extract_predications_v3.py ontario

echo "== exclusions, outcomes (with royal assent lists), audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/apply_royal_assent.py
python3 scripts/step1_debate_text/audit_review_data.py | grep -E "FAIL|PASS, " || true
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== HOW MUCH CHANGED since the data shown at the Sept 29 meeting"
python3 scripts/step1_debate_text/ontario_fix_report.py
echo "== SEPT 24 BEFORE AND AFTER (for the shared sheet)"
python3 scripts/step1_debate_text/sept24_before_after.py
echo "== DONE (the copy from before this pass is in $B)"
