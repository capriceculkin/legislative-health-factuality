"""
claim_factuality_demo.py

END-TO-END FACTUALITY PIPELINE DEMO (single worked example)

For the July 16 meeting. Demonstrates every stage of the proposed pipeline
on ONE real sentence from the Congressional Record, exactly the
predication-level workflow David described: parse the sentence into
(subject, verb, object), then check the concept pair against DBpedia.

STAGES DEMONSTRATED:
  1. SOURCE      - pull a real sentence from actual floor debate text
                   (the S3546 dietary supplement debate, 2006-12-09)
  2. SEMANTICS   - spaCy dependency parse: subject, verb, object,
                   plus adverbial/modal hedging (the factual-commitment layer)
  3. GROUNDING   - map extracted noun phrases to DBpedia resource URIs
  4. VERIFICATION- query DBpedia for direct predicates and one-hop paths
                   between subject and object (Giovanni shortest-path logic)
  5. VERDICT     - report the evidence found

Run: python3 scripts/claim_factuality_demo.py
Requires: pip install spacy && python3 -m spacy download en_core_web_sm
"""

import os
import re
import requests
import spacy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEECH_FILE = os.path.join(
    REPO_ROOT, "data", "us", "congressional_record_speeches", "2006-12-09.txt"
)
SPARQL_ENDPOINT = "https://dbpedia.org/sparql"

# -------------------------------------------------------------------------
# STAGE 3 SUPPORT: entity grounding table.
# In the full pipeline this becomes DBpedia Spotlight or a lookup API call.
# For the demo it's explicit so every mapping decision is visible.
# -------------------------------------------------------------------------
ENTITY_TO_DBPEDIA = {
    "dietary supplement": "http://dbpedia.org/resource/Dietary_supplement",
    "dietary supplements": "http://dbpedia.org/resource/Dietary_supplement",
    "supplement": "http://dbpedia.org/resource/Dietary_supplement",
    "fda": "http://dbpedia.org/resource/Food_and_Drug_Administration",
    "food and drug administration": "http://dbpedia.org/resource/Food_and_Drug_Administration",
    "medicare": "http://dbpedia.org/resource/Medicare_(United_States)",
    "medicaid": "http://dbpedia.org/resource/Medicaid",
    "adverse event": "http://dbpedia.org/resource/Adverse_event",
    "adverse events": "http://dbpedia.org/resource/Adverse_event",
    "consumer": "http://dbpedia.org/resource/Consumer",
    "consumers": "http://dbpedia.org/resource/Consumer",
}

# Hedging/modality markers: the adverbial layer that changes a claim's
# factual commitment ("will always reduce" vs "may reduce").
HEDGE_MARKERS = {
    "may", "might", "could", "should", "would", "possibly", "perhaps",
    "probably", "likely", "unlikely", "always", "never", "often",
    "sometimes", "generally", "typically", "allegedly", "reportedly",
}


def stage1_find_claim_sentence():
    """
    STAGE 1: SOURCE
    Scan the real speech file for a sentence containing two groundable
    entities, that's the minimum for a checkable claim. Returns the first
    good candidate along with basic provenance.
    """
    print("=" * 70)
    print("STAGE 1: SOURCE - locating a checkable claim in real floor debate")
    print("=" * 70)
    print(f"Speech file: {SPEECH_FILE}")
    print("Provenance:  S3546 vote date 2006-12-09, Dietary Supplement and")
    print("             Nonprescription Drug Consumer Protection Act debate\n")

    with open(SPEECH_FILE, encoding="utf-8") as f:
        text = f.read()

    # Collapse PDF line breaks so sentences reassemble
    text = re.sub(r"-\n", "", text)          # de-hyphenate line-wrapped words
    text = re.sub(r"\s*\n\s*", " ", text)     # join wrapped lines
    text = re.sub(r"\s{2,}", " ", text)       # collapse double spaces

    # Rough sentence split (full pipeline uses spaCy's sentencizer;
    # kept simple here so each stage stays inspectable)
    sentences = re.split(r"(?<=[.!?])\s+", text)

    candidates = []
    for sent in sentences:
        low = sent.lower()
        # skip statute text and PDF artifacts, keep spoken debate:
        # bill text is heavily uppercase and full of section markers
        upper_ratio = sum(1 for c in sent if c.isupper()) / max(len(sent), 1)
        if upper_ratio > 0.25 or "\u2018\u2018" in sent or ".\u2014" in sent or "SEC." in sent:
            continue
        found = [e for e in ENTITY_TO_DBPEDIA if e in low]
        # need two DISTINCT groundable resources, not two aliases of one
        distinct_uris = {ENTITY_TO_DBPEDIA[e] for e in found}
        if len(distinct_uris) >= 2 and 40 < len(sent) < 350:
            candidates.append((sent.strip(), found))

    print(f"Sentences scanned: {len(sentences)}")
    print(f"Candidate claim sentences (2+ groundable entities): {len(candidates)}\n")

    if not candidates:
        raise SystemExit("No candidate sentence found, check the entity table.")

    sentence, entities = candidates[0]
    print("SELECTED SENTENCE:")
    print(f'  "{sentence}"\n')
    return sentence, entities


def stage2_semantic_parse(sentence):
    """
    STAGE 2: SEMANTICS
    Dependency-parse the sentence and extract:
      - grammatical subject(s)  (nsubj, nsubjpass)
      - main verb / predicate   (ROOT)
      - object(s)               (dobj, pobj, attr)
      - hedging layer           (modal auxiliaries + adverbial markers)
    This is the (subject, verb, object) predication David described,
    plus the adverb layer that sets factual commitment.
    """
    print("=" * 70)
    print("STAGE 2: SEMANTICS - dependency parse and predication extraction")
    print("=" * 70)

    nlp = spacy.load("en_core_web_sm")
    doc = nlp(sentence)

    print("\nFull token-level parse (token | POS | dependency | head):")
    for token in doc:
        print(f"  {token.text:<20} {token.pos_:<8} {token.dep_:<10} -> {token.head.text}")

    subjects, objects, verbs, hedges = [], [], [], []
    for token in doc:
        if token.dep_ in ("nsubj", "nsubjpass"):
            # take the full noun phrase, not just the head word
            span = doc[token.left_edge.i: token.right_edge.i + 1]
            subjects.append(span.text)
        elif token.dep_ in ("dobj", "pobj", "attr"):
            span = doc[token.left_edge.i: token.right_edge.i + 1]
            objects.append(span.text)
        elif token.dep_ == "ROOT" and token.pos_ in ("VERB", "AUX"):
            verbs.append(token.lemma_)
        if token.text.lower() in HEDGE_MARKERS or token.tag_ == "MD":
            hedges.append(token.text)

    print("\nEXTRACTED PREDICATION:")
    print(f"  SUBJECT(S): {subjects}")
    print(f"  VERB/PRED : {verbs}")
    print(f"  OBJECT(S) : {objects}")
    print(f"  HEDGING   : {hedges if hedges else '(none, unhedged factual assertion)'}")
    print("  NOTE: hedging changes what the claim commits to. An unhedged")
    print("  assertion is checkable as stated; a hedged one is weaker.\n")
    return subjects, verbs, objects, hedges


def stage3_ground_entities(entities):
    """
    STAGE 3: GROUNDING
    Map the surface entity strings found in Stage 1 to DBpedia URIs.
    Deduplicates aliases pointing at the same resource.
    """
    print("=" * 70)
    print("STAGE 3: GROUNDING - mapping surface strings to DBpedia resources")
    print("=" * 70)
    uris = {}
    for e in entities:
        uris[ENTITY_TO_DBPEDIA[e]] = e
    for uri, surface in uris.items():
        print(f'  "{surface}"  ->  {uri}')
    print()
    uri_list = list(uris.keys())
    return uri_list[0], uri_list[1]


def sparql(query):
    resp = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query, "format": "application/sparql-results+json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def stage4_verify(subject_uri, object_uri):
    """
    STAGE 4: VERIFICATION
    Giovanni-style graph evidence between the two grounded concepts:
      a) direct edges (strongest evidence)
      b) one-hop paths through an intermediate node (where Giovanni et al.
         found most of the truth signal)
    """
    print("=" * 70)
    print("STAGE 4: VERIFICATION - querying the DBpedia knowledge graph")
    print("=" * 70)
    print(f"  Subject node: {subject_uri}")
    print(f"  Object node : {object_uri}\n")

    direct_q = f"""
    SELECT DISTINCT ?p WHERE {{
      {{ <{subject_uri}> ?p <{object_uri}> }}
      UNION
      {{ <{object_uri}> ?p <{subject_uri}> }}
    }}"""
    direct = [r["p"]["value"] for r in sparql(direct_q)]

    print(f"  a) DIRECT EDGES between the concepts: {len(direct)}")
    for p in direct:
        print(f"     {p}")

    hop_q = f"""
    SELECT DISTINCT ?p1 ?mid ?p2 WHERE {{
      <{subject_uri}> ?p1 ?mid .
      ?mid ?p2 <{object_uri}> .
    }} LIMIT 15"""
    hops = sparql(hop_q)

    print(f"\n  b) ONE-HOP PATHS (subject -> intermediate -> object): {len(hops)} shown (max 15)")
    for r in hops:
        mid = r["mid"]["value"].split("/")[-1]
        p1 = r["p1"]["value"].split("/")[-1]
        p2 = r["p2"]["value"].split("/")[-1]
        print(f"     --[{p1}]--> {mid} --[{p2}]-->")
    print()
    return direct, hops


def stage5_verdict(direct, hops, hedges):
    """
    STAGE 5: VERDICT
    Demo-level scoring logic, transparent and simple on purpose:
      direct edge present        -> SUPPORTED (strong)
      one-hop paths only         -> SUPPORTED (indirect)
      nothing                    -> NOT FOUND IN GRAPH (not necessarily false)
    Full pipeline replaces this with calibrated path-length scoring.
    """
    print("=" * 70)
    print("STAGE 5: VERDICT")
    print("=" * 70)
    if direct:
        verdict = "SUPPORTED (direct graph evidence)"
    elif hops:
        verdict = "SUPPORTED (indirect, one-hop graph evidence)"
    else:
        verdict = "NOT FOUND IN GRAPH (absence of evidence, not evidence of falsity)"
    print(f"  Evidence verdict: {verdict}")
    if hedges:
        print(f"  Claim was hedged ({hedges}), so the speaker committed to less")
        print("  than a categorical assertion; score accordingly in full pipeline.")
    print("\n  Full pipeline next steps from here: calibrated path-length scoring,")
    print("  claim-vs-opinion classification upstream, aggregation to speech and")
    print("  speaker-on-bill level, and the FR/EN interlanguage node mapping for Quebec.")


def main():
    sentence, entities = stage1_find_claim_sentence()
    subjects, verbs, objects, hedges = stage2_semantic_parse(sentence)
    subject_uri, object_uri = stage3_ground_entities(entities)
    direct, hops = stage4_verify(subject_uri, object_uri)
    stage5_verdict(direct, hops, hedges)


if __name__ == "__main__":
    main()
