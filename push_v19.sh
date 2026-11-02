#!/bin/bash
# push_v19.sh   Rounds 6 and 7 of the claim rules, 900 new sentences (300 per legislature) with a figure each, the two readings
# of every claim, and the Oct 31 files (sense check of the DBpedia concepts, the 190-sentence check book). Reruns
# run_edu.sh on the saved parses (no parsing; about 15 minutes), shows the results, and asks before it commits (as you)
# and pushes.  bash push_v19.sh   (from the project folder)
cd "$(dirname "$0")" || exit 1
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "not inside the project's git repository"; exit 1; }
[ -f venv/bin/activate ] && source venv/bin/activate
rm -rf docs/figures/_incoming
echo "== 1/3 rerunning on the saved parses with the final round 6 rules"
SKIP_PARSE=1 bash scripts/v6/run_edu.sh 2>&1 | tee outputs/edu/run_v19_log.txt
[ "${PIPESTATUS[0]}" = 0 ] || { echo "run_edu.sh stopped with an error (see outputs/edu/run_v19_log.txt); nothing was committed"; exit 1; }
echo "== 2/3 what came out"
grep -E "wrote outputs|discourse first|checks and rule tests|SVG figures" outputs/edu/run_v19_log.txt | grep -v McNemar
echo "   (expected: 900 new sentences; 111 pass, 0 fail; sample en 102/119 found, 55/119 exact; 1030 SVG figures in docs/figures/all)"
echo "== 3/3 commit and push"
for p in scripts/v6/edu_pipeline.py scripts/v6/edu_dbpedia.py scripts/v6/edu_dbpedia_xlsx.py scripts/v6/edu_dbpedia_senses.py \
         scripts/v6/edu_check_book.py scripts/v6/edu_figure_files.py scripts/v6/run_edu.sh scripts/v6/run_dbpedia.sh scripts/v6/hand_check_score.py docs/hand_check_sample.xlsx \
         outputs/edu outputs/dbpedia docs/dbpedia_check.xlsx docs/discourse_first_check_book.pdf docs/discourse_first_check_book.html \
         docs/discourse_first_check_book_all.pdf docs/discourse_first_check_book_all.html docs/figures docs/discourse_first_examples.xlsx \
         docs/discourse_first_figures.html docs/discourse_first_new_sentences.html notebooks/discourse_first.ipynb run_more.sh run_fresh.sh run_fresh2.sh push_v19.sh; do
  [ -e "$p" ] || continue
  git add -- "$p" 2>/dev/null || echo "   not added (ignored): $p"
done
git status --short -- scripts/v6 outputs docs notebooks | grep -v '^??' | head -40
echo
echo "Commit author: $(git config user.name) <$(git config user.email)>"
read -r -p "Commit these and push? Type yes: " OK
[ "$OK" = yes ] || { echo "not committed; the files are staged, so you can look and commit yourself"; exit 0; }
git commit -q -F - <<'MSG'
Claim rules rounds 6 and 7, 900 new sentences with figures, two readings of every claim

Rounds 6 and 7 (scripts/v6/edu_pipeline.py; each rule switched by an r6_, r6b_ or r7_
option) fix the mistakes two readers found most often in the new sentences: a lone
preposition taken as the object, a passive with "by" read backwards, "cannot" not carried
to a second verb joined by "and", an object after a comma or an insertion, procedural
names ("a motion to recommit"), "getting it done", a time, manner or addressee phrase
taken as the object, "Mr. Speaker" or "M. le President" taken as the subject, "make
sure", a past participle on a noun read as active, a copula without its complement, a
missing "I" right before the verb, an expletive "it" / "il faut" / "c'est" given as the
doer of an infinitive, lists read as appositions, and bare modals or false starts read
as claims. One rule was tried and left off (a to-clause done by the noun before it).

Against the keys: unchanged except English sample 102/119 found, 55/119 exact (was 103
and 56: the keys put "last year" and "here" as objects); French held-out extra lines 17
(was 19). The notebook's 111 checks pass.

outputs/edu/more_parses.json now has 300 sentences per legislature (seed 20261026; each
earlier batch unchanged), each with its figure in docs/figures/all and a page in the
check books. Two AI readers judged every claim independently. Rules were written from one
batch and measured on the next, which no rule had seen:
  sentences 101 to 200, round 6b: both readers right on 545 of 839 claims (65%, 95%
  interval 62 to 68); US House 68%, Ontario 67%, Quebec 59%
  sentences 201 to 300, round 7: 649 of 959 (68%, 65 to 71); US House 66%, Ontario 70%,
  Quebec 66%; readers agree on 94%
The readings are in outputs/edu/claim_readings_*.csv. They are AI readings, not a
person's check: docs/hand_check_sample.xlsx is a blind random sample of 120 claims (40 per
legislature) for a person to mark, and scripts/v6/hand_check_score.py compares the marks
with the readers (the readers' verdicts are kept apart in
outputs/edu/hand_check_sample_key.json).

DBpedia rerun on the current claims for the 190 sentences with saved Spotlight answers
(outputs/dbpedia): 68 of 531 claims have a concept at both ends (13%); counting only
senses both readers call right, 32 (6%), or 41 (8%) if either reader does. The same as
on the Oct 30 claims within one claim.
MSG
git log -1 --format='%h %an <%ae>%n%s'
git push
echo "== done"
