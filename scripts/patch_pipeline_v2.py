"""
Patches dbpedia_batch_pipeline.py to add extract_v2 stage.
"""
import os

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
pipeline_path = os.path.join(REPO, "scripts/dbpedia_batch_pipeline.py")

with open(pipeline_path, encoding="utf-8") as f:
    content = f.read()

# The new stage to insert
new_stage = '''
def stage_extract_v2():
    """V2 extract: run Spotlight on predication subject+object strings only.
    Requires predications.json from extract_predications.py to exist first.
    """
    PRED_PATH = os.path.join(WORK_DIR, "predications.json")
    if not os.path.exists(PRED_PATH):
        print(f"ERROR: {PRED_PATH} not found. Run extract_predications.py first.")
        return

    def restart_spotlight(lang="en"):
        container = "spotlight-en" if lang == "en" else "spotlight-fr"
        print(f"  Spotlight unresponsive — restarting {container}...", flush=True)
        os.system(f"ssh -i ~/.ssh/dunkleosteus_key -o StrictHostKeyChecking=no cc3436@10.168.171.152 'docker restart {container}'")
        import time as t; t.sleep(120)
        print(f"  Spotlight restarted, resuming...", flush=True)

    def spotlight_string(text, lang="en"):
        url = SPOTLIGHT_EN if lang == "en" else SPOTLIGHT_FR
        for attempt in range(3):
            try:
                resp = requests.post(url,
                    headers={"Accept": "application/json"},
                    data={"text": text[:300], "confidence": "0.5"},
                    timeout=20)
                if resp.status_code == 200:
                    return [r["@URI"] for r in resp.json().get("Resources", [])
                            if float(r.get("@percentageOfSecondRank", 1.0)) < 0.5]
            except Exception:
                if attempt == 2:
                    restart_spotlight(lang)
            time.sleep(5 * (attempt + 1))
        return []

    with open(PRED_PATH, encoding="utf-8") as f:
        predications = json.load(f)

    triples = []
    seen_ids = set()
    checkpoint = os.path.join(WORK_DIR, "triples_v2.json.checkpoint")
    output = os.path.join(WORK_DIR, "triples_v2.json")

    if os.path.exists(checkpoint):
        with open(checkpoint) as f:
            triples = json.load(f)
        seen_ids = {t["sentence_id"] for t in triples}
        print(f"Resuming from checkpoint: {len(triples)} triples, {len(seen_ids)} predications done")

    total = len(predications)
    for i, pred in enumerate(predications):
        if pred["sentence_id"] in seen_ids:
            continue
        if i % 1000 == 0:
            print(f"  {i}/{total} predications processed, {len(triples)} triples found", flush=True)

        subj_uris = spotlight_string(pred["subject"], SPOTLIGHT_LANG)
        obj_uris  = spotlight_string(pred["object"],  SPOTLIGHT_LANG)

        if not subj_uris or not obj_uris:
            continue

        all_uris = list(dict.fromkeys(subj_uris + obj_uris))
        if len(all_uris) < 2:
            continue

        triples.append({
            "sentence_id": pred["sentence_id"],
            "verb": pred.get("verb_lemma", pred.get("verb", "")),
            "verb_text": pred.get("verb", ""),
            "subject": pred["subject"],
            "object": pred["object"],
            "hedged": pred.get("hedged", False),
            "negated": pred.get("negated", False),
            "concept_uris": all_uris,
            "single_entity": False,
        })

        if len(triples) % 1000 == 0:
            with open(checkpoint, "w", encoding="utf-8") as f:
                json.dump(triples, f, ensure_ascii=False)
            print(f"  checkpoint saved: {len(triples)} triples", flush=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(triples, f, ensure_ascii=False)
    print(f"extract_v2: {len(triples)} claim-bearing predications -> {output}")

'''

# Insert before stage_dedupe
if "def stage_extract_v2():" in content:
    print("stage_extract_v2 already exists — skipping insert")
else:
    content = content.replace("def stage_dedupe():", new_stage + "def stage_dedupe():")
    print("Inserted stage_extract_v2")

# Add extract_v2 to dispatch
dispatch_old = '"annotate": stage_annotate,'
dispatch_new = '"annotate": stage_annotate,\n    "extract_v2": stage_extract_v2,'

if "extract_v2" in content:
    print("extract_v2 already in dispatch")
else:
    content = content.replace(dispatch_old, dispatch_new)
    print("Added extract_v2 to dispatch")

with open(pipeline_path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Saved. New line count:")
print(len(content.split("\n")))

# Verify
import py_compile
try:
    py_compile.compile(pipeline_path, doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
