"""
dbpedia_batch_pipeline.py

Implements David's scaling strategy from the July 16 meeting, verbatim from
the notes: "pre-process all sentences, extract unique predicates, and query
DBpedia in batch to minimize computational overhead."

Four stages, each writes its output to disk so any stage can rerun alone:

  1. COLLECT   walk the clean speech files, split into sentences
  2. EXTRACT   spaCy parse each sentence, pull (subject, verb, object) triples
  3. DEDUPE    build master lists of unique concepts and unique concept PAIRS
  4. QUERY     batch the unique pairs against DBpedia (VALUES-block SPARQL,
               many pairs per request), cache every result, never re-query
  then map cached results back onto sentences.

Depends on the PDF extraction fix landing first, garbage sentences in means
garbage triples out. Run on a small clean subset to validate before scaling.

Usage:
  python3 scripts/dbpedia_batch_pipeline.py collect
  python3 scripts/dbpedia_batch_pipeline.py extract
  python3 scripts/dbpedia_batch_pipeline.py dedupe
  python3 scripts/dbpedia_batch_pipeline.py query
  python3 scripts/dbpedia_batch_pipeline.py annotate
"""

import os
import re
import sys
import json
import time
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEECH_DIR = os.path.join(REPO_ROOT, "data", "us", "congressional_record_speeches")
WORK_DIR = os.path.join(REPO_ROOT, "data", "dbpedia_pipeline")
os.makedirs(WORK_DIR, exist_ok=True)

SENTENCES_PATH = os.path.join(WORK_DIR, "sentences.json")
TRIPLES_PATH = os.path.join(WORK_DIR, "triples.json")
PAIRS_PATH = os.path.join(WORK_DIR, "unique_pairs.json")
RESULTS_PATH = os.path.join(WORK_DIR, "dbpedia_results.json")
ANNOTATED_PATH = os.path.join(WORK_DIR, "annotated_sentences.json")

SPARQL_ENDPOINT = "https://dbpedia.org/sparql"
SPARQL_ENDPOINT_BACKUP = "https://query.wikidata.org/sparql"
SPOTLIGHT_EN = "http://localhost:2222/rest/annotate"
SPOTLIGHT_FR = "http://localhost:2223/rest/annotate"
BATCH_SIZE = 20  # concept pairs per SPARQL request

# demo-scale grounding table; production replaces this with DBpedia Spotlight
ENTITY_TO_DBPEDIA = {
    "dietary supplement": "http://dbpedia.org/resource/Dietary_supplement",
    "fda": "http://dbpedia.org/resource/Food_and_Drug_Administration",
    "food and drug administration": "http://dbpedia.org/resource/Food_and_Drug_Administration",
    "medicare": "http://dbpedia.org/resource/Medicare_(United_States)",
    "medicaid": "http://dbpedia.org/resource/Medicaid",
    "adverse event": "http://dbpedia.org/resource/Adverse_event",
}


def stage_collect():
    sentences = []
    files = sorted(f for f in os.listdir(SPEECH_DIR)
                   if f.endswith(".txt") and "_notes" not in f)
    for fname in files:
        with open(os.path.join(SPEECH_DIR, fname), encoding="utf-8") as f:
            text = f.read()
        text = re.sub(r"-\n", "", text)
        text = re.sub(r"\s*\n\s*", " ", text)
        for i, sent in enumerate(re.split(r"(?<=[.!?])\s+", text)):
            sent = sent.strip()
            if 40 < len(sent) < 400:
                sentences.append({
                    "sentence_id": f"{fname.replace('.txt','')}-{i}",
                    "date": fname.replace(".txt", ""),
                    "text": sent,
                })
    with open(SENTENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sentences, f, ensure_ascii=False)
    print(f"collect: {len(sentences)} sentences from {len(files)} files -> {SENTENCES_PATH}")


def stage_extract():
    import spacy
    nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])

    def spotlight_annotate(text, lang="en"):
        url = SPOTLIGHT_EN if lang == "en" else SPOTLIGHT_FR
        try:
            resp = requests.post(url,
                headers={"Accept": "application/json"},
                data={"text": text[:1000], "confidence": "0.5"},
                timeout=15)
            if resp.status_code == 200:
                resources = resp.json().get("Resources", [])
                # filter out ambiguous links (second rank too close to first)
                good = [r["@URI"] for r in resources
                        if float(r.get("@percentageOfSecondRank", 1.0)) < 0.5]
                return good
        except Exception:
            pass
        return []

    with open(SENTENCES_PATH, encoding="utf-8") as f:
        sentences = json.load(f)

    triples = []
    start_idx = 0
    if os.path.exists(TRIPLES_PATH + ".checkpoint"):
        with open(TRIPLES_PATH + ".checkpoint") as f:
            triples = json.load(f)
        print(f"Resuming from checkpoint: {len(triples)} triples already found")
    total = len(sentences)
    for idx, s in enumerate(sentences):
        if idx % 1000 == 0:
            print(f"  {idx}/{total} sentences processed, {len(triples)} triples found", flush=True)
        uris = spotlight_annotate(s["text"], lang="en")
        if len(uris) < 1:
            continue
        doc = nlp(s["text"])
        root = next((t.lemma_ for t in doc if t.dep_ == "ROOT"), None)
        triples.append({
            "sentence_id": s["sentence_id"],
            "verb": root,
            "concept_uris": list(dict.fromkeys(uris)),
            "single_entity": len(uris) == 1,
        })
    with open(TRIPLES_PATH, "w", encoding="utf-8") as f:
        json.dump(triples, f, ensure_ascii=False)
    print(f"extract: {len(triples)} claim-bearing sentences -> {TRIPLES_PATH}")
    if idx % 10000 == 0 and idx > 0:
            with open(TRIPLES_PATH + ".checkpoint", "w", encoding="utf-8") as f:
                json.dump(triples, f, ensure_ascii=False)

def stage_dedupe():
    with open(TRIPLES_PATH, encoding="utf-8") as f:
        triples = json.load(f)
    pairs = set()
    for t in triples:
        uris = t["concept_uris"]
        for i in range(len(uris)):
            for j in range(i + 1, len(uris)):
                pairs.add((uris[i], uris[j]))
    pairs = sorted(pairs)
    with open(PAIRS_PATH, "w", encoding="utf-8") as f:
        json.dump(pairs, f)
    print(f"dedupe: {len(triples)} sentences reduce to {len(pairs)} unique concept pairs")
    print("        (this is the whole point: DBpedia gets queried once per unique")
    print("         pair, not once per sentence)")


def stage_query():
    with open(PAIRS_PATH, encoding="utf-8") as f:
        pairs = [tuple(p) for p in json.load(f)]
    cache = {}
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    todo = [p for p in pairs if f"{p[0]}|{p[1]}" not in cache]
    print(f"query: {len(pairs)} pairs total, {len(todo)} uncached")

    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start:start + BATCH_SIZE]
        values = " ".join(f"(<{a}> <{b}>)" for a, b in batch)
        q = f"""
        SELECT ?a ?b ?p WHERE {{
          VALUES (?a ?b) {{ {values} }}
          {{ ?a ?p ?b }} UNION {{ ?b ?p ?a }}
        }}"""
        rows = []
        sparql_succeeded = False
        for attempt in range(3):
            try:
                resp = requests.get(SPARQL_ENDPOINT,
                                    params={"query": q, "format": "application/sparql-results+json"},
                                    headers={"User-Agent": "legislative-health-factuality/1.0"},
                                    timeout=30)
                resp.raise_for_status()
                rows = resp.json()["results"]["bindings"]
                break
                sparql_succeeded = True
                break
            except Exception as e:
                print(f"  batch at {start}: attempt {attempt+1} failed: {e}")
                time.sleep(5 * (attempt + 1))
        
        for a, b in batch:
            if f"{a}|{b}" not in cache:
                cache[f"{a}|{b}"] = []
        if not sparql_succeeded:
            continue  # don't cache failed requests
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        if not rows:
            continue

        for a, b in batch:
            cache[f"{a}|{b}"] = []
        for r in rows:
            key = f"{r['a']['value']}|{r['b']['value']}"
            alt = f"{r['b']['value']}|{r['a']['value']}"
            k = key if key in cache else alt
            cache[k].append(r["p"]["value"])

        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        print(f"  batch at {start}: cached, running total {len(cache)} pairs")
        time.sleep(1)
    print(f"query: done -> {RESULTS_PATH}")


def stage_annotate():
    with open(TRIPLES_PATH, encoding="utf-8") as f:
        triples = json.load(f)
    with open(RESULTS_PATH, encoding="utf-8") as f:
        cache = json.load(f)

    for t in triples:
        uris = t["concept_uris"]
        evidence = []
        for i in range(len(uris)):
            for j in range(i + 1, len(uris)):
                preds = cache.get(f"{uris[i]}|{uris[j]}", [])
                if preds:
                    evidence.append({"pair": [uris[i], uris[j]], "predicates": preds})
        t["evidence"] = evidence
        t["supported"] = bool(evidence)

    with open(ANNOTATED_PATH, "w", encoding="utf-8") as f:
        json.dump(triples, f, ensure_ascii=False, indent=1)
    supported = sum(1 for t in triples if t["supported"])
    print(f"annotate: {supported}/{len(triples)} sentences have graph evidence -> {ANNOTATED_PATH}")


STAGES = {
    "collect": stage_collect,
    "extract": stage_extract,
    "dedupe": stage_dedupe,
    "query": stage_query,
    "annotate": stage_annotate,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
        print(f"Usage: python3 scripts/dbpedia_batch_pipeline.py [{'|'.join(STAGES)}]")
        sys.exit(1)
    STAGES[sys.argv[1]]()
