"""
build_full_readme.py
Full detailed README with mermaid diagram, real examples, prose explanations,
GitHub links, OLA/assnat links, no tables, no em dashes, no AI language.
"""
import json, os, re, random
random.seed(42)

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
GH = "https://github.com/capriceculkin/legislative-health-factuality/blob/main"
ONEDRIVE = "https://yaleedu-my.sharepoint.com/:u:/g/personal/caprice_culkin_yale_edu/IQCAGMCyyH_0ToGTWu1erpwpAV8Bcot0NVoBJZ5BJPxiTYI?e=NO1Els"

# Load data
with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    ont_idx = json.load(f)
with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments_clean.json") as f:
    ont_clean = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/sentences.json") as f:
    qc_sents = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/sentences.json") as f:
    us_sents = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/predications.json") as f:
    us_preds = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/predications.json") as f:
    qc_preds = json.load(f)

qc_seg_dir = f"{REPO}/data/canada/quebec_assembly/bill_segments"
qc_seg_files = sorted([f for f in os.listdir(qc_seg_dir) if f.endswith(".txt")])

speeches_dir = f"{REPO}/data/us/congressional_record_speeches"
us_files = sorted([f for f in os.listdir(speeches_dir) if f.endswith(".txt") and f[:4] > "2005"])

# Pull Ontario Bill 94 example
ont_bill94_paras = ont_clean.get("1985-Bill94", {}).get("1986-01-14", [])
ont_bill94_texts = [p if isinstance(p, str) else p.get("text","") for p in ont_bill94_paras]
ont_bill94_long = [t for t in ont_bill94_texts if len(t) > 150]

# Pull Ontario Bill 52 example
ont_bill52_paras = ont_clean.get("1985-Bill52", {}).get("1987-06-25", [])
ont_bill52_texts = [p if isinstance(p, str) else p.get("text","") for p in ont_bill52_paras]
ont_bill52_long = [t for t in ont_bill52_texts if len(t) > 150]

# Pull Quebec example
qc_health = []
for fname in qc_seg_files:
    fpath = f"{qc_seg_dir}/{fname}"
    with open(fpath, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if len(text) > 800 and any(w in text.lower() for w in ["santé","médecin","soins","hôpital"]):
        qc_health.append((fname, text))

qc_fname, qc_text = qc_health[5]
qc_date = f"{qc_fname[:4]}-{qc_fname[4:6]}-{qc_fname[6:8]}"
qc_bill_m = re.search(r"bill(\d+)", qc_fname)
qc_bill_num = qc_bill_m.group(1) if qc_bill_m else "?"

# Pull Quebec raw transcript example for before/after
qc_raw_file = f"{REPO}/data/canada/quebec_assembly/transcripts/{qc_fname[:8]}.txt"
qc_raw_exists = os.path.exists(qc_raw_file)
if qc_raw_exists:
    with open(qc_raw_file, encoding="utf-8", errors="replace") as f:
        qc_raw = f.read()
    # Find a good snippet showing the section marker
    marker_idx = qc_raw.find("Étude du projet")
    if marker_idx < 0:
        marker_idx = qc_raw.find("ÉTUDE DU PROJET")
    qc_before = qc_raw[max(0, marker_idx-300):marker_idx+200] if marker_idx > 0 else qc_raw[:500]
else:
    qc_before = ""

# Pull US example
us_example_text = ""
us_example_file = ""
for fname in us_files:
    fpath = f"{speeches_dir}/{fname}"
    with open(fpath, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if (len(text) > 2000 and "health" in text.lower() 
            and "Daily Digest" not in text[:300]
            and "COMMITTEE MEETINGS" not in text[:300]):
        us_example_file = fname
        us_example_text = text
        break

# Good predications
us_good = [p for p in us_preds 
           if len(p.get("subject","")) > 5 
           and len(p.get("object","")) > 5
           and p.get("verb_lemma","") not in ["be","have","do","get","say","go"]
           and len(p.get("full_text","")) > 60
           and not p.get("hedged", False)][:30]
random.shuffle(us_good)

qc_good = [p for p in qc_preds 
           if len(p.get("subject","")) > 5 
           and len(p.get("object","")) > 5
           and p.get("verb_lemma","") not in ["être","avoir","faire","aller","dire"]
           and len(p.get("full_text","")) > 60][:30]
random.shuffle(qc_good)

ont_total_paras = sum(len(p) for d in ont_clean.values() for p in d.values())

lines = []
def w(s=""): lines.append(s)

w("# Legislative Health Factuality")
w()
w("**Research question:** Does the factual accuracy of legislative health floor debate predict bill passage outcomes?")
w()
w("**Jurisdictions covered:** US House of Representatives, Ontario Legislative Assembly, Quebec National Assembly, spanning 1985 to 2026.")
w()
w("**Investigators:** Caprice Culkin (Yale School of Public Health) with David Chartash and Joanie Bouchard.")
w()
w("**Repository:** github.com/capriceculkin/legislative-health-factuality")
w()

w("---")
w()
w("## Pipeline")
w()
w("The pipeline has five stages. Each stage is documented below with the exact files it reads,")
w("the files it produces, what gets removed at that stage, and real examples showing the")
w("input and output text.")
w()
w("```mermaid")
w("flowchart TD")
w("    classDef source fill:#f5f5f5,stroke:#999,color:#111")
w("    classDef process fill:#e8f4f8,stroke:#5b9bd5,color:#111")
w("    classDef output fill:#e8f5e9,stroke:#4caf50,color:#111")
w()
w("    US_SRC[\"GovInfo API\\nCongressional Record\\n145 health bill-dates\"]:::source")
w("    ON_SRC[\"OLA Azure Search API\\naihansardsearch-apim.azure-api.net\\n329 health bills\"]:::source")
w("    QC_SRC[\"assnat.qc.ca\\nJournal des debats HTML\\n1831 transcript files\"]:::source")
w()
w("    US_EXT[\"US Granules\\n145 bill-dates\\n584K sentences\"]:::process")
w("    ON_EXT[\"Ontario Orders of Day\\n249 verified bills\\n83K paragraphs\\nrescrape in progress\"]:::process")
w("    QC_EXT[\"Quebec Bill Segments\\n11K bill-date segments\\n924K sentences\"]:::process")
w()
w("    PRED[\"Predication Extraction\\nspaCy SVO\\nUS 215K  Quebec 178K  Ontario pending\"]:::process")
w()
w("    SPOT[\"DBpedia Spotlight\\nSubject + Object strings only\\nDunkleosteus EN port 2222 FR port 2223\"]:::process")
w()
w("    SPARQL[\"SPARQL Verification\\nLocal Virtuoso\\nEN + FR DBpedia\\nlocalhost:8890\"]:::process")
w()
w("    SCORES[\"Factuality Scores\\nsupported / total claim-bearing\\nper bill-date\"]:::output")
w()
w("    US_SRC --> US_EXT")
w("    ON_SRC --> ON_EXT")
w("    QC_SRC --> QC_EXT")
w("    US_EXT --> PRED")
w("    ON_EXT --> PRED")
w("    QC_EXT --> PRED")
w("    PRED --> SPOT --> SPARQL --> SCORES")
w("```")
w()

w("---")
w()
w("## Stage 1: Bill-Specific Text Extraction")
w()
w("The denominator for factuality scoring is the set of sentences spoken during")
w("floor debate on a specific health bill. All three jurisdictions extract only")
w("this bill-specific floor debate text, excluding question period, petitions,")
w("member statements, ministerial statements, committee study transcripts, and")
w("all other business on sitting days.")
w()
w("This matches the structure of the US data where GovInfo granules are")
w("bill-specific by construction. Quebec uses section markers in the Journal")
w("des debats. Ontario uses the OLA Azure Search API filtered to Orders of the Day.")
w()

# US
w("### United States")
w()
w(f"Source: GovInfo API at `api.govinfo.gov/packages/`")
w(f"Collection script: [{GH}/scripts/congressional_record_pull.py](scripts/congressional_record_pull.py)")
w(f"Output directory: `data/us/congressional_record_speeches/`")
w()
w("Each GovInfo granule corresponds to one bill's Congressional Record floor debate.")
w("The granule ID encodes the bill and date. Health bills are identified via")
w("CRS policy area tags in the package metadata.")
w()
w(f"After collection: 145 health bill-dates, 584,111 sentences.")
w()
if us_example_file:
    us_date = us_example_file.replace(".txt","")
    parl_date = us_date
    w(f"Full example file: [{GH}/data/us/congressional_record_speeches/{us_example_file}](data/us/congressional_record_speeches/{us_example_file})")
    w()
    w(f"Excerpt from `{us_example_file}`:")
    w()
    w("```")
    for line in us_example_text[:600].split("\n")[:12]:
        if line.strip():
            w(line[:120])
    w("```")
    w()

# Ontario
w("### Ontario")
w()
w(f"Source: OLA Hansard search tool backend at `aihansardsearch-apim.azure-api.net`")
w(f"Collection script: [{GH}/scripts/fetch_ontario_hansard_via_api.py](scripts/fetch_ontario_hansard_via_api.py)")
w(f"Cleaning script: [{GH}/scripts/rebuild_clean_ontario.py](scripts/rebuild_clean_ontario.py)")
w(f"Output: `data/canada/ontario/hansard_api_bill_segments_clean.json` ([Yale OneDrive]({ONEDRIVE}))")
w()
w("The OLA Hansard search tool uses an Azure Cognitive Search backend.")
w("The API endpoint was identified by inspecting browser network traffic on the OLA search page.")
w("The scraper queries each bill's debate dates using an OData filter:")
w()
w("```")
w("POST aihansardsearch-apim.azure-api.net/api/search/keyword")
w("filter: (date ge 1986-01-14T00:00:00Z and date le 1986-01-14T23:59:59Z)")
w("        and typeOfBusiness eq 'ORDERS OF THE DAY'")
w("rows: 500")
w("```")
w()
w("Two capitalizations are required: pre-2018 Hansard uses 'ORDERS OF THE DAY'")
w("in all caps, post-2018 uses 'Orders of the Day' in mixed case. Both are queried.")
w()
w("Bill assignment uses only one criterion: the bill number must appear explicitly")
w("in the paragraph text. For example, a paragraph is assigned to Bill 94 only if")
w("it contains the string 'Bill 94'. No topic fallback and no single-bill date")
w("fallback are used. This ensures every paragraph in the output is verified.")
w()
w("The previous version of the scraper used a single-bill date fallback that")
w("caused wrong assignments. For example, Bill 89 was assigned paragraphs")
w("that opened with 'Resuming the adjourned debate on the motion for second")
w("reading of Bill 68, An Act to amend certain Acts respecting Insurance.'")
w("The current clean corpus removes all such cases.")
w()
w("What is excluded:")
w("- Question Period and Oral Questions")
w("- Members' Statements")
w("- Petitions")
w("- Introduction of Bills (first reading only)")
w("- Committee study transcripts")
w("- Paragraphs that do not mention the specific bill number in the text")
w()
w(f"After collection and verification: {len(ont_clean)} bills, {ont_total_paras:,} paragraphs.")
w("Rescrape with topic field storage is currently running and will increase coverage.")
w()

# Ontario example 1: Bill 94
w(f"Full example: Bill 94, An Act regulating the Amounts that Persons may charge for Insured Services (extra billing)")
w(f"Debate date: 1986-01-14. OLA Hansard page for this date:")
w(f"https://www.ola.org/en/legislative-business/house-documents/parliament-34/session-1/1986-01-14/hansard")
w()
w(f"The paragraph text confirms assignment (Bill 94 mentioned):")
w()
w("```")
for t in ont_bill94_long[:3]:
    w(t[:350])
    w()
w("```")
w()

# Ontario example 2: Bill 52
if ont_bill52_long:
    w(f"Full example: Bill 52, An Act to amend the Health Protection and Promotion Act")
    w(f"Debate date: 1987-06-25. OLA Hansard page:")
    w(f"https://www.ola.org/en/legislative-business/house-documents/parliament-34/session-1/1987-06-25/hansard")
    w()
    w("```")
    for t in ont_bill52_long[:3]:
        w(t[:350])
        w()
    w("```")
    w()

# Quebec
w("### Quebec")
w()
w(f"Source: Assemblee nationale du Quebec at `assnat.qc.ca`")
w(f"Raw transcripts: `data/canada/quebec_assembly/transcripts/` — one .txt file per sitting day")
w(f"Extraction script: [{GH}/scripts/extract_quebec_bill_segments.py](scripts/extract_quebec_bill_segments.py)")
w(f"Output: `data/canada/quebec_assembly/bill_segments/` — one .txt file per bill-date")
w()
w("The Journal des debats uses structured section headers that mark when the")
w("Assembly takes up a specific bill. The extraction script scans each transcript")
w("file for these headers and extracts the text from the header to the next")
w("section break.")
w()
w("Section markers used:")
w()
w("```")
w("Etude du projet de loi n X")
w("Adoption du principe du projet de loi n X")
w("Reprise du debat sur l'adoption du principe du projet de loi n X")
w("Prise en consideration du rapport sur le projet de loi n X")
w("Adoption du projet de loi n X")
w("```")
w()
w("What is excluded:")
w("- Question period (periode des questions)")
w("- Ministerial statements (declarations ministerielles)")
w("- Petitions")
w("- Introduction of bills (depot de projets de loi)")
w("- Commission parlementaire transcripts (separate corpus, same as US excludes committee hearings)")
w("- Everything else on the sitting day not about the specific bill")
w()
w(f"After extraction: {len(qc_seg_files):,} bill-date segment files, {len(qc_sents):,} sentences.")
w()

# Quebec before/after
w(f"Full example: Bill {qc_bill_num}, debate date {qc_date}")
w(f"assnat.qc.ca page: https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/")
w(f"Extracted segment file: [{GH}/data/canada/quebec_assembly/bill_segments/{qc_fname}](data/canada/quebec_assembly/bill_segments/{qc_fname})")
w()

if qc_before:
    w("Raw transcript (before extraction) showing the section marker in context:")
    w()
    w("```")
    for line in qc_before.split("\n")[:15]:
        w(line[:120])
    w("```")
    w()

w("Extracted bill-specific segment (after extraction):")
w()
w("```")
for line in qc_text[:600].split("\n")[:12]:
    w(line[:120])
w("```")
w()

# Stage 2
w("---")
w()
w("## Stage 2: Predication Extraction")
w()
w(f"Script: [{GH}/scripts/extract_predications.py](scripts/extract_predications.py)")
w("Input: sentences.json for each jurisdiction")
w("Output: predications.json")
w()
w("This stage was added at David Chartash's request following the September 11 2026 meeting.")
w("In the original pipeline, DBpedia Spotlight ran on full sentences, which caused")
w("spurious entity pairs. The problem: a sentence can mention two entities without")
w("asserting any factual relationship between them.")
w()
w("The example David raised:")
w()
w("```")
w("Sentence: 'The OMA, which represents 30,000 physicians, endorsed this legislation.'")
w()
w("Old approach: Spotlight on full sentence")
w("  Entities found: OMA, Physician, Legislation")
w("  Pairs generated: (OMA, Physician), (OMA, Legislation), (Physician, Legislation)")
w("  (OMA, Physician) is confirmed by DBpedia")
w("  But the speaker was not claiming anything about OMA and physicians")
w("  The confirmation is spurious")
w()
w("New approach: spaCy extracts the predication first")
w("  subject: Ontario Medical Association")
w("  verb:    endorsed")
w("  object:  legislation")
w("  Spotlight runs on 'Ontario Medical Association' and 'legislation' only")
w("  Pair: (OMA, Legislation) is not in DBpedia")
w("  Correctly unsupported")
w("  The relative clause entity 'physicians' is never considered")
w("```")
w()
w("spaCy's dependency parser identifies the ROOT verb of each sentence, then finds")
w("its nominal subject (nsubj) and direct or indirect object (dobj, obj, obl).")
w("The full noun phrase is expanded for each argument.")
w()
w("What is excluded at this stage:")
w("- Sentences where the root verb is existential: be, have, do, seem, appear")
w("  These are not factual claims. Example: 'It is important that we protect health care.'")
w("- Sentences where no subject or no object is found")
w("- Sentences where subject and object resolve to the same entity")
w("- Entities found only in relative clauses, parentheticals, or appositives")
w()
w("Hedged predicates (may, might, could, should, pourrait, devrait) are included")
w("but flagged with hedged=True so they can be filtered or analyzed separately.")
w()
w(f"Results: US extracted {len(us_preds):,} predications from {len(us_sents):,} sentences (36.9%).")
w(f"Quebec extracted {len(qc_preds):,} predications from {len(qc_sents):,} sentences (19.3%).")
w("Ontario is pending. Quebec's lower rate reflects fr_core_news_lg's lower recall")
w("for Quebec legislative French compared to en_core_web_lg for English.")
w()
w("Sample US predications from health bill debates:")
w()
w("```")
shown = 0
for p in us_good:
    if shown >= 4: break
    w(f"Sentence: \"{p['full_text'][:120]}\"")
    w(f"  subject: \"{p['subject']}\"")
    w(f"  verb:    {p['verb_lemma']}")
    w(f"  object:  \"{p['object']}\"")
    w()
    shown += 1
w("```")
w()
w("Sample Quebec predications from health bill debates:")
w()
w("```")
shown = 0
for p in qc_good:
    if shown >= 4: break
    w(f"Sentence: \"{p['full_text'][:120]}\"")
    w(f"  sujet:  \"{p['subject']}\"")
    w(f"  verbe:  {p['verb_lemma']}")
    w(f"  objet:  \"{p['object']}\"")
    w()
    shown += 1
w("```")
w()

# Stage 3
w("---")
w()
w("## Stage 3: DBpedia Spotlight Entity Linking")
w()
w(f"Script: [{GH}/scripts/dbpedia_batch_pipeline.py](scripts/dbpedia_batch_pipeline.py) — extract_v2 stage")
w("Infrastructure: Dunkleosteus server at 10.168.171.152 (Yale VPN required)")
w("SSH tunnel: ssh -i ~/.ssh/dunkleosteus_key -L 2222:localhost:2222 -L 2223:localhost:2223 cc3436@10.168.171.152")
w("English endpoint: localhost:2222 — French endpoint: localhost:2223")
w()
w("Spotlight receives the subject string and object string from each predication")
w("and returns DBpedia URIs for any named entities it identifies.")
w()
w("```")
w("Input predication:")
w("  subject: 'Ontario Medical Association'")
w("  object:  'legislation'")
w()
w("Spotlight on subject string 'Ontario Medical Association':")
w("  dbpedia.org/resource/Ontario_Medical_Association")
w()
w("Spotlight on object string 'legislation':")
w("  dbpedia.org/resource/Legislation")
w()
w("Entity pair produced: (Ontario_Medical_Association, Legislation)")
w("```")
w()
w("What is excluded here:")
w("- Predications where Spotlight finds no DBpedia entity for the subject")
w("- Predications where Spotlight finds no DBpedia entity for the object")
w("- Predications where subject and object resolve to the same DBpedia resource")
w()

# Stage 4
w("---")
w()
w("## Stage 4: SPARQL Verification")
w()
w(f"Script: [{GH}/scripts/dbpedia_batch_pipeline.py](scripts/dbpedia_batch_pipeline.py) — query stage")
w("Endpoint: local Virtuoso instance on Dunkleosteus at localhost:8890")
w("English DBpedia and French DBpedia are both loaded in the same Virtuoso container.")
w()
w("For each unique entity pair, a SPARQL query checks whether DBpedia contains")
w("a direct triple connecting the two entities in either direction.")
w()
w("```sparql")
w("SELECT ?a ?b ?p WHERE {")
w("  VALUES (?a ?b) { (<URI_A> <URI_B>) }")
w("  { ?a ?p ?b } UNION { ?b ?p ?a }")
w("}")
w("```")
w()
w("A pair is marked supported when DBpedia returns at least one matching triple.")
w()
w("Supported example:")
w()
w("```")
w("Pair: (dbpedia:Canada, dbpedia:United_States)")
w("Result: dbo:neighboringMunicipality")
w("Supported: True")
w("```")
w()
w("Not supported example:")
w()
w("```")
w("Pair: (dbpedia:Ontario_Medical_Association, dbpedia:Legislation)")
w("Result: no triples found")
w("Supported: False")
w("```")
w()
w("The OMA endorsing legislation is a rhetorical claim. The relationship")
w("does not exist in the DBpedia knowledge graph, so the sentence is")
w("correctly marked as not supported by external evidence.")
w()
w("Deduplication runs before querying: the same entity pair can appear")
w("in many sentences. DBpedia is queried once per unique pair and the")
w("result is applied to all sentences containing that pair.")
w()

# Stage 5
w("---")
w()
w("## Stage 5: Factuality Scores")
w()
w(f"Script: [{GH}/scripts/compute_factuality_scores.py](scripts/compute_factuality_scores.py)")
w()
w("For each health bill, the factuality score is:")
w()
w("```")
w("factuality_score = supported_sentences / total_claim_bearing_sentences")
w("```")
w()
w("A claim-bearing sentence is one where Spotlight found DBpedia entities for")
w("both the subject and object of the extracted predication. The denominator")
w("includes all claim-bearing sentences, whether supported or not.")
w()
w("Current results (v1 pipeline, new bill-specific denominator):")
w()
w("US: mean factuality 0.2054. Passed bills 0.2094 (n=386), failed bills 0.2015 (n=34).")
w("Quebec: mean factuality 0.1387. Passed bills 0.1266 (n=767).")
w("Ontario: pipeline running, scores pending.")
w()
w("COVID natural experiment: US factuality decreased 0.036 post-March 2020.")
w("Quebec decreased 0.053. Both consistent with emergency legislative conditions.")
w()
w("Logistic regression on US and Quebec combined: factuality coefficient +0.0467 (p less than 0.05).")
w()

# Large files
w("---")
w()
w("## Large Data Files")
w()
w("The following files exceed GitHub's 100MB size limit and are not tracked in this repository.")
w()
w(f"[hansard_api_bill_segments_clean.json]({ONEDRIVE}) — Ontario verified bill-specific paragraphs")
w(f"249 bills, 83,443 paragraphs. Every paragraph verified: bill number explicitly in paragraph text.")
w("Available via Yale OneDrive (Yale login required).")
w()
w("The following files are excluded from version control and must be regenerated locally:")
w()
w("data/canada/ontario/sentences_bill_specific_api.json (669MB) — regenerate with convert_ontario_api_segments_to_sentences.py")
w("data/dbpedia_pipeline/ontario/sentences.json (669MB) — copy of above")
w("data/dbpedia_pipeline/quebec/sentences.json (200MB) — regenerate with convert_quebec_segments_to_sentences.py")
w("data/dbpedia_pipeline/us/predications.json (86.8MB) — regenerate with extract_predications.py")
w("data/dbpedia_pipeline/quebec/predications.json (80.2MB) — regenerate with extract_predications.py")
w()

# Scripts
w("---")
w()
w("## Scripts")
w()
w("The active pipeline scripts are in `scripts/`. Experimental and archived scripts")
w(f"are in `scripts/archive/`.")
w()
w(f"[fetch_ontario_hansard_via_api.py]({GH}/scripts/fetch_ontario_hansard_via_api.py) — collects Ontario bill-specific text from OLA Azure Search API")
w(f"[rebuild_clean_ontario.py]({GH}/scripts/rebuild_clean_ontario.py) — removes wrong assignments, produces verified-only corpus")
w(f"[fetch_missing_85.py]({GH}/scripts/fetch_missing_85.py) — re-fetches bills missing from verified corpus")
w(f"[extract_quebec_bill_segments.py]({GH}/scripts/extract_quebec_bill_segments.py) — extracts Quebec bill segments using section markers")
w(f"[convert_ontario_api_segments_to_sentences.py]({GH}/scripts/convert_ontario_api_segments_to_sentences.py) — tokenizes Ontario paragraphs into sentences")
w(f"[convert_quebec_segments_to_sentences.py]({GH}/scripts/convert_quebec_segments_to_sentences.py) — tokenizes Quebec segments into sentences")
w(f"[extract_predications.py]({GH}/scripts/extract_predications.py) — spaCy SVO extraction for v2 pipeline")
w(f"[dbpedia_batch_pipeline.py]({GH}/scripts/dbpedia_batch_pipeline.py) — Spotlight extract, dedupe, SPARQL query, annotate")
w(f"[compute_factuality_scores.py]({GH}/scripts/compute_factuality_scores.py) — per-bill factuality scores")
w(f"[run_analyses.py]({GH}/scripts/run_analyses.py) — regression, COVID analysis, era breakdowns, JSD")
w(f"[congressional_record_pull.py]({GH}/scripts/congressional_record_pull.py) — US GovInfo collection")
w(f"[build_ontario_bill_index.py]({GH}/scripts/build_ontario_bill_index.py) — Ontario health bill index")
w(f"[build_quebec_bill_index.py]({GH}/scripts/build_quebec_bill_index.py) — Quebec health bill index")
w()

out = f"{REPO}/README.md"
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Saved {len(lines)} lines to {out}")
