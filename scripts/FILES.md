# scripts

The folders are the three steps of the current pipeline, in order: step1_debate_text, step2_parsers, step3_claims. The files directly in this folder are the first pipeline from August and September. Step 1 still uses some of them, so they stay here.

## Building the bill lists and fetching debates (Aug to Sept)

- `build_ontario_bill_index.py`: Extracts bill citations from every Ontario Hansard transcript in data/canada/ontario/. Bills are keyed by actual parliament-session (e.g.
- `build_quebec_bill_index.py`: Extracts bill mentions ("projet de loi n° X") from every CSSS committee transcript HTML file in data/canada/quebec/.
- `congressional_record_pull.py`: Pulls the full paginated list of daily Congressional Record issues from Congress.gov and saves each issue's article metadata (titles and links) to disk. This is the production version that loops through all available issues.
- `convert_ontario_api_segments_to_sentences.py`: Converts Ontario API bill segments to pipeline sentences.json format. Handles both plain string paragraphs (old format) and dict paragraphs {"text": ..., "speaker": ...} (new format with speaker info).
- `convert_quebec_segments_to_sentences.py`: Converts Quebec bill segment text files into the pipeline sentences.json format. Each segment file contains the debate text for one bill on one date. Speaker turns are extracted using the Quebec speaker pattern (M./Mme name:).
- `extract_quebec_bill_segments.py`: extract_quebec_bill_segmenkts.py
- `fetch_1989_hf.py`: Lists the Ontario health bills in the bill index that have no debate text yet.
- `fetch_missing_85.py`: For the 85 bills missing from the clean corpus, fetches their debate text by: 1. Fetching ALL Orders of the Day for each bill's index dates (no keyword filter) 2.
- `fetch_missing_ontario_bills.py`: Targeted fetch for the 55 Ontario health bills missing from the API segments. For each missing bill, tries all its dates with multiple matching strategies.
- `fetch_ontario_by_session.py`: Fetches ALL Ontario Hansard Orders of the Day content from the OLA Azure Search API, organized by parliament-session date ranges. Assigns paragraphs to health bills using two methods per David Chartash's approach:
- `fetch_ontario_hansard_via_api.py`: Key changes from previous version: - Stores topic field with each paragraph - Uses topic-to-bill matching as primary assignment method - Bill number mention as secondary verification - No single-bill fallback (was causing wrong ...
- `fetch_via_orders_notices.py`: For each missing bill, searches Orders and Notices papers to find the actual floor debate dates, then fetches Hansard text via OLA API.
- `find_correct_debate_dates.py`: For each uncertain Ontario bill, finds the correct debate dates by: 1. Checking myparliament.ca for the bill's legislative history 2. Then fetching the actual debate text from OLA API for those dates
- `rebuild_clean_ontario.py`: Rebuilds hansard_api_bill_segments.json with only verified content.

## The first claims and DBpedia pipeline (Sept)

Whole sentences sent to Spotlight. Replaced by step 3, kept because step 1 still calls some of these.

- `compute_factuality_scores.py`: Computes a factuality score per health bill from the DBpedia-annotated sentences.
- `dbpedia_batch_pipeline.py`: Implements David's scaling strategy from the July 16 meeting, verbatim from the notes: "pre-process all sentences, extract unique predicates, and query DBpedia in batch to minimize computational overhead."
- `extract_predications.py`: Stage 3 of the revised v2 pipeline (David Chartash, Sept 11 2026 meeting).
- `get_examples.py`: Pulls example sentences and claims from the September pipeline (seed 42).
- `patch_pipeline_v2.py`: Patches dbpedia_batch_pipeline.py to add extract_v2 stage.
- `run_analyses.py`: Runs all sub-analyses for US and Ontario factuality scores: 1. Logistic regression: passage ~ factuality + jurisdiction + controls 2. Government vs opposition factuality comparison 3.
- `sept24_before_after.py`: (reads the data, changes nothing)

## Checks

- `audit_ontario.py`: Audits hansard_api_bill_segments.json for wrong bill assignments. Categories: 1. Correct: assigned bill number mentioned in text 2. Wrong: text starts with "Resuming debate on Bill X" where X != assigned bill 3.
- `check_bills.py`: (reads the data, changes nothing)
- `check_days.py`: (reads only; saves nothing into data/)
- `check_ontario_bill_stages.py`: Uses myparliament.ca to check whether each missing Ontario health bill reached second reading (floor debate) or only first reading.
- `check_uncertain_topics.py`: For uncertain bill-date assignments, queries the OLA API to get the actual Hansard topic for those dates. This tells us definitively whether the paragraphs are about the right bill.

## READMEs built from the data

- `build_data_readme.py`: Generates DATA_README.md describing every significant file in the repo, organized by directory, with sizes, descriptions, what produces it, what it connects to, and access notes.
- `build_detailed_readme.py`: Builds a detailed README.md with: - Mermaid pipeline diagram - Full before/after examples at each stage - GitHub links to example files - N counts at every step - What is removed at each step
- `build_full_readme.py`: Full detailed README with mermaid diagram, real examples, prose explanations, GitHub links, OLA/assnat links.
- `build_readme.py`: Writes the project README from the data.
- `build_validation_doc.py`: Every major methodological decision is documented with: - The n at that step - What was excluded and why (with real example sentences) - What had manual review and what Joanie/David said - Where to look in the repo
