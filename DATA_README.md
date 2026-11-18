# Data and Scripts Reference

> **Status, Nov 17, 2026:** Written in September for the first pipeline. Files used by the current pipeline are listed in `REPLICATION.md`.

This file describes every significant file in the repository, organized by directory.
For each file: what it contains, what produces it, what it feeds into, its size, and how to access it.

Files marked **GitHub** are tracked in version control and viewable at
github.com/capriceculkin/legislative-health-factuality

Files marked **Local only** are too large for GitHub. Access and regeneration instructions are noted.

Files marked **Yale OneDrive** are hosted at the linked URL (Yale login required).

---

## scripts/

Active pipeline scripts in alphabetical order. Archived and experimental scripts are in scripts/archive/.

### audit_ontario.py

Audits hansard_api_bill_segments.json for wrong bill assignments. Categorizes each date-section as correct (bill number in text), wrong (text opens with a different bill), or uncertain (no bill number, no clear signal). Produces a report showing which bills have contaminated paragraphs.

Reads: data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json

Writes: Prints audit report to stdout

Run: `python3 scripts/audit_ontario.py`

### build_detailed_readme.py

Generates README.md with pipeline documentation, real examples, GitHub links, and N counts at every stage.

Reads: data/canada/ontario/hansard_api_bill_segments_clean.json, data/dbpedia_pipeline/us/sentences.json, data/dbpedia_pipeline/quebec/sentences.json, data/dbpedia_pipeline/us/predications.json, data/dbpedia_pipeline/quebec/predications.json

Writes: README.md

Run: `python3 scripts/build_detailed_readme.py`

### build_ontario_bill_index.py

Builds the Ontario health bill index from Ontario Legislative Assembly records. Identifies all health bills by keyword matching against bill titles. Stores bill number, title, parliament, session, introduction date, second reading dates, vote outcome, and health_tag boolean.

Reads: data/canada/ontario/ raw vote and proceedings files

Writes: data/canada/ontario/ontario_bill_index.json

Run: `python3 scripts/build_ontario_bill_index.py`

### build_quebec_bill_index.py

Builds the Quebec health bill index from Assemblee nationale records and Cheminement legislative data. Same structure as Ontario index.

Reads: data/canada/quebec/ raw files

Writes: data/canada/quebec/quebec_bill_index.json

Run: `python3 scripts/build_quebec_bill_index.py`

### build_readme.py

Shorter README generator. Produces a summary version of README.md.

Reads: Same as build_detailed_readme.py

Writes: README.md

Run: `python3 scripts/build_readme.py`

### build_validation_doc.py

Generates the transcript division validation document showing how raw sitting-day transcripts are divided into bill-specific segments at each pipeline stage, with N counts and example text.

Reads: data/canada/ontario/hansard_api_bill_segments_clean.json, data/canada/quebec_assembly/bill_segments/, data/us/congressional_record_speeches/

Writes: data/validation/transcript_division_samples.md

Run: `python3 scripts/build_validation_doc.py`

### check_ontario_bill_stages.py

Checks each Ontario health bill's legislative stage history against myparliament.ca to verify that debate dates in the index correspond to actual floor debate and not committee or first reading.

Reads: data/canada/ontario/ontario_bill_index.json

Writes: Prints verification report to stdout

Run: `python3 scripts/check_ontario_bill_stages.py`

### check_uncertain_topics.py

For uncertain Ontario bill assignments (no bill number in text, no clear wrong signal), queries the OLA Azure Search API to get the actual Hansard topic for those dates. Determines whether the assigned topic matches the bill title.

Reads: data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json

Writes: data/canada/ontario/uncertain_topic_check.json

Run: `python3 scripts/check_uncertain_topics.py`

### compute_factuality_scores.py

Computes per-bill factuality scores from annotated sentences. Score = supported_sentences / total_claim_bearing_sentences. Joins vote outcome from bill index. Produces one score record per bill-date.

Reads: data/dbpedia_pipeline/{jurisdiction}/annotated_sentences.json, data/canada/ontario/ontario_bill_index.json

Writes: data/dbpedia_pipeline/{jurisdiction}/factuality_scores.json

Run: `JURISDICTION=us python3 scripts/compute_factuality_scores.py`

### congressional_record_pull.py

Collects US floor debate text from the GovInfo API. Queries CREC packages for health-related bills by CRS policy area. Downloads granule text, extracts House floor sections, saves one .txt file per bill-date. OCR via pytesseract for pre-1993 bound edition PDFs (CRECB).

Reads: GovInfo API at api.govinfo.gov

Writes: data/us/congressional_record_speeches/{date}.txt

Run: `python3 scripts/congressional_record_pull.py`

### convert_ontario_api_segments_to_sentences.py

Tokenizes Ontario bill-specific paragraphs into sentences. Splits on sentence boundaries using regex. Looks up party affiliation from ontario_name_party_lookup.json. Assigns speaker, party, date, and bill_key to each sentence.

Reads: data/canada/ontario/hansard_api_bill_segments_clean.json, data/canada/ontario/ontario_name_party_lookup.json

Writes: data/canada/ontario/sentences_bill_specific_api.json (669MB)

Run: `python3 scripts/convert_ontario_api_segments_to_sentences.py`

### convert_quebec_segments_to_sentences.py

Tokenizes Quebec bill segments into sentences. Reads each bill_segments .txt file, splits into sentences, assigns speaker, party, date, and bill_key from the Journal des debats attribution format.

Reads: data/canada/quebec_assembly/bill_segments/*.txt

Writes: data/dbpedia_pipeline/quebec/sentences.json

Run: `python3 scripts/convert_quebec_segments_to_sentences.py`

### dbpedia_batch_pipeline.py

Main pipeline script. Five stages selectable via command line argument: collect (copy sentences to pipeline directory), extract (v1 Spotlight on full sentences), extract_v2 (v2 Spotlight on predication subject/object strings), dedupe (remove duplicate entity pairs), query (SPARQL verification via local Virtuoso), annotate (join SPARQL results back to sentences). Run with JURISDICTION=us/ontario/quebec environment variable.

Reads: data/dbpedia_pipeline/{jurisdiction}/sentences.json or predications.json

Writes: data/dbpedia_pipeline/{jurisdiction}/triples.json, triples_v2.json, unique_pairs.json, dbpedia_results.json, annotated_sentences.json

Run: `JURISDICTION=us python3 scripts/dbpedia_batch_pipeline.py [collect|extract|extract_v2|dedupe|query|annotate]`

### extract_predications.py

V2 pipeline: extracts Subject-Verb-Object predications from sentences using spaCy dependency parsing. Finds the ROOT verb, expands its nominal subject and direct/indirect object to full noun phrases. Excludes existential roots (be, have, do), sentences with no subject or object, and entities in relative clauses. Flags hedged predicates (may, might, could, should, pourrait, devrait). Uses en_core_web_lg for English, fr_core_news_lg for French.

Reads: data/dbpedia_pipeline/{jurisdiction}/sentences.json

Writes: data/dbpedia_pipeline/{jurisdiction}/predications.json

Run: `JURISDICTION=us python3 scripts/extract_predications.py`

### extract_quebec_bill_segments.py

Extracts bill-specific text from Quebec full sitting-day transcripts using section markers. Scans each transcript for headers: Etude du projet de loi n X, Adoption du principe, Reprise du debat, Prise en consideration, Adoption. Extracts text from the marker to the next section break. Saves one .txt file per bill-date.

Reads: data/canada/quebec_assembly/YYYYMMDD.txt (full sitting-day transcripts)

Writes: data/canada/quebec_assembly/bill_segments/YYYYMMDD_billN.txt

Run: `python3 scripts/extract_quebec_bill_segments.py`

### fetch_1989_hf.py

Fetches pre-2001 Ontario Hansard content from the HuggingFace a2aj/hansard dataset for the 1989 parliament where the OLA API coverage is sparse. Filters by date and OrderofBusiness field, applies client-side bill number verification.

Reads: HuggingFace dataset a2aj/hansard, data/canada/ontario/ontario_bill_index.json

Writes: Appends to data/canada/ontario/hansard_api_bill_segments_clean.json

Run: `python3 scripts/fetch_1989_hf.py`

### fetch_missing_85.py

For the 85 Ontario bills missing from the verified clean corpus after rebuild_clean_ontario.py runs, fetches debate text by date-only filter (no keyword filter, which is broken in the API). Filters client-side to keep only paragraphs where the bill number appears in text.

Reads: data/canada/ontario/hansard_api_bill_segments_clean.json, data/canada/ontario/ontario_bill_index.json

Writes: Updates data/canada/ontario/hansard_api_bill_segments_clean.json

Run: `python3 scripts/fetch_missing_85.py`

### fetch_missing_ontario_bills.py

Targeted fetch for specific Ontario bills that are still missing after the main rescrape. Takes a list of bill keys and fetches each from the OLA API using date-based queries with client-side bill number verification.

Reads: data/canada/ontario/ontario_bill_index.json

Writes: Updates data/canada/ontario/hansard_api_bill_segments_clean.json

Run: `python3 scripts/fetch_missing_ontario_bills.py`

### fetch_ontario_hansard_via_api.py

Main Ontario Hansard scraper. Queries the OLA Azure Search API for each health bill's debate dates, filtering to Orders of the Day (both capitalizations). Stores topic field with each paragraph for verification. Assigns paragraphs to bills using bill number mention in text as primary criterion and topic keyword match as secondary. Handles rate limiting with exponential backoff. Saves checkpoint every 10 batches.

Reads: data/canada/ontario/ontario_bill_index.json, OLA Azure Search API

Writes: data/canada/ontario/hansard_api_bill_segments.json

Run: `python3 scripts/fetch_ontario_hansard_via_api.py`

### fetch_via_orders_notices.py

Supplements the OLA API scrape by fetching Orders and Notices papers (the daily House agenda) to verify which bills were actually scheduled for debate on specific dates. Used to correct wrong dates in the bill index.

Reads: OLA website Orders and Notices pages, data/canada/ontario/ontario_bill_index.json

Writes: Prints verified debate dates to stdout

Run: `python3 scripts/fetch_via_orders_notices.py`

### find_correct_debate_dates.py

For uncertain Ontario bills, queries the OLA API to find the actual dates when each bill was debated under Orders of the Day. Uses keyword search for the bill number across all dates to locate real debate dates.

Reads: data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json

Writes: data/canada/ontario/correct_debate_dates.json

Run: `python3 scripts/find_correct_debate_dates.py`

### get_examples.py

Utility script that pulls real example predications, supported/unsupported sentences, Ontario paragraphs, and factuality score samples for documentation purposes.

Reads: data/canada/ontario/hansard_api_bill_segments_clean.json, data/dbpedia_pipeline/us/predications.json, data/dbpedia_pipeline/quebec/predications.json, data/dbpedia_pipeline/us/annotated_sentences.json, data/dbpedia_pipeline/us/factuality_scores.json

Writes: Prints examples to stdout

Run: `python3 scripts/get_examples.py`

### patch_pipeline_v2.py

One-time patch script that added the extract_v2 stage to dbpedia_batch_pipeline.py. Kept for reference.

Reads: scripts/dbpedia_batch_pipeline.py

Writes: scripts/dbpedia_batch_pipeline.py (modified in place)

Run: `python3 scripts/patch_pipeline_v2.py`

### rebuild_clean_ontario.py

Rebuilds hansard_api_bill_segments_clean.json from the raw API output. Two passes: first keeps existing paragraphs where the bill number is in the text (verified). Then re-fetches bills with no verified content using OLA API keyword search, keeping only paragraphs that explicitly mention the bill number. Produces a corpus where every paragraph is verified.

Reads: data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json

Writes: data/canada/ontario/hansard_api_bill_segments_clean.json

Run: `python3 scripts/rebuild_clean_ontario.py`

### run_analyses.py

Runs all downstream analyses on factuality scores: logistic regression (factuality predicting bill passage), Jensen-Shannon divergence across jurisdictions and parties, COVID natural experiment (pre/post March 2020), era and party breakdowns. Saves figures to figures/ directory.

Reads: data/dbpedia_pipeline/us/factuality_scores.json, data/dbpedia_pipeline/ontario/factuality_scores.json, data/dbpedia_pipeline/quebec/factuality_scores.json

Writes: figures/regression_results.png, figures/jsd_distributions.png, figures/covid_comparison.png, figures/era_breakdown.png

Run: `python3 scripts/run_analyses.py`

---

## data/

### data/canada/

**Codebook.pdf** (GitHub)
Codebook for the Canadian Parliamentarian Biographies dataset (PPB.csv). Describes all fields in the biographical dataset.

**PPB.csv** (GitHub)
Canadian Parliamentarian Biographies. Harvard Dataverse dataset. Used to build member lookup tables for Ontario and Quebec party attribution.

**member_lookup.json** (GitHub)
Combined lookup table mapping member names to party affiliations for both Ontario and Quebec. Produced by build_canada_member_lookup.py.

**ontario_bill_passages.json** (GitHub)
Ontario health bill passage outcomes. Scraped from Ontario Legislative Assembly vote records. Used to join vote results to factuality scores.

**ontario_members.json** (GitHub)
Ontario MPP biographical data scraped from OLA member pages. Name, party, riding, years served.

### data/canada/ontario/

**ontario_bill_index.json** (GitHub, 1MB)
Master index of all Ontario health bills. Fields: bill_key, bill_number, title, parliament, session, health_tag, dates (floor debate dates), vote_result. Produced by build_ontario_bill_index.py. Read by almost every Ontario script.

**ontario_name_party_lookup.json** (GitHub, 72KB)
Maps MPP names to party affiliations across all parliaments 1985-2026. Used by convert_ontario_api_segments_to_sentences.py to assign party to each sentence.

**ontario_vote_index.json** (GitHub, 54KB)
Ontario vote records indexed by bill key. Includes vote date, result (passed/failed), vote counts.

**ontario_votes_proceedings.json** (GitHub, 635B)
Raw vote proceedings data scraped from Ontario Votes and Proceedings documents.

**ontario_fsob_votes.json** (GitHub, 603KB)
Ontario final bill status and vote outcomes. Supplementary to ontario_vote_index.json.

**hansard_api_bill_segments.json** (Local only, 138MB)
Raw output from fetch_ontario_hansard_via_api.py. Contains all paragraphs fetched from the OLA API including unverified assignments. 128MB. Use hansard_api_bill_segments_clean.json for analysis.

**hansard_api_bill_segments_clean.json** (Yale OneDrive, 117MB)
[Download](https://yaleedu-my.sharepoint.com/:u:/g/personal/caprice_culkin_yale_edu/IQCAGMCyyH_0ToGTWu1erpwpAV8Bcot0NVoBJZ5BJPxiTYI?e=NO1Els)
Verified bill-specific paragraphs. Every paragraph confirmed: bill number appears explicitly in text. 249 bills, 83,443 paragraphs. Produced by rebuild_clean_ontario.py. Read by convert_ontario_api_segments_to_sentences.py.

**sentences_bill_specific_api.json** (Local only, 669MB)
Ontario bill-specific sentences tokenized from hansard_api_bill_segments_clean.json. 1,942,246 sentences. Fields: sentence_id, date, text, speaker, party, bill_key. 669MB. Read by extract_predications.py.

**uncertain_topic_check.json** (Local only, 9KB)
Output of check_uncertain_topics.py. For each uncertain bill-date, stores the actual Hansard topic returned by the OLA API to determine whether the assignment is correct.

**correct_debate_dates.json** (Local only, 2B)
Output of find_correct_debate_dates.py. Stores verified correct debate dates for bills that had wrong dates in the original index.

### data/canada/quebec_assembly/

**YYYYMMDD.txt** (GitHub, 1,831 files)
Full sitting-day transcripts from assnat.qc.ca. Plain text with HTML stripped. One file per sitting day. Produced by archive/quebec_assembly_transcripts_pull.py. Read by extract_quebec_bill_segments.py.

**bill_segments/YYYYMMDD_billN.txt** (GitHub, 11,369 files)
Bill-specific text extracted from full transcripts using section markers. One file per bill-date. Produced by extract_quebec_bill_segments.py. Read by convert_quebec_segments_to_sentences.py.

### data/us/

**congressional_record_speeches/{date}.txt** (GitHub)
[Browse](https://github.com/capriceculkin/legislative-health-factuality/tree/main/data/us/congressional_record_speeches)
Floor debate text for one health bill-date. 448 files. Bill-specific by construction (GovInfo granule = one bill's floor debate). Produced by congressional_record_pull.py. Read by extract_speaker_turns_us.py (archived).

**health_bills_final_matched.csv** (GitHub)
US health bill index. Bill number, title, CRS policy area, Congress, vote date, vote outcome. Used to build the bill index and join vote results.

**us_speaker_turns.json** (Local only)
US speaker turns extracted from congressional_record_speeches. Intermediate file before sentence tokenization.

**voteview/house_rollcalls_1985_present.csv** (GitHub)
VoteView rollcall data for US House 1985 to present. Used to verify vote outcomes.

**voteview/house_members_1985_present.csv** (GitHub)
VoteView member data for US House 1985 to present. Party, state, district.

### data/dbpedia_pipeline/

Pipeline working directory. One subdirectory per jurisdiction: us/, ontario/, quebec/.
All files in this directory are local only and must be regenerated using dbpedia_batch_pipeline.py.

**{jurisdiction}/sentences.json** (Local only)
Bill-specific sentences copied from the jurisdiction's source sentences file. Input to extract_predications.py and dbpedia_batch_pipeline.py collect stage. US: 584,111 sentences. Ontario: 1,942,246. Quebec: 923,634.
Feeds into: extract_predications.py, dbpedia_batch_pipeline.py collect

**{jurisdiction}/predications.json** (Local only)
Subject-Verb-Object triples extracted from sentences by extract_predications.py. Fields: subject, verb, verb_lemma, object, hedged, negated, sentence_id, full_text. US: 215,412. Quebec: 177,952. Ontario: pending.
Feeds into: dbpedia_batch_pipeline.py extract_v2

**{jurisdiction}/triples.json** (Local only)
V1 pipeline output. Spotlight run on full sentences. Superseded by triples_v2.json but kept as reference baseline.
Feeds into: dbpedia_batch_pipeline.py dedupe (v1)

**{jurisdiction}/triples_v2.json** (Local only)
V2 pipeline output. Spotlight run on subject and object strings only. Fields: sentence_id, subject, object, verb_lemma, concept_uris, hedged. Running for US and Quebec.
Feeds into: dbpedia_batch_pipeline.py dedupe

**{jurisdiction}/unique_pairs.json** (Local only)
Deduplicated entity URI pairs. One entry per unique (URI_A, URI_B) pair across all sentences. SPARQL queried once per unique pair.
Feeds into: dbpedia_batch_pipeline.py query

**{jurisdiction}/dbpedia_results.json** (Local only)
SPARQL query results cache. One entry per unique pair. Stores supported boolean and matched predicates.
Feeds into: dbpedia_batch_pipeline.py annotate

**{jurisdiction}/annotated_sentences.json** (Local only)
Each predication annotated with supported boolean. Fields: sentence_id, supported, concept_uris, date, party, bill_key, verb.
Feeds into: compute_factuality_scores.py

**{jurisdiction}/factuality_scores.json** (Local only)
Per bill-date factuality scores. Fields: date, bill_key, score, total_sentences, supported_sentences, vote_result, party_in_power. US mean: 0.2054. Quebec mean: 0.1387. Ontario V1 mean: 0.1006.
Feeds into: run_analyses.py

### data/validation/

**transcript_division_samples.md** (GitHub)
Validation document showing how raw sitting-day transcripts are divided into bill-specific segments at each pipeline stage. Includes N counts, example text, and before/after comparisons for all three jurisdictions. Produced by build_validation_doc.py.
