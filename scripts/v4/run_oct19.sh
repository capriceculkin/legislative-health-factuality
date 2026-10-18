#!/bin/bash
# run_oct19.sh   Overnight, before the Oct 19 meeting. Reads only; writes ~/Desktop/next_steps/oct19/.
#   1. every parser (spaCy, Stanza, the Berkeley parser for French, the discourse parser) plus the two-of-three vote on
#      300 random sentences from each jurisdiction: seconds per sentence for each tool, the projected hours for the whole
#      corpus, and the claim yield on sentences the old extractor never chose (about 30 to 90 minutes, offline)
#   2. Wikipedia text check, version 2: a sentence counts only when it mentions both ends of the claim, and the search
#      uses the claim's words and concept names (needs the internet; about 1 to 2 hours, mostly Wikipedia fetches)
# No tunnel needed. Everything printed also goes to ~/Desktop/next_steps/oct19/run_log.txt.
# The same parse script without --sample is the full-corpus run (run_full_parse.sh), for after the meeting.
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HOME/MiscellaneousProjects/legislative-health-factuality"
[ -d "$PROJECT" ] && cd "$PROJECT"
OUT="$HOME/Desktop/next_steps/oct19"; mkdir -p "$OUT"
export OCT19_OUT="$OUT"
exec > >(tee "$OUT/run_log.txt") 2>&1
echo "== Oct 19 steps, version Oct 19a (if you do not see this line, an older copy ran)"
date
python3 -c "import spacy, stanza, torch, transformers" 2>/dev/null || { echo "spacy, stanza, torch or transformers is missing in $(command -v python3). Use the venv the Oct 15 run used (source venv/bin/activate). Nothing changed."; exit 1; }
[ -f data/dbpedia_pipeline/us/sentences_v3.json ] || { echo "data/dbpedia_pipeline/us/sentences_v3.json is not here, so this is not the project folder. Nothing changed."; exit 1; }
N="${SAMPLE:-300}"
echo "== 1 of 2: timing and claim yield on $N random sentences per jurisdiction"
for j in us ontario quebec; do
  python3 "$HERE/parse_corpus_v5.py" "$j" --sample "$N" || echo "   $j: the timing run failed; the lines above say why. The next one still runs."
done
echo "== 2 of 2: Wikipedia text check v2 (both ends of the claim required)"
python3 "$HERE/text_evidence_v2.py" || echo "   the text check failed; the lines above say why."
echo "== DONE. Attach these from ~/Desktop/next_steps/oct19 to the chat: run_log.txt, timing_us.json, timing_ontario.json, timing_quebec.json, text_evidence_v2.json"
ls -la "$OUT"
