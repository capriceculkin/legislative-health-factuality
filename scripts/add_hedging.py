"""
add_hedging.py
Post-processing: adds hedging flag to triples.json by re-checking
the sentence text for modal auxiliaries using spaCy.
Runs fast — no Spotlight or SPARQL needed.
"""
import json, os
import spacy

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
SENTENCES_PATH = f"{REPO}/data/dbpedia_pipeline/sentences.json"
TRIPLES_PATH = f"{REPO}/data/dbpedia_pipeline/triples.json"
ANNOTATED_PATH = f"{REPO}/data/dbpedia_pipeline/annotated_sentences.json"

HEDGE_WORDS = {"may", "might", "could", "would", "should", "possibly",
               "perhaps", "allegedly", "reportedly", "suggest", "appear"}

nlp = spacy.load("en_core_web_sm")

print("Loading sentences...")
with open(SENTENCES_PATH) as f:
    sentences = json.load(f)
sent_lookup = {s["sentence_id"]: s["text"] for s in sentences}

print("Loading annotated sentences...")
with open(ANNOTATED_PATH) as f:
    annotated = json.load(f)

print(f"Adding hedging to {len(annotated)} annotated sentences...")
hedged_count = 0
for i, s in enumerate(annotated):
    if i % 10000 == 0:
        print(f"  {i}/{len(annotated)}")
    text = sent_lookup.get(s["sentence_id"], "")
    if not text:
        s["hedged"] = False
        continue
    doc = nlp(text[:200])  # limit length for speed
    hedged = any(token.text.lower() in HEDGE_WORDS for token in doc)
    s["hedged"] = hedged
    if hedged:
        hedged_count += 1

print(f"Hedged sentences: {hedged_count}/{len(annotated)} ({hedged_count/len(annotated)*100:.1f}%)")

with open(ANNOTATED_PATH, "w") as f:
    json.dump(annotated, f)

print("Saved updated annotated_sentences.json")
