#!/bin/bash
# run_us_sections_fix.sh   (about 45 minutes; downloads only a few Assemblee pages for the Quebec check)
#
# 1. A read-only check of what the next Ontario and Quebec 1985-1994 fixes need (canada_open_diag.txt).
# 2. US: text belongs to a bill only from the Record's own line that brings that bill before the House
#    (us_sections.py). Other measures' debates and procedural items come out only when two independent
#    checks agree; one-minute speeches, special orders, printed bill text, roll-call lists and vehicle
#    days are tagged, and data/us/v3/text_choices.json decides which tags count (printed text and
#    roll-call lists out; speeches and vehicle days in, pending questions 8 and 9).
#    Re-cuts the US sections, re-extracts US sentences and claims, then outcomes, audit, workbook,
#    and a before-and-after report checked against the Sept 29 hand reading and against Congress.gov.
#
# Before running:  export GOVINFO_API_KEY=<your key>   (only used if a Record day is not saved yet)
# Run from the project folder:
#   caffeinate -i bash scripts/step1_debate_text/run_us_sections_fix.sh 2>&1 | tee outputs/audit/us_sections_fix.log
set -eo pipefail
[ -n "$GOVINFO_API_KEY" ] || { echo "Run  export GOVINFO_API_KEY=<your key>  first, then this again."; exit 1; }
for f in us_sections.py us_sections_cmd_segment.py patch_us_sections.py apply_us_text_choices.py \
         us_sections_report.py diagnose_canada_open.py; do
  [ -f "scripts/step1_debate_text/$f" ] || { echo "scripts/step1_debate_text/$f is missing; move all the new files into scripts/step1_debate_text first."; exit 1; }
done

echo "== 1. Ontario and Quebec: what the next fixes need (reads only)"
python3 scripts/step1_debate_text/diagnose_canada_open.py || echo "(the check stopped early; the US fix goes on)"

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_us_sections_$STAMP"
echo "== 2. keeping a copy of the current US data in $B"
mkdir -p "$B"
cp data/us/v3/segments_index.json "$B/"
cp -R data/us/v3/cr_segments_v3 "$B/cr_segments_v3"
cp data/dbpedia_pipeline/us/sentences_v3.json data/dbpedia_pipeline/us/predications_v3.json "$B/"
cp data/v3_outcomes.json "$B/"
cp scripts/step1_debate_text/us_rebuild.py "$B/"

echo "== 3. patch and re-cut the US sections"
python3 scripts/step1_debate_text/patch_us_sections.py
rm -f data/us/v3/cr_segments_v3/*.txt          # files of bill-days that no longer exist must not linger
python3 scripts/step1_debate_text/us_rebuild.py segment
python3 scripts/step1_debate_text/us_rebuild.py verify

echo "== 4. US sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py us
mkdir -p data/dbpedia_pipeline/us/_old_resume
mv -f data/dbpedia_pipeline/us/predications_v3.json \
      data/dbpedia_pipeline/us/_old_resume/predications_v3_before_sections.json
python3 scripts/step1_debate_text/extract_predications_v3.py us

echo "== 5. exclusions, text choices, outcomes (with royal assent lists), audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/apply_us_text_choices.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/apply_royal_assent.py
python3 scripts/step1_debate_text/audit_review_data.py | grep -E "FAIL|PASS, " || true
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== 6. what changed, checked against the Sept 29 hand reading and against Congress.gov"
python3 scripts/step1_debate_text/us_sections_report.py "$B"
python3 scripts/step1_debate_text/check_us_duplicates.py
echo "== DONE (the copy from before this run is in $B)"
