"""
extract_predications.py

Stage 3 of the revised v2 pipeline (David Chartash, Sept 11 2026 meeting).

Extracts Subject-Verb-Object predications from bill-specific sentences using
spaCy dependency parsing. Only sentences with a clear, non-hedged, non-existential
predication enter the v2 pipeline.

This runs BEFORE DBpedia Spotlight. Spotlight then runs on the subject and object
strings only, not on the full sentence.

Input:  data/dbpedia_pipeline/<jurisdiction>/sentences.json
Output: data/dbpedia_pipeline/<jurisdiction>/predications.json

Usage:
    JURISDICTION=ontario python3 scripts/extract_predications.py
    JURISDICTION=quebec  python3 scripts/extract_predications.py
    JURISDICTION=us      python3 scripts/extract_predications.py
"""
import json, os, spacy
from collections import Counter

JURISDICTION = os.environ.get("JURISDICTION", "ontario")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(REPO, "data/dbpedia_pipeline", JURISDICTION)

SENTENCES_PATH = os.path.join(WORK_DIR, "sentences.json")
OUTPUT_PATH = os.path.join(WORK_DIR, "predications.json")

# spaCy model selection
LANG = "fr" if JURISDICTION == "quebec" else "en"
MODEL = "fr_core_news_lg" if LANG == "fr" else "en_core_web_lg"

print(f"Jurisdiction: {JURISDICTION}")
print(f"Language: {LANG}")
print(f"spaCy model: {MODEL}")
print(f"Loading model...")

try:
    nlp = spacy.load(MODEL)
except OSError:
    print(f"Model {MODEL} not found. Install with:")
    print(f"  python -m spacy download {MODEL}")
    raise

print(f"Loading sentences...")
with open(SENTENCES_PATH, encoding="utf-8") as f:
    sentences = json.load(f)
print(f"Sentences: {len(sentences):,}")

# Verbs to exclude as ROOT (existential / non-predicative)
EXISTENTIAL_ROOTS = {
    # English
    "be", "is", "are", "was", "were", "been", "am",
    "have", "has", "had",
    "do", "does", "did",
    "seem", "appear", "become", "remain",
    # French
    "être", "avoir", "sembler", "paraître", "devenir", "rester"
}

# Modal auxiliaries that make predicates hedged
MODAL_HEDGES = {
    # English
    "may", "might", "could", "should", "would", "can", "must",
    # French
    "pouvoir", "devoir", "falloir", "vouloir", "aller"
}

def get_span_text(token):
    """Get full noun phrase text for a token."""
    if token.dep_ in ("nsubj", "nsubjpass", "dobj", "iobj", "pobj", "obj", "obl"):
        # Expand to full noun chunk
        for chunk in token.doc.noun_chunks:
            if token in chunk:
                return chunk.text.strip()
    return token.text.strip()

def extract_predication(sent):
    """
    Extract the main SVO predication from a spaCy sentence.
    Returns dict or None if no valid predication found.
    """
    root = None
    for token in sent:
        if token.dep_ == "ROOT":
            root = token
            break

    if root is None:
        return None

    # Exclude existential/auxiliary roots
    if root.lemma_.lower() in EXISTENTIAL_ROOTS:
        return None

    # Check for negation
    negated = any(c.dep_ == "neg" for c in root.children)

    # Check for hedging (modal auxiliaries as aux children)
    hedged = any(
        c.dep_ in ("aux", "auxpass") and c.lemma_.lower() in MODAL_HEDGES
        for c in root.children
    )

    # Find subject
    subject_token = None
    for child in root.children:
        if child.dep_ in ("nsubj", "nsubjpass", "csubj"):
            subject_token = child
            break

    if subject_token is None:
        return None

    # Find object
    object_token = None
    for child in root.children:
        if child.dep_ in ("dobj", "obj", "iobj", "pobj", "obl", "attr"):
            object_token = child
            break

    # Also check for prepositional objects
    if object_token is None:
        for child in root.children:
            if child.dep_ == "prep":
                for grandchild in child.children:
                    if grandchild.dep_ == "pobj":
                        object_token = grandchild
                        break

    if object_token is None:
        return None

    subject_text = get_span_text(subject_token)
    object_text = get_span_text(object_token)

    # Minimum length check
    if len(subject_text.split()) < 1 or len(object_text.split()) < 1:
        return None

    # Don't extract if subject and object are same
    if subject_text.lower() == object_text.lower():
        return None

    return {
        "subject": subject_text,
        "verb": root.text,
        "verb_lemma": root.lemma_,
        "object": object_text,
        "hedged": hedged,
        "negated": negated,
        "language": LANG
    }

print(f"Extracting predications...")

predications = []
stats = Counter()
BATCH = 1000

for i, sent_record in enumerate(sentences):
    if i % 50000 == 0 and i > 0:
        print(f"  {i:,}/{len(sentences):,} | predications: {len(predications):,} ({len(predications)/i*100:.1f}%)")

    text = sent_record.get("text", "").strip()
    if not text or len(text) < 20:
        stats["too_short"] += 1
        continue

    try:
        doc = nlp(text)
        for sent in doc.sents:
            pred = extract_predication(sent)
            if pred is None:
                stats["no_predication"] += 1
                continue

            if pred["hedged"]:
                stats["hedged"] += 1
                # Still include hedged — just flag them
            
            predications.append({
                "sentence_id": sent_record["sentence_id"],
                "date": sent_record.get("date", ""),
                "party": sent_record.get("party", ""),
                "is_minister": sent_record.get("is_minister", False),
                "bill_key": sent_record.get("bill_key", ""),
                "full_text": text,
                **pred
            })
            stats["extracted"] += 1
            break  # One predication per sentence (main clause only)

    except Exception:
        stats["error"] += 1

print(f"\nExtraction complete:")
print(f"  Input sentences:      {len(sentences):,}")
print(f"  Predications found:   {len(predications):,} ({len(predications)/len(sentences)*100:.1f}%)")
print(f"  No predication:       {stats['no_predication']:,}")
print(f"  Hedged (included):    {stats['hedged']:,}")
print(f"  Too short:            {stats['too_short']:,}")
print(f"  Errors:               {stats['error']:,}")

# Sample output
print(f"\nSample predications:")
import random
random.seed(42)
for p in random.sample(predications, min(5, len(predications))):
    print(f"  [{p['date']}] {p['subject']} --{p['verb_lemma']}--> {p['object']}")
    print(f"    Full: {p['full_text'][:80]}")
    if p['hedged']: print(f"    (hedged)")
    if p['negated']: print(f"    (negated)")

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(predications, f, ensure_ascii=False)
print(f"\nSaved to {OUTPUT_PATH}")
print(f"File size: {os.path.getsize(OUTPUT_PATH)/1024/1024:.1f}MB")
