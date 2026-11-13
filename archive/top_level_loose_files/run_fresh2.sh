#!/bin/bash
# run_fresh2.sh  A fresh test: 300 sentences per legislature. Sentences 1 to 200 are the same as now (same
# seed); 201 to 300 are new, and no rule has been written while looking at them. Runs the whole discourse-first design
# with the current rules (round 7). About 10 minutes. Commits nothing.
#   bash run_fresh2.sh
cd "$(dirname "$0")" || exit 1
[ -f venv/bin/activate ] && source venv/bin/activate
mkdir -p outputs/edu/before_fresh2
cp outputs/edu/more_parses.json outputs/edu/more_reparsed.json outputs/edu/edu_trees.json outputs/edu/before_fresh2/ 2>/dev/null
MORE=300 caffeinate -i bash scripts/v6/run_edu.sh 2>&1 | tee outputs/edu/run_fresh2_log.txt
echo "== finished $(date)" | tee -a outputs/edu/run_fresh2_log.txt
