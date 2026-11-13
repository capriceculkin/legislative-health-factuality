#!/bin/bash
# run_floordays.sh
# Adds the House debate days the vote-day window missed (from each bill's Congress.gov
# action list), then rebuilds the US data and the review workbook.
# Before running:  export GOVINFO_API_KEY=<your key>
# Run from the project folder:
#   caffeinate -i bash scripts/step1_debate_text/run_floordays.sh 2>&1 | tee outputs/audit/floordays.log
set -eo pipefail
[ -n "$GOVINFO_API_KEY" ] || { echo "Run  export GOVINFO_API_KEY=<your key>  first, then this again."; exit 1; }

echo "== keeping a copy of the files sent on 9/27"
mkdir -p outputs/sent_2026-09-27
cp outputs/health_bills_review.xlsx outputs/transcripts_us.xlsx outputs/transcripts_ontario.xlsx \
   outputs/transcripts_quebec.xlsx outputs/sent_2026-09-27/
cp data/us/v3/segments_index.json data/us/v3/segments_index_before_floordays.json

echo "== House debate days from Congress.gov"
python3 scripts/step1_debate_text/us_rebuild.py floor-days
python3 scripts/step1_debate_text/fetch_official_status.py us-bound

if [ -s data/us/v3/floor_days_bound_todo.txt ]; then
  echo "== reading the added pre-1994 days from the PDFs (the slow part)"
  python3 scripts/step1_debate_text/reextract_bound.py --ocr --only "$(cat data/us/v3/floor_days_bound_todo.txt)"
fi

echo "== rebuilding US sections, sentences and claims"
python3 scripts/step1_debate_text/us_rebuild.py segment
python3 scripts/step1_debate_text/us_rebuild.py verify
python3 scripts/step1_debate_text/build_sentences_v3.py us
mkdir -p data/dbpedia_pipeline/us/_old_resume
mv -f data/dbpedia_pipeline/us/predications_v3.json \
      data/dbpedia_pipeline/us/_old_resume/predications_v3_before_floordays.json
python3 scripts/step1_debate_text/extract_predications_v3.py us

echo "== exclusions, outcomes, audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/audit_review_data.py
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== what is still missing after the fix"
python3 scripts/step1_debate_text/compare_debate_days.py
echo "== DONE"
