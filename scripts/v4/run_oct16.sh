#!/bin/bash
# run_oct16.sh   Two other groups' methods, tried on our data. Reads only; writes ~/Desktop/next_steps/oct16/.
#   1. relation-aware path score (KL-REL, Shiralkar et al. 2017) next to the current one (KL), on the 300 judged facts
#      and the debate statements. Offline; uses the graph in ~/.kg_dump. About 30 to 60 minutes.
#   2. Wikipedia text check with a multilingual inference model (mDeBERTa-v3, NLI), on the same facts and statements.
#      Needs the internet (Wikipedia, and the model download from Hugging Face once, about 1.1 GB). About 15 to 30 minutes.
# No tunnel needed. Everything printed also goes to ~/Desktop/next_steps/oct16/run_log.txt.
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HOME/MiscellaneousProjects/legislative-health-factuality"
[ -d "$PROJECT" ] && cd "$PROJECT"
OUT="$HOME/Desktop/next_steps/oct16"; mkdir -p "$OUT"
export OCT16_OUT="$OUT"
exec > >(tee "$OUT/run_log.txt") 2>&1
echo "== Oct 16 steps, version Oct 16a (if you do not see this line, an older copy ran)"
date
python3 -c "import numpy, scipy, spacy" 2>/dev/null || { echo "numpy, scipy or spacy is missing in $(command -v python3). Use the venv the earlier runs used. Nothing changed."; exit 1; }
cd "$HERE"
echo "== 1 of 2: relation-aware path score"
python3 "$HERE/rel_linker.py" || echo "   part 1 failed; the lines above say why. Part 2 still runs."
echo "== 2 of 2: Wikipedia text check"
if python3 -c "import torch, transformers, sentencepiece" 2>/dev/null; then
  python3 "$HERE/text_evidence.py" || echo "   part 2 failed; the lines above say why."
else
  echo "   torch, transformers or sentencepiece is missing in $(command -v python3); part 2 is skipped."
fi
echo "== DONE. Attach these files from ~/Desktop/next_steps/oct16 to the chat:"
ls -la "$OUT"
