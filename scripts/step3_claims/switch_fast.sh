#!/bin/bash
# switch_fast.sh   Moves the full run over to --fast --threads 1 (speed test from Nov 15), only if the check passes.
#   bash scripts/step3_claims/switch_fast.sh
# 1. stops the Quebec copy, so the check has room in memory (Ontario keeps going)
# 2. runs the 900-sentence check with --fast --threads 1
# 3. check passes: stops Ontario and starts both copies again with --fast --threads 1, each in a new Terminal window
#    check fails: starts Quebec again the normal way and leaves Ontario alone
# Finished chunks are kept either way. Everything it does is written to outputs/full/switch_fast_log.txt.
cd "$(dirname "$0")/../.." || exit 1
source venv/bin/activate
PROJ="$(pwd)"
LOG="outputs/full/switch_fast_log.txt"
say() { echo "$(date '+%H:%M:%S') $1" | tee -a "$LOG"; }

# stopping one copy: the launcher first, so it can't start the copy again, then the parse itself (same as Ctrl-C)
stop_copy() {
  pkill -KILL -f "run_full\.sh $1( |$)" 2>/dev/null
  pkill -INT -f "run_full_corpus\.py --jur $1( |$)" 2>/dev/null
  for i in $(seq 1 60); do
    pgrep -f "run_full_corpus\.py --jur $1( |$)" >/dev/null || { say "$1 stopped"; return 0; }
    sleep 2
  done
  say "$1 did not stop after 2 minutes, nothing else changed"; exit 1
}

# starting one copy in its own Terminal window
start_copy() {
  osascript -e "tell app \"Terminal\" to do script \"cd '$PROJ' && bash scripts/step3_claims/run_full.sh $*\"" >/dev/null
  say "started: run_full.sh $*"
}

say "== switch to --fast --threads 1"
stop_copy quebec

# the check, with the fast settings
OUT="outputs/full/_check/fast_check.txt"
mkdir -p outputs/full/_check
python3 scripts/step3_claims/run_full_corpus.py --check --fast --threads 1 > "$OUT" 2>&1
cat "$OUT" >> "$LOG"
tail -3 "$OUT"
parses_ok=$(grep -c "same units 900/900, same relations 900/900, same sentence trees 900/900, same unit trees 900/900" "$OUT")
claims_ok=$(grep -c "claims: 900/900 sentences give the same claims (2645 vs 2645 claims)" "$OUT")

if [ "$parses_ok" -ge 1 ] && [ "$claims_ok" -ge 1 ]; then
  say "check passed with --fast --threads 1: switching both copies"
  stop_copy ontario
  start_copy ontario --fast --threads 1
  start_copy quebec --fast --threads 1
else
  say "CHECK DID NOT PASS: Ontario left as it was, Quebec started again the normal way"
  start_copy quebec
fi
say "== done"
