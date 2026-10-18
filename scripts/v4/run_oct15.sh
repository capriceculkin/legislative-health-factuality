#!/bin/bash
# run_oct15.sh   David's Oct 8 notes, the parts still open. Reads only; writes ~/Desktop/next_steps/oct15/.
#   1. French constituency trees (Berkeley parser, benepar_fr2), so French also has all three parses
#   2. predications from all three parses together, with the discourse parse; scored against the answer key
#   3. concepts in DBpedia (institutions, common nouns, better senses) and path scores on the full graph (concepts_v3:
#      location-based country check, nouns only, French through Wikipedia language links, factual links only)
# Everything printed also goes to ~/Desktop/next_steps/oct15/run_log.txt, so the log can be attached instead of copied.
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HOME/MiscellaneousProjects/legislative-health-factuality"
[ -d "$PROJECT" ] && cd "$PROJECT"
OUT="$HOME/Desktop/next_steps/oct15"; mkdir -p "$OUT"
export OCT15_OUT="$OUT"
exec > >(tee "$OUT/run_log.txt") 2>&1
echo "== Oct 15 steps, version Oct 15e (if you do not see this line, an older copy ran)"
date
python3 -c "import numpy, scipy" 2>/dev/null || { echo "numpy or scipy is missing in $(command -v python3). Use the venv the full-graph run used. Nothing changed."; exit 1; }
rm -f "$OUT/concepts_v3.json" "$OUT/spotlight_raw.json"
echo "== 1 of 3: French constituency parse"
if python3 "$HERE/fr_setup.py"; then
  python3 "$HERE/fr_const_run.py"; rc=$?
  if [ $rc -eq 3 ]; then
    echo "   route 1 (current transformers, patched) did not work; trying route 2 (transformers 4.30.2 in a side environment)"
    SIDEPY=$(bash "$HERE/fr_side_env.sh" | tee /dev/stderr | tail -1)
    if [ -x "$SIDEPY" ]; then
      "$SIDEPY" "$HERE/fr_const_run.py" || echo "   route 2 failed too; the lines above say why. Parts 2 and 3 still run."
    else
      echo "   route 2 could not be set up; the lines above say why. Parts 2 and 3 still run."
    fi
  elif [ $rc -ne 0 ]; then
    echo "   part 1 failed; the lines above say why. Parts 2 and 3 still run."
  fi
else
  echo "   part 1 skipped; the lines above say why. French uses the two dependency parses. Parts 2 and 3 still run."
fi
echo "== 2 of 3: predications from all three parses"
python3 "$HERE/statements_v4.py" || { echo "   part 2 failed; the lines above say why. Part 3 needs it, so stopping here."; exit 1; }
echo "== 3 of 3: concepts and paths (needs the tunnel to Dunkleosteus open in another window)"
if ! python3 -c "import os, socket, urllib.parse as u; p = u.urlparse(os.environ.get('SPOTLIGHT_EN', 'http://localhost:2222/rest')); socket.create_connection((p.hostname, p.port or 80), 5)" 2>/dev/null; then
  echo "   Nothing is listening on localhost:2222, so the tunnel to Dunkleosteus is not open. Part 3 is skipped."
  echo "   Open the tunnel in another Terminal window and run the bundle again (parts 1 and 2 are quick the second time)."
else
  python3 "$HERE/concepts_v3.py" || echo "   part 3 failed; the lines above say why."
fi
echo "== DONE. Attach these files from ~/Desktop/next_steps/oct15 to the chat (run_log.txt matters most):"
ls -la "$OUT"
