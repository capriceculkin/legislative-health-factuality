#!/bin/bash
# run_us_dedupe.sh
# A bill with several House votes (H.R. 1 in 2003 had many) reached the same debate day from
# more than one vote, and that day's text was stored once per vote: 12 bill-days, 55,160 extra
# sentences, 6,771 extra claims. us_rebuild.py now keeps each bill-day once, with the text every
# vote found for it. This re-cuts the US sections, re-extracts US claims and rebuilds the workbook.
# The audit gains two checks (B6: every sentence stored once; C3: each US bill-day listed once).
# Before running:  export GOVINFO_API_KEY=<your key>   (only used if a day is not saved yet)
# Run from the project folder (about 35 minutes, mostly re-extracting US claims):
#   caffeinate -i bash scripts/v3/run_us_dedupe.sh 2>&1 | tee outputs/audit/us_dedupe.log
set -eo pipefail
[ -n "$GOVINFO_API_KEY" ] || { echo "Run  export GOVINFO_API_KEY=<your key>  first, then this again."; exit 1; }

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_us_dedupe_$STAMP"
echo "== keeping a copy of the current US data in $B"
mkdir -p "$B"
cp data/us/v3/segments_index.json "$B/"
cp data/dbpedia_pipeline/us/sentences_v3.json data/dbpedia_pipeline/us/predications_v3.json "$B/"

echo "== US: re-cut sections, each bill-day once"
python3 scripts/v3/us_rebuild.py segment
python3 scripts/v3/us_rebuild.py verify

echo "== US sentences and claims"
python3 scripts/v3/build_sentences_v3.py us
mkdir -p data/dbpedia_pipeline/us/_old_resume
mv -f data/dbpedia_pipeline/us/predications_v3.json \
      data/dbpedia_pipeline/us/_old_resume/predications_v3_before_dedupe.json
python3 scripts/v3/extract_predications_v3.py us

echo "== exclusions, outcomes, audit, workbook"
python3 scripts/v3/apply_exclusions.py
python3 scripts/v3/outcomes_v3.py
python3 scripts/v3/audit_review_data.py
python3 scripts/v3/export_review_inputs.py
python3 scripts/v3/build_review_excel.py

echo "== checks"
python3 scripts/v3/compare_debate_days.py
python3 scripts/v3/check_us_duplicates.py
echo "== DONE (the copy from before this run is in $B)"
