#!/bin/bash
# run_parity.sh   English-French parity check (Oct 20). Reads only; writes ~/Desktop/next_steps/oct20/.
set -o pipefail
PROJ="$HOME/MiscellaneousProjects/legislative-health-factuality"
cd "$PROJ" || { echo "Project folder not found at $PROJ. Nothing changed."; exit 1; }
if [ -f venv/bin/activate ]; then source venv/bin/activate; else echo "venv not found in $PROJ. Nothing changed."; exit 1; fi
[ -f scripts/step2_parsers/parse_corpus_v5.py ] || { echo "scripts/step2_parsers/parse_corpus_v5.py not found (pull the Oct 18 push first). Nothing changed."; exit 1; }
mkdir -p "$HOME/Desktop/next_steps/oct20"
echo "== python: $(which python3)"
python3 "$(cd "$(dirname "$0")" && pwd)/parity_collect.py" 2>&1 | tee "$HOME/Desktop/next_steps/oct20/parity_log.txt"
