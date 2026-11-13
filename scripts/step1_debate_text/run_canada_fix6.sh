#!/bin/bash
# run_canada_fix6.sh
# Sixth Canada pass, Quebec only (Ontario data is not touched). Includes fix 5 (title fallback off).
#   Some 2007-2009 journal pages close many paragraphs as empty tags (<p align="CENTER" />) and put
#   the words after them. The parser read only what sits inside <p>, so on those pages it missed
#   every bill heading and the first paragraph of every speech (25% of the words on 2007-06-05).
#   The paragraphs are now rebuilt on those pages only. Pages where every word already sits
#   inside a <p> are not touched.
# Run from the project folder AFTER run_canada_fix5.sh has printed "== DONE" (about 25 minutes):
#   caffeinate -i bash scripts/step1_debate_text/run_canada_fix6.sh 2>&1 | tee outputs/audit/canada_fix6.log
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

echo "== every cached Quebec page: are all its words read now?"
python3 scripts/step1_debate_text/check_quebec_pages.py

echo "== Quebec: re-cut every page"
python3 scripts/step1_debate_text/quebec_rebuild.py segment
python3 scripts/step1_debate_text/quebec_rebuild.py verify

echo "== what changed, bill-day by bill-day"
python3 scripts/step1_debate_text/canada_before_after.py "$B"

echo "== Quebec sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py quebec
mkdir -p data/dbpedia_pipeline/quebec/_old_resume
mv -f data/dbpedia_pipeline/quebec/predications_v3.json \
      data/dbpedia_pipeline/quebec/_old_resume/predications_v3_before_canada_fix6.json
python3 scripts/step1_debate_text/extract_predications_v3.py quebec

echo "== exclusions, outcomes, audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/outcomes_v3.py
if [ -f data/canada/ontario/v3/royal_assent_lists.json ]; then python3 scripts/step1_debate_text/apply_royal_assent.py; else echo "royal assent lists missing: run scripts/step1_debate_text/check_royal_assent.py, then this script again"; fi
python3 scripts/step1_debate_text/audit_review_data.py
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== what is still missing, a look inside what changed, and bill identity"
python3 scripts/step1_debate_text/compare_debate_days_canada.py
python3 scripts/step1_debate_text/diagnose_canada_days.py
python3 scripts/step1_debate_text/check_canada_changes.py "$B"
python3 scripts/step1_debate_text/check_quebec_bill_identity.py
echo "== the three bill-days that had unreadable pages (all should now have a section)"
python3 -c "import json;idx=json.load(open('data/canada/quebec_assembly/v3/segments_index.json'));want={('38-1-Bill1','20070605'),('39-1-Bill7','20090923'),('39-1-Bill7','20090924')};got={(e['bill_key'],e['date']):e for e in idx};[print(k, (str(got[k]['n_paragraphs'])+' paragraphs, '+str(got[k]['methods'])) if k in got else 'no section') for k in sorted(want)]"
python3 -c "import json;idx=json.load(open('data/canada/quebec_assembly/v3/segments_index.json'));n=[e['bill_key']+' '+e['date'] for e in idx if any(str(k).startswith('title_similarity') for k in (e.get('methods') or {}))];print('sections made by the title fallback (should be 0):', len(n), n[:10])"
echo "== DONE (the copy from before this pass is in $B)"
