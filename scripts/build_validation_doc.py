"""
build_validation_doc.py  (v3 — full detail, real examples, all pipeline decisions)

Every major methodological decision is documented with:
  - The n at that step
  - What was excluded and why (with real example sentences)
  - What had manual review and what Joanie/David said
  - Where to look in the repo

One English (Ontario) and one French (Quebec) sentence carried through all stages.

Output: data/validation/transcript_division_samples.md
"""

import json, os, re, random, unicodedata
from collections import Counter, defaultdict

random.seed(42)
REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
OUT_DIR = os.path.join(REPO, "data/validation")
os.makedirs(OUT_DIR, exist_ok=True)

lines = []
def pr(*args): lines.append(" ".join(str(a) for a in args))
def blank(): lines.append("")
def section(t): blank(); pr(f"## {t}"); blank()
def sub(t): blank(); pr(f"### {t}"); blank()
def subsub(t): blank(); pr(f"#### {t}"); blank()
def code(t): pr("```"); pr(t.strip()); pr("```"); blank()
def fpath(p): pr(f"_File: `{os.path.relpath(p, REPO)}`_"); blank()

def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None

# ── load all data ─────────────────────────────────────────────────────────────

qc_seg_dir    = os.path.join(REPO, "data/canada/quebec_assembly/bill_segments")
qc_idx        = load(os.path.join(REPO, "data/canada/quebec_bills/quebec_bill_segments_index.json")) or {}
qc_sentences  = load(os.path.join(REPO, "data/dbpedia_pipeline/quebec/sentences.json")) or []
qc_db1        = load(os.path.join(REPO, "data/dbpedia_pipeline/quebec/db1_claim_bearing.json")) or []
qc_pairs      = load(os.path.join(REPO, "data/dbpedia_pipeline/quebec/unique_pairs.json")) or []
qc_annotated  = load(os.path.join(REPO, "data/dbpedia_pipeline/quebec/annotated_sentences.json")) or []
qc_supported  = sum(1 for s in qc_annotated if s.get("supported"))
qc_scores     = load(os.path.join(REPO, "data/dbpedia_pipeline/quebec/factuality_scores.json")) or {}

ont_seg       = load(os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")) or {}
ont_idx       = load(os.path.join(REPO, "data/canada/ontario/ontario_bill_index.json")) or {}
ont_sentences = load(os.path.join(REPO, "data/dbpedia_pipeline/ontario/sentences.json")) or []
ont_triples_path = os.path.join(REPO, "data/dbpedia_pipeline/ontario/triples.json")
ont_triples_cp   = os.path.join(REPO, "data/dbpedia_pipeline/ontario/triples.json.checkpoint")
ont_annotated = load(os.path.join(REPO, "data/dbpedia_pipeline/ontario/annotated_sentences.json")) or []
ont_pairs     = load(os.path.join(REPO, "data/dbpedia_pipeline/ontario/unique_pairs.json")) or []
ont_scores    = load(os.path.join(REPO, "data/dbpedia_pipeline/ontario/factuality_scores.json")) or {}
ont_supported = sum(1 for s in ont_annotated if s.get("supported"))
ont_total_paras = sum(len(p) for d in ont_seg.values() for p in d.values())

# Ontario extract progress
ont_triples_n = "PENDING"
if os.path.exists(ont_triples_path):
    t = load(ont_triples_path) or []
    ont_triples_n = f"{len(t):,}" if isinstance(t, list) else "see file"
elif os.path.exists(ont_triples_cp):
    t = load(ont_triples_cp) or []
    if isinstance(t, list):
        ont_triples_n = f"~{len(t):,} (in progress)"

us_sentences  = load(os.path.join(REPO, "data/dbpedia_pipeline/us/sentences.json")) or []
us_db1        = load(os.path.join(REPO, "data/dbpedia_pipeline/us/db1_claim_bearing.json")) or []
us_pairs      = load(os.path.join(REPO, "data/dbpedia_pipeline/us/unique_pairs.json")) or []
us_annotated  = load(os.path.join(REPO, "data/dbpedia_pipeline/us/annotated_sentences.json")) or []
us_supported  = sum(1 for s in us_annotated if s.get("supported"))
us_scores     = load(os.path.join(REPO, "data/dbpedia_pipeline/us/factuality_scores.json")) or {}

# ── pick example sentences ───────────────────────────────────────────────────

pool_en = [s for s in (ont_annotated or us_annotated)
           if s.get("supported") and len(s.get("text","")) > 80 and len(s.get("concept_uris",[])) >= 2]
random.shuffle(pool_en)
EN = pool_en[0] if pool_en else None

pool_fr = [s for s in qc_annotated
           if s.get("supported") and len(s.get("text","")) > 80 and len(s.get("concept_uris",[])) >= 2]
random.shuffle(pool_fr)
FR = pool_fr[0] if pool_fr else None

# ── n helpers ────────────────────────────────────────────────────────────────

def pn(label, us, ont, qc):
    pr(f"**{label}**")
    pr(f"    US:      {us}")
    pr(f"    Ontario: {ont}")
    pr(f"    Quebec:  {qc}")
    blank()

ont_s = f"{len(ont_sentences):,}" if ont_sentences else "PENDING"
ont_a = f"{len(ont_annotated):,}" if ont_annotated else "PENDING"
ont_p = f"{len(ont_pairs):,}" if ont_pairs else "PENDING"
ont_sc = f"{len(ont_scores):,}" if ont_scores else "PENDING"
ont_supp = f"{ont_supported:,}" if ont_annotated else "PENDING"

# ════════════════════════════════════════════════════════════════════════════
# DOCUMENT
# ════════════════════════════════════════════════════════════════════════════

pr("# Transcript Division Validation")
pr("## Legislative Health Factuality — Full Pipeline Documentation")
blank()
pr(f"Repo: `{REPO}`  |  Generated: run `python3 scripts/build_validation_doc.py` to refresh")
blank()
pr("This document provides exhaustive documentation of every pipeline stage:")
pr("what enters, what is excluded and why, what had manual review, and where to")
pr("find the data. One English sentence (Ontario) and one French sentence (Quebec)")
pr("are carried through every stage so the transformation is concrete.")

# ═══════════════════════════════════════════════════════════════════════════
section("0. Two Sentences Carried Through the Entire Pipeline")
# ═══════════════════════════════════════════════════════════════════════════

pr("These appear at every stage below.")
blank()
pr("**English (Ontario)**")
if EN:
    pr(f"> Text: \"{EN.get('text','')}\"")
    pr(f">")
    pr(f"> Date: {EN.get('date','')}  |  Speaker: {EN.get('speaker','')}  |  Party: {EN.get('party','')}")
    pr(f"> Sentence ID: `{EN.get('sentence_id','')}`")
    pr(f"> Source: {EN.get('source','')}")
else:
    pr("> _(Ontario annotate not yet complete — will populate on rerun)_")
blank()
pr("**French (Quebec)**")
if FR:
    pr(f"> Text: \"{FR.get('text','')}\"")
    pr(f">")
    pr(f"> Date: {FR.get('date','')}  |  Speaker: {FR.get('speaker','')}  |  Party: {FR.get('party','')}")
    pr(f"> Sentence ID: `{FR.get('sentence_id','')}`")
    pr(f"> Source: {FR.get('source','ola_cheminement')}")
else:
    pr("> _(not available)_")

# ═══════════════════════════════════════════════════════════════════════════
section("1. N at Every Pipeline Stage")
# ═══════════════════════════════════════════════════════════════════════════

pr("Ontario numbers marked PENDING will update when the extract stage finishes")
pr("and the script is rerun.")
blank()

pn("Health bill debate dates",
   "145 bills (663 roll call + 118 voice vote)",
   "327 of 329 bills (99.4%)",
   "2,177 bill-date segments (100% of scored)")

pn("Raw text units collected",
   f"{len(us_sentences):,} sentences (GovInfo granule files, 1 per bill)",
   f"{ont_total_paras:,} paragraphs (OLA Azure Search API)",
   "Journal des Débats files (one per sitting day)")

pn("After sentence tokenization",
   f"{len(us_sentences):,}",
   ont_s,
   f"{len(qc_sentences):,}")

pn("Claim-bearing sentences (2+ DBpedia entities via Spotlight)",
   f"{len(us_db1):,} ({len(us_db1)/max(len(us_sentences),1)*100:.1f}% of total)",
   f"{ont_triples_n}",
   f"{len(qc_db1):,} ({len(qc_db1)/max(len(qc_sentences),1)*100:.1f}% of total)")

pn("Unique entity pairs (after dedupe)",
   f"{len(us_pairs):,}",
   ont_p,
   f"{len(qc_pairs):,}")

pn("Sentences with DBpedia evidence (supported=True)",
   f"{us_supported:,} ({us_supported/max(len(us_annotated),1)*100:.1f}% of claim-bearing)",
   ont_supp,
   f"{qc_supported:,} ({qc_supported/max(len(qc_annotated),1)*100:.1f}% of claim-bearing)")

pn("Bills scored",
   f"{len(us_scores)}",
   ont_sc,
   f"{len(qc_scores)}")

pn("Mean factuality score",
   "0.2054",
   "PENDING" if not ont_scores else f"{sum(v['factuality_score'] for v in ont_scores.values())/max(len(ont_scores),1):.4f}",
   "0.1387")

# ═══════════════════════════════════════════════════════════════════════════
section("2. Stage 1 — Health Bill Identification")
# ═══════════════════════════════════════════════════════════════════════════

pr("Before any text is collected, we identify which bills count as health bills.")
pr("Each jurisdiction uses a different method, all of which had manual review.")
blank()

sub("2a. US House — CRS Policy Area")
pr("Source: VoteView + Congressional Research Service (CRS) policy area codes.")
pr("Bills are health if their CRS policy area is 'Health' or 'Social Welfare'.")
pr("No further classification needed — CRS coding is authoritative.")
blank()
pr(f"    Bills: 663 roll-call + 118 voice-vote = 781 total")
pr(f"    File: `data/us/congressional_record_granule_index.json`")
blank()

sub("2b. Ontario — Keyword Tagging (Manual)")
pr("Ontario bills are tagged health if their title contains any of these keywords:")
pr("(stored in `ontario_bill_index.json` under `health_tag`)")
blank()
code("""HEALTH_KW = [
    'Health', 'Hospital', 'Medical', 'Drug', 'Care', 'Mental',
    'Nursing', 'Dental', 'Disability', 'Long-Term', 'Home Care',
    'Pharmacy', 'Midwif', 'Chiropract', 'Optom', 'Physiother',
    'Ambulance', 'Cancer', 'Pandemic', 'Vaccine', 'Tobacco',
    'Alcohol', 'Addiction', 'Workplace Safety', 'Occupational Health',
    'Environmental Health', 'Public Health', 'Vital Statistics',
    'Community Services', 'Physicians', 'Surgeons', 'Nurses',
    'Regulated Health', 'Assisted Living', 'Palliative'
]""")
pr("    329 health bills identified. 327 have recoverable floor debate text (99.4%).")
pr("    The 2 missing (2021-Bill94, 2021-Bill95) had first reading only —")
pr("    confirmed via myparliament.ca.")
pr(f"    File: `data/canada/ontario/ontario_bill_index.json`")
blank()

sub("2c. Quebec — Keyword Filter + XLM-RoBERTa + Joanie Annotation")
pr("Quebec classification uses three layers because French health bill titles")
pr("are harder to match by keyword alone (e.g. 'procréation assistée',")
pr("'autonomie des personnes aînées', 'consommation supervisée').")
blank()
pr("**Layer 1 — Keyword filter** (primary, accent-insensitive):")
pr("Uses `unicodedata.normalize('NFD')` to strip accents before matching,")
pr("so 'santé' matches 'sante', 'aînés' matches 'aines'.")
blank()
code("""FRENCH_HEALTH_KW = [
    'sante', 'hopital', 'medical', 'medicament', 'soins',
    'mental', 'infirmier', 'dentaire', 'invalidite', 'handicap',
    'pharmacie', 'sage-femme', 'chiroprat', 'optometr',
    'physiotherap', 'ambulance', 'cancer', 'pandemie',
    'vaccin', 'vaccination', 'pause-vaccin',
    'urgence sanitaire', 'etat d urgence',
    'consommation supervisee', 'injection supervisee',
    'personnes ainees', 'autonomie des aines',
    'sante sexuelle', 'sexuelle et reproductive',
    'funeraires', 'soins funeraires',
    'cannabis', 'substances psychoactives',
    'maltraitance', 'proches aidants',
    'medicaments', 'procreation assistee',
    'medecin', 'chirurgie', 'infirmiere',
    'preposee', 'auxiliaires familiaux',
    'services sociaux', 'protection de la jeunesse'
]""")
blank()
pr("    Sensitivity: 0.966 (misses 3 bills) | Specificity: 0.197 | F1: 0.752")
blank()
pr("**Layer 2 — XLM-RoBERTa** (`xlm-roberta-large-french-cap-v3` from poltextlab):")
pr("Zero-shot health classification on bill titles. Access via Zoé Baumgartner.")
pr("    Sensitivity: 0.693 | Specificity: 0.727 | F1: 0.731")
blank()
pr("**Layer 3 — Joanie Bouchard annotation (Université de Sherbrooke):**")
pr("Joanie manually reviewed 154 bills (July 16, 2026 email):")
pr("    - Confirmed 149 negatives (false positives from keyword filter)")
pr("    - Corrected 1 misclassification: Session 37-1 Bill 197 (organ donation)")
pr("    - Adding her 149 negatives pushed n-gram CV F1 from 0.463 to 0.696")
blank()
pr("**Final ensemble (AND of keyword + XLM-RoBERTa):**")
pr("    Sensitivity: 0.966 | Specificity: 0.985 | F1: 0.977 (in-sample)")
pr("    Honest cross-validated F1: 0.696 (n-gram component only)")
blank()
pr("    4 bills missed by XLM-RoBERTa, caught by keyword filter:")
pr("      - 42-1 Bill 2: Loi resserrant l'encadrement du cannabis")
pr("      - 42-1 Bill 73: procréation assistée")
pr("      - 42-1 Bill 196: sécurité dans les sports")
pr("      - 42-2 Bill 11: services de première ligne")
blank()
pr(f"    Files: `scripts/quebec_health_bill_filter.py`")
pr(f"           `scripts/xlm_roberta_health_classifier.py`")
pr(f"           `scripts/build_classifier_2x2.py` (Joanie labels hardcoded)")

# ═══════════════════════════════════════════════════════════════════════════
section("3. Stage 2 — Bill-Specific Text Collection")
# ═══════════════════════════════════════════════════════════════════════════

pr("**The denominator problem:** All three jurisdictions must use the same")
pr("denominator — only floor debate text specific to the bill being scored.")
pr("Earlier pipeline versions used full sitting-day text for Ontario and Quebec,")
pr("which inflated Ontario denominators by ~5x and produced incomparable scores.")
blank()

sub("3a. US House — GovInfo Granule Files")
pr("Each health bill has an exact granule ID in the GovInfo Bound Congressional")
pr("Record API. The granule file IS the bill-specific floor debate — no extraction")
pr("needed. Senate, Extensions of Remarks, and Daily Digest are excluded at")
pr("collection time by filtering to the House section only.")
blank()
pr("    118 voice-vote bills (1985-1998) required OCR from bound edition PDFs")
pr("    using pytesseract. PDF files streamed to /tmp due to size constraints.")
blank()
pr("    API: `https://api.govinfo.gov/collections/CRECB/...`")
pr("    Package ID format: `GPO-CRECB-{year}-pt{part}`")
pr("    Granule suffix: `-2` = House section")
pr("    POST requests with `offsetMark: '*'` for pagination")
pr(f"    Files: `data/us/congressional_record_speeches/`")
blank()
pr("    **What is excluded:**")
pr("    - All Senate debate")
pr("    - Extensions of Remarks (written submissions, not spoken)")
pr("    - Daily Digest (summary section)")
pr("    - Voice-vote bills with no retrievable floor text (0 — all recovered)")
blank()

sub("3b. Ontario LA — OLA Azure Search API")
pr("The OLA website hosts the full Ontario Hansard (1975-present) via a hidden")
pr("Azure Search API discovered by inspecting `drupalSettings` JSON on the Hansard")
pr("search page.")
blank()
pr("    Endpoint: `https://aihansardsearch-apim.azure-api.net/api/search/keyword`")
pr("    Key finding: keyword+date filter is BROKEN — keyword searches with date")
pr("    filters always return cached 1996 results. Correct approach: use")
pr("    `keyword: '*'` with a date filter, or `keyword: 'Bill X'` without date.")
pr("    The API requires BOTH capitalization variants:")
pr("      `typeOfBusiness eq 'ORDERS OF THE DAY'`  (pre-2018)")
pr("      `typeOfBusiness eq 'Orders of the Day'`  (post-2018)")
blank()
pr("    Coverage: 327/329 health bills (99.4%).")
pr("    The 2 missing (2021-Bill94, 2021-Bill95) had first reading only.")
pr("    Pre-1995 content retrieved from HuggingFace `a2aj/hansard` as fallback")
pr("    (ola.org returns 403 for pre-1995 pages).")
blank()
pr("    **What is excluded:**")
pr("    - Question Period")
pr("    - Members' Statements")
pr("    - Petitions")
pr("    - Introduction of Bills (first reading remarks only)")
pr("    - Opposition Day")
pr("    - Any Order of the Day about a different bill on the same date")
pr("      (resolved by filtering to bill-specific SubjectofBusiness topic or")
pr("       bill number mention in paragraph text)")
blank()
pr(f"    File: `data/canada/ontario/hansard_api_bill_segments.json`")
pr(f"    Bill index: `data/canada/ontario/ontario_bill_index.json`")
blank()

sub("3c. Quebec NA — Journal des Débats Section Markers")
pr("The Journal des Débats uses structured section headers that mark the start")
pr("and end of debate on each bill. These are extracted using regex markers:")
blank()
code("""SECTION_MARKERS = [
    r"[ÉE]tude du projet de loi n[o°]\s*\d+",   # Study of Bill X
    r"Reprise du débat",                          # Resumption of debate
    r"Adoption du principe",                      # Adoption in principle
    r"Mise aux voix",                             # Vote
    r"Projet de loi n[o°]\s*\d+\b",              # Bill X (standalone header)
]""")
blank()
pr("    Coverage: 2,177 bill-date segments = 100% of scored dates.")
pr("    11.1% of bill-date slots in Cheminement had no corresponding transcript")
pr("    section — these are procedural sittings where no bill study occurred.")
pr("    Pre-1994 transcripts included via Cheminement pagination (Playwright).")
pr("    `python3 -B` required to bypass stale bytecode on Cheminement scraper.")
blank()
pr("    Possible pre-segmented source: Ménard & Aleksandrova ParlaCLARIN 2022")
pr("    corpus (University of Montreal) — not yet integrated.")
blank()
pr("    **What is excluded:**")
pr("    - Période de questions et de réponses orales (Question Period)")
pr("    - Affaires courantes (Routine Proceedings)")
pr("    - Déclarations ministérielles (Ministerial Statements)")
pr("    - Motions des membres (Members' motions)")
pr("    - Anything outside a bill-study section marker")
blank()
pr(f"    Files: `data/canada/quebec_assembly/bill_segments/` (one .txt per bill-date)")
pr(f"    Index: `data/canada/quebec_bills/quebec_bill_segments_index.json`")

# ═══════════════════════════════════════════════════════════════════════════
section("4. Stage 3 — Sentence Tokenization")
# ═══════════════════════════════════════════════════════════════════════════

pr("Raw paragraph/segment text is split into sentences using spaCy.")
pr("  English: `en_core_web_sm`")
pr("  French: `fr_core_news_sm`")
blank()
pr("Each sentence row has fields: `sentence_id`, `date`, `text`, `speaker`,")
pr("`speaker_full`, `party`, `is_minister`, `subject`, `source`.")
blank()
pr("**What is excluded at tokenization:**")
pr("    - Empty strings and whitespace-only rows")
pr("    - Lines under ~20 characters (procedural one-liners: 'Motion agreed to.',")
pr("      'Carried.', 'Question.', procedural formulas)")
pr("    - Speaker attribution lines that are not speech content")
pr("      ('Mr. SMITH:', 'L'hon. mme JONES :' — these are parsing artifacts)")
blank()
pr("**Speaker attribution fixes applied:**")
pr("  US: all-caps surname pattern `Mr. SMITH.` with bioguide member lookup")
pr("  Ontario: `Mr. Smith:` / `Hon. Ms. Jones:` pattern with ola.org MPP lookup")
pr("  Quebec: `M. Legault :` / `Mme Anglade :` / `Le Président :` pattern")
pr("    — accent normalization applied: `unicodedata.normalize('NFD')` strips")
pr("      accents before lookup so 'Pagé' matches 'page' in PPB.csv")
pr("    — pre-1994 Quebec: 3,458 turns for 'pagé', 1,755 for 'bélisle' etc.")
pr("      required accent fix. After fix: 100% party matched across 103,578 turns.")
pr("    — year-aware lookup so same name resolves to correct party in different eras")
pr("      (e.g. Sam Elkas = Liberal 1990, not CAQ)")
blank()

pr("**Ontario party attribution note:** ~62% of API-sourced Ontario sentences")
pr("show 'Unknown' party. The OLA API does not return party affiliation directly.")
pr("Speaker names are matched to `data/canada/ontario/speaker_party_lookup.json`")
pr("(911 names from ola.org MPP biographies). Pre-1995 informal first-name-only")
pr("references and procedural speaker labels remain unmatched. This does NOT")
pr("affect factuality scoring — only the gov vs. opp sub-analysis.")
blank()

if EN:
    pr("**English example at tokenization stage:**")
    pr(f"    Input paragraph: (the raw OLA API paragraph containing this sentence)")
    pr(f"    Output sentence_id: `{EN.get('sentence_id','')}`")
    pr(f"    text: \"{EN.get('text','')[:150]}\"")
    pr(f"    speaker: {EN.get('speaker','')}  |  party: {EN.get('party','')}  |  is_minister: {EN.get('is_minister','')}")
    blank()

if FR:
    pr("**French example at tokenization stage:**")
    pr(f"    Input: (Journal des Débats bill segment)")
    pr(f"    Output sentence_id: `{FR.get('sentence_id','')}`")
    pr(f"    text: \"{FR.get('text','')[:150]}\"")
    pr(f"    speaker: {FR.get('speaker','')}  |  party: {FR.get('party','')}  |  is_minister: {FR.get('is_minister','')}")
    blank()

pr(f"Files: `data/dbpedia_pipeline/us/sentences.json` ({len(us_sentences):,})")
pr(f"       `data/dbpedia_pipeline/ontario/sentences.json` ({ont_s})")
pr(f"       `data/dbpedia_pipeline/quebec/sentences.json` ({len(qc_sentences):,})")

# ═══════════════════════════════════════════════════════════════════════════
section("5. Stage 4 — DBpedia Spotlight Entity Linking")
# ═══════════════════════════════════════════════════════════════════════════

pr("Each sentence is sent to the self-hosted DBpedia Spotlight instance on")
pr("`dunkleosteus.med.yale.internal` (10.168.171.152).")
pr("  English: port 2222  |  French: port 2223")
pr("  SSH tunnel: `ssh -i ~/.ssh/dunkleosteus_key -o ServerAliveInterval=60`")
pr("  `-L 2222:localhost:2222 -L 2223:localhost:2223 -L 8890:localhost:8890`")
pr("  `-fN cc3436@10.168.171.152`")
blank()
pr("Settings: confidence=0.5, percentageOfSecondRank < 0.5")
pr("This quality filter was critical — an earlier run without it produced only")
pr("46,443 triples. With the filter: 376,347 (US), ~687K (Ontario in progress),")
pr("329,790 (Quebec).")
blank()
pr("**A sentence is claim-bearing if Spotlight finds 2+ distinct DBpedia entities.**")
pr("Non-claim-bearing sentences (0 or 1 entity) are excluded from factuality")
pr("scoring but ARE counted in the denominator (total sentences spoken).")
blank()
pr("**What is excluded at this stage (examples from actual data):**")
blank()
pr("    Reason 1 — Zero entities found (Spotlight returns nothing):")
pr("    These are sentences with purely abstract or procedural language.")
blank()

# Show real zero-entity examples from db2 if available
us_db2 = load(os.path.join(REPO, "data/dbpedia_pipeline/us/db2_non_claim_bearing.json")) or []
zero_entity = [s for s in us_db2 if s.get("single_entity") == False]
random.shuffle(zero_entity)
for s in zero_entity[:4]:
    pr(f"    Example: \"{s.get('text','')[:140]}\"")
pr("")

pr("    Reason 2 — Single entity only (cannot form a verifiable pair):")
pr("    Spotlight finds one entity but no second entity to connect it to.")
blank()
single_entity = [s for s in us_db2 if s.get("single_entity") == True]
random.shuffle(single_entity)
for s in single_entity[:4]:
    pr(f"    Example: \"{s.get('text','')[:140]}\"")
pr("")

pr("    Reason 3 — Spotlight disambiguation errors (known failure modes):")
pr("    These survive into DB1 but fail the SPARQL query (no evidence found).")
pr("    The most common errors seen in this corpus:")
pr("      'Mr. Speaker'     → linked to 'Speaker of the Parliament of Sri Lanka'")
pr("      'Yesterday'       → linked to 'Yesterday (Beatles song)'")
pr("      'Ferrara'         → linked to 'Ferrara (city)' instead of a person")
pr("      'M.E.N.T. B.C.'  → no clean DBpedia resource found")
pr("      'ING Group'       → financial entity, not health-related")
blank()

if EN:
    uris_en = EN.get("concept_uris", [])
    pr("**English example — entities found by Spotlight:**")
    for u in uris_en[:5]:
        name = u.split('/')[-1].replace('_', ' ')
        pr(f"    `{name}`  →  {u}")
    pr(f"    confidence=0.5 filter applied. Both entities confirmed in DBpedia.")
    blank()

if FR:
    uris_fr = FR.get("concept_uris", [])
    pr("**French example — entities found by Spotlight (fr.dbpedia.org):**")
    for u in uris_fr[:5]:
        name = u.split('/')[-1].replace('_', ' ')
        pr(f"    `{name}`  →  {u}")
    pr(f"    French Spotlight on port 2223. fr.dbpedia.org URIs used throughout.")
    pr(f"    CRITICAL: HTTPS cert for fr.dbpedia.org expired August 2026. Use HTTP only.")
    blank()

pr(f"Files: `data/dbpedia_pipeline/us/triples.json` ({len(us_db1):,} claim-bearing)")
pr(f"       `data/dbpedia_pipeline/ontario/triples.json` ({ont_triples_n})")
pr(f"       `data/dbpedia_pipeline/quebec/triples.json` ({len(qc_db1):,} claim-bearing)")

# ═══════════════════════════════════════════════════════════════════════════
section("6. Stage 5 — Deduplicate Entity Pairs")
# ═══════════════════════════════════════════════════════════════════════════

pr("All (entity_A, entity_B) pairs across all claim-bearing sentences are")
pr("deduplicated so DBpedia is queried once per unique pair. This reduces")
pr("SPARQL query volume by ~40-50%.")
blank()
pr("    US:      376,347 claim-bearing → 313,662 unique pairs (dedupe ratio 1.20x)")
pr(f"    Quebec:  329,790 claim-bearing → {len(qc_pairs):,} unique pairs")
pr(f"    Ontario: {ont_triples_n} claim-bearing → {ont_p} unique pairs (PENDING)")
blank()
pr("**Nothing is excluded at this stage.** Both sentences in a duplicate pair")
pr("share the same cached SPARQL result — if the pair is supported, both")
pr("sentences are annotated supported=True.")
blank()

if EN and len(EN.get("concept_uris", [])) >= 2:
    uris = EN["concept_uris"]
    pr(f"**English example — dedupe key:**")
    pr(f"    `{uris[0]}|{uris[1]}`")
    pr(f"    This key is looked up in `dbpedia_results.json` before any SPARQL query.")
    blank()

if FR and len(FR.get("concept_uris", [])) >= 2:
    uris = FR["concept_uris"]
    pr(f"**French example — dedupe key:**")
    pr(f"    `{uris[0]}|{uris[1]}`")
    blank()

pr(f"Files: `data/dbpedia_pipeline/us/unique_pairs.json` ({len(us_pairs):,})")
pr(f"       `data/dbpedia_pipeline/ontario/unique_pairs.json` ({ont_p})")
pr(f"       `data/dbpedia_pipeline/quebec/unique_pairs.json` ({len(qc_pairs):,})")

# ═══════════════════════════════════════════════════════════════════════════
section("7. Stage 6 — SPARQL Query Against DBpedia")
# ═══════════════════════════════════════════════════════════════════════════

pr("Each unique entity pair is sent as a SPARQL VALUES query:")
blank()
code("""SELECT ?a ?b ?p WHERE {
    VALUES (?a ?b) { (<EntityA> <EntityB>) }
    { ?a ?p ?b } UNION { ?b ?p ?a }
}""")
blank()
pr("**Infrastructure:**")
pr("The public dbpedia.org SPARQL endpoint experienced extended outages (14+ hours")
pr("during this project). We switched to the local Virtuoso instance on Dunkleosteus")
pr("which has both English and French DBpedia loaded (~40-50GB each).")
blank()
pr("    Endpoint: `http://localhost:8890/sparql` (tunneled from Dunkleosteus)")
pr("    BATCH_SIZE = 5 pairs per request (Virtuoso rejects larger queries with 400)")
pr("    Retry logic: 3 attempts per batch, exponential backoff")
pr("    Result cache: `dbpedia_results.json` saves after every successful batch")
blank()
pr("**Critical Quebec SPARQL rule:**")
pr("    fr.dbpedia.org returns EMPTY results when a FROM clause is included.")
pr("    `graph_clause` must be set to empty string `''` for all Quebec queries.")
pr("    fr.dbpedia.org URIs must NOT be converted to English equivalents.")
blank()
pr("**What is excluded at this stage:**")
pr("    Any pair where no predicate connects entity_A to entity_B in DBpedia.")
pr("    These sentences are annotated supported=False.")
blank()
pr("    Examples of pairs with NO DBpedia relationship (real from corpus):")
blank()

qc_results = load(os.path.join(REPO, "data/dbpedia_pipeline/quebec/dbpedia_results.json")) or {}
empty_pairs = [(k, v) for k, v in qc_results.items() if not v]
random.shuffle(empty_pairs)
for k, _ in empty_pairs[:5]:
    parts = k.split("|")
    if len(parts) == 2:
        a = parts[0].split("/")[-1].replace("_", " ")
        b = parts[1].split("/")[-1].replace("_", " ")
        pr(f"    {a}  ←→  {b}  →  no relationship in DBpedia")
blank()

pr("    Examples of pairs WITH DBpedia relationship (supported=True):")
blank()
supported_pairs = [(k, v) for k, v in qc_results.items() if v]
random.shuffle(supported_pairs)
for k, preds in supported_pairs[:5]:
    parts = k.split("|")
    if len(parts) == 2:
        a = parts[0].split("/")[-1].replace("_", " ")
        b = parts[1].split("/")[-1].replace("_", " ")
        pred = preds[0].split("/")[-1] if preds else "?"
        pr(f"    {a}  ←[{pred}]→  {b}")
blank()

if EN:
    pr(f"**English example:**")
    pr(f"    Pair queried → supported: {'Yes' if EN.get('supported') else 'No'}")
    blank()
if FR:
    pr(f"**French example:**")
    pr(f"    Pair queried → supported: {'Yes' if FR.get('supported') else 'No'}")
    blank()

pr(f"Files: `data/dbpedia_pipeline/us/dbpedia_results.json`")
pr(f"       `data/dbpedia_pipeline/ontario/dbpedia_results.json`")
pr(f"       `data/dbpedia_pipeline/quebec/dbpedia_results.json`")

# ═══════════════════════════════════════════════════════════════════════════
section("8. Stage 7 — Annotation (supported=True/False)")
# ═══════════════════════════════════════════════════════════════════════════

pr("Each claim-bearing sentence is annotated based on SPARQL results.")
pr("A sentence is supported=True if at least one entity pair in that sentence")
pr("has a confirmed DBpedia relationship.")
blank()

sub("8a. Supported sentences — 10 random examples per jurisdiction")
blank()

for label, ann_pool, lang in [
    ("US", us_annotated, "en"),
    ("Quebec", qc_annotated, "fr"),
    ("Ontario", ont_annotated, "en"),
]:
    pr(f"**{label}:**")
    if not ann_pool:
        pr("    _(PENDING)_"); blank(); continue
    pool = [s for s in ann_pool if s.get("supported") and s.get("concept_uris")]
    random.shuffle(pool)
    for s in pool[:10]:
        uris = s.get("concept_uris", [])
        e1 = uris[0].split("/")[-1].replace("_"," ") if uris else "?"
        e2 = uris[1].split("/")[-1].replace("_"," ") if len(uris)>1 else "?"
        pr(f"    [{s.get('date','')}] \"{s.get('text','')[:120]}\"")
        pr(f"         Entities: {e1}  ←→  {e2}")
        blank()

sub("8b. Unsupported sentences — 10 random examples per jurisdiction")
blank()

for label, ann_pool in [("US", us_annotated), ("Quebec", qc_annotated), ("Ontario", ont_annotated)]:
    pr(f"**{label}:**")
    if not ann_pool:
        pr("    _(PENDING)_"); blank(); continue
    pool = [s for s in ann_pool if not s.get("supported") and s.get("concept_uris")]
    random.shuffle(pool)
    for s in pool[:10]:
        uris = s.get("concept_uris", [])
        e1 = uris[0].split("/")[-1].replace("_"," ") if uris else "?"
        e2 = uris[1].split("/")[-1].replace("_"," ") if len(uris)>1 else "?"
        pr(f"    [{s.get('date','')}] \"{s.get('text','')[:120]}\"")
        pr(f"         Entities: {e1}  ←→  {e2}  →  no DBpedia relationship")
        blank()

pr(f"Files: `data/dbpedia_pipeline/us/annotated_sentences.json` ({len(us_annotated):,})")
pr(f"       `data/dbpedia_pipeline/ontario/annotated_sentences.json` ({ont_a})")
pr(f"       `data/dbpedia_pipeline/quebec/annotated_sentences.json` ({len(qc_annotated):,})")

# ═══════════════════════════════════════════════════════════════════════════
section("9. Stage 8 — Factuality Score Computation")
# ═══════════════════════════════════════════════════════════════════════════

pr("For each bill:")
blank()
pr("    factuality_score = supported_sentences / total_claim_bearing_sentences")
blank()
pr("Bills with 0 claim-bearing sentences receive 0.0 and are excluded from")
pr("aggregate means. Bill passage outcome (passed/failed) is sourced from:")
pr("  US: VoteView roll-call votes (yea/nay counts + outcome)")
pr("  Ontario: FSOB (Votes and Proceedings) PDFs, all 27 sessions 1985-2026")
pr("  Quebec: Cheminement legislative tracking system")
blank()

sub("9a. 10 random scored bills — US")
sample = random.sample(list(us_scores.keys()), min(10, len(us_scores)))
for d in sorted(sample):
    v = us_scores[d]
    pr(f"    {d}  |  Bill: {v.get('bill_number','—')}  |  Score: {v.get('factuality_score',0):.4f}  |  "
       f"CB: {v.get('total_sentences',0)}  |  Supported: {v.get('supported_sentences',0)}  |  "
       f"Outcome: {v.get('vote_result','?')}")
blank()

sub("9b. 10 random scored bills — Quebec")
if qc_scores:
    sample = random.sample(list(qc_scores.keys()), min(10, len(qc_scores)))
    for d in sorted(sample):
        v = qc_scores[d]
        pr(f"    {d}  |  Score: {v.get('factuality_score',0):.4f}  |  "
           f"CB: {v.get('total_sentences',0)}  |  Supported: {v.get('supported_sentences',0)}  |  "
           f"Outcome: {v.get('vote_result','?')}")
    blank()

sub("9c. 10 random scored bills — Ontario")
if ont_scores:
    sample = random.sample(list(ont_scores.keys()), min(10, len(ont_scores)))
    for d in sorted(sample):
        v = ont_scores[d]
        pr(f"    {d}  |  Bill: {v.get('bill_number','—')}  |  Score: {v.get('factuality_score',0):.4f}  |  "
           f"CB: {v.get('total_sentences',0)}  |  Supported: {v.get('supported_sentences',0)}  |  "
           f"Outcome: {v.get('vote_result','?')}")
    blank()
else:
    pr("    _(PENDING — Ontario annotate stage not yet complete)_")
    blank()

pr(f"Files: `data/dbpedia_pipeline/us/factuality_scores.json` ({len(us_scores)})")
pr(f"       `data/dbpedia_pipeline/ontario/factuality_scores.json` ({ont_sc})")
pr(f"       `data/dbpedia_pipeline/quebec/factuality_scores.json` ({len(qc_scores)})")

# ═══════════════════════════════════════════════════════════════════════════
section("10. Known Gaps, Limitations, and Pending Changes")
# ═══════════════════════════════════════════════════════════════════════════

pr("**Pending pipeline redesign (David's Sept 11 directive):**")
pr("The current pipeline applies Spotlight to full sentences, which finds entities")
pr("in sentences where the grammatical relationship is not a predication.")
pr("Example: 'The Ontario Medical Association has endorsed this legislation.'")
pr("Spotlight finds OMA + legislation, DBpedia confirms they are linked,")
pr("sentence counted as supported. But 'endorsed' is not a health fact.")
blank()
pr("David's revised pipeline:")
pr("  1. Extract predications from sentences first using spaCy (SVO triples)")
pr("  2. Filter: only keep triples where verb is a meaningful health predicate")
pr("     (not: agree, endorse, support, oppose, say, argue, believe, think)")
pr("  3. Run Spotlight only on extracted predications")
pr("  4. SPARQL query as before")
pr("  5. Regenerate DB1/DB2 entirely")
blank()
pr("Current results are the pre-redesign baseline. DB1/DB2 will change.")
blank()

pr("**Ontario party unknown (~62% of sentences):**")
pr("Does not affect factuality scoring. Will be partially resolved by")
pr("expanding the speaker_party_lookup.json with additional name variants.")
blank()

pr("**Quebec 11.1% gap:**")
pr("Procedural sittings with no bill study section in Journal des Débats.")
pr("Not a data gap — there was no floor debate to collect.")
blank()

pr("**DBpedia evidence rate (8-16%):**")
pr("This is a finding, not a failure. It reflects the proportion of parliamentary")
pr("speech making claims verifiable in DBpedia. Rhetorical argument, procedural")
pr("remarks, and claims too narrow or current for DBpedia coverage account for")
pr("the remainder. David noted (Sept 11): consistent with parliamentary studies")
pr("and rhetoric literature on speech types (procedural, rhetorical, factual).")
blank()

pr("**Ontario 2 missing bills (2021-Bill94, 2021-Bill95):**")
pr("First reading only — confirmed via myparliament.ca. No floor debate exists.")
pr("99.4% is the true maximum for Ontario.")

# ─────────────────────────────────────────────────────────────────────────────
# WRITE
# ─────────────────────────────────────────────────────────────────────────────

out_file = os.path.join(OUT_DIR, "transcript_division_samples.md")
with open(out_file, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Saved {len(lines)} lines to {os.path.relpath(out_file, REPO)}")
