#!/bin/bash
# run_more.sh   100 new sentences from each legislature (300 in all) instead of 20, through the whole discourse-first
# design: discourse parse, a tree for every unit, the claims, a figure for every sentence, and the check books.
# The first 20 per legislature are the same sentences as before (same seed), so nothing already looked at is lost.
# Keeps the Mac awake while it runs (about 1 to 2 hours). Commits nothing.
#   bash run_more.sh
cd "$(dirname "$0")" || exit 1
[ -f venv/bin/activate ] && source venv/bin/activate
mkdir -p outputs/edu/before_more100
cp outputs/edu/more_parses.json outputs/edu/more_reparsed.json outputs/edu/edu_trees.json outputs/edu/before_more100/ 2>/dev/null
MORE=100 caffeinate -i bash scripts/v6/run_edu.sh 2>&1 | tee outputs/edu/run_more100_log.txt
echo "== finished $(date)" | tee -a outputs/edu/run_more100_log.txt
