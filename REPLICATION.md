# Replication Guide: Legislative Health Factuality Pipeline

This guide explains how to run the whole claim pipeline on another computer and check that every step gives the same result as the original run. It lists every command, every file each step reads and writes, how long each step takes, and what the output should look like. Written November 17, 2026, by Caprice Culkin, for Cathy Liu and anyone who replicates the work later.


## 1. What the pipeline does

The pipeline turns legislative health debate into claims. A claim is a subject, a verb and an object, such as His doctor | prescribed | the medication, marked as asserted, embedded or reported, and as negated or hedged. It covers the US House, the Ontario Legislative Assembly and the Quebec National Assembly from 1985 to 2026, in English and French.

| Step | What happens | Main script | Result |
|---|---|---|---|
| 1. Debate text and sentences | Each health bill's debate is cut into sentences, and each sentence is tagged with its language | scripts/step1_debate_text/build_sentences_v3.py | data/dbpedia_pipeline/<legislature>/sentences_v3.json |
| 2. Discourse parse and trees | Each sentence is cut into discourse units (UniRST), and each unit gets its own phrase tree (Stanza for English, the Berkeley parser for French) | scripts/step3_claims/run_full_corpus.py | outputs/full/<legislature>/parses_*.json and trees_*.json |
| 3. Claims | Subjects, verbs and objects are read from each unit's tree; discourse relations pass subjects between units and mark reported speech; 39 repair rules fix recurring errors | run_full_corpus.py --claims (runs edu_pipeline.py) | outputs/full/<legislature>/claims_*.json |
| Exports | Plain CSV files for each step, one row per sentence, unit, relation or claim | scripts/step3_claims/export_steps.py | outputs/full/exports/<legislature>/*.csv |

Linking claims to DBpedia is paused and is not part of this replication. Nothing in steps 1 to 3 uses Spotlight, DBpedia or any outside service once the models are downloaded.


## 2. What replicated means here

The pipeline uses no randomness, so the same inputs, code, package versions and models should give the same output, word for word. Replication is checked in four places:

1. **Inputs:** the input files have the same fingerprints (SHA-256) as the originals (section 5).
2. **Step 1:** the sentences rebuilt from the debate text have the same fingerprints as the originals (section 6).
3. **Steps 2 and 3 on a test set:** the 900 sentences from the CLAY talk give the same units, relations, trees and claims as the saved results (section 7).
4. **Steps 2 and 3 on the whole corpus:** every sentence gives the same units, relations and claims as the original full run (sections 8 and 9).

Parsers run on a GPU can give slightly different numbers on different chips. If any check differs, that is a finding to report, not a failure on your part: send the output to Caprice.


## 3. What you need

- **Computer:** the original run used a MacBook Pro with an Apple M4 chip and 16 GB of memory, on macOS 26.6. Another Apple silicon Mac should work. Windows and Linux have not been tried.
- **Python 3.10:** the original used Python 3.10.7. Other versions may install different packages.
- **Disk space:** about 25 GB free (about 7 GB for the full-run output, the models, and room to unzip the inputs).
- **Internet:** only for installing packages and downloading the models the first time.
- **Access:** the GitHub repository github.com/capriceculkin/legislative-health-factuality (ask Caprice to add you), and the Teams folder 04 Data for Cathy (Nov 16).
- **Time:** setup and the test-set check take an afternoon. The full run takes several days of computer time (section 8), but it runs on its own.

## 4. Set up

Open the Terminal app. Each command below is typed on one line and run from the folder named in the step.

1. **Get the code:** git clone https://github.com/capriceculkin/legislative-health-factuality.git ~/MiscellaneousProjects/legislative-health-factuality
2. **Go to the project folder:** cd ~/MiscellaneousProjects/legislative-health-factuality
3. **Make the environment with Python 3.10:** python3.10 -m venv venv
4. **Turn it on (every time you open a new Terminal window):** source venv/bin/activate
5. **Install the exact package versions:** pip install -r requirements.txt
6. **Download the Stanza models:** python3 -c "import stanza; stanza.download('en', processors='tokenize,mwt,pos,lemma,depparse,constituency'); stanza.download('fr', processors='tokenize,mwt,pos,lemma,depparse')"
7. **Record your machine and versions:** python3 scripts/step3_claims/machine_info.py

The last command writes outputs/machine.txt. Compare its package lines with the original, below. Every one of these versions must match. If one differs, install that exact version (pip install name==version) before going on.

| Package or model | Version in the original run |
|---|---|
| Python | 3.10.7 |
| spacy | 3.8.14 |
| en_core_web_lg | 3.8.0 |
| fr_core_news_lg | 3.8.0 |
| stanza | 1.15.0 |
| benepar (Berkeley parser) | 0.2.0, model benepar_fr2 |
| torch | 2.13.0 |
| transformers | 5.14.1 |
| isanlp_rst (UniRST discourse parser) | 3.2.2, model tchewik/isanlp_rst_v3, version unirst |

Two models download by themselves the first time they are used. The French Berkeley parser model (benepar_fr2) comes from the parser's GitHub releases; scripts/step2_parsers/benepar_fix.py handles the download and four known incompatibilities with newer torch and transformers. The discourse parser model comes from Hugging Face (tchewik/isanlp_rst_v3). Both need internet the first time.

The requirements file was made from the original environment on November 17 and has not yet been installed on a fresh computer. If pip cannot find a version, send Caprice the error.


## 5. Get the inputs and check their fingerprints

Some input files are too large for GitHub, so they are shared as one zip file.

1. **Download** Replication inputs (2026-11-17).zip from the Teams folder 04 Data for Cathy (Nov 16).
2. **Unzip it into the project folder, so each file lands in its place:** unzip -o "$HOME/Downloads/Replication inputs (2026-11-17).zip" -d ~/MiscellaneousProjects/legislative-health-factuality
3. **Fingerprint the files:** shasum -a 256 data/dbpedia_pipeline/*/sentences_v3.json data/canada/ontario/v3/hansard_segments_v3.json data/us/v3/segments_index.json data/canada/quebec_assembly/v3/segments_index.json data/us/v3/ocr_word_fixes.json data/canada/quebec_assembly/v3/ocr_word_fixes.json
4. **Compare** each value with the table below. The full values are in docs/replication_checksums_2026-11-17.txt, which is also inside the zip.

| File | What it is | Fingerprint starts with |
|---|---|---|
| data/dbpedia_pipeline/us/sentences_v3.json | US House sentences (338,772) | 2e48c3a9d0e4cecd |
| data/dbpedia_pipeline/ontario/sentences_v3.json | Ontario sentences (500,666) | 544d73eac843ce72 |
| data/dbpedia_pipeline/quebec/sentences_v3.json | Quebec sentences (438,007) | 4683f2f27e9d11a2 |
| data/canada/ontario/v3/hansard_segments_v3.json | Ontario debate text, paragraph by paragraph, by bill and day | 92ae454ca52681c2 |
| data/us/v3/segments_index.json | List of the US debate text files | 325377b49929f935 |
| data/canada/quebec_assembly/v3/segments_index.json | List of the Quebec debate text files | c3b384e3c52c5e85 |
| data/us/v3/ocr_word_fixes.json | Corrections for scanning errors in US text from before 1994 | 705aab591084ef5b |
| data/canada/quebec_assembly/v3/ocr_word_fixes.json | Corrections for scanning errors in Quebec text from before 1994 | b0270769b0232a2e |

The debate text files themselves (761 US files and 1,362 Quebec files) are on GitHub, in data/us/v3/cr_segments_v3/ and data/canada/quebec_assembly/v3/bill_segments_v3/.


## 6. Check step 1: rebuild the sentences

This rebuilds the three sentence files from the debate text and checks that they match the originals. It overwrites the sentence files from the zip, which is fine, since you can unzip them again.

1. **Rebuild:** python3 scripts/step1_debate_text/build_sentences_v3.py all
2. **Read the printout:** for each legislature it prints the language counts. If it says lingua is not installed, stop; the language tags would be checked one way only and could differ.
3. **Fingerprint the new files:** shasum -a 256 data/dbpedia_pipeline/*/sentences_v3.json
4. **Compare** with the first three rows of the table in section 5.

Status: this rebuild has not yet been rerun to confirm that it reproduces the original files byte for byte. If a fingerprint differs, count the sentences (python3 -c "import json; print(len(json.load(open('data/dbpedia_pipeline/us/sentences_v3.json'))))") and send Caprice the counts and the printout. Then unzip the original sentence files again before going on, so the next steps start from the same inputs.

Rebuilding the debate text itself from the original websites (the US Congressional Record, the Ontario Hansard and the Quebec Journal des débats) is described in scripts/step1_debate_text/RUN_ORDER.md, steps 2 to 5. It needs a GovInfo API key and many hours, and the sites change over time, so an exact match is not expected. It is not needed for this replication.


## 7. Check steps 2 and 3 on the 900 test sentences

This is the most important check, and it needs nothing but GitHub and the models. It parses the 900 sentences used for the CLAY talk again and compares every unit, relation, tree and claim with the saved results in outputs/edu/ (more_parses.json, edu_trees.json and more_reparsed.json, all on GitHub).

```
python3 scripts/step3_claims/run_full_corpus.py --check --fast --threads 1
```

It loads the parsers first. Read the loading lines: each one must say loaded, including loaded the Berkeley parser (benepar_fr2) and loaded the discourse parser (UniRST). If either says would not load, stop and send the output, because French claims or the discourse step would quietly change. On the original laptop every count was 900 of 900, with 2,645 claims on both sides, which the check prints in this form:

```
parses: same units 900/900, same relations 900/900, same sentence trees 900/900, same unit trees 900/900
claims: 900/900 sentences give the same claims (2645 vs 2645 claims)
```

If a number is lower than 900, the check prints the first ten sentences that differ. Copy everything it printed and send it to Caprice.


## 8. The full run

The full run parses every sentence in the pool: sentences of 8 to 60 words with an id and text, leaving out quoted bill text. Each legislature runs in its own Terminal window and restarts by itself after a crash, keeping every finished chunk of 500 sentences. The Mac is kept awake while it runs; keep it plugged in.

| Legislature | Sentences | In the pool | Chunks | Minutes per chunk (original) | About |
|---|---|---|---|---|---|
| US House | 338,772 | 268,949 | 538 | about 5 (English) | 2 days |
| Ontario | 500,666 | 415,686 | 832 | about 5 | 3 days |
| Quebec | 438,007 | 348,815 | 698 | about 8 (French) | 4 days |

1. **Count the pool first (no parsing):** python3 scripts/step3_claims/run_full_corpus.py --count. The pool sizes must match the table.
2. **Start each legislature in its own Terminal window** (cd to the project folder and source venv/bin/activate in each): bash scripts/step3_claims/run_full.sh ontario --fast --threads 1, then the same with quebec and with us. The original ran two at a time on 16 GB of memory.
3. **Check progress at any time, from another window:** python3 scripts/step3_claims/run_full_corpus.py --status
4. **When all chunks of a legislature are parsed, read the claims:** python3 scripts/step3_claims/run_full_corpus.py --claims
5. **Check that every sentence is there exactly once:** python3 scripts/step3_claims/run_full_corpus.py --verify
6. **Write the CSV exports:** python3 scripts/step3_claims/export_steps.py. The files are written to outputs/full/exports/<legislature>/.

What --fast and --threads 1 do: --fast skips work the claims never read (English lemmas and dependencies, and a second parse of one-unit sentences); on the original laptop it gave the same trees on every test sentence and the same 2,645 claims on the 900 test sentences. --threads 1 lets two or three copies run side by side; 1, 2 and 4 threads gave the same parses. The original run used both.

**The run's fingerprint:** the first run of each legislature writes outputs/full/<legislature>/input.json, which records the sentence list, the code and the package versions, and stops the run if any of them later change. Its sentence_ids_sha1 must match the original:

| Legislature | sentence_ids_sha1 in the original input.json |
|---|---|
| Ontario | ad2329e98a37a1db3ca45fd2466f09ec2622fa6d |
| Quebec | 0df58b218a8e1b035d1f13ae79995369fd1271dd |
| US House | not yet started in the original run; to be added |


## 9. Compare your run with the original

Caprice's exports are in the Teams folder 04 Data for Cathy (Nov 16). Download them so that each legislature's four CSV files sit in their own folder, named exactly ontario, quebec and us, inside one folder such as ~/Downloads/caprice_exports. Then run:

```
python3 scripts/step3_claims/compare_exports.py outputs/full/exports ~/Downloads/caprice_exports --out outputs/compare
```

It compares only the sentences both runs have finished, so it can be run before either run is complete. For every shared sentence it checks step 1 (text, language, word count), step 2 (units and relations) and step 3 (every claim, in order). It ends with RESULT: every shared sentence is the same at every step, or with the number that differ and the first ten. With --out it also writes summary.csv and differences.csv. Send Caprice both of these files.

The comparison script was tested two ways: compared with themselves, the Quebec exports (68,500 sentences) matched at every step, and against a copy with one unit and one claim changed on purpose, it found exactly those two differences.


## 10. Every file the replication uses

**Scripts, in the order they run:**

| File | What it does | Reads | Writes |
|---|---|---|---|
| scripts/step1_debate_text/build_sentences_v3.py | Cuts each bill's debate into sentences and tags each with its language | the debate text files and the files in section 5 | data/dbpedia_pipeline/<legislature>/sentences_v3.json |
| scripts/step1_debate_text/v3_common.py | Shared helpers for step 1: file paths, language detection with two detectors |  |  |
| scripts/step1_debate_text/para_join.py | Joins sentences broken across paragraphs, and applies the scanning corrections | us_words.txt, ocr_word_fixes.json |  |
| scripts/step3_claims/run_full.sh | Runs one legislature, keeps the Mac awake, restarts after a crash |  | outputs/full/log_<legislature>.txt |
| scripts/step3_claims/run_full_corpus.py | The full run in chunks: count, check, parse, status, claims, verify | sentences_v3.json | outputs/full/<legislature>/ |
| scripts/step3_claims/edu_collect.py | How each sentence and each discourse unit is parsed |  |  |
| scripts/step2_parsers/parse_corpus_v5.py | Loads the parsers (spaCy, Stanza, Berkeley, UniRST) and runs them | the models |  |
| scripts/step2_parsers/benepar_fix.py | Makes the Berkeley parser work with current torch and transformers, and downloads its French model |  |  |
| scripts/step3_claims/edu_pipeline.py | Reads the claims from the parses: units, trees, discourse relations and the repair rules | parses_*.json, trees_*.json | claims_*.json |
| scripts/step3_claims/preds.py, lexicon.py, const_fr.py, combine_lib.py | The rules: claims from trees, the paired English-French word lists, French trees |  |  |
| scripts/step3_claims/export_steps.py | Writes the CSV exports | outputs/full/<legislature>/ | outputs/full/exports/<legislature>/ |
| scripts/step3_claims/compare_exports.py | Compares two sets of exports sentence by sentence | two export folders | summary.csv, differences.csv |
| scripts/step3_claims/machine_info.py | Records the machine and package versions |  | outputs/machine.txt |

**Files the full run writes, for each legislature:**

| File | What it holds |
|---|---|
| outputs/full/<legislature>/input.json | The run's fingerprint: sentence list, chunk size, code and package versions |
| outputs/full/<legislature>/parses_00000.json and up | For each chunk of 500 sentences: the discourse units, relations and sentence trees |
| outputs/full/<legislature>/trees_00000.json and up | The phrase tree of every discourse unit |
| outputs/full/<legislature>/claims_00000.json and up | The claims read from each chunk |
| outputs/full/<legislature>/claims_rules.json | The fingerprint of the rules the claims were read with |
| outputs/full/exports/<legislature>/step1_sentences.csv | One row per sentence: id, bill, date, language, words, whether it parsed, number of units, text |
| outputs/full/exports/<legislature>/step2_units.csv | One row per discourse unit: start, end, text, number of claims |
| outputs/full/exports/<legislature>/step2_relations.csv | One row per relation between units: units, relation, parser label, main part |
| outputs/full/exports/<legislature>/step3_claims.csv | One row per claim: subject, verb, object, kind, negated, hedged, borrowed subject, how it was read |

Every file joins on sentence_id, which encodes the legislature, bill, sitting day, paragraph and sentence (for example ON|33-1-Bill7|1985-10-22|p0|s0).


## 11. If something goes wrong

- **The run stops with STOP: and does not restart:** something has to be fixed first, for example the code or a package version changed since the run began (the fingerprint in input.json no longer matches). Read the STOP line and send it to Caprice. Do not delete input.json to get around it.
- **A second copy of the same legislature will not start:** each copy leaves a lock file so two copies never work on the same chunks. Check that the first copy really stopped before starting again.
- **A parser would not load:** send the whole printout. Do not continue, because the French claims or the discourse step would change without any error.
- **The Mac went to sleep or the window closed:** run the same run_full.sh command again. Finished chunks are kept, so only the chunk that was running is redone.
- **Out of disk space:** the full run needs about 7 GB. Free space, then run the same command again.
- **Many sentences in one chunk fail:** the chunk is not saved and the run stops, so a broken parser never fills the output with empty results.

## 12. What has been checked, and how

| Item | First check | Second check | Status |
|---|---|---|---|
| Input files (section 5) | SHA-256 fingerprints made from the original files | Sentence counts match the counts recorded in the full run and the status guide | Checked two ways |
| Package versions | outputs/machine.txt from the original run | The installed package folders in the original environment | Checked two ways |
| --fast gives the same result as the normal run | Same trees on every test sentence (speed test, Nov 15) | Same 2,645 claims on the 900 test sentences | Checked two ways, on the original laptop |
| compare_exports.py | A run compared with itself matches everywhere | Two planted differences are found exactly | Checked two ways |
| Rebuilding step 1 reproduces the sentence files |  |  | Not yet checked |
| requirements.txt installs on a fresh computer |  |  | Not yet checked |
| The same output on a different Mac |  |  | This is what the replication measures |

