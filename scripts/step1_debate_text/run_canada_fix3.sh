#!/bin/bash
# run_canada_fix3.sh   (run AFTER run_us_dedupe.sh has finished)
# Third Canada pass:
#   Quebec   "Depot de l'amendement du depute de ..." is a heading inside a debate, not the Routine
#            Proceedings section, so it no longer hides the bill that follows (42-1 Bill 31, 2020);
#            opposition bills whose debate opens "Que le principe du projet de loi n 898 ..." are found
#   checks   the day check marks Ontario days whose full Hansard shows no debate on the bill, and
#            Quebec official dates that fall outside the bill's legislature; a new check confirms each
#            Quebec bill's page and debate links belong to that bill
# Run from the project folder (about 25 minutes):
#   caffeinate -i bash scripts/step1_debate_text/run_canada_fix3.sh 2>&1 | tee outputs/audit/canada_fix3.log
set -eo pipefail
if pgrep -f "run_us_dedupe.sh" >/dev/null; then
  echo "run_us_dedupe.sh is still running. Start this after it prints == DONE."; exit 1
fi

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_canada_fix_$STAMP"
echo "== keeping a copy of the current Canada data in $B"
mkdir -p "$B"
cp data/canada/ontario/v3/hansard_segments_v3.json "$B/"
cp data/canada/quebec_assembly/v3/segments_index.json "$B/"
cp -R data/canada/quebec_assembly/v3/bill_segments_v3 "$B/quebec_bill_segments_v3"
cp data/dbpedia_pipeline/quebec/sentences_v3.json "$B/quebec_sentences_v3.json"
cp data/dbpedia_pipeline/quebec/predications_v3.json "$B/quebec_predications_v3.json"

echo "== Quebec: re-cut every page"
python3 scripts/step1_debate_text/quebec_rebuild.py segment
python3 scripts/step1_debate_text/quebec_rebuild.py verify

echo "== what changed, bill-day by bill-day"
python3 scripts/step1_debate_text/canada_before_after.py "$B"

echo "== Quebec sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py quebec
mkdir -p data/dbpedia_pipeline/quebec/_old_resume
mv -f data/dbpedia_pipeline/quebec/predications_v3.json \
      data/dbpedia_pipeline/quebec/_old_resume/predications_v3_before_canada_fix3.json
python3 scripts/step1_debate_text/extract_predications_v3.py quebec

echo "== exclusions, outcomes, audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/audit_review_data.py
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== what is still missing, a look inside what changed, and bill identity"
python3 scripts/step1_debate_text/compare_debate_days_canada.py
python3 scripts/step1_debate_text/diagnose_canada_days.py
python3 scripts/step1_debate_text/check_canada_changes.py "$B"
python3 scripts/step1_debate_text/check_quebec_bill_identity.py
echo "== US: what the sections on days Congress.gov does not list actually are"
python3 scripts/step1_debate_text/check_us_not_listed.py
echo "== DONE (the copy from before this pass is in $B)"
