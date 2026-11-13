#!/bin/bash
# run_ontario_variants_fix.sh
# Finishes the Ontario text fix after run_ontario_rowid_fix.sh. Quebec and US are not touched.
#   1. Downloads again the official-day text that the last run moved aside and did not re-download
#      (3 bill-days, 18 paragraphs: 36-1-Bill149 1997-12-03, 36-1-Bill67 1996-06-25, 41-1-Bill27 2015-06-02).
#   2. Downloads the full Hansard of every day a health bill is debated or moved, and adds paragraphs
#      filed under a different spelling of the bill's own heading, which the exact-spelling download
#      missed (34-1-Bill174 on 1988-12-15: 135 paragraphs in the full day, 15 in our data).
#   3. Rebuilds Ontario text, sentences, claims, outcomes, audit and workbook, then reports how much
#      changed since the data shown at the Sept 29 meeting.
# Run from the project folder AFTER run_ontario_rowid_fix.sh has printed "== DONE" (about 3 hours):
#   caffeinate -i bash scripts/step1_debate_text/run_ontario_variants_fix.sh 2>&1 | tee outputs/audit/ontario_variants_fix.log
set -eo pipefail

grep -q PATCHED_ROWID_2026_10_01 scripts/step1_debate_text/ontario_rebuild.py || { echo "run patch_ontario_rowid.py first"; exit 1; }
STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_ontario_variants_$STAMP"
echo "== keeping a copy of the current data in $B"
mkdir -p "$B"
cp data/canada/ontario/v3/hansard_segments_v3.json "$B/"
cp data/canada/quebec_assembly/v3/segments_index.json "$B/"
cp -R data/canada/quebec_assembly/v3/bill_segments_v3 "$B/quebec_bill_segments_v3"
cp data/dbpedia_pipeline/ontario/sentences_v3.json "$B/ontario_sentences_v3.json"
if [ -f data/dbpedia_pipeline/ontario/predications_v3.json ]; then
  cp data/dbpedia_pipeline/ontario/predications_v3.json "$B/ontario_predications_v3.json"; fi
cp data/v3_outcomes.json "$B/"
export OLA_SLEEP=4

echo "== 1. official-day text that the last run moved aside"
python3 scripts/step1_debate_text/ontario_rebuild.py official-days

echo "== 2. full days: every spelling of each health bill's own heading"
python3 scripts/step1_debate_text/fill_heading_variants.py --apply
python3 scripts/step1_debate_text/ontario_rebuild.py assign
python3 scripts/step1_debate_text/ontario_rebuild.py verify

echo "== checks: saved full days, Bill 50, 30 random bill-days against the full day, Bill 174"
python3 scripts/step1_debate_text/check_row_ids.py --sample 30
python3 scripts/step1_debate_text/check_bills.py 34-1-Bill174 35-3-Bill50 | grep -v "^              first:"
echo "== the 3 bill-days the last run dropped (each should have paragraphs again)"
python3 -c "import json;s=json.load(open('data/canada/ontario/v3/hansard_segments_v3.json'));[print(k,d,len(s.get(k,{}).get(d,[])),'paragraphs') for k,d in [('36-1-Bill149','1997-12-03'),('36-1-Bill67','1996-06-25'),('41-1-Bill27','2015-06-02')]]"

echo "== what changed in this pass (paragraphs matched by address and text; Quebec should show no change;"
echo "   paragraphs added under a bill's own heading are expected here even where marked UNEXPECTED)"
python3 scripts/step1_debate_text/canada_before_after.py "$B"

echo "== Ontario sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py ontario
mkdir -p data/dbpedia_pipeline/ontario/_old_resume
if [ -f data/dbpedia_pipeline/ontario/predications_v3.json ]; then
  mv -f data/dbpedia_pipeline/ontario/predications_v3.json \
        data/dbpedia_pipeline/ontario/_old_resume/predications_v3_before_variants_fix.json; fi
python3 scripts/step1_debate_text/extract_predications_v3.py ontario

echo "== exclusions, outcomes (with royal assent lists), audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/apply_royal_assent.py
python3 scripts/step1_debate_text/audit_review_data.py
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== HOW MUCH CHANGED since the data shown at the Sept 29 meeting"
python3 scripts/step1_debate_text/ontario_fix_report.py
echo "== DONE (the copy from before this pass is in $B)"
