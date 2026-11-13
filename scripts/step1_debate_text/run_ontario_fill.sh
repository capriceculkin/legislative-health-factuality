#!/bin/bash
# run_ontario_fill.sh
# Ontario: add the debate days the rebuild missed (stages moved "on behalf of" a minister,
# for example Bill 50's third reading on 1993-12-08), repair unreadable raw files, then
# rebuild Ontario text, sentences, claims, outcomes, audit and workbook. Quebec is not touched.
# Run from the project folder:
#   caffeinate -i bash scripts/step1_debate_text/run_ontario_fill.sh 2>&1 | tee outputs/audit/ontario_fill.log
set -eo pipefail

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_ontario_fill_$STAMP"
echo "== keeping a copy of the current data in $B"
mkdir -p "$B"
cp data/canada/ontario/v3/hansard_segments_v3.json "$B/"
cp data/canada/quebec_assembly/v3/segments_index.json "$B/"
cp -R data/canada/quebec_assembly/v3/bill_segments_v3 "$B/quebec_bill_segments_v3"
cp data/dbpedia_pipeline/ontario/sentences_v3.json "$B/ontario_sentences_v3.json"
cp data/dbpedia_pipeline/ontario/predications_v3.json "$B/ontario_predications_v3.json"
cp data/v3_outcomes.json "$B/"

echo "== before: reading days not fully covered"
python3 scripts/step1_debate_text/check_missing_stages.py

echo "== Ontario: download the missed days and repair unreadable raw files"
python3 scripts/step1_debate_text/fill_missing_stages.py --apply
python3 scripts/step1_debate_text/ontario_rebuild.py assign
python3 scripts/step1_debate_text/ontario_rebuild.py verify

echo "== after: reading days not fully covered"
python3 scripts/step1_debate_text/check_missing_stages.py

echo "== what changed, bill-day by bill-day (Quebec should show no change)"
python3 scripts/step1_debate_text/canada_before_after.py "$B"

echo "== Ontario sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py ontario
mkdir -p data/dbpedia_pipeline/ontario/_old_resume
mv -f data/dbpedia_pipeline/ontario/predications_v3.json \
      data/dbpedia_pipeline/ontario/_old_resume/predications_v3_before_ontario_fill.json
python3 scripts/step1_debate_text/extract_predications_v3.py ontario

echo "== exclusions, outcomes (with royal assent lists), audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/apply_royal_assent.py
python3 scripts/step1_debate_text/audit_review_data.py
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== Bill 50 on 1993-12-08 (should now be about 44 paragraphs, with the third-reading motion)"
python3 scripts/step1_debate_text/check_bills.py 35-3-Bill50
echo "== the royal assent lists behind the other two study bills now marked passed (33-3-Bill79, 34-2-Bill208)"
python3 scripts/step1_debate_text/check_days.py 1987-06-29:79 1990-06-25:208 | grep -A 3 "paragraphs that name" || true
echo "== DONE (the copy from before this pass is in $B)"
