"""
run_poltextlab_classifier.py

Runs the poltextlab French CAP classifier on all Quebec health bills
and evaluates against Joanie's manual annotations.
CAP code 3 = Health (our target class).

Usage: python3 scripts/run_poltextlab_classifier.py
"""
import os, json, re
from transformers import AutoTokenizer, pipeline
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("HF_TOKEN")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JOANIE_NOT_HEALTH = {
    ("43-2","25"), ("43-2","498"), ("43-2","29"),
    ("43-1","95"), ("43-1","36"), ("43-1","66"), ("43-1","101"),
    ("43-1","141"), ("43-1","136"), ("43-1","149"), ("43-1","150"),
    ("43-1","61"), ("43-1","192"), ("43-1","213"),
    ("42-1","9"), ("42-1","12"), ("42-1","35"), ("42-1","61"),
    ("42-1","85"), ("42-1","75"), ("42-1","59"), ("42-1","598"), ("42-1","691"),
    ("41-1","97"), ("41-1","126"), ("41-1","152"), ("41-1","162"),
    ("41-1","170"), ("41-1","221"),
    ("40-1","67"), ("39-1","104"),
    ("38-1","23"), ("38-1","50"),
    ("36-2","151"), ("35-2","190"),
}

def main():
    print("Loading poltextlab French CAP model...")
    tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-large")
    pipe = pipeline(
        model="poltextlab/xlm-roberta-large-french-cap-v3",
        task="text-classification",
        tokenizer=tokenizer,
        use_fast=False,
        token=TOKEN,
    )
    print("Model loaded.\n")

    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills_combined.json")) as f:
        bills = json.load(f)

    print(f"Classifying {len(bills)} Quebec bills...")
    results = []
    health_count = 0

    for b in bills:
        title = b.get("title", "")
        session = b.get("session", "")
        m = re.search(r"n[°o\xa0]\s*(\d+)", title)
        num = m.group(1) if m else ""

        if not title:
            continue

        pred = pipe(title[:512])[0]
        label = pred["label"]
        score = pred["score"]
        is_health = label == "Health"
        if is_health:
            health_count += 1

        results.append({
            "session": session,
            "bill_number": num,
            "title": title[:80],
            "predicted_label": label,
            "predicted_health": is_health,
            "confidence": round(score, 3),
        })

    print(f"Classified as Health: {health_count}/{len(results)}")

    # evaluate against Joanie's labels
    tp = fp = tn = fn = 0
    for r in results:
        key = (r["session"], r["bill_number"])
        joanie_health = key not in JOANIE_NOT_HEALTH
        pred_health = r["predicted_health"]

        # only evaluate bills Joanie explicitly reviewed
        # bills in our list but NOT in NOT_HEALTH are implicit yes
        if key in JOANIE_NOT_HEALTH:
            joanie_health = False
        else:
            joanie_health = True  # implicit yes from silence

        if joanie_health and pred_health:     tp += 1
        elif joanie_health and not pred_health: fn += 1
        elif not joanie_health and pred_health: fp += 1
        else:                                   tn += 1

    sens = tp/(tp+fn) if (tp+fn) else 0
    spec = tn/(tn+fp) if (tn+fp) else 0
    prec = tp/(tp+fp) if (tp+fp) else 0
    f1   = 2*prec*sens/(prec+sens) if (prec+sens) else 0

    print(f"\n{'='*55}")
    print("poltextlab French CAP Model Performance")
    print(f"Evaluated against Joanie's 262 labels (227 implicit yes, 35 explicit no)\n")
    print(f"                    Predicted +    Predicted -")
    print(f"Joanie says health:     {tp:>4} (TP)     {fn:>4} (FN)")
    print(f"Joanie says not health: {fp:>4} (FP)     {tn:>4} (TN)")
    print(f"\nSensitivity: {sens:.3f}  Specificity: {spec:.3f}  F1: {f1:.3f}")

    # save predictions
    out_path = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/poltextlab_fr_predictions.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved predictions to {out_path}")


if __name__ == "__main__":
    main()
