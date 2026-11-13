# Where everything is

Reorganized Nov 13, 2026. The pipeline has three steps and each has its own folder under `scripts/`. Every script
folder has a `FILES.md` that lists each file with what it does.

## The pipeline, in order

1. `scripts/step1_debate_text/` (was `scripts/v3`): rebuilds the debate text for every health bill in the US House,
   Ontario and Quebec and cuts it into sentences. Started after the Sept 24 meeting with David, finished Oct 8. Its result is
   `data/dbpedia_pipeline/<legislature>/sentences_v3.json`.
2. `scripts/step2_parsers/` (was `scripts/v4`): the parsers and the DBpedia concept step, from Oct 15 to 19, working
   through David's notes from the Oct 8 meeting. Step 3 loads the parsers from here.
3. `scripts/step3_claims/` (was `scripts/v6`): discourse first, then claims, the design from the Oct 22 meeting with
   David and Joanie. The rules, the tests, the DBpedia check on the sample, and the full run. David asked on Nov 13
   for a data export at each step, which `export_steps.py` writes.

The files directly in `scripts/` are the first pipeline from August and September. Step 1 still uses some of them.

## The full run

    cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
    python3 scripts/step3_claims/run_full_corpus.py --check       # the 900 CLAY sentences must come out the same
    bash scripts/step3_claims/run_full.sh ontario                 # one window per legislature: ontario, quebec, us
    python3 scripts/step3_claims/run_full_corpus.py --status      # progress
    python3 scripts/step3_claims/run_full_corpus.py --claims      # when the parsing is finished
    python3 scripts/step3_claims/run_full_corpus.py --verify      # every sentence is there exactly once
    python3 scripts/step3_claims/export_steps.py                  # CSV files for each step, for sharing

## Folders

- `data/`: the debates and everything built from them.
  - `data/dbpedia_pipeline/<legislature>/sentences_v3.json`: the sentences the full run reads. The other files in
    those folders are from the September pipeline.
  - `data/us/`, `data/canada/`: the bill lists, the fetched debates and the rebuilt text (in the `v3` subfolders).
  - `data/parity_oct19/`: the 220 answer-key sentences with their saved parses.
  - `data/v3_*.json`: hand checks, exclusions, outcomes and title fixes from the rebuild.
  - `data/ptb_sample/`: the Penn Treebank sample. Stays off GitHub.
  - `data/politifact/`, `data/validation/`, `data/completeness_reports/`, `data/v4_sample/`: inputs and reports from
    earlier checks.
- `outputs/`: what the scripts write.
  - `outputs/full/`: the full run. Chunks per legislature, then `exports/` with the CSV files.
  - `outputs/edu/`: discourse first on the samples (the 220 answer-key sentences and the 900 CLAY sentences).
  - `outputs/dbpedia/`, `outputs/dbpedia_right/`: the DBpedia check on the sample.
  - `outputs/scores_v6b/`, `outputs/ud_eval/`, `outputs/wsj/`: test scores.
  - `outputs/audit/`, `outputs/sent_2026-09-27/` and the spreadsheets: the review of the rebuilt debate text.
- `docs/`: the CLAY deck and notes (latest versions), the check books, the workbooks and the figures.
- `notebooks/`: the analysis notebooks (factuality over time, government and opposition, COVID, JSD) and the
  discourse-first notebook.
- `figures/`: figures from the September analysis notebooks.
- `archive/`: everything moved out of the way on Nov 13. See `archive/README.md`.
- `README.md`, `DATA_README.md`, `DATABASE_README.md`: the project and data descriptions written in September.
  They describe the first pipeline.
