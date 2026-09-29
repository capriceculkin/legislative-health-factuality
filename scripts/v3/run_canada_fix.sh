#!/bin/bash
# run_canada_fix.sh
# Fixes the two Canada problems found by diagnose_canada_days.py, then rebuilds the
# Ontario and Quebec data and the review workbook.
#   Ontario  paragraphs filed under a non-bill heading (HOSPITAL RESTRUCTURING in Bill 149)
#            are kept only after a line that names the bill; official OLA debate and vote
#            days with no text are downloaded from the OLA API and added.
#   Quebec   the Journal parser now reads bill headings on end-of-session pages, short
#            heading lines, and split numbers ("n 3 7"); failed page downloads are retried.
# A copy of the current Canada data is kept first, and canada_before_after.txt lists every
# bill-day that changed.
# Run from the project folder (about an hour; the OLA download is the slow part):
#   caffeinate -i bash scripts/v3/run_canada_fix.sh 2>&1 | tee outputs/audit/canada_fix.log
set -eo pipefail

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_canada_fix_$STAMP"
echo "== keeping a copy of the current Canada data in $B"
mkdir -p "$B"
cp data/canada/ontario/v3/hansard_segments_v3.json "$B/"
cp data/canada/quebec_assembly/v3/segments_index.json "$B/"
cp -R data/canada/quebec_assembly/v3/bill_segments_v3 "$B/quebec_bill_segments_v3"
for j in ontario quebec; do
  cp "data/dbpedia_pipeline/$j/sentences_v3.json" "$B/${j}_sentences_v3.json"
  cp "data/dbpedia_pipeline/$j/predications_v3.json" "$B/${j}_predications_v3.json"
done

echo "== Ontario: keep non-bill-heading paragraphs only after a line naming the bill"
python3 scripts/v3/ontario_rebuild.py assign
echo "== Ontario: download official debate/vote days that have no text (OLA API)"
python3 scripts/v3/ontario_rebuild.py official-days
python3 scripts/v3/ontario_rebuild.py assign
python3 scripts/v3/ontario_rebuild.py verify

echo "== Quebec: retry failed page downloads, then re-cut every page with the fixed parser"
python3 scripts/v3/quebec_rebuild.py fetch
python3 scripts/v3/quebec_rebuild.py segment
python3 scripts/v3/quebec_rebuild.py verify

echo "== what changed, bill-day by bill-day"
python3 scripts/v3/canada_before_after.py "$B"

echo "== sentences and claims for Ontario and Quebec"
python3 scripts/v3/build_sentences_v3.py ontario
python3 scripts/v3/build_sentences_v3.py quebec
for j in ontario quebec; do
  mkdir -p "data/dbpedia_pipeline/$j/_old_resume"
  mv -f "data/dbpedia_pipeline/$j/predications_v3.json" \
        "data/dbpedia_pipeline/$j/_old_resume/predications_v3_before_canada_fix.json"
done
python3 scripts/v3/extract_predications_v3.py ontario
python3 scripts/v3/extract_predications_v3.py quebec

echo "== exclusions, outcomes, audit, workbook"
python3 scripts/v3/apply_exclusions.py
python3 scripts/v3/outcomes_v3.py
python3 scripts/v3/audit_review_data.py
python3 scripts/v3/export_review_inputs.py
python3 scripts/v3/build_review_excel.py

echo "== what is still missing, and why"
python3 scripts/v3/compare_debate_days_canada.py
python3 scripts/v3/diagnose_canada_days.py
echo "== DONE (the copy from before the fix is in $B)"
