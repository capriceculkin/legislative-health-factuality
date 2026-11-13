#!/bin/bash
# run_dbpedia.sh   Which claims have DBpedia concepts at their ends, why not, and the walk between them (Oct 22, 48:16 to
# 48:46). Uses the Oct 15 concept step (scripts/step2_parsers/concepts_v3.py) unchanged on the discourse-first claims in outputs/edu.
# Needs the SSH tunnel to Spotlight (ports 2222 and 2223) and the graph in ~/.kg_dump, as on Oct 15.
#   cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate && bash scripts/step3_claims/run_dbpedia.sh
#   OFFLINE=1 bash scripts/step3_claims/run_dbpedia.sh   reuses Spotlight's saved answers (outputs/dbpedia/spotlight_edu_raw.json)
set -e
R=scripts/step3_claims; O=outputs/dbpedia
mkdir -p $O docs
CDIR="${CONCEPTS_DIR:-}"
if [ -z "$CDIR" ]; then
  for c in scripts/step2_parsers "$HOME"/Desktop/next_steps/*/ "$HOME"/Desktop/next_steps/*/*/; do
    if [ -f "$c/concepts_v3.py" ] && [ -f "$c/concept_check.json" ]; then CDIR="$c"; break; fi
  done
fi
[ -n "$CDIR" ] || { echo "concepts_v3.py (with concept_check.json beside it) was not found in scripts/step2_parsers or ~/Desktop/next_steps. Run with CONCEPTS_DIR=/path/to/that/folder"; exit 1; }
echo "== 1/2 concepts and walks for every claim (concept step from $CDIR)"
python3 $R/edu_dbpedia.py $O outputs/edu/edu_reparsed.json outputs/edu/more_reparsed.json --concepts-dir "$CDIR" $( [ "${OFFLINE:-0}" = 1 ] && echo --offline )
echo "== 2/2 the check workbook (docs/dbpedia_check.xlsx)"
if [ -f $O/sense_check.csv ]; then        # the two readings of each page's sense, and the counts with only right senses
  python3 $R/edu_dbpedia_senses.py $O/edu_dbpedia.json $O/sense_check.csv $O/sense_adjusted.json --concepts-dir "$CDIR"
  python3 $R/edu_dbpedia_xlsx.py $O/edu_dbpedia.json docs/dbpedia_check.xlsx $O/sense_check.csv $O/sense_adjusted.json
else
  python3 $R/edu_dbpedia_xlsx.py $O/edu_dbpedia.json docs/dbpedia_check.xlsx
fi
echo "== done: $O/edu_dbpedia.json, $O/edu_dbpedia_summary.txt, docs/dbpedia_check.xlsx"
