# Step 1: debate text (was scripts/v3)

Rebuilds the debate text for every health bill in the US House, Ontario and Quebec, and cuts it into sentences (data/dbpedia_pipeline/<legislature>/sentences_v3.json). Started after the Sept 24 meeting with David and finished Oct 8. The full run in step 3 reads those sentences.

## How to run the rebuild

- `RUN_ORDER.md`: The order to run the rebuild in, with the command for each step.

## The rebuild for each legislature

These fetch the debates, find each bill's debate and write the text.

- `crec_columns.py`: Reads bound Congressional Record PDF pages (scanned images with a machine-read text layer) in true reading order, two independent ways, and checks they agree.
- `crec_ocr.py`: Second machine reading of bound Congressional Record page images with Tesseract, used to correct the GovInfo text layer word by word, conservatively.
- `fetch_official_status.py`: Downloads the official record for each predicated bill so outcomes can be checked against the legislature itself. Raw pages are cached; nothing is parsed here (outcomes_v3.py parses, so a parser fix never needs a refetch).
- `find_quebec_pre1994.py`: Quebec health bills from 1985 to 1994 (32nd to 34th legislatures) have no debate text in the data: their Assnat bill pages have no "cheminement", so the rebuild never learns which Journal des debats pages to read.
- `journal_outcomes_pre1994.py`: (reads the saved Journal pages; updates data/canada/quebec_bills/quebec_pre1994_vote_outcomes.json)
- `ontario_rebuild.py`: Rebuilds the Ontario bill-to-debate assignment from the OLA Hansard API using procedural anchors plus a per-session topic hash table (David, Sept 24: "assign by similarity of the hash table").
- `para_join.py`: (used by build_sentences_v3.py and apply_us_text_choices.py; changes no data file)
- `quebec_pre1994.py`: Quebec health bills of 1985 to 1994 (legislature 33, sessions 1 and 2; legislature 34, sessions 1 to 3).
- `quebec_rebuild.py`: Rebuilds Quebec bill segments from the Journal des debats, using each health bill's own legislative history (cheminement) as the list of debate dates and URLs.
- `us_rebuild.py`: Rebuilds US bill segments from the Congressional Record.
- `us_sections.py`: (used by us_rebuild.py segment; can also be imported on its own) ROUND6_2026_10_03
- `us_sections_cmd_segment.py`: A piece of code that patch_us_sections.py pastes into us_rebuild.py. Not run by itself.
- `us_sections_line_diff.py`: (reads only; changes nothing)
- `us_sections_report.py`: What the US section fix changed, checked two independent ways.
- `us_words.txt`: A word list used to rejoin words the Congressional Record split across lines (pa- tients becomes patients).
- `v3_common.py`: Shared helpers for the v3 rebuild scripts. Nothing in this file touches the network.

## Sentences, outcomes and claims from the rebuilt text

- `build_review_excel.py`: Review workbooks for David Chartash and Joanie Bouchard.
- `build_sentences_v3.py`: Turns the rebuilt segments into data/dbpedia_pipeline/<jurisdiction>/sentences_v3.json.
- `cleanup_leftover_text.py`: The text folders keep files from earlier runs: a rebuild writes the files of the bill-days it has now, but never deletes the file of a bill-day an earlier run had and this one does not (on Oct 3 GitHub had 1,580 Ontario files for ...
- `compute_scores_v3.py`: Per-bill factuality scores. Replaces the date-keyed join in compute_factuality_scores.py.
- `export_review_inputs.py`: One row per predicated bill in all three jurisdictions, with its official title and how much of its debate text is about health, so every bill's place on the health list can be checked against its title AND its text.
- `extract_predications_v3.py`: Bilingual version of extract_predications.py. The old script loaded one spaCy model per jurisdiction, so French sentences in Ontario were parsed by the English model ("Tout a l'heure je vous --ai--> parler", which Spotlight then ...
- `filter_questions18.py`: Removes, from the claims already extracted, every claim whose sentence is itself a question (the same rule the patched extractor now applies), so no 90-minute re-extraction is needed.
- `outcomes_v3.py`: One outcome table for all three jurisdictions, keyed by the predications' bill_key. Every outcome records its source and what it was checked against.
- `predication_demo.py`: (reads the data, changes nothing)
- `rebuild_us_index.py`: Rebuilds the US index (data/us/v3/segments_index.json) from the debate text files in data/us/v3/cr_segments_v3 and the bill plan (data/us/v3/plan.json).
- `reextract_bound.py`: Re-reads every pre-1994 (bound edition) House day from the GovInfo PDF, column by column, and replaces the old interleaved text the pipeline had used.
- `sample_official_pages.py`: Prints short samples of the official Ontario and Quebec bill pages and the Quebec debate list, so the Canada day check can be matched to their real layout. Reads only.

## Fixes applied after hand checks

Each patch or fix changed the data once, after a problem was found by reading. Their numbers follow the order they were made.

- `apply_exclusions.py`: Removes bill-days listed in data/v3_exclusions.json from the sentences and predications files, but ONLY after the bill-day is confirmed against an official record independent of our own text: US Congress.gov action list for the ...
- `apply_royal_assent.py`: (run after outcomes_v3.py; changes data/v3_outcomes.json)
- `apply_us_text_choices.py`: Decides which US sentences and claims count, from the tag us_rebuild.py segment puts on every paragraph (segments_index.json "para_tags") and the choices in data/us/v3/text_choices.json:
- `fill_heading_variants.py`: Why: after the paragraph-ID fix, one known bill-day is still short: Bill 174 (34-1) on 1988-12-15 has 135 paragraphs under its own heading in the full day, 15 in our data.
- `fill_missing_stages.py`: Why: the rebuild downloads a health bill's own debate headings only from its first to its last FIRMLY moved stage plus 45 days. A stage moved "on behalf of" the minister counts as a weak line, so it does not stretch that window.
- `fix_outcome_fix9.py`: (edits data/v3_hand_checks.json and scripts/step1_debate_text/outcomes_v3.py; keeps backups)
- `fix_sections_fix8.py`: (edits the US and Ontario section data; keeps copies; a minute)
- `patch_compute_scores_outcomes.py`: Makes compute_scores_v3.py read data/v3_outcomes.json (built by outcomes_v3.py) instead of its own outcome code, which had three bugs: - Quebec read quebec_health_bills_combined.json, which has no outcome field - US kept the LAST ...
- `patch_dbpedia_v3.py`: Two edits to scripts/dbpedia_batch_pipeline.py, stage extract_v2: 1.
- `patch_extractor.py`: (edits scripts/step1_debate_text/extract_predications_v3.py; keeps a backup)
- `patch_extractor17.py`: (edits scripts/step1_debate_text/extract_predications_v3.py; keeps a backup)
- `patch_ontario_conflicts.py`: (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)
- `patch_ontario_conflicts2.py`: (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)
- `patch_ontario_order.py`: (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)
- `patch_ontario_rowid.py`: (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)
- `patch_ontario_supplement.py`: (edits scripts/step1_debate_text/ontario_rebuild.py; keeps a backup)
- `patch_quebec_oldformat.py`: (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)
- `patch_quebec_oldformat2.py`: (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)
- `patch_quebec_oldformat3.py`: (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)
- `patch_quebec_oldformat4.py`: (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)
- `patch_quebec_verify7.py`: (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)
- `patch_sentence_joins.py`: (edits scripts/step1_debate_text/build_sentences_v3.py and scripts/step1_debate_text/apply_us_text_choices.py; keeps backups; needs scripts/step1_debate_text/para_join.py next to them)
- `patch_sheet_remove_days.py`: Edits the finished review workbooks instead of rebuilding them.
- `patch_us_ocr.py`: (edits scripts/step1_debate_text/build_sentences_v3.py, apply_us_text_choices.py, audit_review_data.py; keeps backups; needs fix10 first, and scripts/step1_debate_text/para_join.py and data/us/v3/ocr_word_fixes.json from this ...
- `patch_us_sections.py`: (edits scripts/step1_debate_text/us_rebuild.py; keeps a backup; changes no data)

## Checks, audits and tests

These read the data and report. They change nothing.

- `audit_pipeline.py`: (read only, no network, changes nothing)
- `audit_review_data.py`: Full audit of everything bill-specific before the review sheet goes to David and Joanie. Every date and link is checked by at least two independent methods.
- `audit_v3.py`: Five checks on the rebuilt sentences (sentences_v3.json), printed to the screen: fields and id format, US segments, Ontario bill keys and counts, duplicate bill and date pairs, and Ontario session format. Changes nothing.
- `check_aca.py`: Prints the size and checksum of the saved debate text for the three Affordable Care Act bills (111-HR3590, 111-HR4872, 111-HR3962) and what the US index says about them. Changes nothing.
- `check_bill2_days.py`: (reads only; a few seconds) The three Bill 2 (1985) days that grew or appeared in the fix7e run: 1985-12-17 (41 -> 781 paragraphs), 1986-05-15 (new, 60) and 1986-05-20 (new, 107).
- `check_bills.py`: (reads the data, changes nothing)
- `check_canada_changes.py`: Looks inside the sections the Canada fix added or grew, to confirm each one is its own bill's debate and did not run on into something else: QUEBEC every added or grown section: how often it names its own bill vs other bills, and ...
- `check_days.py`: (reads only; saves nothing into data/)
- `check_fix10.py`: (reads only; a few minutes)
- `check_fix11.py`: (reads only; a few minutes)
- `check_fix12.py`: Checks after Bill 149's evening sitting of December 2, 1997 was added from the page you saved: 1. every other Ontario bill-day is unchanged 2.
- `check_fix13.py`: (reads only; a few minutes)
- `check_fix14.py`: (reads only; a few minutes)
- `check_fix15.py`: (reads only; a few minutes)
- `check_fix17.py`: (reads only; a few minutes)
- `check_fix18.py`: Two different checks that only question claims were removed: A. no claim left comes from a question (the rule applied again to every claim now) B.
- `check_fix19.py`: Checks on the v19 claims that do not depend on how the parser read each sentence: A. no claim comes from a question (v18 rule) B.
- `check_fix7d.py`: (reads only; about a minute)
- `check_fix7e.py`: (reads only; about a minute)
- `check_fix7f.py`: (reads only; about a minute)
- `check_fix8.py`: (reads only; a minute or two)
- `check_fix9.py`: Checks after the Ontario rebuild with the vetted supplement: 1. every Ontario bill-day that existed before is unchanged, except 33-2 Bill 55 on 1986-07-10, which only grows 2.
- `check_links.py`: (reads the sheet, changes nothing in it) Opens every distinct link in outputs/health_bills_review.xlsx, the way a browser would, and records what each site answered.
- `check_missing_stages.py`: (reads only; no downloads; changes nothing)
- `check_open_items.py`: (reads only, about a minute)
- `check_qc_sections.py`: (reads only; about a minute)
- `check_quebec_bill_identity.py`: Checks that every Quebec bill's official page and debate links belong to that bill's own legislature.
- `check_quebec_pages.py`: Word accounting for every cached Quebec journal page. For each page it counts * the words inside <contenu> (the whole debate text of the day), * the words the old paragraph reading missed (text sitting outside any <p>), * whether ...
- `check_row_ids.py`: (reads only; 2 API requests; nothing is saved into data/)
- `check_royal_assent.py`: (reads only; changes nothing in data/)
- `check_us_duplicates.py`: 1. US bill-days listed twice in segments_index.json (two votes can point to the same debate day) 2. whether those days' sentences and claims are stored twice 3.
- `check_us_not_listed.py`: Shows what each US section is on a day Congress.gov lists no House floor action for its bill ("NOT LISTED on Congress.gov" in debate_days_vs_congress.csv): the Record headings of the section, how it was chosen, how often it names ...
- `compare_debate_days.py`: (reads only; changes nothing) For every US bill, compares the sitting days in our data with the House floor days in the bill's own Congress.gov action list (data/v3_status_cache/us/{bill}.actions.json, already downloaded).
- `compare_debate_days_canada.py`: (reads only; changes nothing) The Ontario and Quebec version of compare_debate_days.py: for every predicated bill, compares our sitting days with the debate days the legislature's own bill page lists.
- `diag_us_sections.py`: Read-only diagnostic. Part 1: why H.R. 7667's June 8, 2022 debate was not picked up. Lists every House granule on 2022-06-07/08/09 that mentions H.R. 7667 or its title.
- `diagnose_bound.py`: Explains the flagged pages and the days with no House PDF after reextract_bound.py. Run from project root:
- `diagnose_canada_days.py`: (reads only; changes nothing; no internet)
- `diagnose_canada_open.py`: (reads only; changes no data; about 3 minutes, about 60 small downloads)
- `diagnose_missing.py`: Read-only. For every bill-vote in segments_missing.json: which days were searched, how much text each day has, and whether the bill number appears in the text of any day from 4 days before to 1 day after the vote.
- `diagnose_remaining.py`: Collects the facts needed to fix the audit FAILs: 1. where compute_scores_v3.py gets outcomes 2. what Quebec outcome data exists (cheminement) 3. the real Ontario health list (bills_master.json) vs the predicated bills 4.
- `expected_fix12.json`: What check_fix12.py expects to find after fix 12.
- `expected_fix7f.json`: What check_fix7f.py expects to find after fix 7f.
- `expected_fix9.json`: What check_fix9.py expects to find after fix 9.
- `list_excluded_sections.py`: Read-only. Every section that names a US bill but was NOT used for it, with the reason, so each rule's exclusions can be checked. Prints: 1. counts by reason 2.
- `ontario_fix_report.py`: How much of the Ontario data changed between a saved copy and now: paragraphs, bill-days, sentences and claims, by Parliament and by bill, plus any change in pass/fail outcomes.
- `ontario_missing_check.py`: For each Ontario health bill that the old health list had and the rebuild gives no debate text, says why, from the rebuild's own files. Run after ontario_rebuild.py assign.
- `recheck_blocked_links.py`: Second check of every link check_links.py could not open (BLOCKED means the site refused an automated request with HTTP 403/429; it says nothing about whether the page exists). Each one is checked again by a different route:
- `test_sample.py`: Before the full run: the 100 sampled sentences are run through the old extractor (the backup) and the new one, side by side (outputs/audit/fix15_sample_side_by_side.txt).
- `test_v17.py`: Before the full run: the 1,380 sentences Claude worked the rules out on are parsed again here with spaCy and run through the patched extractor.
- `test_v3.py`: (offline; uses temporary folders; touches none of your data)

## Run scripts

Each ran one fix or one long job from start to finish.

- `push_text_folders.sh`: Puts the rebuilt text on GitHub so the links in the "Sept 24 examples: before and after" sheet open: data/canada/ontario/v3/bill_texts/ (Ontario, one file per bill-day) data/canada/quebec_assembly/v3/bill_segments_v3/ (Quebec, ...
- `run_canada_fix.sh`: Fixes the two Canada problems found by diagnose_canada_days.py, then rebuilds the Ontario and Quebec data and the review workbook.
- `run_canada_fix2.sh`: Second pass of the Canada fix, after canada_changes_check.txt: Ontario a bill only LISTED in a committee report under a non-bill heading ("Bill 176, An Act to amend the Nursing Homes Act.") no longer starts a section; a line ...
- `run_canada_fix3.sh`: (run AFTER run_us_dedupe.sh has finished) Third Canada pass: Quebec "Depot de l'amendement du depute de ..." is a heading inside a debate, not the Routine Proceedings section, so it no longer hides the bill that follows (42-1 ...
- `run_canada_fix4.sh`: Fourth Canada pass, Quebec only (Ontario data is not touched): headings 2007-2009 Journal pages mark headings only with <p align="CENTER">; the parser now reads them (38-1 Bill 1 on 2007-06-05, 39-1 Bill 7 on 2009-09-23 and 24 ...
- `run_canada_fix5.sh`: Fifth Canada pass, Quebec only (Ontario data is not touched): The title-matching fallback is turned off.
- `run_canada_fix6.sh`: Sixth Canada pass, Quebec only (Ontario data is not touched). Includes fix 5 (title fallback off). Some 2007-2009 journal pages close many paragraphs as empty tags (<p align="CENTER" />) and put the words after them.
- `run_floordays.sh`: Adds the House debate days the vote-day window missed (from each bill's Congress.gov action list), then rebuilds the US data and the review workbook.
- `run_ontario_fill.sh`: Ontario: add the debate days the rebuild missed (stages moved "on behalf of" a minister, for example Bill 50's third reading on 1993-12-08), repair unreadable raw files, then rebuild Ontario text, sentences, claims, outcomes, ...
- `run_ontario_order_fix.sh`: (about 25 minutes, no downloads) Puts Ontario paragraphs in Hansard order on pages where they all share one address (Bill 50 on 1993-12-08 started with "How much heat?" instead of the third-reading motion), fills a missing page ...
- `run_ontario_rowid_fix.sh`: Ontario: download every health bill's debate again with a paragraph ID that is really unique, then rebuild Ontario text, sentences, claims, outcomes, audit and workbook. Quebec and US are not touched.
- `run_ontario_variants_fix.sh`: Finishes the Ontario text fix after run_ontario_rowid_fix.sh. Quebec and US are not touched. 1.
- `run_overnight.sh`: Waits for run_us_dedupe.sh to finish, checks it ended cleanly, then runs 1.
- `run_us_dedupe.sh`: A bill with several House votes (H.R. 1 in 2003 had many) reached the same debate day from more than one vote, and that day's text was stored once per vote: 12 bill-days, 55,160 extra sentences, 6,771 extra claims.
- `run_us_sections_fix.sh`: (about 45 minutes; downloads only a few Assemblee pages for the Quebec check)
- `run_us_sections_fix2.sh`: (about 45 minutes, no downloads)
