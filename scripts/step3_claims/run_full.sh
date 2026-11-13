#!/bin/bash
# run_full.sh us|ontario|quebec   The full parse for one legislature. Keeps the Mac awake, writes a log, and
# starts again by itself after a crash (finished chunks are kept). It does not start again when the script
# stops on purpose (something has to be fixed first) or when it has finished.
#   bash scripts/step3_claims/run_full.sh ontario
J="$1"
case "$J" in us|ontario|quebec) ;; *) echo "use: bash scripts/step3_claims/run_full.sh us|ontario|quebec"; exit 1;; esac
cd "$(dirname "$0")/../.." || exit 1
[ -f venv/bin/activate ] && source venv/bin/activate
mkdir -p outputs/full
LOG="outputs/full/log_$J.txt"
caffeinate -i -w $$ &          # keeps the Mac awake for as long as this script is running
tries=0
while true; do
  python3 scripts/step3_claims/run_full_corpus.py --jur "$J" 2>&1 | tee -a "$LOG"
  code=${PIPESTATUS[0]}
  if [ "$code" -eq 0 ]; then echo "== $J finished $(date)" | tee -a "$LOG"; break; fi
  if [ "$code" -eq 3 ]; then echo "== $J stopped on purpose $(date): read the STOP line above" | tee -a "$LOG"; break; fi
  tries=$((tries + 1))
  if [ "$tries" -ge 10 ]; then echo "== $J crashed $tries times, giving up $(date)" | tee -a "$LOG"; break; fi
  echo "== $J stopped with code $code, starting again in 30 seconds (try $tries) $(date)" | tee -a "$LOG"
  sleep 30
done
