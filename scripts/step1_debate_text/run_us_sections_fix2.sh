#!/bin/bash
# run_us_sections_fix2.sh   (about 45 minutes, no downloads)
#
# Second pass of the US section rule, after reading the first run's report:
#   - a House debate on a House bill that the House then passed a Senate bill in place of ("A similar
#     House bill (H.R. 1872) was laid on the table") counts for the Senate bill (tag companion) when the
#     House bill is not itself in the data; when it is, the text stays under the House bill only
#   - the debate on the rule (H. Res.) that brings a bill up is tagged rule (rule debates were left out
#     by title before; the choices file keeps them out)
#   - veto messages and override debates, the Corrections Calendar ("The Clerk called the bill"),
#     "further consideration of the bill", special orders "recognized for 60 minutes", sub-heading items
#     inside a debate ("ANNOUNCEMENT BY THE CHAIRMAN"), and speaker names like McDERMOTT and DeLAURO
#   - headings: an item title that the Record ties to another measure is that measure's (H.R. 810 vs
#     H.R. 2520); inside a scanned block the nearest heading above the text is used
#   - the Boyle-Turton omnibus: taken out only when Congress.gov shows no House debate on the bill
#   - a bill-day is kept whole only when Congress.gov lists House DEBATE that day (not a passage by
#     unanimous consent alone)
# The report compares with the data from BEFORE the first pass, and adds a check of the printed-text
# tag that does not use the tagging rule (does the text address the Chair, or read like bill text).
#
# Run from the project folder:
#   caffeinate -i bash scripts/step1_debate_text/run_us_sections_fix2.sh 2>&1 | tee outputs/audit/us_sections_fix2.log
set -eo pipefail
for f in us_sections.py us_sections_cmd_segment.py patch_us_sections.py apply_us_text_choices.py us_sections_report.py; do
  [ -f "scripts/step1_debate_text/$f" ] || { echo "scripts/step1_debate_text/$f is missing; move the new files into scripts/step1_debate_text first."; exit 1; }
done
ORIG=$(ls -d data/_before_us_sections_* 2>/dev/null | sort | head -1)
[ -n "$ORIG" ] || { echo "No copy from before the first pass (data/_before_us_sections_*) was found; nothing changed."; exit 1; }
echo "== the report will compare with the data from before the first pass: $ORIG"

STAMP=$(date +%Y%m%d-%H%M%S)
B="data/_before_us_sections2_$STAMP"
echo "== 1. keeping a copy of the current US data in $B"
mkdir -p "$B"
cp data/us/v3/segments_index.json "$B/"
cp -R data/us/v3/cr_segments_v3 "$B/cr_segments_v3"
cp data/dbpedia_pipeline/us/sentences_v3.json data/dbpedia_pipeline/us/predications_v3.json "$B/"
mv -f data/dbpedia_pipeline/us/*_set_aside*.json "$B/" 2>/dev/null || true   # they belong to the first pass
cp data/v3_outcomes.json "$B/"
cp scripts/step1_debate_text/us_rebuild.py "$B/"

echo "== 2. patch and re-cut the US sections"
python3 scripts/step1_debate_text/patch_us_sections.py
rm -f data/us/v3/cr_segments_v3/*.txt
python3 scripts/step1_debate_text/us_rebuild.py segment
python3 scripts/step1_debate_text/us_rebuild.py verify

echo "== 3. US sentences and claims"
python3 scripts/step1_debate_text/build_sentences_v3.py us
mkdir -p data/dbpedia_pipeline/us/_old_resume
mv -f data/dbpedia_pipeline/us/predications_v3.json \
      data/dbpedia_pipeline/us/_old_resume/predications_v3_before_sections2.json
python3 scripts/step1_debate_text/extract_predications_v3.py us

echo "== 4. exclusions, text choices, outcomes (with royal assent lists), audit, workbook"
python3 scripts/step1_debate_text/apply_exclusions.py
python3 scripts/step1_debate_text/apply_us_text_choices.py
python3 scripts/step1_debate_text/outcomes_v3.py
python3 scripts/step1_debate_text/apply_royal_assent.py
python3 scripts/step1_debate_text/audit_review_data.py | grep -E "FAIL|PASS, " || true
python3 scripts/step1_debate_text/export_review_inputs.py
python3 scripts/step1_debate_text/build_review_excel.py

echo "== 5. what changed since before the first pass, checked against the Sept 29 hand reading, Congress.gov, and the printed-text test"
python3 scripts/step1_debate_text/us_sections_report.py "$ORIG"
python3 scripts/step1_debate_text/check_us_duplicates.py
echo "== DONE (copies: before the first pass $ORIG; before this pass $B)"
