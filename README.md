# Legislative Health Factuality

> **Status, Nov 17, 2026:** This README describes the first pipeline (August and September). The current pipeline, and how to run and replicate it, is in `REPLICATION.md` and `REPO_MAP.md`.

**Research question:** Does the factual accuracy of legislative health debate predict bill passage outcomes?

**Study:** Comparative analysis across the US House of Representatives, Ontario Legislative Assembly, and Quebec National Assembly from 1985 to 2026.

**Investigators:** Caprice Culkin (Yale School of Public Health) — David Chartash, Joanie Bouchard (advisors)

**Repository:** `github.com/capriceculkin/legislative-health-factuality`

---

## Research Design

For each health-related bill in each legislature, we extract the floor debate text, link named entities to DBpedia using NLP, verify relationships via SPARQL, and compute a per-bill factuality score. We then test whether factuality predicts bill passage using logistic regression.

**Hypothesis:** Bills with higher factual accuracy in floor debate are more likely to pass.

---

## Data Sources

### United States House of Representatives

Source: GovInfo Congressional Record (CREC) granules via the GovInfo API
URL: `https://api.govinfo.gov/packages/`

Each granule is a single bill's floor debate — bill-specific by definition. No extraction needed. We query the GovInfo API for all health-related CREC granules from 1985 to 2026.

Health bill identification: bills tagged with health-related policy areas in the GovInfo package metadata (e.g., HEALTH, MEDICINE, PUBLIC HEALTH, MEDICAL CARE).

    Total health bill-dates collected: 145
    Date range: 1985 to 2026
    Source format: plain text, one file per bill-date

**Sample granule (2020-03-14):**

    Mr. PALLONE. Mr. Speaker, I rise today in support of H.R. 6201, the Families
    First Coronavirus Response Act. This legislation provides free COVID-19 testing,
    guarantees paid sick leave and family and medical leave, strengthens food
    security initiatives, and increases federal Medicaid funding...

### Ontario Legislative Assembly

Source: OLA Azure Search API
URL: `https://aihansardsearch-apim.azure-api.net/api/search/keyword`

The OLA Hansard search tool uses an Azure Cognitive Search backend that indexes all Ontario Hansard from 1974 to present. We query the API for each health bill's debate dates, filtering to `typeOfBusiness eq 'ORDERS OF THE DAY'` or `typeOfBusiness eq 'Orders of the Day'` (capitalization varies by era).

Bill identification: Ontario health bill index built from OLA bill registry, cross-referenced with HuggingFace `a2aj/hansard` dataset for session/parliament metadata.

Bill assignment: paragraphs are assigned to specific bills using (1) bill number mention in paragraph text, (2) topic keyword overlap with bill title, (3) single-bill date fallback. Private members' bills debated under 'Private Members' Public Business' are also included.

    Total health bills in index: 329
    Bills with floor debate recovered: 327 (99.4%)
    Bills excluded (no floor debate confirmed): 2
    Reason for exclusion: first reading only (private members' bills never called for second reading)
    Total paragraphs collected: 168,672
    Date range: 1985 to 2026

**Sample paragraph (2009-04-02, Bill 104 — Personal Health Information Protection Act):**

    Mr. Khalil Ramal (London-Fanshawe): I'm very proud to stand up today and speak
    on behalf of Bill 104, An Act to amend the Personal Health Information Protection
    Act, 2004. This bill will strengthen privacy protections for patients' health
    information across Ontario's health system...

### Quebec National Assembly

Source: Assemblée nationale du Québec — Journal des débats
URL: `https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/`

The Quebec Journal des débats uses structured section headers to mark when the Assembly takes up a specific bill. We download full transcript HTML files and extract text between bill-specific markers.

**Section markers used:**

    Étude du projet de loi n° X
    Adoption du principe du projet de loi n° X
    Reprise du débat sur l'adoption du principe du projet de loi n° X
    Prise en considération du rapport sur le projet de loi n° X
    Adoption du projet de loi n° X

What is excluded: question period (période des questions), ministerial statements (déclarations ministérielles), petitions, introduction of bills (dépôt de projets de loi), and any other business on sitting days that is not about the specific bill. Committee study transcripts (commission parlementaire) are in a separate corpus and are not included — consistent with the US approach of using floor debate only.

    Total bill-date segments extracted: 8,236
    Unique bills with segments: 373
    Date range: 1985 to 2026

**Sample segment (Bill 130, 1995-12-04):**

    plus tôt aujourd'hui sur l'adoption du principe du projet de loi n° 28,
     Loi visant à mettre fin à l'état d'urgence sanitaire. M. le député de Robert-Baldwin,
     je vous cède la parole.
    
    M. Carlos J. Leitão

---

## Pipeline

The pipeline has six stages. Below, we trace how the data transforms at each stage, with exact N counts and example sentences showing how the input and output differ.

---

### Stage 1: Raw transcript text

Starting point: the raw legislative text for each jurisdiction, before any extraction.

    US:      145 granule files (one per health bill-date) — already bill-specific
    Ontario: 168,672 paragraphs across 327 bills (extracted from OLA API)
    Quebec:  8,236 bill-date segments (extracted using section markers)

**What a raw Quebec sitting day looks like (before extraction):**

    [1995-12-04, full sitting day — 8,400 words]

    DÉCLARATIONS DE DÉPUTÉS
    Mme Carrier-Perreault: Je veux souligner le travail remarquable...

    QUESTIONS ET RÉPONSES ORALES
    M. Johnson: M. le Président, ma question s'adresse au premier ministre...

    ÉTUDE DU PROJET DE LOI N° 130
    M. Rochon: M. le Président, l'Assemblée nationale prend maintenant en
    considération le projet de loi 130 sur les services de santé et les services
    sociaux. Ce projet de loi vise à moderniser notre réseau de santé...

    PÉTITIONS
    M. Beaudet: Je dépose la pétition suivante de citoyens de ma circonscription...

After extraction: only the 'ÉTUDE DU PROJET DE LOI N° 130' section is kept.
Removed: declarations, oral questions, petitions, all other business.

---

### Stage 2: Sentence tokenization

Each bill-specific text block is split into sentences using spaCy. Short sentences (under 20 characters) are removed.

    US:      584,111 sentences
    Ontario: 1,942,246 sentences (pipeline running)
    Quebec:  923,634 sentences

**Example — one paragraph becomes multiple sentences:**

    Input paragraph:
    'The government has proposed Bill 104 to strengthen patient privacy. This
    legislation will require hospitals to obtain explicit consent before sharing
    health records. The Ontario Medical Association has endorsed this approach.'

    Output sentences:
    [1] 'The government has proposed Bill 104 to strengthen patient privacy.'
    [2] 'This legislation will require hospitals to obtain explicit consent
         before sharing health records.'
    [3] 'The Ontario Medical Association has endorsed this approach.'

Each sentence record includes:

    {
      "sentence_id": "20090402-api-2009b104-p3-s2",
      "date": "2009-04-02",
      "text": "The Ontario Medical Association has endorsed this approach.",
      "speaker": "Mr. Khalil Ramal (London-Fanshawe)",
      "party": "Ontario Liberal Party",
      "is_minister": false,
      "bill_key": "2009-Bill104",
      "source": "ola_api"
    }

---

### Stage 3: DBpedia Spotlight entity linking (DB1 — claim-bearing sentences)

Each sentence is sent to DBpedia Spotlight, which identifies named entities and links them to DBpedia URIs. Sentences where Spotlight finds two or more distinct entities are called 'claim-bearing' and enter DB1. Sentences with zero or one entity are counted in the denominator but cannot be verified against DBpedia.

    US:      376,347 claim-bearing sentences (64.4% of total)
    Ontario: (pipeline running)
    Quebec:  334,522 claim-bearing sentences (36.2% of total)

**What is excluded at this stage:**

    Single-entity sentences (~60%): Spotlight finds only one entity — cannot form a
    verifiable subject-object pair. Example:
    'I would like to acknowledge the work of the Ontario Medical Association.'
    → entity: Ontario_Medical_Association (only one) → excluded from DB1

    Zero-entity sentences (~25%): No named entities found. Example:
    'We need to do more to protect the health of our communities.'
    → no DBpedia entities → excluded from DB1

**What enters DB1 — example:**

    'The Ontario Medical Association has endorsed this legislation.'
    → entities: Ontario_Medical_Association, Legislation
    → concept pair: (Ontario_Medical_Association, Legislation)
    → sentence_id: 20090402-api-2009b104-p3-s2
    → enters DB1 ✓

    'Le gouvernement a modifié la Loi sur les services de santé et services sociaux.'
    → entities: Gouvernement_du_Québec, Loi_sur_les_services_de_santé_et_les_services_sociaux
    → concept pair: (Gouvernement_du_Québec, Loi_sur_les_services_de_santé)
    → enters DB1 ✓

Spotlight endpoints:
    English (US + Ontario): spotlight-en on Dunkleosteus, port 2222
    French (Quebec): spotlight-fr on Dunkleosteus, port 2223
    Accessed via SSH tunnel: ssh -L 2222:localhost:2222 -L 2223:localhost:2223

---

### Stage 4: Deduplication

Many sentences reference the same pair of concepts. We deduplicate to avoid querying DBpedia for the same pair multiple times. This dramatically reduces the number of SPARQL queries needed.

    US:      376,347 claim-bearing sentences → 313,705 unique concept pairs (83.4% reduction)
    Ontario: (pipeline running)
    Quebec:  334,522 claim-bearing sentences → 130,691 unique concept pairs (39.1% reduction)

**Example — why deduplication matters:**

    Sentence 1: 'The Ontario Medical Association endorsed Bill 104.'
    Sentence 2: 'Bill 104 was supported by the Ontario Medical Association.'
    Sentence 3: 'The OMA has long supported this type of legislation.'

    All three produce the same concept pair:
    (Ontario_Medical_Association, Legislation)

    DBpedia is queried once for this pair, and the result applies to all three sentences.

---

### Stage 5: SPARQL / DBpedia verification

For each unique concept pair, we query DBpedia via SPARQL to check whether a direct relationship exists between the two entities in the DBpedia knowledge graph. If DBpedia confirms a relationship, the sentence is marked as 'supported.'

SPARQL endpoint: local Virtuoso instance on Dunkleosteus (`http://localhost:8890/sparql` via SSH tunnel)
English DBpedia and French DBpedia are both loaded in the same Virtuoso container.

**Query template:**

    SELECT ?a ?b ?p WHERE {
      VALUES (?a ?b) { (<URI_A> <URI_B>) }
      { ?a ?p ?b } UNION { ?b ?p ?a }
    }

**Example — supported:**

    Pair: (dbpedia:Canada, dbpedia:United_States)
    Result: dbo:neighboringMunicipality → supported = True

    Pair: (dbpedia:Ontario_Medical_Association, dbpedia:Physician)
    Result: dbo:type → supported = True

**Example — not supported:**

    Pair: (dbpedia:Ontario_Medical_Association, dbpedia:Legislation)
    Result: [] → supported = False

    This is the key distinction: the OMA endorsing legislation is a rhetorical
    claim, not a fact DBpedia can verify. The relationship doesn't exist in the
    DBpedia knowledge graph.

    US:      58,979 supported / 376,347 claim-bearing = 15.7% support rate
    Ontario: (pipeline running)
    Quebec:  43,004 supported / 334,522 claim-bearing = 12.9% support rate

Note on the support rate: roughly 10-15% of claim-bearing sentences are supported by DBpedia. This is expected. Legislative speech is primarily rhetorical and argumentative, not factual in the DBpedia sense. The support rate reflects the proportion of verifiable factual claims embedded in debate. David Chartash's framing: the remaining ~90% represents the procedural and rhetorical content that the parliamentary speech and rhetoric literature would predict — the denominator is meaningful precisely because it captures this mix.

---

### Stage 6: Factuality score computation

For each health bill, the factuality score is computed as:

    factuality_score = supported_sentences / total_claim_bearing_sentences

Where 'total_claim_bearing_sentences' is the count of sentences in DB1 for that bill (sentences with two or more DBpedia entities identified by Spotlight).

**Example bill scores:**

    US 1988-07-12: score=0.092 (181 supported / 1962 claim-bearing) — 
    US 2020-02-06: score=0.153 (33 supported / 215 claim-bearing) — Passed
    US 2003-06-19: score=0.251 (57 supported / 227 claim-bearing) — Passed

    Quebec 2005-06-08: score=0.142 (18 supported / 127 claim-bearing)
    Quebec 2003-12-09: score=0.086 (77 supported / 896 claim-bearing)
    Quebec 1996-12-10: score=0.166 (96 supported / 577 claim-bearing)

---

## Results

Ontario results are pending pipeline completion. US and Quebec results below.

### Factuality and bill passage

    US passed bills:  mean factuality = 0.2094 (n=386)
    US failed bills:  mean factuality = 0.2015 (n=34)
    Quebec passed:    mean factuality = 0.1253 (n=775)
    Ontario:          (pipeline running)

    Logistic regression (US + Quebec, controlling for jurisdiction):
    Factuality coefficient: +0.0467 (higher factuality → more likely to pass, p < 0.05)

### COVID natural experiment (pre/post March 2020)

    US:     pre-COVID mean = 0.2142, post-COVID mean = 0.1780 (−0.036)
    Quebec: pre-COVID mean = 0.1394, post-COVID mean = 0.0868 (−0.053)
    Both jurisdictions show decreased factuality post-COVID — consistent with
    emergency legislative conditions reducing deliberation quality.

### Political era analysis — Quebec

    PQ 1994-2003:       0.1353 (n=167)
    Liberal 2003-2012:  0.1421 (n=169)
    PQ minority 2012-2014: 0.1773 (n=57) — highest
    Liberal 2014-2018:  0.1413 (n=115)
    CAQ 2018-present:   0.0933 (n=259) — lowest

---

## Denominator standardization

A critical methodological decision is the denominator: what text counts as 'the debate about this bill.'

All three jurisdictions use the same definition: floor/plenary debate text specific to each bill, excluding committee study transcripts, question period, and all other legislative business.

    US:      GovInfo granules are bill-specific by construction — each file is one
             bill's Congressional Record floor debate. No extraction needed.
             Coverage: 100%

    Ontario: OLA Azure Search API, filtered to Orders of the Day on each bill's
             debate dates, assigned to specific bills by number/topic matching.
             Coverage: 327/329 bills (99.4%)
             Excluded: 2 bills had first reading only (no floor debate confirmed
             via myparliament.ca)

    Quebec:  Section marker extraction from Journal des débats HTML files.
             Markers: 'Étude du projet de loi', 'Adoption du principe',
             'Reprise du débat', 'Prise en considération', 'Adoption'.
             Coverage: 100% of scored bill-dates have bill-specific segments.

---

## Reproducibility

### Requirements

    Python 3.10+
    pip install -r requirements.txt
    Access to Dunkleosteus server (Yale VPN required)
    HuggingFace account (for a2aj/hansard dataset)
    GovInfo API key

### Key scripts

    scripts/fetch_ontario_hansard_via_api.py    Fetch Ontario bill-specific text from OLA API
    scripts/convert_ontario_api_segments_to_sentences.py  Convert to sentences format
    scripts/extract_quebec_bill_segments.py     Extract Quebec bill segments from transcripts
    scripts/convert_quebec_segments_to_sentences.py  Convert to sentences format
    scripts/dbpedia_batch_pipeline.py           Main pipeline (extract/dedupe/query/annotate)
    scripts/compute_factuality_scores.py        Compute per-bill scores
    scripts/run_analyses.py                     Full analysis (regression, COVID, era)
    scripts/build_validation_doc.py             Generate transcript division samples

### Pipeline commands

    # Ontario
    python3 scripts/fetch_ontario_hansard_via_api.py
    python3 scripts/convert_ontario_api_segments_to_sentences.py
    cp data/canada/ontario/sentences_bill_specific_api.json data/dbpedia_pipeline/ontario/sentences.json
    JURISDICTION=ontario python3 scripts/dbpedia_batch_pipeline.py extract
    JURISDICTION=ontario python3 scripts/dbpedia_batch_pipeline.py dedupe
    JURISDICTION=ontario python3 scripts/dbpedia_batch_pipeline.py query
    JURISDICTION=ontario python3 scripts/dbpedia_batch_pipeline.py annotate
    JURISDICTION=ontario python3 scripts/compute_factuality_scores.py

    # Quebec
    python3 scripts/extract_quebec_bill_segments.py
    python3 scripts/convert_quebec_segments_to_sentences.py
    cp data/canada/quebec_bills/sentences_bill_specific.json data/dbpedia_pipeline/quebec/sentences.json
    JURISDICTION=quebec python3 scripts/dbpedia_batch_pipeline.py extract
    JURISDICTION=quebec python3 scripts/dbpedia_batch_pipeline.py dedupe
    JURISDICTION=quebec python3 scripts/dbpedia_batch_pipeline.py query
    JURISDICTION=quebec python3 scripts/dbpedia_batch_pipeline.py annotate
    JURISDICTION=quebec python3 scripts/compute_factuality_scores.py

    # Analysis
    python3 scripts/run_analyses.py
    python3 scripts/build_validation_doc.py
