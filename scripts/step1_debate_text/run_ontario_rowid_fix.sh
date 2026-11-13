#!/bin/bash
# run_ontario_rowid_fix.sh
# Ontario: download every health bill's debate again with a paragraph ID that is really unique,
# then rebuild Ontario text, sentences, claims, outcomes, audit and workbook. Quebec and US are
# not touched.
#   Why: paragraphs were de-duplicated by their paraUrl, which on many 1993-1997 pages is the same
#   for a whole sitting ('.../hansard-1#'), so only one paragraph per page part was kept (Bill 50:
#   4 of 44 paragraphs on 1993-12-08, 3 of 79 on 1993-07-27). check_row_ids.py found the API's own
#   'id' field unique on 100% of rows. The download also now takes each heading with and without
#   "(CONTINUED)" and runs to 45 days after the last reading line, weak lines included.
# Run from the project folder (several hours: about 2,000 API requests at OLA_SLEEP=4):
#   caffeinate -i bash scripts/step1_debate_text/run_ontario_rowid_fix.sh 2>&1 | tee outputs/audit/ontario_rowid_fix.log
set -eo pipefail

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_ontario_rowid_fix_$STAMP"
echo "== keeping a copy of the current data in $B"
mkdir -p "$B"
cp data/canada/ontario/v3/hansard_segments_v3.json "$B/"
cp data/canada/quebec_assembly/v3/segments_index.json "$B/"
cp -R data/canada/quebec_assembly/v3/bill_segments_v3 "$B/quebec_bill_segments_v3"
cp data/dbpedia_pipeline/ontario/sentences_v3.json "$B/ontario_sentences_v3.json"
cp data/dbpedia_pipeline/ontario/predications_v3.json "$B/ontario_predications_v3.json"
cp data/v3_outcomes.json "$B/"
cp scripts/step1_debate_text/ontario_rebuild.py "$B/"

echo "== patch the rebuild: paragraph ID, headings with and without (CONTINUED), window"
python3 scripts/step1_debate_text/patch_ontario_rowid.py

echo "== move the old Ontario downloads aside (kept in $B), then download again"
mv data/canada/ontario/v3/raw "$B/raw"
if [ -d data/canada/ontario/v3/raw_official ]; then mv data/canada/ontario/v3/raw_official "$B/raw_official"; fi
export OLA_SLEEP=4
python3 scripts/step1_debate_text/ontario_rebuild.py fetch
python3 scripts/step1_debate_text/ontario_rebuild.py official-days
python3 scripts/step1_debate_text/ontario_rebuild.py assign
python3 scripts/step1_debate_text/ontario_rebuild.py verify

echo "== checks: shared IDs, Bill 50, saved full days, and 30 random bill-days against the full day"
python3 scripts/step1_debate_text/check_row_ids.py --sample 30
python3 scripts/step1_debate_text/check_missing_stages.py

echo "== what changed, bill-day by bill-day (Quebec should show no change)"
python3 scripts/step1_debate_text/canada_before_after.py "$B"

echo "== Ontario sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py ontario
mkdir -p data/dbpedia_pipeline/ontario/_old_resume
mv -f data/dbpedia_pipeline/ontario/predications_v3.json \
      data/dbpedia_pipeline/ontario/_old_resume/predications_v3_before_rowid_fix.json
python3 scripts/step1_debate_text/extract_predications_v3.py ontario

echo "== exclusions, outcomes (with royal assent lists), audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/apply_royal_assent.py
python3 scripts/step1_debate_text/audit_review_data.py
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== Bill 50 (should now show about 44 paragraphs on 1993-12-08 and 79 on 1993-07-27)"
python3 scripts/step1_debate_text/check_bills.py 35-3-Bill50
echo "== DONE (the copy from before this pass, including the old downloads, is in $B)"
