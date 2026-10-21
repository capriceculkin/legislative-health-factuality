#!/bin/bash
# run_all.sh   Every number on the walkthrough page, recomputed from the parses saved on Oct 19. No parser runs, nothing
# outside outputs/scores_v6b/ changes. Plain python3, no packages. A few minutes.
#
#   cd ~/MiscellaneousProjects/legislative-health-factuality && bash scripts/v6/run_all.sh
#
# Writes to outputs/scores_v6b/:
#   parity_score.txt       each parser, the vote and the final lines, loose score (sample, held-out, 45 test pairs)
#   strict.txt             loose against exact, the three-slot lines against the full predications
#   compare3.txt           each parser alone against the vote: exact scores, McNemar tests, bootstrap intervals, agreement
#   walkthrough_sentences.txt    the two walked-through sentences (sample #1 and test A8, English and French), every part
#   pronouns.txt           how often a subject or object is a pronoun or a stand-in instead of a name
#   full_predications.json every full predication for all 220 sentences
#   ptb_rules.txt          the English tree rules on the Penn Treebank's own gold trees, scored against its human marks
#   dep_disagree.txt       where spaCy and Stanza disagree on the UD treebanks, and which one is right (needs ud_eval.py first)
# and prints the headline numbers to check against the page.
set -o pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
R=scripts/v6
D=data/parity_oct19/parity_parses.json
O=outputs/scores_v6b
[ -f "$D" ] || { echo "$D is missing. Run this from the project folder. Nothing changed."; exit 1; }
mkdir -p "$O"
export PYTHONDONTWRITEBYTECODE=1
t0=$(date +%s)
echo "== 1/9 paired English-French word list";  python3 $R/lexicon.py | tail -1
echo "== 2/9 loose score, every stage";          python3 $R/parity_score.py $R $D > $O/parity_score.txt || exit 1
echo "== 3/9 strict score";                      python3 $R/strict.py $R $D > $O/strict.txt || exit 1
echo "== 4/9 the three parsers compared";        python3 $R/compare3.py $R $D > $O/compare3.txt || exit 1
echo "== 5/9 the two walked-through sentences";             python3 $R/full.py $R $D --rows "sample|1,test|A8|en,test|A8|fr" > $O/walkthrough_sentences.txt || exit 1
echo "== 6/9 every full predication";            python3 $R/full.py $R $D --json $O/full_predications.json > /dev/null || exit 1
echo "== 7/9 pronouns and stand-ins in place of names";  python3 $R/pronouns.py $R $D > $O/pronouns.txt || exit 1
echo "== 8/9 tree rules on the Penn Treebank gold trees";  python3 $R/ptb_gold.py $R data/ptb_sample/combined --show 20 > $O/ptb_rules.txt || exit 1
echo "== 9/9 the two dependency parses: agree, disagree, who is right"
if [ -f outputs/ud_eval/gold_fr_gsd.conllu ]; then python3 $R/dep_disagree.py outputs/ud_eval > $O/dep_disagree.txt || exit 1; else echo "   skipped: run python3 scripts/v6/ud_eval.py first"; fi
echo
echo "== check these against the page (minutes: $(( ($(date +%s) - t0) / 60 )))"
echo "-- parallel tests (page: EN 11/11 7/7 6/6 5/5 11/12 4/4, FR all full)"
grep "by group" $O/parity_score.txt
echo "-- sample, loose (page: vote EN 108/119, FR 94/116)"
grep -A2 "^-- sample" $O/parity_score.txt | tail -2 | sed 's/   stanza.*vote/   ... vote/'
echo "-- exact, all three slots (page: sample EN 60, FR 34; held-out EN 21, FR 9)"
grep -E "^(sample|heldout) +(en|fr) +vote  " $O/compare3.txt
echo "-- Stanza alone exact (page: sample EN 63, FR 42)"
grep -E "^sample +(en|fr) +Stanza alone" $O/compare3.txt
echo "-- vote against Stanza, French exact (page: only vote 3, only stanza 11, p = 0.06)"
grep -E "^sample +fr +vote vs Stanza alone +exact" $O/compare3.txt
echo "-- Tree-first design: tree as backbone, fixed by the dependency parses (sample, exact: EN 53, FR 30; with lines added: EN 54, FR 32)"
grep -E "^sample +(en|fr) +tree" $O/compare3.txt
echo "-- subjects that are pronouns (EN 33 of 159, FR 31 of 153)"
grep -E "subjects: pronoun" $O/pronouns.txt
echo "-- The two walked-through sentences (page: recipient split 'not to themselves' / 'to others', 'result (that is why)', 'object not stated' twice)"
grep -cE "not to 'themselves' \(negated\) but to others|result \('that is why'\)|object not stated" $O/walkthrough_sentences.txt | xargs echo "   lines found (expect 4):"
echo "-- Penn Treebank, tree rules on gold trees (expect: all 9520 lines, found 74.5%, heads 65.8%, exact 52.7%)"
grep -E "^all  " $O/ptb_rules.txt
echo "== done. Outputs are in $O/"
