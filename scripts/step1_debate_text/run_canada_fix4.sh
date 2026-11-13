#!/bin/bash
# run_canada_fix4.sh
# Fourth Canada pass, Quebec only (Ontario data is not touched):
#   headings    2007-2009 Journal pages mark headings only with <p align="CENTER">; the parser now
#               reads them (38-1 Bill 1 on 2007-06-05, 39-1 Bill 7 on 2009-09-23 and 24 had no text)
#   quotes      a paragraph in quotation marks is a motion being read out; mid-sentence anchors no
#               longer start a bill there (36-1 Bill 170 took in a closure motion on 2000-12-19)
#   fallback    the title-matching fallback only looks where bills are debated (Affaires du jour and
#               the like); on 2004-10-19 it picked a new member's maiden speech for 37-1 Bill 56
# Every change is listed bill-day by bill-day in the before/after report, and the copy made first
# can be put back if anything looks wrong.
# Run from the project folder (about 25 minutes):
#   caffeinate -i bash scripts/step1_debate_text/run_canada_fix4.sh 2>&1 | tee outputs/audit/canada_fix4.log
set -eo pipefail

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
      data/dbpedia_pipeline/quebec/_old_resume/predications_v3_before_canada_fix4.json
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
echo "== the five bill-days this fix is for"
python3 -c "import json;idx=json.load(open('data/canada/quebec_assembly/v3/segments_index.json'));want={('38-1-Bill1','20070605'),('39-1-Bill7','20090923'),('39-1-Bill7','20090924'),('37-1-Bill56','20041019'),('36-1-Bill170','20001219')};got={(e['bill_key'],e['date']):e for e in idx};[print(k, (str(got[k]['n_paragraphs'])+' paragraphs, '+str(got[k]['methods'])) if k in got else 'no section') for k in sorted(want)]"
echo "== DONE (the copy from before this pass is in $B)"
