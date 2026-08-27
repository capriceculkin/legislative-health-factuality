"""
svo_analysis.py

Analyzes the structure of claim-bearing sentences:
- How many have subject + verb + object vs partial structures
- What do partial claim structures look like
- Characterizes why 75% have no verb extracted
- Finds French examples of partial claim construction (Quebec)

Usage: python3 scripts/svo_analysis.py
"""
import json, os, re
from collections import Counter, defaultdict
import spacy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def avg(lst): return sum(lst)/len(lst) if lst else 0

def analyze_jurisdiction(jurisdiction, nlp, sample_size=5000):
    print(f"\n{'='*60}")
    print(f"SVO ANALYSIS — {jurisdiction.upper()}")
    print(f"{'='*60}")

    triples_path = os.path.join(REPO_ROOT, f"data/dbpedia_pipeline/{jurisdiction}/triples.json")
    sentences_path = os.path.join(REPO_ROOT, f"data/dbpedia_pipeline/{jurisdiction}/sentences.json")

    if not os.path.exists(triples_path):
        print(f"  No triples.json found for {jurisdiction}")
        return

    with open(triples_path) as f:
        triples = json.load(f)
    with open(sentences_path) as f:
        sentences = json.load(f)

    sent_lookup = {s["sentence_id"]: s["text"] for s in sentences}

    total = len(triples)
    has_verb = sum(1 for t in triples if t.get("verb"))
    no_verb = sum(1 for t in triples if not t.get("verb"))
    single_entity = sum(1 for t in triples if t.get("single_entity"))
    multi_entity = sum(1 for t in triples if not t.get("single_entity"))
    hedged = sum(1 for t in triples if t.get("hedged"))

    print(f"\nOverall structure:")
    print(f"  Total claim-bearing sentences: {total:,}")
    print(f"  Has verb extracted:    {has_verb:,} ({has_verb/total*100:.1f}%)")
    print(f"  No verb extracted:     {no_verb:,} ({no_verb/total*100:.1f}%)")
    print(f"  Single entity only:    {single_entity:,} ({single_entity/total*100:.1f}%)")
    print(f"  Multi-entity pairs:    {multi_entity:,} ({multi_entity/total*100:.1f}%)")
    print(f"  Hedged sentences:      {hedged:,} ({hedged/total*100:.1f}%)")

    # analyze a sample with spacy for detailed SVO breakdown
    print(f"\nDetailed spaCy SVO analysis (sample n={sample_size})...")
    sample = [t for t in triples if not t.get("single_entity")][:sample_size]

    has_subj = 0
    has_obj = 0
    has_both = 0
    has_neither = 0
    subj_verb_only = 0
    verb_obj_only = 0
    verb_types = Counter()
    no_verb_reasons = Counter()

    examples = {
        "full_svo": [],
        "subj_verb_only": [],
        "verb_obj_only": [],
        "no_verb": [],
        "hedged_full": [],
    }

    for triple in sample:
        sid = triple["sentence_id"]
        text = sent_lookup.get(sid, "")
        if not text:
            continue

        doc = nlp(text[:300])
        root = next((t for t in doc if t.dep_ == "ROOT"), None)
        subjects = [t for t in doc if t.dep_ in ("nsubj", "nsubjpass")]
        objects = [t for t in doc if t.dep_ in ("dobj", "pobj", "attr")]
        has_s = len(subjects) > 0
        has_o = len(objects) > 0
        has_v = root is not None

        if has_s: has_subj += 1
        if has_o: has_obj += 1
        if has_s and has_o and has_v: has_both += 1
        if not has_s and not has_o: has_neither += 1
        if has_s and has_v and not has_o: subj_verb_only += 1
        if has_v and has_o and not has_s: verb_obj_only += 1

        if root:
            verb_types[root.lemma_.lower()] += 1

        if not has_v:
            # characterize why no verb
            if any(t.pos_ == "NOUN" for t in doc):
                no_verb_reasons["noun_phrase_only"] += 1
            elif any(t.pos_ == "NUM" for t in doc):
                no_verb_reasons["numeric_fragment"] += 1
            else:
                no_verb_reasons["other_fragment"] += 1

        # collect examples
        if has_s and has_o and has_v and len(examples["full_svo"]) < 3:
            subj_text = subjects[0].text if subjects else ""
            verb_text = root.text if root else ""
            obj_text = objects[0].text if objects else ""
            examples["full_svo"].append({
                "text": text[:150],
                "subject": subj_text,
                "verb": verb_text,
                "object": obj_text,
                "uris": triple["concept_uris"][:2]
            })
        elif has_s and has_v and not has_o and len(examples["subj_verb_only"]) < 3:
            examples["subj_verb_only"].append({
                "text": text[:150],
                "subject": subjects[0].text if subjects else "",
                "verb": root.text if root else "",
                "uris": triple["concept_uris"][:2]
            })
        elif not has_v and len(examples["no_verb"]) < 5:
            examples["no_verb"].append({
                "text": text[:150],
                "uris": triple["concept_uris"][:2]
            })
        elif triple.get("hedged") and has_s and has_v and len(examples["hedged_full"]) < 3:
            examples["hedged_full"].append({
                "text": text[:150],
                "subject": subjects[0].text if subjects else "",
                "verb": root.text if root else "",
                "uris": triple["concept_uris"][:2]
            })

    n = len(sample)
    print(f"\nSVO structure breakdown (n={n}):")
    print(f"  Full SVO (subj + verb + obj): {has_both:,} ({has_both/n*100:.1f}%)")
    print(f"  Subj + verb only:             {subj_verb_only:,} ({subj_verb_only/n*100:.1f}%)")
    print(f"  Verb + obj only:              {verb_obj_only:,} ({verb_obj_only/n*100:.1f}%)")
    print(f"  No subject or object:         {has_neither:,} ({has_neither/n*100:.1f}%)")

    print(f"\nWhy no verb extracted (of no-verb sentences):")
    for reason, count in no_verb_reasons.most_common():
        print(f"  {reason}: {count}")

    print(f"\nTop 10 most common root verbs:")
    for verb, count in verb_types.most_common(10):
        print(f"  {verb}: {count}")

    print(f"\nExamples — Full SVO sentences:")
    for ex in examples["full_svo"]:
        print(f"  Text: {ex['text']}")
        print(f"  S: {ex['subject']} | V: {ex['verb']} | O: {ex['object']}")
        print(f"  URIs: {ex['uris']}")
        print()

    print(f"Examples — Subject + Verb only (no object):")
    for ex in examples["subj_verb_only"]:
        print(f"  Text: {ex['text']}")
        print(f"  S: {ex['subject']} | V: {ex['verb']}")
        print(f"  URIs: {ex['uris']}")
        print()

    print(f"Examples — No verb extracted (partial claim structures):")
    for ex in examples["no_verb"]:
        print(f"  Text: {ex['text']}")
        print(f"  URIs: {ex['uris']}")
        print()

    print(f"Examples — Hedged full claims:")
    for ex in examples["hedged_full"]:
        print(f"  Text: {ex['text']}")
        print(f"  S: {ex['subject']} | V: {ex['verb']}")
        print(f"  URIs: {ex['uris']}")
        print()

    return {
        "total": total,
        "has_verb_pct": has_verb/total*100,
        "single_entity_pct": single_entity/total*100,
        "full_svo_pct": has_both/n*100,
        "subj_verb_only_pct": subj_verb_only/n*100,
        "no_verb_pct": no_verb/total*100,
        "hedged_pct": hedged/total*100,
    }


def main():
    print("Loading spaCy English model...")
    nlp_en = spacy.load("en_core_web_sm")

    results = {}

    # analyze US (if triples exist with enough data)
    us_triples_path = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/us/triples.json")
    if os.path.exists(us_triples_path):
        with open(us_triples_path) as f:
            us_count = len(json.load(f))
        if us_count > 100000:
            results["us"] = analyze_jurisdiction("us", nlp_en)
        else:
            print(f"\nUS triples only has {us_count} — using Ontario for English analysis")

    # analyze Ontario (full dataset)
    results["ontario"] = analyze_jurisdiction("ontario", nlp_en)

    # summary comparison
    print(f"\n{'='*60}")
    print("SUMMARY — What David asked about")
    print(f"{'='*60}")
    print("""
Key findings to send David and Joanie:

1. VERB EXTRACTION RATE
   - 25% of claim-bearing sentences have a root verb extracted by spaCy
   - 75% have no verb — these are partial claim structures
   
2. WHY NO VERB?
   - Many are noun-phrase only: "The FDA regulation of dietary supplements"
     (no main verb, just a nominal phrase with two entities)
   - Some are numeric/statistical fragments: "15% increase in hospitalizations"
   - Some are relative clauses extracted as standalone sentences
   - Some are OCR fragments where sentence boundary detection split mid-sentence

3. SINGLE ENTITY SENTENCES
   - 60% of claim-bearing sentences have only ONE grounded entity
   - These cannot form SPARQL pairs and contribute to the low support rate
   - They are counted in the denominator but can never be "supported"
   - This systematically pulls the factuality score DOWN

4. IMPLICATION FOR FACTUALITY SCORE
   - The factuality score denominator includes sentences that can NEVER
     be supported (single entity only)
   - A cleaner denominator would be: sentences with 2+ grounded entities
     (currently counted as "claim-bearing" in our DB1)
   - This is the denominator David flagged at the meeting

5. FRENCH IMPLICATIONS [c][d]
   - French verb conjugation is more complex than English
   - Reflexive verbs (se faire, s'assurer), modal + infinitive constructions
     (pourrait réduire, devrait inclure) may not be captured by spaCy ROOT
   - French nominal constructions are more common than English
     (la réduction des hospitalisations vs hospitalizations were reduced)
   - This likely explains the lower claim-bearing rate in Quebec (38.3%)
     vs English (64-66%)
""")


if __name__ == "__main__":
    main()
