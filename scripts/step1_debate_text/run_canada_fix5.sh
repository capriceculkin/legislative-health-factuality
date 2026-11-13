#!/bin/bash
# run_canada_fix5.sh
# Fifth Canada pass, Quebec only (Ontario data is not touched):
#   The title-matching fallback is turned off. It filled a listed debate day with the stretch of
#   text whose words best matched the bill's title, and every such section read by hand was about
#   something else: a maiden speech, congratulations to the new Speaker, the budget debate, the
#   Assembly's own estimates. A section now needs a heading or procedural line naming its bill.
#   The before/after report lists every section this removes, so each one can be looked at.
# Run from the project folder (about 25 minutes):
#   caffeinate -i bash scripts/step1_debate_text/run_canada_fix5.sh 2>&1 | tee outputs/audit/canada_fix5.log
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
      data/dbpedia_pipeline/quebec/_old_resume/predications_v3_before_canada_fix5.json
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
echo "== the bill-days the fallback had filled (all should now say no section)"
python3 -c "import json;idx=json.load(open('data/canada/quebec_assembly/v3/segments_index.json'));want={('38-1-Bill1','20070515'),('42-1-Bill52','20200310'),('42-1-Bill7','20190507'),('37-1-Bill56','20041019')};got={(e['bill_key'],e['date']):e for e in idx};[print(k, (str(got[k]['n_paragraphs'])+' paragraphs, '+str(got[k]['methods'])) if k in got else 'no section') for k in sorted(want)]"
python3 -c "import json;idx=json.load(open('data/canada/quebec_assembly/v3/segments_index.json'));n=[e['bill_key']+' '+e['date'] for e in idx if any(str(k).startswith('title_similarity') for k in (e.get('methods') or {}))];print('sections still made by the title fallback:', len(n), n[:10])"
echo "== DONE (the copy from before this pass is in $B)"
