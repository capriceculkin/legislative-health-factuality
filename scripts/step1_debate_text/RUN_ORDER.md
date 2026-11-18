# v3 rebuild: run order

> **Status, Nov 17, 2026:** Steps 1 to 5 still describe how the debate text and sentences were rebuilt. Steps 6 and 7 (Spotlight, DBpedia and scores) belong to the September design and are not part of the current pipeline. To replicate the current pipeline, follow `REPLICATION.md` at the top of the repository.

Every command runs from the repo root with the venv active. The three jurisdictions use different sources, so steps 2, 3 and 4 can run at the same time in separate terminal tabs.

```bash
cd /Users/caprice/MiscellaneousProjects/legislative-health-factuality
source venv/bin/activate
mkdir -p scripts/step1_debate_text
unzip -o ~/Downloads/v3_rebuild.zip -d scripts/step1_debate_text
pip install requests beautifulsoup4 pdfplumber lingua-language-detector
```

## Step 1. Tests and audit (no network, about 10 minutes)

```bash
python3 scripts/step1_debate_text/test_v3.py
python3 scripts/step1_debate_text/audit_pipeline.py | tee audit_before.txt
```

The test file should end with `47 passed, 0 failed`. The audit measures every problem in the old pipeline two different ways and writes `audit_summary.csv`. That file is the evidence for David of what was wrong and how large each problem was. The audit reads the old files only, so it describes the old pipeline; the `verify` step of each rebuild is the evidence for the new one.

## Step 2. Ontario

First the probe, which sends about ten requests and decides how the rest of the run behaves:

```bash
python3 scripts/step1_debate_text/ontario_rebuild.py probe
```

Two lines matter in its output. The 1986-01-14 line should show session 33-1 both by URL and by the API field. The `anchors_jan_1986` line should contain `('1986-01-14', 'second', 94, True, 'HEALTH CARE ACCESSIBILITY ACT')`. If either is missing, stop and send me the whole probe output before running anything else.

Then the long run, which keeps the Mac awake and survives closing the terminal:

```bash
nohup caffeinate -dis sh -c 'for s in discover master fetch assign verify; do python3 scripts/step1_debate_text/ontario_rebuild.py $s || exit 1; done' > ontario_v3.log 2>&1 &
tail -f ontario_v3.log
```

Every step saves progress, so if it stops you rerun the same command and it continues where it left off. When `master` finishes, open these two files:

* `data/canada/ontario/v3/health_bills_review.csv` lists every bill flagged as health, why it was flagged, and a blank `keep_yes_no` column for Joanie and David.
* `data/canada/ontario/v3/old_health_bills_not_rediscovered.csv` lists old health bills that no procedural anchor matched, which is where to look for anything the discovery step missed.

## Step 3. Quebec

```bash
nohup caffeinate -dis python3 scripts/step1_debate_text/quebec_rebuild.py all > quebec_v3.log 2>&1 &
```

Check `data/canada/quebec_assembly/v3/segments_missing.json` and find Bill 116 on 1995-12-04 in `quebec_running_table.csv`. Health bills with no Assembly URLs in the cheminement (mostly before 1994) are listed in `health_bills_without_assembly_urls.csv`; this rebuild does not cover them and needs a separate source for those years.

## Step 4. US

```bash
export GOVINFO_API_KEY=your_key_here
nohup caffeinate -dis python3 scripts/step1_debate_text/us_rebuild.py all > us_v3.log 2>&1 &
```

In `data/us/v3/us_running_table.csv`, rows with vote date 2006-12-09 should show debate date 2006-12-08 and issue `Vol. 152, No. 135`. Bills that could not be found are in `segments_missing.json` with the number of House units available on each day searched.

For the bound edition (before 1994), open one PDF from `data/us/v3/cache/bound_pdf/` in Preview next to its extracted text in `cr_segments_v3/`. The column parser has only been tested on a synthetic three-column page so far, so this side-by-side comparison is its second check.

## Step 5. Sentences and predications

```bash
python3 scripts/step1_debate_text/build_sentences_v3.py all
caffeinate -dis python3 scripts/step1_debate_text/extract_predications_v3.py all
```

The sentence step prints the language counts per jurisdiction. If it says lingua is not installed, language was checked only one way. Before Spotlight, send Joanie 50 French predications from `data/dbpedia_pipeline/quebec/predications_v3.json` for a quick read.

## Step 6. Spotlight and DBpedia

Open the tunnel (Yale VPN on) and check both Spotlight servers:

```bash
ssh -i ~/.ssh/dunkleosteus_key -o ServerAliveInterval=60 -L 2222:localhost:2222 -L 2223:localhost:2223 -L 8890:localhost:8890 -fN cc3436@10.168.171.152
curl -s -H "Accept: application/json" "http://localhost:2222/rest/annotate?text=Medicare%20pays%20hospitals&confidence=0.35" | head -c 300; echo
curl -s -H "Accept: application/json" "http://localhost:2223/rest/annotate?text=la%20R%C3%A9gie%20de%20l%27assurance%20maladie&confidence=0.35" | head -c 300; echo
```

The Ontario query cache was truncated during a write on Sept 24. Check it and move it aside if it does not load:

```bash
python3 -c "import json; json.load(open('data/dbpedia_pipeline/ontario/dbpedia_results.json')); print('ontario cache OK')" || mv data/dbpedia_pipeline/ontario/dbpedia_results.json data/dbpedia_pipeline/ontario/dbpedia_results_corrupt.json
```

Patch the pipeline so each predication uses the Spotlight server for its own language, and swap in the v3 predications (the old files are kept as `predications_v2_backup.json`):

```bash
python3 scripts/step1_debate_text/patch_dbpedia_v3.py ontario quebec us
```

Then run the four stages per jurisdiction:

```bash
for J in us quebec ontario; do
  JURISDICTION=$J caffeinate -dis python3 scripts/dbpedia_batch_pipeline.py extract_v2 &&
  JURISDICTION=$J python3 scripts/dbpedia_batch_pipeline.py dedupe &&
  JURISDICTION=$J python3 scripts/dbpedia_batch_pipeline.py query &&
  JURISDICTION=$J python3 scripts/dbpedia_batch_pipeline.py annotate || break
done
```

## Step 7. Scores

```bash
python3 scripts/step1_debate_text/compute_scores_v3.py all
```

This writes `factuality_scores_v3.csv` per jurisdiction with both denominators side by side. Compare the supported count it prints with the count the annotate stage printed; they have to match before any score is reported.

## Step 8. Push the texts and running tables

The `github_text` column in each running table points at GitHub, so the links work once these are pushed:

```bash
git add -f scripts/step1_debate_text data/canada/ontario/v3/bill_texts data/canada/ontario/v3/*.csv \
  data/canada/quebec_assembly/v3/bill_segments_v3 data/canada/quebec_assembly/v3/*.csv \
  data/us/v3/cr_segments_v3 data/us/v3/*.csv audit_summary.csv
git commit -m "v3 rebuild: URL-based Ontario sessions with anchor and heading-hash assignment, cheminement-driven Quebec segments, daily-edition US segments, per-sentence language routing"
git push
```

The three running tables are the table David asked for: one row per bill and debate date with session, dates, the procedural evidence, the Hansard or Journal or GovInfo link, the GitHub text link, and an excerpt. Every row is written by a script from the data. They can be imported straight into Google Sheets.

## What has been checked, and how

| Item | Method 1 | Method 2 | Status |
|---|---|---|---|
| Ontario 33-1 ends Feb 12 1986, 33-2 starts Apr 22 1986 | Archived OLA Hansard index | York University archive (the API session field agrees as a third source) | Verified two ways |
| Ontario assignment | Procedural anchor on that date, from the separate discovery queries | Reading dates in the FSOB file | Two ways if the FSOB file has dates; the verify step says so explicitly if it does not |
| Quebec segments | Text names its own bill | Debate is listed in the bill's cheminement (coverage) | Two ways |
| US segments | Text names its own bill | Printed Record date equals the debate date used | Two ways |
| Language labels | Function-word and accent counts | lingua model | Two ways only with lingua installed |
| US column parser | Synthetic three-column PDF test | Your side-by-side check of one real page | One way until step 4 |
| All v1 and v2 scores | | | Unconfirmed; nothing from before this rebuild should be reported |
