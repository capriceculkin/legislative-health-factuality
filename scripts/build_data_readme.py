"""
build_data_readme.py
Generates DATA_README.md describing every significant file in the repo,
organized by directory, with sizes, descriptions, what produces it,
what it connects to, and access notes.
"""
import os, json, subprocess

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
OUT = f"{REPO}/DATA_README.md"
GH = "https://github.com/capriceculkin/legislative-health-factuality/blob/main"
ONEDRIVE = "https://yaleedu-my.sharepoint.com/:u:/g/personal/caprice_culkin_yale_edu/IQCAGMCyyH_0ToGTWu1erpwpAV8Bcot0NVoBJZ5BJPxiTYI?e=NO1Els"

def sz(path):
    full = f"{REPO}/{path}"
    if not os.path.exists(full): return "not found"
    s = os.path.getsize(full)
    for unit in ["B","KB","MB","GB"]:
        if s < 1024: return f"{s:.0f}{unit}"
        s /= 1024
    return f"{s:.1f}GB"

def on_github(path):
    result = subprocess.run(
        ["git","ls-files","--error-unmatch", path],
        cwd=REPO, capture_output=True
    )
    return result.returncode == 0

lines = []
def w(s=""): lines.append(s)

w("# Data and Scripts Reference")
w()
w("This file describes every significant file in the repository, organized by directory.")
w("For each file: what it contains, what produces it, what it feeds into, its size, and how to access it.")
w()
w("Files marked **GitHub** are tracked in version control and viewable at")
w("github.com/capriceculkin/legislative-health-factuality")
w()
w("Files marked **Local only** are too large for GitHub. Access and regeneration instructions are noted.")
w()
w("Files marked **Yale OneDrive** are hosted at the linked URL (Yale login required).")
w()

# ── SCRIPTS ──────────────────────────────────────────────────────────────────
w("---")
w()
w("## scripts/")
w()
w("Active pipeline scripts in alphabetical order. Archived and experimental scripts are in scripts/archive/.")
w()

scripts = {
    "audit_ontario.py": {
        "desc": "Audits hansard_api_bill_segments.json for wrong bill assignments. Categorizes each date-section as correct (bill number in text), wrong (text opens with a different bill), or uncertain (no bill number, no clear signal). Produces a report showing which bills have contaminated paragraphs.",
        "reads": "data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json",
        "writes": "Prints audit report to stdout",
        "run": "python3 scripts/audit_ontario.py"
    },
    "build_ontario_bill_index.py": {
        "desc": "Builds the Ontario health bill index from Ontario Legislative Assembly records. Identifies all health bills by keyword matching against bill titles. Stores bill number, title, parliament, session, introduction date, second reading dates, vote outcome, and health_tag boolean.",
        "reads": "data/canada/ontario/ raw vote and proceedings files",
        "writes": "data/canada/ontario/ontario_bill_index.json",
        "run": "python3 scripts/build_ontario_bill_index.py"
    },
    "build_quebec_bill_index.py": {
        "desc": "Builds the Quebec health bill index from Assemblee nationale records and Cheminement legislative data. Same structure as Ontario index.",
        "reads": "data/canada/quebec/ raw files",
        "writes": "data/canada/quebec/quebec_bill_index.json",
        "run": "python3 scripts/build_quebec_bill_index.py"
    },
    "build_detailed_readme.py": {
        "desc": "Generates README.md with pipeline documentation, real examples, GitHub links, and N counts at every stage.",
        "reads": "data/canada/ontario/hansard_api_bill_segments_clean.json, data/dbpedia_pipeline/us/sentences.json, data/dbpedia_pipeline/quebec/sentences.json, data/dbpedia_pipeline/us/predications.json, data/dbpedia_pipeline/quebec/predications.json",
        "writes": "README.md",
        "run": "python3 scripts/build_detailed_readme.py"
    },
    "build_readme.py": {
        "desc": "Shorter README generator. Produces a summary version of README.md.",
        "reads": "Same as build_detailed_readme.py",
        "writes": "README.md",
        "run": "python3 scripts/build_readme.py"
    },
    "build_validation_doc.py": {
        "desc": "Generates the transcript division validation document showing how raw sitting-day transcripts are divided into bill-specific segments at each pipeline stage, with N counts and example text.",
        "reads": "data/canada/ontario/hansard_api_bill_segments_clean.json, data/canada/quebec_assembly/bill_segments/, data/us/congressional_record_speeches/",
        "writes": "data/validation/transcript_division_samples.md",
        "run": "python3 scripts/build_validation_doc.py"
    },
    "check_ontario_bill_stages.py": {
        "desc": "Checks each Ontario health bill's legislative stage history against myparliament.ca to verify that debate dates in the index correspond to actual floor debate and not committee or first reading.",
        "reads": "data/canada/ontario/ontario_bill_index.json",
        "writes": "Prints verification report to stdout",
        "run": "python3 scripts/check_ontario_bill_stages.py"
    },
    "check_uncertain_topics.py": {
        "desc": "For uncertain Ontario bill assignments (no bill number in text, no clear wrong signal), queries the OLA Azure Search API to get the actual Hansard topic for those dates. Determines whether the assigned topic matches the bill title.",
        "reads": "data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json",
        "writes": "data/canada/ontario/uncertain_topic_check.json",
        "run": "python3 scripts/check_uncertain_topics.py"
    },
    "compute_factuality_scores.py": {
        "desc": "Computes per-bill factuality scores from annotated sentences. Score = supported_sentences / total_claim_bearing_sentences. Joins vote outcome from bill index. Produces one score record per bill-date.",
        "reads": "data/dbpedia_pipeline/{jurisdiction}/annotated_sentences.json, data/canada/ontario/ontario_bill_index.json",
        "writes": "data/dbpedia_pipeline/{jurisdiction}/factuality_scores.json",
        "run": "JURISDICTION=us python3 scripts/compute_factuality_scores.py"
    },
    "congressional_record_pull.py": {
        "desc": "Collects US floor debate text from the GovInfo API. Queries CREC packages for health-related bills by CRS policy area. Downloads granule text, extracts House floor sections, saves one .txt file per bill-date. OCR via pytesseract for pre-1993 bound edition PDFs (CRECB).",
        "reads": "GovInfo API at api.govinfo.gov",
        "writes": "data/us/congressional_record_speeches/{date}.txt",
        "run": "python3 scripts/congressional_record_pull.py"
    },
    "convert_ontario_api_segments_to_sentences.py": {
        "desc": "Tokenizes Ontario bill-specific paragraphs into sentences. Splits on sentence boundaries using regex. Looks up party affiliation from ontario_name_party_lookup.json. Assigns speaker, party, date, and bill_key to each sentence.",
        "reads": "data/canada/ontario/hansard_api_bill_segments_clean.json, data/canada/ontario/ontario_name_party_lookup.json",
        "writes": "data/canada/ontario/sentences_bill_specific_api.json (669MB)",
        "run": "python3 scripts/convert_ontario_api_segments_to_sentences.py"
    },
    "convert_quebec_segments_to_sentences.py": {
        "desc": "Tokenizes Quebec bill segments into sentences. Reads each bill_segments .txt file, splits into sentences, assigns speaker, party, date, and bill_key from the Journal des debats attribution format.",
        "reads": "data/canada/quebec_assembly/bill_segments/*.txt",
        "writes": "data/dbpedia_pipeline/quebec/sentences.json",
        "run": "python3 scripts/convert_quebec_segments_to_sentences.py"
    },
    "dbpedia_batch_pipeline.py": {
        "desc": "Main pipeline script. Five stages selectable via command line argument: collect (copy sentences to pipeline directory), extract (v1 Spotlight on full sentences), extract_v2 (v2 Spotlight on predication subject/object strings), dedupe (remove duplicate entity pairs), query (SPARQL verification via local Virtuoso), annotate (join SPARQL results back to sentences). Run with JURISDICTION=us/ontario/quebec environment variable.",
        "reads": "data/dbpedia_pipeline/{jurisdiction}/sentences.json or predications.json",
        "writes": "data/dbpedia_pipeline/{jurisdiction}/triples.json, triples_v2.json, unique_pairs.json, dbpedia_results.json, annotated_sentences.json",
        "run": "JURISDICTION=us python3 scripts/dbpedia_batch_pipeline.py [collect|extract|extract_v2|dedupe|query|annotate]"
    },
    "extract_predications.py": {
        "desc": "V2 pipeline: extracts Subject-Verb-Object predications from sentences using spaCy dependency parsing. Finds the ROOT verb, expands its nominal subject and direct/indirect object to full noun phrases. Excludes existential roots (be, have, do), sentences with no subject or object, and entities in relative clauses. Flags hedged predicates (may, might, could, should, pourrait, devrait). Uses en_core_web_lg for English, fr_core_news_lg for French.",
        "reads": "data/dbpedia_pipeline/{jurisdiction}/sentences.json",
        "writes": "data/dbpedia_pipeline/{jurisdiction}/predications.json",
        "run": "JURISDICTION=us python3 scripts/extract_predications.py"
    },
    "extract_quebec_bill_segments.py": {
        "desc": "Extracts bill-specific text from Quebec full sitting-day transcripts using section markers. Scans each transcript for headers: Etude du projet de loi n X, Adoption du principe, Reprise du debat, Prise en consideration, Adoption. Extracts text from the marker to the next section break. Saves one .txt file per bill-date.",
        "reads": "data/canada/quebec_assembly/YYYYMMDD.txt (full sitting-day transcripts)",
        "writes": "data/canada/quebec_assembly/bill_segments/YYYYMMDD_billN.txt",
        "run": "python3 scripts/extract_quebec_bill_segments.py"
    },
    "fetch_1989_hf.py": {
        "desc": "Fetches pre-2001 Ontario Hansard content from the HuggingFace a2aj/hansard dataset for the 1989 parliament where the OLA API coverage is sparse. Filters by date and OrderofBusiness field, applies client-side bill number verification.",
        "reads": "HuggingFace dataset a2aj/hansard, data/canada/ontario/ontario_bill_index.json",
        "writes": "Appends to data/canada/ontario/hansard_api_bill_segments_clean.json",
        "run": "python3 scripts/fetch_1989_hf.py"
    },
    "fetch_missing_85.py": {
        "desc": "For the 85 Ontario bills missing from the verified clean corpus after rebuild_clean_ontario.py runs, fetches debate text by date-only filter (no keyword filter, which is broken in the API). Filters client-side to keep only paragraphs where the bill number appears in text.",
        "reads": "data/canada/ontario/hansard_api_bill_segments_clean.json, data/canada/ontario/ontario_bill_index.json",
        "writes": "Updates data/canada/ontario/hansard_api_bill_segments_clean.json",
        "run": "python3 scripts/fetch_missing_85.py"
    },
    "fetch_missing_ontario_bills.py": {
        "desc": "Targeted fetch for specific Ontario bills that are still missing after the main rescrape. Takes a list of bill keys and fetches each from the OLA API using date-based queries with client-side bill number verification.",
        "reads": "data/canada/ontario/ontario_bill_index.json",
        "writes": "Updates data/canada/ontario/hansard_api_bill_segments_clean.json",
        "run": "python3 scripts/fetch_missing_ontario_bills.py"
    },
    "fetch_ontario_hansard_via_api.py": {
        "desc": "Main Ontario Hansard scraper. Queries the OLA Azure Search API for each health bill's debate dates, filtering to Orders of the Day (both capitalizations). Stores topic field with each paragraph for verification. Assigns paragraphs to bills using bill number mention in text as primary criterion and topic keyword match as secondary. Handles rate limiting with exponential backoff. Saves checkpoint every 10 batches.",
        "reads": "data/canada/ontario/ontario_bill_index.json, OLA Azure Search API",
        "writes": "data/canada/ontario/hansard_api_bill_segments.json",
        "run": "python3 scripts/fetch_ontario_hansard_via_api.py"
    },
    "fetch_via_orders_notices.py": {
        "desc": "Supplements the OLA API scrape by fetching Orders and Notices papers (the daily House agenda) to verify which bills were actually scheduled for debate on specific dates. Used to correct wrong dates in the bill index.",
        "reads": "OLA website Orders and Notices pages, data/canada/ontario/ontario_bill_index.json",
        "writes": "Prints verified debate dates to stdout",
        "run": "python3 scripts/fetch_via_orders_notices.py"
    },
    "find_correct_debate_dates.py": {
        "desc": "For uncertain Ontario bills, queries the OLA API to find the actual dates when each bill was debated under Orders of the Day. Uses keyword search for the bill number across all dates to locate real debate dates.",
        "reads": "data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json",
        "writes": "data/canada/ontario/correct_debate_dates.json",
        "run": "python3 scripts/find_correct_debate_dates.py"
    },
    "get_examples.py": {
        "desc": "Utility script that pulls real example predications, supported/unsupported sentences, Ontario paragraphs, and factuality score samples for documentation purposes.",
        "reads": "data/canada/ontario/hansard_api_bill_segments_clean.json, data/dbpedia_pipeline/us/predications.json, data/dbpedia_pipeline/quebec/predications.json, data/dbpedia_pipeline/us/annotated_sentences.json, data/dbpedia_pipeline/us/factuality_scores.json",
        "writes": "Prints examples to stdout",
        "run": "python3 scripts/get_examples.py"
    },
    "patch_pipeline_v2.py": {
        "desc": "One-time patch script that added the extract_v2 stage to dbpedia_batch_pipeline.py. Kept for reference.",
        "reads": "scripts/dbpedia_batch_pipeline.py",
        "writes": "scripts/dbpedia_batch_pipeline.py (modified in place)",
        "run": "python3 scripts/patch_pipeline_v2.py"
    },
    "rebuild_clean_ontario.py": {
        "desc": "Rebuilds hansard_api_bill_segments_clean.json from the raw API output. Two passes: first keeps existing paragraphs where the bill number is in the text (verified). Then re-fetches bills with no verified content using OLA API keyword search, keeping only paragraphs that explicitly mention the bill number. Produces a corpus where every paragraph is verified.",
        "reads": "data/canada/ontario/hansard_api_bill_segments.json, data/canada/ontario/ontario_bill_index.json",
        "writes": "data/canada/ontario/hansard_api_bill_segments_clean.json",
        "run": "python3 scripts/rebuild_clean_ontario.py"
    },
    "run_analyses.py": {
        "desc": "Runs all downstream analyses on factuality scores: logistic regression (factuality predicting bill passage), Jensen-Shannon divergence across jurisdictions and parties, COVID natural experiment (pre/post March 2020), era and party breakdowns. Saves figures to figures/ directory.",
        "reads": "data/dbpedia_pipeline/us/factuality_scores.json, data/dbpedia_pipeline/ontario/factuality_scores.json, data/dbpedia_pipeline/quebec/factuality_scores.json",
        "writes": "figures/regression_results.png, figures/jsd_distributions.png, figures/covid_comparison.png, figures/era_breakdown.png",
        "run": "python3 scripts/run_analyses.py"
    },
}

for name in sorted(scripts.keys()):
    info = scripts[name]
    w(f"### {name}")
    w()
    w(info["desc"])
    w()
    w(f"Reads: {info['reads']}")
    w()
    w(f"Writes: {info['writes']}")
    w()
    w(f"Run: `{info['run']}`")
    w()

# ── DATA FILES ───────────────────────────────────────────────────────────────
w("---")
w()
w("## data/")
w()
w("### data/canada/")
w()

canada_files = [
    ("Codebook.pdf", "Codebook for the Canadian Parliamentarian Biographies dataset (PPB.csv). Describes all fields in the biographical dataset.", "GitHub", None),
    ("PPB.csv", "Canadian Parliamentarian Biographies. Harvard Dataverse dataset. Used to build member lookup tables for Ontario and Quebec party attribution.", "GitHub", None),
    ("member_lookup.json", "Combined lookup table mapping member names to party affiliations for both Ontario and Quebec. Produced by build_canada_member_lookup.py.", "GitHub", None),
    ("ontario_bill_passages.json", "Ontario health bill passage outcomes. Scraped from Ontario Legislative Assembly vote records. Used to join vote results to factuality scores.", "GitHub", None),
    ("ontario_members.json", "Ontario MPP biographical data scraped from OLA member pages. Name, party, riding, years served.", "GitHub", None),
]

for fname, desc, access, url in canada_files:
    w(f"**{fname}** ({access})")
    w(desc)
    w()

w("### data/canada/ontario/")
w()

ontario_files = [
    ("ontario_bill_index.json", "Master index of all Ontario health bills. Fields: bill_key, bill_number, title, parliament, session, health_tag, dates (floor debate dates), vote_result. Produced by build_ontario_bill_index.py. Read by almost every Ontario script.", "GitHub", None),
    ("ontario_name_party_lookup.json", "Maps MPP names to party affiliations across all parliaments 1985-2026. Used by convert_ontario_api_segments_to_sentences.py to assign party to each sentence.", "GitHub", None),
    ("ontario_vote_index.json", "Ontario vote records indexed by bill key. Includes vote date, result (passed/failed), vote counts.", "GitHub", None),
    ("ontario_votes_proceedings.json", "Raw vote proceedings data scraped from Ontario Votes and Proceedings documents.", "GitHub", None),
    ("ontario_fsob_votes.json", "Ontario final bill status and vote outcomes. Supplementary to ontario_vote_index.json.", "GitHub", None),
    ("hansard_api_bill_segments.json", "Raw output from fetch_ontario_hansard_via_api.py. Contains all paragraphs fetched from the OLA API including unverified assignments. 128MB. Use hansard_api_bill_segments_clean.json for analysis.", "Local only", None),
    ("hansard_api_bill_segments_clean.json", "Verified bill-specific paragraphs. Every paragraph confirmed: bill number appears explicitly in text. 249 bills, 83,443 paragraphs. Produced by rebuild_clean_ontario.py. Read by convert_ontario_api_segments_to_sentences.py.", "Yale OneDrive", ONEDRIVE),
    ("sentences_bill_specific_api.json", "Ontario bill-specific sentences tokenized from hansard_api_bill_segments_clean.json. 1,942,246 sentences. Fields: sentence_id, date, text, speaker, party, bill_key. 669MB. Read by extract_predications.py.", "Local only", None),
    ("uncertain_topic_check.json", "Output of check_uncertain_topics.py. For each uncertain bill-date, stores the actual Hansard topic returned by the OLA API to determine whether the assignment is correct.", "Local only", None),
    ("correct_debate_dates.json", "Output of find_correct_debate_dates.py. Stores verified correct debate dates for bills that had wrong dates in the original index.", "Local only", None),
]

for fname, desc, access, url in ontario_files:
    sz_str = sz(f"data/canada/ontario/{fname}")
    w(f"**{fname}** ({access}, {sz_str})")
    if url:
        w(f"[Download]({url})")
    w(desc)
    w()

w("### data/canada/quebec_assembly/")
w()
w("**YYYYMMDD.txt** (GitHub, 1,831 files)")
w("Full sitting-day transcripts from assnat.qc.ca. Plain text with HTML stripped. One file per sitting day. Produced by archive/quebec_assembly_transcripts_pull.py. Read by extract_quebec_bill_segments.py.")
w()
w("**bill_segments/YYYYMMDD_billN.txt** (GitHub, 11,369 files)")
w("Bill-specific text extracted from full transcripts using section markers. One file per bill-date. Produced by extract_quebec_bill_segments.py. Read by convert_quebec_segments_to_sentences.py.")
w()

w("### data/us/")
w()

us_files = [
    ("congressional_record_speeches/{date}.txt", "Floor debate text for one health bill-date. 448 files. Bill-specific by construction (GovInfo granule = one bill's floor debate). Produced by congressional_record_pull.py. Read by extract_speaker_turns_us.py (archived).", "GitHub", "https://github.com/capriceculkin/legislative-health-factuality/tree/main/data/us/congressional_record_speeches"),
    ("health_bills_final_matched.csv", "US health bill index. Bill number, title, CRS policy area, Congress, vote date, vote outcome. Used to build the bill index and join vote results.", "GitHub", None),
    ("us_speaker_turns.json", "US speaker turns extracted from congressional_record_speeches. Intermediate file before sentence tokenization.", "Local only", None),
    ("voteview/house_rollcalls_1985_present.csv", "VoteView rollcall data for US House 1985 to present. Used to verify vote outcomes.", "GitHub", None),
    ("voteview/house_members_1985_present.csv", "VoteView member data for US House 1985 to present. Party, state, district.", "GitHub", None),
]

for fname, desc, access, url in us_files:
    w(f"**{fname}** ({access})")
    if url:
        w(f"[Browse]({url})")
    w(desc)
    w()

w("### data/dbpedia_pipeline/")
w()
w("Pipeline working directory. One subdirectory per jurisdiction: us/, ontario/, quebec/.")
w("All files in this directory are local only and must be regenerated using dbpedia_batch_pipeline.py.")
w()

pipeline_files = [
    ("sentences.json", "Bill-specific sentences copied from the jurisdiction's source sentences file. Input to extract_predications.py and dbpedia_batch_pipeline.py collect stage. US: 584,111 sentences. Ontario: 1,942,246. Quebec: 923,634.", "extract_predications.py, dbpedia_batch_pipeline.py collect"),
    ("predications.json", "Subject-Verb-Object triples extracted from sentences by extract_predications.py. Fields: subject, verb, verb_lemma, object, hedged, negated, sentence_id, full_text. US: 215,412. Quebec: 177,952. Ontario: pending.", "dbpedia_batch_pipeline.py extract_v2"),
    ("triples.json", "V1 pipeline output. Spotlight run on full sentences. Superseded by triples_v2.json but kept as reference baseline.", "dbpedia_batch_pipeline.py dedupe (v1)"),
    ("triples_v2.json", "V2 pipeline output. Spotlight run on subject and object strings only. Fields: sentence_id, subject, object, verb_lemma, concept_uris, hedged. Running for US and Quebec.", "dbpedia_batch_pipeline.py dedupe"),
    ("unique_pairs.json", "Deduplicated entity URI pairs. One entry per unique (URI_A, URI_B) pair across all sentences. SPARQL queried once per unique pair.", "dbpedia_batch_pipeline.py query"),
    ("dbpedia_results.json", "SPARQL query results cache. One entry per unique pair. Stores supported boolean and matched predicates.", "dbpedia_batch_pipeline.py annotate"),
    ("annotated_sentences.json", "Each predication annotated with supported boolean. Fields: sentence_id, supported, concept_uris, date, party, bill_key, verb.", "compute_factuality_scores.py"),
    ("factuality_scores.json", "Per bill-date factuality scores. Fields: date, bill_key, score, total_sentences, supported_sentences, vote_result, party_in_power. US mean: 0.2054. Quebec mean: 0.1387. Ontario V1 mean: 0.1006.", "run_analyses.py"),
]

for fname, desc, feeds in pipeline_files:
    w(f"**{{jurisdiction}}/{fname}** (Local only)")
    w(f"{desc}")
    w(f"Feeds into: {feeds}")
    w()

w("### data/validation/")
w()
w("**transcript_division_samples.md** (GitHub)")
w("Validation document showing how raw sitting-day transcripts are divided into bill-specific segments at each pipeline stage. Includes N counts, example text, and before/after comparisons for all three jurisdictions. Produced by build_validation_doc.py.")
w()

out_str = "\n".join(lines)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(out_str)
print(f"Saved {len(lines)} lines to {OUT}")
