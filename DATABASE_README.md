# Legislative Health Factuality: Database README

> **Status, Nov 17, 2026:** Written on Sept 4 for the first pipeline, before the September rebuild. See `REPLICATION.md` for the current pipeline.

# For: David Chartash and Joanie Bouchard
# Project: Does factual accuracy in legislative health debate predict bill outcomes?
# Jurisdictions: US House (1985-2026), Ontario LA (1985-2026), Quebec NA (1985-2026)

---
## HOW TO READ THIS DOCUMENT

Each jurisdiction has the same set of database files. This README explains:
  1. What each file contains and why it exists
  2. The key numbers and proportions for each jurisdiction
  3. Sample rows so you can see the structure
  4. Which file to open depending on what question you want to answer

All files are JSON. All files are in:
  data/dbpedia_pipeline/us/
  data/dbpedia_pipeline/ontario/
  data/dbpedia_pipeline/quebec/



## THE PIPELINE 

Every sentence spoken in a health bill floor debate is checked against the
DBpedia knowledge graph. If DBpedia can confirm a direct relationship between
two named entities in the sentence, that sentence is "supported." The factuality
score for a bill is: supported sentences / total claim-bearing sentences.



## FILE 1: sentences.json
### "Every sentence spoken, by whom, when, from which party"

This is the raw input to everything else. One row per sentence.

FIELDS:
  sentence_id  Unique ID in format {date}-{turn}-{sentence_index}
  date         Date of debate (YYYY-MM-DD)
  text         Full sentence text as spoken
  speaker      Normalized speaker surname (lowercase)
  party        Political party at time of speech
  is_minister  True if speaker was a cabinet minister at time of speech
  speaker_full Full name of speaker (Ontario and Quebec only)

COUNTS AND PROPORTIONS:
  US:      584,111 sentences | 1985-2026 | bill-specific debate text only
  Ontario: 734,300 sentences | 1985-2026 | full sitting-day transcripts
  Quebec:  900,985 sentences | 1985-2026 | full sitting-day transcripts

  Note on why Quebec has more: Quebec sentences were collected from ALL
  speaker turns across all transcript files. Ontario was collected from dates
  when health bills were debated. US is bill-specific (one file per bill).
  This means Ontario and Quebec denominators include non-health speech,
  which is why their factuality scores are lower than US.

SAMPLE ROW (Ontario):
  {
    "sentence_id": "1985-06-14-turn0-0",
    "date": "1985-06-14",
    "text": "I rise in my place in my capacity as Provincial Secretary for
             Resources Development to announce that the Lieutenant Governor
             in Council has approved the Niagara Escarpment plan.",
    "speaker": "timbrell",
    "party": "Progressive Conservative Party of Ontario",
    "is_minister": true,
    "speaker_full": "Dennis Roy Timbrell"
  }



## FILE 2: db1_claim_bearing.json
### "The primary analysis database: sentences with named entities"

DB1 contains every sentence where DBpedia Spotlight found 2+ named entities
linked to DBpedia concept pages. These are the sentences that CAN be
checked against the knowledge graph. The "supported" field tells you whether
DBpedia confirmed a relationship between the entities.

FIELDS: Same as sentences.json, plus:
  concept_uris  List of DBpedia entity URIs found in the sentence
  supported     True if at least one entity pair was confirmed in DBpedia
  hedged        True if sentence contains a modal auxiliary (may/might/could/would)

COUNTS AND PROPORTIONS:
                    US          Ontario     Quebec
  Total DB1 rows:   376,347     283,033     334,522
  As % of all sent: 64.4%       38.6%       37.2%
  Supported:        58,979      30,115      43,788
  Support rate:     15.7%       10.6%       13.1%
  Hedged:           44,649      89,306      334
  Hedged rate:      11.9%       12.2%       0.1%

  Why Ontario DB1 is smaller than sentences.json total (283K vs 734K):
  Only 38.6% of Ontario sentences have 2+ grounded entities, the rest are
  rhetorical, procedural, or too general for knowledge graph verification.

  Why Quebec claim-bearing rate is lower (37.2% vs 64.4% US):
  French parliamentary style uses more nominalizations, passive constructions,
  and modal verbs that prevent spaCy from identifying a clean entity pair.

SAMPLE ROW: SUPPORTED sentence (Ontario):
  {
    "sentence_id": "1989-04-13-turn12-3",
    "date": "1989-04-13",
    "text": "The Ontario Medical Association has endorsed this legislation.",
    "speaker": "caplan",
    "party": "Ontario Liberal Party",
    "is_minister": true,
    "speaker_full": "Elinor Caplan",
    "concept_uris": [
      "http://dbpedia.org/resource/Ontario_Medical_Association",
      "http://dbpedia.org/resource/Ontario"
    ],
    "supported": true,
    "hedged": false
  }

SAMPLE ROW: NOT SUPPORTED sentence (Ontario):
  {
    "sentence_id": "1991-11-04-turn5-2",
    "date": "1991-11-04",
    "text": "The member for Sudbury East should know better than to suggest
             that the Ministry of Health has failed in its duty.",
    "speaker": "lankin",
    "party": "New Democratic Party of Ontario",
    "is_minister": false,
    "speaker_full": "Frances Lankin",
    "concept_uris": [
      "http://dbpedia.org/resource/Sudbury_East",
      "http://dbpedia.org/resource/Ontario_Ministry_of_Health"
    ],
    "supported": false,
    "hedged": false
  }

HOW TO USE DB1:
  Government vs opposition analysis:
    Filter by is_minister=True for government, False for opposition
    Compare support rates

  Factuality by party:
    Group by party field, compute support rate per group

  Find factual sentences:
    Filter supported=True, these are sentences with confirmed entity relationships

  Find hedged claims:
    Filter hedged=True, these express uncertainty (may increase, could reduce, etc.)

  Find sentences about a specific entity:
    Search concept_uris for the DBpedia URI of that entity



## FILE 3: db2_non_claim_bearing.json
### "The other sentences rhetorical, procedural, opinion"

DB2 contains every sentence that did NOT make it into DB1 either because
Spotlight found fewer than 2 grounded entities, or found none at all.
These are primarily procedural formulas, rhetorical positioning, and opinion.

FIELDS: Same as sentences.json (no concept_uris, no supported field)

COUNTS AND PROPORTIONS:
                    US          Ontario     Quebec
  Total DB2 rows:   207,764     258,458*    566,463
  As % of all sent: 35.6%       35.2%       62.9%

  *Note: Ontario DB2 count (258,458) plus DB1 (283,033) = 541,491, which is
  less than total sentences (734,300). The difference (192,809) represents
  sentences collected from health bill debate dates that went through
  Spotlight but produced zero entity links, these are in annotated_sentences.json
  but not in either DB.

SAMPLE ROW (Ontario):
  {
    "sentence_id": "2019-03-12-turn3-1",
    "date": "2019-03-12",
    "text": "Mr. Speaker, I rise today to speak to Bill 74.",
    "speaker": "morrison",
    "party": "Progressive Conservative Party of Ontario",
    "is_minister": false,
    "speaker_full": "Suze Morrison"
  }

SAMPLE ROW (Quebec):
  {
    "sentence_id": "2015-04-16-turn8-0",
    "date": "2015-04-16",
    "text": "M. le Président, je pense que le gouvernement devrait écouter
             les Québécois sur cette question importante.",
    "speaker": "lisée",
    "party": "Parti Quebecois",
    "is_minister": false,
    "speaker_full": "Jean-François Lisée"
  }


## FILE 4: factuality_scores.json
### "The main result, one factuality score per bill"

One row per bill-date, the factuality score = supported / total claim-bearing.

FIELDS:
  bill_number         Bill identifier
  vote_result         Outcome: passed / failed / unknown (US and Quebec)
  result / outcome    Outcome field name varies by jurisdiction
  factuality_score    Supported sentences / total claim-bearing sentences
  total_sentences     Total claim-bearing sentences for this bill-date
  supported_sentences Sentences with at least one confirmed entity pair

COUNTS AND KEY RESULTS:
  US (441 bill-dates scored):
    Overall mean factuality: 0.2054
    Passed bills (n=386):    0.2094
    Failed bills (n=34):     0.2015
    Difference:              +0.0079

  Ontario (2,056 bill-dates; 329 per-bill aggregated):
    Overall mean factuality: 0.0971 (per-date) / 0.1006 (per-bill)
    Passed bills (n=158):    0.0992
    Failed bills (n=34):     0.0983
    Difference:              +0.0009

  Quebec (2,448 bill-dates scored):
    Overall mean factuality: 0.1334
    Passed bills (n=816):    0.1333
    Failed bills:            n/a (all health bills in corpus passed)

  Ontario also has:
    factuality_scores_per_bill.json — aggregated per bill (not per date)
    factuality_scores_health_filtered.json — only sentences with health
      DBpedia entities (mean 0.1709, more comparable to US 0.2054)

PASS RATE CONTEXT (comment [30]):
  Of all health bills identified in each corpus:
    US:      420 scored out of 441 bill-dates (95.2% have factuality scores)
             386 passed / 34 failed (91.9% pass rate on recorded votes)
    Ontario: 329 bills scored out of health bill index
             158 passed / 34 failed / 137 unknown outcome
    Quebec:  816 bills scored with "passed" outcome
             51 bills with None outcome (died on order paper)
             0 failed bills — all health bills that reached a vote passed

SAMPLE ROW (US):
  {
    "1985-06-18": {
      "bill_number": "HR2369",
      "vote_result": "failed",
      "factuality_score": 0.1842,
      "total_sentences": 152,
      "supported_sentences": 28
    }
  }



## FILE 5: dbpedia_results.json
### Entity pairs that have knowledge graph connections

One entry per unique entity pair. Key is "URI_A|URI_B", value is list of
predicate URIs connecting them the empty list = no connection found.

COUNTS AND EVIDENCE RATES:
  US:      313,705 pairs queried | 15.7% with evidence (English DBpedia)
  Ontario: 248,972 pairs queried | 10.3% with evidence (English DBpedia)
  Quebec:  137,964 pairs queried | 15.4% with evidence (French DBpedia)

  Of Quebec pairs with evidence:
    94% connected via wikiPageWikiLink (general Wikipedia co-mention)
    6% connected via specific semantic predicates:
      country, birthPlace, nationality, headquarter, party, profession

SAMPLE ENTRY WITH EVIDENCE (Quebec):
  "http://fr.dbpedia.org/resource/Agnès_Maltais|
   http://fr.dbpedia.org/resource/Parti_québécois":
    ["http://dbpedia.org/ontology/party"]

SAMPLE ENTRY WITHOUT EVIDENCE:
  "http://dbpedia.org/resource/Ontario|
   http://dbpedia.org/resource/Canadian_dollar": []



## FILE 6: triples.json
### Entity extraction results from DBpedia Spotlight

One row per claim-bearing sentence, contains the raw output of the spaCy
and Spotlight entity extraction stage.

FIELDS:
  sentence_id   Links back to sentences.json
  verb          Root verb extracted by spaCy (empty if none found — see note)
  hedged        Boolean — modal auxiliary present
  concept_uris  List of DBpedia entity URIs found by Spotlight
  single_entity Boolean — only one entity successfully grounded

KEY FINDING — VERB EXTRACTION (comment [25] and [32]):
  Of 729,549 Ontario claim-bearing sentences:
    Has verb extracted:   182,729 (25.0%)
    No verb extracted:   546,820 (75.0%)
    Single entity only:  439,623 (60.3%) — these CANNOT be SPARQL-verified

  Top root verbs are existential rather than action verbs:
    be: 143,228  |  have: 36,546  |  do: 1,271  |  get: 1,236

  Comment [25] — "THERE IS A VERB, why didn't it pick it up?":
  Some sentences with clear verbs get empty verb fields because:
  (a) spaCy labels a pronoun or auxiliary as ROOT instead of the main verb
  (b) The verb is in a subordinate clause and spaCy identifies a different ROOT
  (c) For French: modal+infinitive constructions where ROOT = modal not infinitive

  Full SVO breakdown (5,000-sentence Ontario sample):
    Full subject + verb + object: 26.1%
    Subject + verb only:           0.6%
    Verb + object only:            0.9%
    No subject or object:          0.0%

  French-specific constructions that break verb extraction (10,000 Quebec sentences):
    Passive voice (a été + participle):      1.6% — ROOT = auxiliary "a"
    Modal + infinitive (pourrait + verb):    1.2% — ROOT = modal, real verb missed
    Reflexive (se + infinitive):             1.0% — obscures agent-action structure
    Nominalization (la X-tion de):           6.0% — no verb at all
    Negation (n'est/n'a pas):               4.5% — complicates verification
    Impersonal (il faut/il s'agit):         2.0% — no clear subject-object pair

SAMPLE ROW (Ontario, verb present):
  {
    "sentence_id": "2012-04-17-turn4-1",
    "verb": "increase",
    "hedged": false,
    "concept_uris": [
      "http://dbpedia.org/resource/Ministry_of_Health_(Ontario)",
      "http://dbpedia.org/resource/Long-term_care"
    ],
    "single_entity": false
  }

SAMPLE ROW (Ontario, no verb — nominalization):
  {
    "sentence_id": "2018-11-06-turn11-3",
    "verb": "",
    "hedged": false,
    "concept_uris": [
      "http://dbpedia.org/resource/Ontario_Health_Insurance_Plan",
      "http://dbpedia.org/resource/Physician"
    ],
    "single_entity": false
  }



## FILE 7: unique_pairs.json
### Deduplicated entity pairs for SPARQL querying

Each row is a [URI_A, URI_B] pair. Deduplication means DBpedia is queried
once per unique pair regardless of how many sentences contain it.
This is why 729,549 Ontario sentences become 248,972 unique pairs.

COUNTS:
  US:      313,705 unique pairs (from 376,347 claim-bearing sentences)
  Ontario: 248,972 unique pairs (from 283,033 claim-bearing sentences)
  Quebec:  137,964 unique pairs (from 334,522 claim-bearing sentences)



## FILE 8: annotated_sentences.json
### All claim-bearing sentences with graph evidence field added

This is the intermediate file between SPARQL querying and the DB1/DB2 split,
same structure as DB1. You probably don't need this directly.



## WHICH FILE ANSWERS WHICH QUESTION

Question                                          File
-------------------------------------------------  ----------------------------------------
Does factuality predict bill passage?              factuality_scores_per_bill.json (Ontario)
                                                   factuality_scores.json (US, Quebec)

Government vs opposition factuality?               db1_claim_bearing.json
                                                   filter by is_minister field

Factuality by party or era?                        db1_claim_bearing.json
                                                   join date to governing period

What did a specific member say?                    sentences.json
                                                   filter by speaker field

Which sentences have graph support?                db1_claim_bearing.json
                                                   filter supported=True

COVID vs non-COVID factuality?                     factuality_scores.json
                                                   filter date >= 2020

MAiD debate sentences specifically?                db1_claim_bearing.json
                                                   filter concept_uris contains
                                                   "medical_assistance_in_dying" etc.

Why is verb extraction failing?                    triples.json
                                                   verb="" rows with concept_uris

Which entity pairs are connected?                  dbpedia_results.json

Bill typology (proposed by whom, etc.)?            sentences.json + external bill metadata
                                                   (ontario_bill_index.json,
                                                    cheminement_all_sessions.json,
                                                    health_bills_final_matched.csv)

Pass rate proportions?                             factuality_scores.json
                                                   count by vote_result field


## KEY PROPORTIONS SUMMARY 

                          US          Ontario     Quebec
Total sentences:          584,111     734,300     900,985
Claim-bearing (DB1):      376,347     283,033     334,522
  As % of total:          64.4%       38.6%       37.2%
Non-claim-bearing (DB2):  207,764     258,458     566,463
  As % of total:          35.6%       35.2%       62.9%

Of claim-bearing sentences:
  Supported:              58,979      30,115      43,788
  Support rate:           15.7%       10.6%       13.1%
  Single entity only*:    ~51%        60.3%       n/a
  * These inflate denominator — can never be verified

Of all bills scored:
  US:  420 bills | 386 passed (91.9%) | 34 failed (8.1%)
  ON:  329 bills | 158 carried (48.0%) | 34 lost (10.3%) | 137 unknown
  QC:  816 bills | 816 passed (100%) | 0 failed | 51 died on order paper

Factuality scores:
  US:      mean 0.2054 | passed 0.2094 | failed 0.2015 | diff +0.0079
  Ontario: mean 0.1006 | passed 0.0992 | failed 0.0983 | diff +0.0009
  Quebec:  mean 0.1334 | passed 0.1333 | failed n/a

---

## DENOMINATOR NOTE

The factuality score denominator currently = all claim-bearing sentences
(those where Spotlight found 2+ entity mentions). This includes:

  (a) Sentences with only ONE successfully grounded entity — 60% of Ontario DB1
      These can NEVER be SPARQL-verified. They pull scores downward.

  (b) Non-health sentences — included because Ontario/Quebec use full
      sitting-day transcripts. Ontario health-entity-filtered score (0.1709)
      restricts to sentences with health-related DBpedia entities.

Three possible denominators under consideration:
  1. All claim-bearing sentences (current) — most inclusive
  2. Health-entity-filtered (Ontario computed, others pending)
  3. Sentences with 2+ successfully grounded entity pairs (not yet computed)

---

## NOTES ON DATA SOURCES

US: Congressional Record via GovInfo API (1985-1998 bound editions, OCR'd)
    and daily digital issues (1999-2026). Bill-specific text only.

Ontario: Hansard from ola.org, full sitting-day transcripts.
    Speaker attribution covers all three format eras:
    pre-2008 (Mr. Smith:), NDP era (Mr Smith:), post-2008 (Mrs. Gila Martow:)
    Total speaker turns: 359,694 across 1985-2026.

Quebec: Journal des Débats from assnat.qc.ca (post-1994) and
    Bibliothèque de l'Assemblée nationale (pre-1994, Playwright scraping).
    Total speaker turns: 367,274 across 1985-2026, 100% party-matched.

DBpedia Spotlight: Hosted on Yale DEM server (dunkleosteus.med.yale.internal)
    English model port 2222, French model port 2223.
    Confidence threshold: 0.5, percentageOfSecondRank < 0.5 quality filter.

SPARQL endpoints:
    English: https://dbpedia.org/sparql
    French:  http://fr.dbpedia.org/sparql (HTTP; HTTPS cert expired Aug 2026)
