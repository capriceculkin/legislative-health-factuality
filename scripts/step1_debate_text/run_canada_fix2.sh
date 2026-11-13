#!/bin/bash
# run_canada_fix2.sh
# Second pass of the Canada fix, after canada_changes_check.txt:
#   Ontario  a bill only LISTED in a committee report under a non-bill heading ("Bill 176, An Act to
#            amend the Nursing Homes Act.") no longer starts a section; a line naming another bill
#            ends the current one (the 1986-1994 committee-report "days" and Bill 208 on 1990-03-26)
#   Quebec   the chair calling the next item ("L'article 24 du feuilleton. L'Assemblee prend en
#            consideration le rapport ... projet de loi n 42") moves the text to that bill even with
#            no new heading (Bill 51 on 2009-06-18 had picked up Bills 42 and 28)
# Nothing is downloaded from Quebec again; Ontario only asks the OLA API if a new gap appears.
# Run from the project folder (about 45 minutes, mostly re-extracting claims):
#   caffeinate -i bash scripts/step1_debate_text/run_canada_fix2.sh 2>&1 | tee outputs/audit/canada_fix2.log
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

echo "== Ontario: re-assign (committee-report listings no longer start a section)"
python3 scripts/step1_debate_text/ontario_rebuild.py assign
python3 scripts/step1_debate_text/ontario_rebuild.py official-days
python3 scripts/step1_debate_text/ontario_rebuild.py assign
python3 scripts/step1_debate_text/ontario_rebuild.py verify

echo "== Quebec: re-cut every page (the chair's call of the next bill now switches bills)"
python3 scripts/step1_debate_text/quebec_rebuild.py segment
python3 scripts/step1_debate_text/quebec_rebuild.py verify

echo "== what changed, bill-day by bill-day"
python3 scripts/step1_debate_text/canada_before_after.py "$B"

echo "== sentences and claims for Ontario and Quebec"
python3 scripts/step1_debate_text/build_sentences_v3.py ontario
python3 scripts/step1_debate_text/build_sentences_v3.py quebec
for j in ontario quebec; do
  mkdir -p "data/dbpedia_pipeline/$j/_old_resume"
  mv -f "data/dbpedia_pipeline/$j/predications_v3.json" \
        "data/dbpedia_pipeline/$j/_old_resume/predications_v3_before_canada_fix2.json"
done
python3 scripts/step1_debate_text/extract_predications_v3.py ontario
python3 scripts/step1_debate_text/extract_predications_v3.py quebec

echo "== exclusions, outcomes, audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/audit_review_data.py
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== what is still missing, and a look inside what changed"
python3 scripts/step1_debate_text/compare_debate_days_canada.py
python3 scripts/step1_debate_text/diagnose_canada_days.py
python3 scripts/step1_debate_text/check_canada_changes.py "$B"
echo "== DONE (the copy from before this pass is in $B)"
