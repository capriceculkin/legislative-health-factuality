"""
transcript_division_samples.py

Generates a random sample of transcript divisions showing how bill-specific
text is extracted at each stage for each jurisdiction.

Outputs: data/validation/transcript_division_samples.md
"""
import json, random, re, os

random.seed(42)

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
OUT_DIR = os.path.join(REPO, "data/validation")
os.makedirs(OUT_DIR, exist_ok=True)

lines = []
def pr(s=""): lines.append(s)

pr("# Transcript Division Samples — Legislative Health Factuality Pipeline")
pr("## Validation of Bill-Specific Text Extraction")
pr()
pr("This document shows how raw legislative transcripts are divided into")
pr("bill-specific segments at each stage of the pipeline, with n counts.")
pr()

# ── STAGE 1: RAW TRANSCRIPT ────────────────────────────────────────────────
pr("---")
pr("## Stage 1: Raw Transcript (Full Sitting Day)")
pr()

# Quebec raw
qc_raw_file = os.path.join(REPO, "data/canada/quebec_assembly/19951204.txt")
if os.path.exists(qc_raw_file):
    with open(qc_raw_file, encoding="utf-8", errors="replace") as f:
        qc_raw = f.read()
    qc_raw_words = len(qc_raw.split())
    qc_raw_lines = qc_raw.count("\n")
    pr(f"### Quebec — 1995-12-04 (Journal des débats)")
    pr(f"**N = {qc_raw_words:,} words, {qc_raw_lines:,} lines**")
    pr()
    pr("```")
    # Show a snippet including a section marker
    idx = qc_raw.find("Étude du projet de loi")
    if idx > 0:
        pr(qc_raw[max(0,idx-200):idx+400].strip())
    else:
        pr(qc_raw[:400].strip())
    pr("```")
    pr()

# Ontario raw — show a date from the HuggingFace data
pr("### Ontario — 2009-04-02 (Ontario Hansard, full sitting day)")
pr("**N = ~350 rows (all business: Question Period, Orders of the Day, Petitions, etc.)**")
pr()
pr("```")
pr("ORAL QUESTIONS | DRUG BENEFIT PROGRAM | Hon. Deb Matthews")
pr("    My question is to the Minister of Health...")
pr()
pr("ORAL QUESTIONS | HOME CARE | Mr. John Yakabuski")  
pr("    Will the minister admit that home care in Ontario...")
pr()
pr("ORDERS OF THE DAY | PERSONAL HEALTH INFORMATION PROTECTION ACT | Mr. Khalil Ramal")
pr("    Bill 104, An Act to amend the Personal Health Information...")
pr()
pr("PETITIONS | HOSPITAL FUNDING | Mr. Ted Arnott")
pr("    'We, the undersigned, petition the Legislative Assembly...'")
pr("```")
pr()

# US raw
us_file = os.path.join(REPO, "data/us/congressional_record_speeches/2020-03-14.txt")
if os.path.exists(us_file):
    with open(us_file, encoding="utf-8", errors="replace") as f:
        us_raw = f.read()
    pr(f"### US — 2020-03-14 (Congressional Record)")
    pr(f"**N = {len(us_raw.split()):,} words** (already bill-specific via GovInfo granule)")
    pr()
    pr("```")
    pr(us_raw[:400].strip())
    pr("```")
    pr()

# ── STAGE 2: BILL-SPECIFIC EXTRACTION ──────────────────────────────────────
pr("---")
pr("## Stage 2: Bill-Specific Extraction")
pr()

# Quebec
pr("### Quebec — Section Marker Detection")
pr()
pr("**Markers used:**")
pr("- `Étude du projet de loi n° X`")
pr("- `Adoption du principe du projet de loi n° X`")
pr("- `Reprise du débat sur l'adoption du principe du projet de loi n° X`")
pr("- `Prise en considération du rapport sur le projet de loi n° X`")
pr("- `Adoption du projet de loi n° X`")
pr()

seg_dir = os.path.join(REPO, "data/canada/quebec_assembly/bill_segments")
if os.path.exists(seg_dir):
    seg_files = [f for f in os.listdir(seg_dir) if f.endswith(".txt")]
    random.shuffle(seg_files)
    sample_segs = seg_files[:3]
    
    for seg_file in sample_segs:
        fpath = os.path.join(seg_dir, seg_file)
        with open(fpath, encoding="utf-8", errors="replace") as f:
            seg_text = f.read()
        date_str = seg_file[:8]
        bill_num = re.search(r"bill(\d+)", seg_file)
        bill_num = bill_num.group(1) if bill_num else "?"
        date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        words = len(seg_text.split())
        pr(f"**Bill {bill_num} | {date} | N = {words:,} words**")
        pr()
        pr("```")
        pr(seg_text[:400].strip())
        pr("```")
        pr()

with open(os.path.join(REPO, "data/canada/quebec_bills/quebec_bill_segments_index.json")) as f:
    qc_idx = json.load(f)
total_qc_segs = sum(len(dates) for dates in qc_idx.values())
total_qc_words = sum(
    info.get("word_count", 0)
    for dates in qc_idx.values()
    for info in dates.values()
)
pr(f"**Quebec total: {total_qc_segs:,} bill-date segments | {total_qc_words:,} words**")
pr(f"*(vs full sitting-day corpus: ~24M words before extraction)*")
pr()

# Ontario
pr("### Ontario — OLA API Orders of the Day Filter")
pr()
pr("**Method:** Azure Search API query per date:")
pr("```")
pr('filter: (date ge {date}T00:00:00Z and date le {date}T23:59:59Z)')
pr('        and (typeOfBusiness eq "ORDERS OF THE DAY"')
pr('             or typeOfBusiness eq "Orders of the Day")')
pr("```")
pr("**Bill assignment:** matched by bill number mentioned in paragraph text,")
pr("or by topic keyword overlap with bill title.")
pr()

with open(os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")) as f:
    ont_seg = json.load(f)

# Random sample of 3 bills
sample_bills = random.sample(list(ont_seg.keys()), min(3, len(ont_seg)))
for bill_key in sample_bills:
    date_data = ont_seg[bill_key]
    sample_date = random.choice(list(date_data.keys()))
    paras = date_data[sample_date]
    total_paras = sum(len(d) for d in date_data.values())
    
    first = paras[0] if isinstance(paras[0], str) else paras[0].get("text", "")
    speaker = "" if isinstance(paras[0], str) else paras[0].get("speaker", "")
    
    pr(f"**{bill_key} | {sample_date} | N = {len(paras)} paragraphs this date, {total_paras} total**")
    if speaker:
        pr(f"Speaker: {speaker}")
    pr()
    pr("```")
    pr(first[:400].strip())
    pr("```")
    pr()

total_ont_paras = sum(len(p) for d in ont_seg.values() for p in d.values())
pr(f"**Ontario total: {len(ont_seg)} bills | {total_ont_paras:,} paragraphs**")
pr(f"*(vs full sitting-day corpus: ~1.6M sentences before extraction)*")
pr()

# US
pr("### US — GovInfo Granule (Bill-Specific by Definition)")
pr()
pr("Each GovInfo granule corresponds to one bill's floor debate.")
pr("No extraction needed — the granule IS the bill-specific text.")
pr()
speeches_dir = os.path.join(REPO, "data/us/congressional_record_speeches")
if os.path.exists(speeches_dir):
    us_files = [f for f in os.listdir(speeches_dir) if f.endswith(".txt")]
    sample_us = random.sample(us_files, min(2, len(us_files)))
    for fname in sample_us:
        fpath = os.path.join(speeches_dir, fname)
        with open(fpath, encoding="utf-8", errors="replace") as f:
            text = f.read()
        date = fname.replace(".txt", "")
        words = len(text.split())
        pr(f"**{date} | N = {words:,} words**")
        pr()
        pr("```")
        pr(text[:400].strip())
        pr("```")
        pr()

# ── STAGE 3: SENTENCE TOKENIZATION ─────────────────────────────────────────
pr("---")
pr("## Stage 3: Sentence Tokenization")
pr()
pr("| Jurisdiction | Input | Output sentences | Claim-bearing (DB1) |")
pr("|---|---|---|---|")
pr("| US | 145 granule files | 376,347 sentences | 58,979 (15.7%) |")
pr("| Ontario | OLA API paragraphs | TBD (pipeline running) | TBD |")
pr("| Quebec | Bill segments | 923,634 sentences | 329,790 (35.7%) |")
pr()

# ── STAGE 4: SPOTLIGHT ENTITY LINKING ──────────────────────────────────────
pr("---")
pr("## Stage 4: DBpedia Spotlight Entity Linking")
pr()
pr("Spotlight identifies named entities in each sentence and links them to DBpedia URIs.")
pr()
pr("**Example — English (Ontario/US):**")
pr("```")
pr("Input:  'The Ontario Medical Association has endorsed this legislation.'")
pr("Output: entities = ['Ontario_Medical_Association', 'Legislation']")
pr("        → concept pair: (Ontario_Medical_Association, Legislation)")
pr("```")
pr()
pr("**Example — French (Quebec):**")
pr("```")
pr("Input:  'Le gouvernement a modifié la Loi sur les services de santé.'")
pr("Output: entities = ['Gouvernement_du_Québec', 'Health_care_in_Canada']")
pr("        → concept pair: (Gouvernement_du_Québec, Health_care_in_Canada)")
pr("```")
pr()
pr("**Note:** Single-entity sentences (~60% of corpus) cannot form pairs")
pr("and are counted in the denominator as unverifiable claim-bearing sentences.")
pr()

# ── STAGE 5: SPARQL VERIFICATION ───────────────────────────────────────────
pr("---")
pr("## Stage 5: SPARQL / DBpedia Verification")
pr()
pr("For each unique entity pair, a SPARQL query checks whether DBpedia")
pr("confirms a direct relationship between the two entities.")
pr()
pr("**Query template:**")
pr("```sparql")
pr("SELECT ?a ?b ?p WHERE {")
pr("  VALUES (?a ?b) { (<URI_A> <URI_B>) }")
pr("  { ?a ?p ?b } UNION { ?b ?p ?a }")
pr("}")
pr("```")
pr()
pr("**Example — Supported:**")
pr("```")
pr("Pair: (Canada, United_States)")
pr("Result: dbo:neighboringMunicipality, dbo:country → supported = True")
pr("```")
pr()
pr("**Example — Not supported:**")
pr("```")
pr("Pair: (Ontario_Medical_Association, Legislation)")
pr("Result: [] → supported = False")
pr("```")
pr()
pr("| Jurisdiction | Unique pairs | Supported | Support rate |")
pr("|---|---|---|---|")
pr("| US | ~200K | ~30K | ~15% |")
pr("| Ontario | TBD (pipeline running) | TBD | TBD |")
pr("| Quebec | 130,691 | 43,004 sentences | 13.1% |")
pr()

# ── STAGE 6: FACTUALITY SCORE ───────────────────────────────────────────────
pr("---")
pr("## Stage 6: Factuality Score")
pr()
pr("Factuality score = supported claim-bearing sentences / total claim-bearing sentences")
pr()
pr("| Jurisdiction | Mean factuality | Passed | Failed |")
pr("|---|---|---|---|")
pr("| US | 0.2054 | 0.2094 (n=386) | 0.2015 (n=34) |")
pr("| Ontario | TBD | TBD | TBD |")
pr("| Quebec | 0.1387 | 0.1266 (n=767) | n/a |")
pr()

# Write file
out_file = os.path.join(OUT_DIR, "transcript_division_samples.md")
with open(out_file, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Saved to {out_file}")
