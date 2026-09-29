#!/bin/bash
# run_overnight.sh
# Waits for run_us_dedupe.sh to finish, checks it ended cleanly, then runs
#   1. run_canada_fix3.sh        (Quebec re-cut, labels for the remaining missing days, bill identity
#                                 check, and what the 33 US days Congress.gov does not list really are)
#   2. find_quebec_pre1994.py    (finds the 1985-1994 Quebec debates; adds new files only)
# Start it in a second Terminal tab (Cmd+T opens one in the same folder):
#   caffeinate -i bash scripts/v3/run_overnight.sh 2>&1 | tee outputs/audit/overnight.log
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
echo "== $(date '+%H:%M') waiting for the US run to finish (checks every minute)"
while pgrep -f "run_us_dedupe.sh" >/dev/null; do sleep 60; done
if ! tail -5 outputs/audit/us_dedupe.log 2>/dev/null | grep -q "== DONE"; then
  echo "The US run did not end with == DONE in outputs/audit/us_dedupe.log, so nothing else was started."
  echo "Nothing was changed. The last lines of that log say what happened:"
  tail -15 outputs/audit/us_dedupe.log 2>/dev/null
  exit 1
fi
echo "== $(date '+%H:%M') US run finished cleanly. Canada fix 3:"
if bash scripts/v3/run_canada_fix3.sh 2>&1 | tee outputs/audit/canada_fix3.log; then
  FIX3="finished"
else
  FIX3="STOPPED WITH AN ERROR (see outputs/audit/canada_fix3.log)"
fi
echo "== $(date '+%H:%M') Quebec 1985-1994 scan:"
if python3 scripts/v3/find_quebec_pre1994.py 2>&1 | tee outputs/audit/quebec_pre1994_scan.log; then
  SCAN="finished"
else
  SCAN="STOPPED WITH AN ERROR (see outputs/audit/quebec_pre1994_scan.log)"
fi
echo "== $(date '+%H:%M') ALL DONE. Canada fix 3: $FIX3. Quebec 1985-1994 scan: $SCAN."
