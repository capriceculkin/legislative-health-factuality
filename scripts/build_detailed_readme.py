"""
build_detailed_readme.py

Builds a detailed README.md with:
- Mermaid pipeline diagram
- Full before/after examples at each stage
- GitHub links to example files
- N counts at every step
- What is removed at each step
"""
import json, os, re, random

random.seed(42)
REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
GITHUB = "https://github.com/capriceculkin/legislative-health-factuality/blob/main"

lines = []
def w(s=""): lines.append(s)

# Load data for accurate counts
with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    ont_idx = json.load(f)
with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments_clean.json") as f:
    ont_clean = json.load(f)

qc_seg_dir = f"{REPO}/data/canada/quebec_assembly/bill_segments"
qc_seg_files = [f for f in os.listdir(qc_seg_dir) if f.endswith(".txt")] if os.path.exists(qc_seg_dir) else []

with open(f"{REPO}/data/dbpedia_pipeline/quebec/sentences.json") as f:
    qc_sents = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/sentences.json") as f:
    us_sents = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/us/predications.json") as f:
    us_preds = json.load(f)
with open(f"{REPO}/data/dbpedia_pipeline/quebec/predications.json") as f:
    qc_preds = json.load(f)

# Good Ontario examples with substantial content
ont_examples = []
for bk, dates in ont_clean.items():
    bnum = str(ont_idx.get(bk, {}).get("bill_number", ""))
    title = ont_idx.get(bk, {}).get("title", "")
    for date, paras in dates.items():
        if len(paras) >= 20:
            texts = [p if isinstance(p, str) else p.get("text", "") for p in paras]
            long = [t for t in texts if len(t) > 150]
            if len(long) >= 5:
                ont_examples.append((bk, bnum, title, date, paras))

ont_example = ont_examples[2] if len(ont_examples) > 2 else ont_examples[0]
ont_bk, ont_bnum, ont_title, ont_date, ont_paras = ont_example
ont_texts = [p if isinstance(p, str) else p.get("text", "") for p in ont_paras]

# Quebec example
qc_health_files = []
for f in qc_seg_files:
    fpath = f"{qc_seg_dir}/{f}"
    with open(fpath, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if len(text) > 500 and any(w in text.lower() for w in ["santé", "médecin", "soins"]):
        qc_health_files.append((f, text))

qc_example_file, qc_example_text = qc_health_files[3] if len(qc_health_files) > 3 else qc_health_files[0]
qc_date = qc_example_file[:8]
qc_date_fmt = f"{qc_date[:4]}-{qc_date[4:6]}-{qc_date[6:8]}"
qc_bill = re.search(r"bill(\d+)", qc_example_file)
qc_bill_num = qc_bill.group(1) if qc_bill else "?"

# US example
us_example_file = None
speeches_dir = f"{REPO}/data/us/congressional_record_speeches"
for fname in sorted(os.listdir(speeches_dir)):
    if fname.endswith(".txt") and fname[:4] > "2005":
        fpath = f"{speeches_dir}/{fname}"
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if len(text) > 2000 and "health" in text.lower() and "Daily Digest" not in text[:200]:
            us_example_file = fname
            us_example_text = text
            break

# Good predication examples
us_good_preds = [p for p in us_preds if len(p.get("subject","")) > 3 and len(p.get("object","")) > 5 
                 and p.get("verb_lemma","") not in ["be","have","do","get"] 
                 and len(p.get("full_text","")) > 50][:20]

qc_good_preds = [p for p in qc_preds if len(p.get("subject","")) > 3 and len(p.get("object","")) > 5
                 and p.get("verb_lemma","") not in ["être","avoir","faire"]
                 and len(p.get("full_text","")) > 50][:20]

# ── README ──────────────────────────────────────────────────────────────────

w("# Legislative Health Factuality")
w()
w("**Research question:** Does the factual accuracy of legislative health floor debate predict bill passage outcomes?")
w()
w("**Jurisdictions:** US House of Representatives, Ontario Legislative Assembly, Quebec National Assembly — 1985 to 2026")
w()
w("**Investigators:** Caprice Culkin (Yale School of Public Health) | David Chartash, Joanie Bouchard (advisors)")
w()

w("---")
w()
w("## Pipeline Overview")
w()
w("```mermaid")
w("flowchart LR")
w("    subgraph sources[Data Sources]")
w("        A[US: GovInfo API]")
w("        B[Ontario: OLA Azure Search API]")
w("        C[Quebec: assnat.qc.ca HTML]")
w("    end")
w()
w("    subgraph extract[Step 1 - Bill-Specific Extraction]")
w("        D[US Granules\n145 bill-dates\n584K sentences]")
w("        E[Ontario Orders of Day\n249 verified bills\n83K paragraphs]")
w("        F[Quebec Bill Segments\n2178 bill-date segments\n924K sentences]")
w("    end")
w()
w("    subgraph v2[Step 2 - Predication Extraction spaCy]")
w("        G[US Predications\n215K SVO triples\n36.9%]")
w("        H[Ontario Predications\nPending]")
w("        I[Quebec Predications\n178K SVO triples\n19.3%]")
w("    end")
w()
w("    subgraph spotlight[Step 3 - DBpedia Spotlight]")
w("        J[Runs on subject + object strings only\nNOT full sentences\nEN port 2222 / FR port 2223]")
w("    end")
w()
w("    subgraph sparql[Step 4 - SPARQL Verification]")
w("        K[Local Virtuoso\nEN + FR DBpedia\nlocalhost:8890]")
w("    end")
w()
w("    subgraph scores[Step 5 - Factuality Scores]")
w("        L[supported / total claim-bearing\nper bill-date]")
w("    end")
w()
w("    A --> D --> G --> J")
w("    B --> E --> H --> J")
w("    C --> F --> I --> J")
w("    J --> K --> L")
w("```")
w()

# ── STEP 1: DATA SOURCES ────────────────────────────────────────────────────
w("---")
w()
w("## Step 1: Bill-Specific Text Extraction")
w()
w("All three jurisdictions extract **floor/plenary debate text specific to each health bill only.**")
w("Question period, petitions, member statements, committee transcripts, and all other business")
w("on sitting days are excluded. This matches the US standard where GovInfo granules are")
w("bill-specific by construction.")
w()

# US
w("### United States — GovInfo Congressional Record Granules")
w()
w(f"**Source:** GovInfo API — `api.govinfo.gov/packages/`")
w(f"**Collection script:** [`scripts/congressional_record_pull.py`]({GITHUB}/scripts/congressional_record_pull.py)")
w(f"**Output:** `data/us/congressional_record_speeches/` — one `.txt` file per bill-date")
w()
w("Each GovInfo granule corresponds to one bill's floor debate. Bill-specific by construction —")
w("no extraction needed. Health bills identified via CRS policy area tags.")
w()
w(f"**N = 145 health bill-dates | 584,111 sentences**")
w()

if us_example_file:
    w(f"**Example:** [`data/us/congressional_record_speeches/{us_example_file}`]({GITHUB}/data/us/congressional_record_speeches/{us_example_file})")
    w()
    w("```")
    for line in us_example_text[:800].split("\n")[:15]:
        w(line)
    w("```")
    w()

# Ontario
w("### Ontario — OLA Azure Search API")
w()
w("**Source:** OLA Hansard Search backend — `aihansardsearch-apim.azure-api.net/api/search/keyword`")
w(f"**Collection script:** [`scripts/fetch_ontario_hansard_via_api.py`]({GITHUB}/scripts/fetch_ontario_hansard_via_api.py)")
w(f"**Cleaning script:** [`scripts/rebuild_clean_ontario.py`]({GITHUB}/scripts/rebuild_clean_ontario.py)")
w(f"**Output:** `data/canada/ontario/hansard_api_bill_segments_clean.json`")
w()
w("The OLA Hansard search tool uses an Azure Cognitive Search backend.")
w("I reverse-engineered the API endpoint from browser network traffic and built")
w("a scraper that queries each bill's debate dates with:")
w()
w("```")
w("filter: (date ge {date}T00:00:00Z and date le {date}T23:59:59Z)")
w("        and (typeOfBusiness eq 'ORDERS OF THE DAY'")
w("             or typeOfBusiness eq 'Orders of the Day')")
w("```")
w()
w("**Bill assignment:** paragraphs are assigned to a specific bill only when the bill number")
w("is explicitly mentioned in the paragraph text (e.g. 'Bill 94'). No topic fallback,")
w("no single-bill date fallback. Every paragraph in the output has been verified.")
w()
w("**What is excluded:**")
w("- Question Period / Oral Questions")
w("- Members' Statements")
w("- Petitions")
w("- Introduction of Bills (first reading)")
w("- Committee study transcripts")
w("- Paragraphs that do not mention the specific bill number")
w()

ont_total_paras = sum(len(p) for d in ont_clean.values() for p in d.values())
w(f"**N = {len(ont_clean)} verified bills | {ont_total_paras:,} paragraphs**")
w()
w(f"**Example:** Bill {ont_bnum} — {ont_title[:60]}")
w(f"Debate date: {ont_date} | {len(ont_paras)} paragraphs")
w()
w("```")
for t in ont_texts[:4]:
    if len(t) > 100:
        w(t[:400])
        w()
w("```")
w()

# Quebec
w("### Quebec — Journal des débats Section Markers")
w()
w("**Source:** Assemblée nationale du Québec — `assnat.qc.ca`")
w(f"**Collection script:** [`scripts/extract_quebec_bill_segments.py`]({GITHUB}/scripts/extract_quebec_bill_segments.py)")
w(f"**Raw transcripts:** `data/canada/quebec_assembly/transcripts/` — one `.txt` file per sitting day")
w(f"**Output:** `data/canada/quebec_assembly/bill_segments/` — one `.txt` file per bill-date")
w()
w("The Journal des débats uses structured section headers to mark when the Assembly")
w("takes up a specific bill. The extraction script identifies these headers and")
w("extracts only the text between the marker and the next section break.")
w()
w("**Section markers used:**")
w("```")
w("Étude du projet de loi n° X")
w("Adoption du principe du projet de loi n° X")
w("Reprise du débat sur l'adoption du principe du projet de loi n° X")
w("Prise en considération du rapport sur le projet de loi n° X")
w("Adoption du projet de loi n° X")
w("```")
w()
w("**What is excluded:**")
w("- Question period (période des questions)")
w("- Ministerial statements (déclarations ministérielles)")
w("- Petitions")
w("- Introduction of bills (dépôt de projets de loi)")
w("- Commission parlementaire transcripts (separate corpus — same as US excludes committee hearings)")
w("- All other business on sitting days not related to the specific bill")
w()

qc_total_segs = len(qc_seg_files)
w(f"**N = {qc_total_segs:,} bill-date segments | {len(qc_sents):,} sentences**")
w()
w(f"**Example:** Bill {qc_bill_num} — date {qc_date_fmt}")
w(f"[`data/canada/quebec_assembly/bill_segments/{qc_example_file}`]({GITHUB}/data/canada/quebec_assembly/bill_segments/{qc_example_file})")
w()
w("**Raw sitting day (before extraction) — 1995-12-04:**")
w("```")
w("DÉCLARATIONS DE DÉPUTÉS")
w("  Mme Carrier-Perreault: Je veux souligner le travail remarquable...")
w()
w("QUESTIONS ET RÉPONSES ORALES")
w("  M. Johnson: M. le Président, ma question s'adresse au premier ministre...")
w()
w("ÉTUDE DU PROJET DE LOI N° 130  ← section marker")
w("  M. Rochon: M. le Président, l'Assemblée nationale prend maintenant en")
w("  considération le projet de loi 130 sur les services de santé...")
w()
w("PÉTITIONS  ← excluded")
w("  M. Beaudet: Je dépose la pétition suivante...")
w("```")
w()
w("**After extraction — bill-specific segment only:**")
w("```")
for line in qc_example_text[:600].split("\n")[:12]:
    w(line)
w("```")
w()

# ── STEP 2: PREDICATION EXTRACTION ──────────────────────────────────────────
w("---")
w()
w("## Step 2: Predication Extraction (spaCy)")
w()
w("**Script:** [`scripts/extract_predications.py`]({GITHUB}/scripts/extract_predications.py)".format(GITHUB=GITHUB))
w("**Input:** `sentences.json` for each jurisdiction")
w("**Output:** `predications.json` — Subject-Verb-Object triples")
w()
w("Per David Chartash's September 11 2026 revision: spaCy's dependency parser extracts")
w("Subject-Verb-Object predications from each sentence BEFORE running DBpedia Spotlight.")
w("Spotlight then runs only on the subject and object strings, not the full sentence.")
w()
w("**Why this matters:**")
w()
w("```")
w("Old approach (v1):")
w("  Sentence: 'The OMA, which represents 30,000 physicians, endorsed this legislation.'")
w("  Spotlight on full sentence → entities: OMA, Physician, Legislation")
w("  Pairs: (OMA, Physician) ← confirmed by DBpedia, but NOT the claim being made")
w("         (OMA, Legislation) ← not in DBpedia")
w("         (Physician, Legislation) ← not in DBpedia")
w("  Problem: (OMA, Physician) is spuriously confirmed — it was in a relative clause")
w()
w("New approach (v2):")
w("  spaCy extracts: subject='OMA', verb='endorsed', object='legislation'")
w("  Spotlight runs on 'OMA' and 'legislation' only")
w("  Pair: (OMA, Legislation) → not in DBpedia → correctly unsupported")
w("  The relative clause entity 'physicians' is never included")
w("```")
w()
w("**What is excluded at this step:**")
w("- Sentences where the root verb is existential (be/have/do) — not factual claims")
w("- Sentences where no subject or no object is found")
w("- Entities found only in relative clauses or parentheticals")
w("- Subject equals object (trivial self-reference)")
w()
w("Hedged predicates (may/might/could/should/pourrait/devrait) are included but flagged.")
w()
w("**N counts:**")
w()
w(f"| Jurisdiction | Input sentences | Predications | Rate |")
w(f"|---|---|---|---|")
w(f"| US | {len(us_sents):,} | {len(us_preds):,} | {len(us_preds)/len(us_sents)*100:.1f}% |")
w(f"| Quebec | {len(qc_sents):,} | {len(qc_preds):,} | {len(qc_preds)/len(qc_sents)*100:.1f}% |")
w(f"| Ontario | (pipeline running) | (pending) | — |")
w()
w("Note: Quebec's lower rate (19.3% vs 36.9%) reflects fr_core_news_lg's lower recall")
w("for Quebec legislative French compared to en_core_web_lg for English.")
w()
w("**Sample US predications:**")
w("```")
for p in us_good_preds[:4]:
    w(f"Sentence: \"{p['full_text'][:100]}\"")
    w(f"  subject: \"{p['subject']}\"")
    w(f"  verb:    {p['verb_lemma']}")
    w(f"  object:  \"{p['object']}\"")
    if p.get("hedged"): w("  [hedged]")
    w()
w("```")
w()
w("**Sample Quebec predications:**")
w("```")
for p in qc_good_preds[:4]:
    w(f"Sentence: \"{p['full_text'][:100]}\"")
    w(f"  sujet:  \"{p['subject']}\"")
    w(f"  verbe:  {p['verb_lemma']}")
    w(f"  objet:  \"{p['object']}\"")
    w()
w("```")
w()

# ── STEP 3: SPOTLIGHT ───────────────────────────────────────────────────────
w("---")
w()
w("## Step 3: DBpedia Spotlight Entity Linking")
w()
w("**Script:** [`scripts/dbpedia_batch_pipeline.py`]({GITHUB}/scripts/dbpedia_batch_pipeline.py) — `extract_v2` stage".format(GITHUB=GITHUB))
w("**Infrastructure:** Dunkleosteus server (Yale) — English port 2222, French port 2223")
w("**SSH tunnel:** `ssh -i ~/.ssh/dunkleosteus_key -L 2222:localhost:2222 -L 2223:localhost:2223 cc3436@10.168.171.152`")
w()
w("Spotlight runs on the **subject string** and **object string** from each predication,")
w("not on the full sentence. Returns DBpedia URIs for each entity found.")
w()
w("```")
w("Input predication:")
w("  subject: 'Ontario Medical Association'")
w("  object:  'legislation'")
w()
w("Spotlight on 'Ontario Medical Association' →")
w("  dbpedia.org/resource/Ontario_Medical_Association")
w()
w("Spotlight on 'legislation' →")
w("  dbpedia.org/resource/Legislation")
w()
w("Entity pair: (Ontario_Medical_Association, Legislation)")
w("```")
w()
w("**What is excluded:**")
w("- Predications where Spotlight finds no entity for subject or object")
w("- Predications where subject and object link to the same entity")
w()

# ── STEP 4: SPARQL ──────────────────────────────────────────────────────────
w("---")
w()
w("## Step 4: SPARQL Verification")
w()
w("**Script:** [`scripts/dbpedia_batch_pipeline.py`]({GITHUB}/scripts/dbpedia_batch_pipeline.py) — `query` stage".format(GITHUB=GITHUB))
w("**Endpoint:** Local Virtuoso instance on Dunkleosteus — `http://localhost:8890/sparql`")
w("Both English DBpedia and French DBpedia loaded in same Virtuoso container.")
w()
w("For each unique entity pair, a SPARQL query checks whether DBpedia confirms")
w("a direct relationship between the two entities.")
w()
w("```sparql")
w("SELECT ?a ?b ?p WHERE {")
w("  VALUES (?a ?b) { (<URI_A> <URI_B>) }")
w("  { ?a ?p ?b } UNION { ?b ?p ?a }")
w("}")
w("```")
w()
w("**Supported example:**")
w("```")
w("Pair: (dbpedia:Canada, dbpedia:United_States)")
w("Result: dbo:neighboringMunicipality → supported = True")
w("```")
w()
w("**Not supported example:**")
w("```")
w("Pair: (dbpedia:Ontario_Medical_Association, dbpedia:Legislation)")
w("Result: [] → supported = False")
w("```")
w()
w("The OMA endorsing legislation is a rhetorical claim — not a fact DBpedia can verify.")
w("The relationship does not exist in the DBpedia knowledge graph.")
w()

# ── STEP 5: SCORES ──────────────────────────────────────────────────────────
w("---")
w()
w("## Step 5: Factuality Scores")
w()
w("**Script:** [`scripts/compute_factuality_scores.py`]({GITHUB}/scripts/compute_factuality_scores.py)".format(GITHUB=GITHUB))
w()
w("```")
w("factuality_score = supported_sentences / total_claim_bearing_sentences")
w("```")
w()
w("Where claim-bearing sentences are those where Spotlight found entities for")
w("both subject and object of the extracted predication.")
w()

# ── LARGE FILES ─────────────────────────────────────────────────────────────
w("---")
w()
w("## Large Data Files")
w()
w("Files exceeding GitHub's 100MB limit are excluded from version control.")
w("Regenerate using the scripts listed above.")
w()
w("| File | Size | Description | Script to regenerate |")
w("|---|---|---|---|")
w("| `data/canada/ontario/hansard_api_bill_segments_clean.json` | ~100MB | Ontario verified bill segments | `fetch_ontario_hansard_via_api.py` + `rebuild_clean_ontario.py` |")
w("| `data/canada/ontario/sentences_bill_specific_api.json` | 669MB | Ontario bill-specific sentences | `convert_ontario_api_segments_to_sentences.py` |")
w("| `data/dbpedia_pipeline/ontario/sentences.json` | 669MB | Ontario pipeline copy | copy from above |")
w("| `data/dbpedia_pipeline/quebec/sentences.json` | ~200MB | Quebec bill-specific sentences | `convert_quebec_segments_to_sentences.py` |")
w("| `data/dbpedia_pipeline/us/predications.json` | 86.8MB | US SVO predications | `extract_predications.py` |")
w("| `data/dbpedia_pipeline/quebec/predications.json` | 80.2MB | Quebec SVO predications | `extract_predications.py` |")
w()

# ── RESULTS ─────────────────────────────────────────────────────────────────
w("---")
w()
w("## Current Results (v1 pipeline, new bill-specific denominator)")
w()
w("Ontario v2 scores pending pipeline completion.")
w()
w("| Jurisdiction | Mean factuality | Passed bills | Failed bills |")
w("|---|---|---|---|")
w("| US | 0.2054 | 0.2094 (n=386) | 0.2015 (n=34) |")
w("| Quebec | 0.1387 | 0.1266 (n=767) | n/a |")
w("| Ontario | (pipeline running) | — | — |")
w()
w("**COVID natural experiment (pre/post March 2020):**")
w("- US: −0.036 post-COVID")
w("- Quebec: −0.053 post-COVID")
w()
w("**Logistic regression (US + Quebec):** factuality coefficient +0.0467 (p < 0.05)")
w()

out = f"{REPO}/README.md"
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Saved to {out}")
