#!/bin/bash
# run_full_parse.sh   The whole corpus through the three parses, the two-of-three vote and the discourse re-read.
# For after the Oct 19 meeting. Writes data/dbpedia_pipeline/{us,ontario,quebec}/statements_v5.jsonl, one line per
# sentence, as it goes. Stopping it loses nothing: run it again and it continues from the last line written.
# It takes days on the laptop; the timing run (run_oct19.sh) says how many. Keep the Mac awake: this script runs
# under caffeinate, but close the lid and it stops; run it again when the Mac is open.
#   bash ~/.oct19_files/run_full_parse.sh                  one jurisdiction after another: us, ontario, quebec
#   ONLY=quebec bash ~/.oct19_files/run_full_parse.sh      one jurisdiction
#   RST=none bash ~/.oct19_files/run_full_parse.sh         skip the discourse parse (stated/embedded from the syntax)
#   PARALLEL=1 bash ~/.oct19_files/run_full_parse.sh       all three at once (only on a Mac with 32 GB or more)
# Progress at any time:   wc -l data/dbpedia_pipeline/*/statements_v5.jsonl
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HOME/MiscellaneousProjects/legislative-health-factuality"
[ -d "$PROJECT" ] && cd "$PROJECT"
[ -f data/dbpedia_pipeline/us/sentences_v3.json ] || { echo "not the project folder. Nothing changed."; exit 1; }
mkdir -p outputs/audit
RST="${RST:-multi}"
LIST="${ONLY:-us ontario quebec}"
if [ "$PARALLEL" = "1" ]; then
  export PARSE_THREADS="${PARSE_THREADS:-3}"
  for j in $LIST; do
    nohup caffeinate -i python3 "$HERE/parse_corpus_v5.py" "$j" --rst "$RST" >> "outputs/audit/parse_v5_$j.log" 2>&1 &
    echo "started $j (log: outputs/audit/parse_v5_$j.log)"
  done
  wait
else
  for j in $LIST; do
    caffeinate -i python3 "$HERE/parse_corpus_v5.py" "$j" --rst "$RST" 2>&1 | tee -a "outputs/audit/parse_v5_$j.log"
  done
fi
echo "== lines written so far:"
wc -l data/dbpedia_pipeline/*/statements_v5.jsonl
