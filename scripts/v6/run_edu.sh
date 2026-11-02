#!/bin/bash
# run_edu.sh   Discourse first (the Oct 22 design), end to end on this Mac: the discourse parse, every discourse unit
# parsed on its own by the constituency parser, 20 new sentences per legislature, the lines, the scores, the figures and
# the notebook. About 30 to 50 minutes, most of it parsing.
#   cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate && bash scripts/v6/run_edu.sh
#   SKIP_PARSE=1 bash scripts/v6/run_edu.sh   reuses the saved unit parses (when only the rules changed; about 15 minutes)
set -e
R=scripts/v6; O=outputs/edu; D=data/parity_oct19/parity_parses.json
mkdir -p $O docs notebooks
echo "== 1/7 parse every discourse unit on its own, and 20 new sentences per legislature"
if [ "${SKIP_PARSE:-0}" = 1 ] && [ -s $O/edu_trees.json ] && [ -s $O/more_parses.json ]; then
  echo "   SKIP_PARSE=1: reusing the saved unit parses in $O/edu_trees.json and $O/more_parses.json"
else
  python3 $R/edu_collect.py --more "${MORE:-20}"
fi
echo "== 2/7 lines from each unit's own tree, connected through the discourse parse"
python3 $R/edu_pipeline.py $R $D $O/edu_reparsed.json --edu-trees $O/edu_trees.json
python3 $R/edu_pipeline.py $R $O/more_parses.json $O/more_reparsed.json --edu-trees $O/edu_trees.json
#    for comparison only (not part of the design): the same, with the whole sentence's tree allowed to fill gaps
python3 $R/edu_pipeline.py $R $D $O/edu_with_sentence_tree.json --edu-trees $O/edu_trees.json --with-sentence-tree
echo "== 3/7 scores against the answer keys"
python3 $R/edu_score.py $R $D $O/edu_reparsed.json > $O/edu_score_reparsed.txt
python3 $R/edu_score.py $R $D $O/edu_with_sentence_tree.json > $O/edu_score_with_sentence_tree.txt
grep -E "discourse first" $O/edu_score_reparsed.txt | grep -v McNemar || true
echo "== 4/7 figures (tree inside a tree)"
python3 $R/edu_figures.py $O/edu_reparsed.json docs/discourse_first_figures.html
python3 $R/edu_figures.py $O/more_reparsed.json docs/discourse_first_new_sentences.html --rows first:4
python3 $R/edu_figure_files.py docs/figures $O/edu_reparsed.json $O/more_reparsed.json
echo "== 5/7 the notebook: every step, more sentences per legislature, the data files, and the tests (about 10 minutes)"
python3 $R/build_disc_nb.py notebooks/discourse_first.ipynb --run 2> $O/notebook_log.txt || { echo "   the notebook did not run here (see $O/notebook_log.txt); writing it without outputs so it can be run in Jupyter"; python3 $R/build_disc_nb.py notebooks/discourse_first.ipynb; }
python3 -c "import json; nb=json.load(open('notebooks/discourse_first.ipynb')); open('$O/notebook_outputs.txt','w').write('\n\n'.join(''.join(o.get('text') or o.get('data',{}).get('text/plain',[])) for c in nb['cells'] if c['cell_type']=='code' for o in c['outputs']))" || true
echo "== 6/7 the workbook (docs/discourse_first_examples.xlsx)"
python3 $R/edu_xlsx.py docs/discourse_first_examples.xlsx --project . $( [ -f $O/french_misses_round5.csv ] && echo --misses $O/french_misses_round5.csv ) || echo "   the workbook was not built (see above)"
echo "== 7/7 the check book: each new sentence on its own page, with its figure and boxes to mark each claim"
python3 $R/edu_check_book.py docs/discourse_first_check_book $O/more_reparsed.json || echo "   the check book was not built (see above)"
python3 $R/edu_check_book.py docs/discourse_first_check_book_all $O/edu_reparsed.json $O/more_reparsed.json --sets sample,heldout,more || echo "   the full check book was not built (see above)"
python3 $R/edu_figure_files.py docs/figures/all $O/edu_reparsed.json $O/more_reparsed.json --sets sample,heldout,more || echo "   the figures for every sentence were not built (see above)"
echo "== done: outputs/edu/, docs/discourse_first_*.html, docs/discourse_first_check_book.pdf, docs/figures/, docs/discourse_first_examples.xlsx, notebooks/discourse_first.ipynb, $O/notebook_outputs.txt (the notebook's results as text)"
