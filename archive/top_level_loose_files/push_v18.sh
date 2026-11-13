#!/bin/bash
# push_v18.sh   Commits (as you) and pushes what was added on Oct 31: a figure for every sentence (docs/figures/all), the
# check book for all 190 sentences, and the sense check of the DBpedia concepts. Nothing is rerun; it only commits.
#   bash push_v18.sh        (from the project folder)
cd "$(dirname "$0")" || exit 1
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "not inside the project's git repository"; exit 1; }
rm -rf docs/figures/_incoming                      # the copy of the figures as it came over (already unpacked into docs/figures/all)
for p in scripts/v6/edu_dbpedia.py scripts/v6/edu_dbpedia_xlsx.py scripts/v6/edu_dbpedia_senses.py scripts/v6/edu_check_book.py \
         scripts/v6/edu_figure_files.py scripts/v6/run_edu.sh scripts/v6/run_dbpedia.sh outputs/dbpedia docs/dbpedia_check.xlsx \
         docs/discourse_first_check_book_all.pdf docs/discourse_first_check_book_all.html docs/figures/all; do
  git add -- "$p" 2>/dev/null || echo "   not added (ignored or missing): $p"
done
git status --short -- scripts/v6 outputs/dbpedia docs | grep -v '^??'
echo
echo "Commit author: $(git config user.name) <$(git config user.email)>"
read -r -p "Commit these and push? Type yes: " OK
[ "$OK" = yes ] || { echo "not committed; the files are staged, so you can look and commit yourself"; exit 0; }
git commit -q -F - <<'MSG'
A figure for every sentence, the full check book, and a sense check of the DBpedia concepts

docs/figures/all has the tree-inside-a-tree figure (SVG and PNG) for each of the 190 real
sentences: the 100 sample sentences, the 30 held-out ones and the 60 new ones. README.md
there lists them with their text. docs/discourse_first_check_book_all.pdf is the check book
for the same 190 sentences, one per page; a page that would spill onto a second sheet now
has its figure shrunk to fit, and the sample and held-out pages show their legislature.
run_edu.sh builds both (edu_figure_files.py and edu_check_book.py take --sets).

Sense check: every distinct word and page pair the DBpedia step gave (284 in the graph)
was read twice, independently, for whether the page is what the speaker means
(outputs/dbpedia/sense_check.csv). Both readings call 175 right and 88 wrong; they
disagree or are unsure on 21. These are AI readings, not a person's check. Counting only
right senses (edu_dbpedia_senses.py), claims with both ends in DBpedia go from 69 of 534
to 32 (strict) or 41 (lenient). docs/dbpedia_check.xlsx shows both readings beside a
blank Right? column.

edu_dbpedia.py reports more but finds the same concepts: Spotlight's phrases per sentence
by language (English 6.7, French 0.9, none at all in 37 of 84 French sentences), the pages
that are not in the 2022 graph, and the one place its why-not replay disagreed with the
concept step. That place is a concept step error: in sample|57, "du gouvernement" in "du
gouvernement federal" is taken as the Government of Quebec. An end whose noun list page is
not in the graph (infirmieres -> Nurse) now says so instead of "Spotlight spotted nothing".
MSG
git log -1 --format='%h %an <%ae>%n%s'
git push
echo "== done"
