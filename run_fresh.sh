#!/bin/bash
# run_fresh.sh   A fresh test: 200 sentences per legislature instead of 100. Sentences 1 to 100 are the same as now (same
# seed); 101 to 200 are new, and no rule has been written while looking at them. Runs the whole discourse-first design
# with the current rules (round 6b). About 10 minutes. Commits nothing.
#   bash run_fresh.sh
cd "$(dirname "$0")" || exit 1
[ -f venv/bin/activate ] && source venv/bin/activate
mkdir -p outputs/edu/before_fresh
cp outputs/edu/more_parses.json outputs/edu/more_reparsed.json outputs/edu/edu_trees.json outputs/edu/before_fresh/ 2>/dev/null
MORE=200 caffeinate -i bash scripts/v6/run_edu.sh 2>&1 | tee outputs/edu/run_fresh_log.txt
echo "== finished $(date)" | tee -a outputs/edu/run_fresh_log.txt
