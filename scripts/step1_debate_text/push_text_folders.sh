#!/bin/bash
# push_text_folders.sh
# Puts the rebuilt text on GitHub so the links in the "Sept 24 examples: before and after" sheet open:
#   data/canada/ontario/v3/bill_texts/            (Ontario, one file per bill-day)
#   data/canada/quebec_assembly/v3/bill_segments_v3/   (Quebec, one file per bill-day section)
#   data/us/v3/cr_segments_v3/                    (US, one file per bill-day)
#   data/dbpedia_pipeline/{ontario,quebec,us}/predications_v3.json   (claims now)
# It commits ONLY these paths (anything else you have staged or changed is left alone), pushes main,
# then checks on GitHub's copy that every file and folder the sheet links to is there.
# Files moved out of these folders (old leftovers) are removed from GitHub in the same commit.
# It stops without changing anything if: the branch is not main, GitHub has commits you don't have,
# or any file is over 95 MB (GitHub refuses files over 100 MB).
# Run:  bash ~/Downloads/push_text_folders.sh     (or wherever the file landed)

PROJECT="$HOME/MiscellaneousProjects/legislative-health-factuality"
cd "$PROJECT" 2>/dev/null || { echo "Project folder not found at $PROJECT. Nothing changed."; exit 1; }
git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "Not a git repository. Nothing changed."; exit 1; }

branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" != "main" ]; then
  echo "You are on branch '$branch', and the sheet links point at main. Nothing changed."
  echo "Switch with:  git checkout main   then run this again."
  exit 1
fi
remote=$(git remote get-url origin 2>/dev/null)
case "$remote" in
  *capriceculkin/legislative-health-factuality*) ;;
  *) echo "origin is '$remote', not capriceculkin/legislative-health-factuality. Nothing changed."; exit 1 ;;
esac

echo "== 1. Checking GitHub's copy is not ahead of yours"
git fetch -q origin main || { echo "Could not reach GitHub (git fetch failed). Nothing changed."; exit 1; }
ahead_remote=$(git rev-list --count HEAD..origin/main)
if [ "$ahead_remote" != "0" ]; then
  echo "GitHub has $ahead_remote commit(s) you don't have. Nothing changed. Send this output to Claude."
  git log --oneline HEAD..origin/main | head -10
  exit 1
fi
echo "   ok"

PATHS="data/canada/ontario/v3/bill_texts data/canada/quebec_assembly/v3/bill_segments_v3 data/us/v3/cr_segments_v3 data/dbpedia_pipeline/ontario/predications_v3.json data/dbpedia_pipeline/quebec/predications_v3.json data/dbpedia_pipeline/us/predications_v3.json"

echo "== 2. Sizes (GitHub refuses files over 100 MB)"
keep=""
for p in $PATHS; do
  if [ ! -e "$p" ]; then echo "   MISSING  $p (skipped)"; continue; fi
  n=$(find "$p" -type f | wc -l | tr -d ' ')
  total=$(du -sh "$p" | cut -f1)
  big=$(find "$p" -type f -size +95M | head -1)
  if [ -n "$big" ]; then
    echo "   TOO BIG  $p: $big is over 95 MB, so this path is skipped"
    continue
  fi
  warn=$(find "$p" -type f -size +50M | wc -l | tr -d ' ')
  note=""
  [ "$warn" != "0" ] && note="  ($warn file(s) over 50 MB: GitHub will warn but accept)"
  echo "   ok       $p: $n file(s), $total$note"
  keep="$keep $p"
done
[ -z "$keep" ] && { echo "Nothing to add. Nothing changed."; exit 1; }

echo "== 3. Adding"
for p in $keep; do
  first=$(find "$p" -type f | head -1)
  if git check-ignore -q --no-index "$p" || git check-ignore -q --no-index "$first"; then
    echo "   $p is listed in .gitignore; adding these exact files anyway (other ignored files stay ignored)"
    git add -f -- "$p"
  else
    git add -- "$p"
  fi
done
new=$(git diff --cached --name-only -- $keep | wc -l | tr -d ' ')
echo "   files new or changed in these paths: $new"
if [ "$new" = "0" ]; then
  echo "   nothing new to commit; going straight to the check"
else
  msgfile=$(mktemp)
  if [ -n "$PUSH_MESSAGE_FILE" ] && [ -s "$PUSH_MESSAGE_FILE" ]; then
    cp "$PUSH_MESSAGE_FILE" "$msgfile"
  else
  cat > "$msgfile" <<'MSG'
Rebuild: Quebec 1985-1994 debates, Ontario shared headings, US S. 974; drop old leftover files

Quebec bill-day sections now include the 1985-1994 health bills (found in the Journal des debats),
Ontario bill-day texts include debates under bill headings two bills of one session share, the US
text of S. 974 on 1986-01-30 is its own debate again, and text files left from earlier runs (not in
the current index) are removed. Claims files (predications_v3.json) rebuilt from this text.

MSG
  fi
  git commit -q -F "$msgfile" -- $keep || { echo "Commit failed. Nothing was pushed. Send this output to Claude."; rm -f "$msgfile"; exit 1; }
  rm -f "$msgfile"
  echo "   committed $(git log -1 --format='%h %s')"
  echo "== 4. Pushing"
  git push origin main || { echo "Push failed. The commit is saved locally. Send this output to Claude."; exit 1; }
fi

echo "== 5. Checking GitHub's copy has every file and folder the sheet links to"
git fetch -q origin main
miss=0
for f in \
  data/canada/ontario/v3/bill_texts/33-1-Bill94/1986-01-14.txt \
  data/canada/ontario/v3/bill_texts/33-1-Bill94/1986-01-17.txt \
  data/canada/ontario/v3/bill_texts/33-1-Bill94/1986-01-20.txt \
  data/canada/ontario/v3/bill_texts/33-2-Bill94/1986-06-02.txt \
  data/canada/ontario/v3/bill_texts/33-2-Bill94/1986-06-19.txt \
  data/canada/ontario/v3/bill_texts/33-2-Bill113/1986-07-03.txt \
  data/canada/ontario/v3/bill_texts/33-2-Bill113/1986-11-19.txt \
  data/canada/ontario/v3/bill_texts/33-2-Bill113/1986-11-27.txt \
  data/canada/ontario/v3/bill_texts/35-3-Bill50/1993-07-26.txt \
  data/canada/ontario/v3/bill_texts/35-3-Bill50/1993-12-08.txt \
  data/canada/ontario/v3/bill_texts/42-1-Bill175/2020-02-25.txt \
  data/canada/ontario/v3/bill_texts/42-1-Bill175/2020-03-02.txt \
  data/canada/ontario/v3/bill_texts/42-1-Bill175/2020-03-03.txt \
  data/canada/quebec_assembly/v3/bill_segments_v3/35-1_bill116_19951204_6585.txt \
  data/canada/quebec_assembly/v3/bill_segments_v3/42-2_bill28_20220413_323345.txt \
  data/us/v3/cr_segments_v3/109-S3546_2006-12-08.txt \
  data/us/v3/cr_segments_v3/99-HR2290_1985-06-18.txt \
  data/us/v3/cr_segments_v3/99-HR2369_1985-06-18.txt \
  data/us/v3/cr_segments_v3/99-HR2417_1985-06-18.txt \
  data/dbpedia_pipeline/ontario/predications_v3.json \
  data/dbpedia_pipeline/quebec/predications_v3.json \
  data/dbpedia_pipeline/us/predications_v3.json \
  data/canada/quebec_assembly/bill_segments/19851218_bill2.txt \
  data/canada/quebec_assembly/bill_segments/20220413_bill28.txt \
  data/us/congressional_record_speeches/1985-06-18.txt \
  data/us/congressional_record_speeches/2006-12-09-test_notes.txt \
  data/dbpedia_pipeline/ontario/predications.json \
  data/dbpedia_pipeline/quebec/predications.json \
  data/dbpedia_pipeline/us/predications.json ; do
  if git cat-file -e "origin/main:$f" 2>/dev/null; then :; else echo "   NOT ON GITHUB  $f"; miss=$((miss+1)); fi
done
for d in data/canada/ontario/v3/bill_texts data/canada/quebec_assembly/v3/bill_segments_v3 data/us/v3/cr_segments_v3 \
         data/canada/quebec_assembly/bill_segments data/us/congressional_record_speeches; do
  if [ -z "$(git ls-tree origin/main -- "$d")" ]; then echo "   FOLDER NOT ON GITHUB  $d"; miss=$((miss+1)); fi
done
echo "   linked files and folders missing on GitHub: $miss (of 34)"
echo "   Quebec Bill 2 (1985) files on GitHub now:"
git ls-tree -r --name-only origin/main -- data/canada/quebec_assembly/v3/bill_segments_v3 | grep -E "/33-1_bill2_" \
  | sed 's#^#     https://github.com/capriceculkin/legislative-health-factuality/blob/main/#' || echo "     none"
echo "== 6. File counts, your folder vs GitHub"
for d in data/canada/ontario/v3/bill_texts data/canada/quebec_assembly/v3/bill_segments_v3 data/us/v3/cr_segments_v3; do
  here=$(find "$d" -type f 2>/dev/null | wc -l | tr -d ' ')
  there=$(git ls-tree -r --name-only origin/main -- "$d" | wc -l | tr -d ' ')
  echo "   $d: here $here, GitHub $there"
done
echo "== DONE"
