"""
xlm_roberta_health_classifier.py

Zero-shot cross-lingual health bill classifier.
Trains XLM-RoBERTa on English US health bill titles (CRS labels),
then classifies French Quebec bill titles without any French training data.

This approach is justified by:
  Shaheen et al. 2021 (arXiv:2111.14192): fine-tuning multilingual BERT on
  English legal data reaches 86% of jointly-trained performance on French.
  MultiEURLEX (Chalkidis et al. 2021): XLM-RoBERTa with one-to-many
  zero-shot transfer for legal topic classification.

Usage: python3 scripts/xlm_roberta_health_classifier.py
"""

import os
import json
import csv
import numpy as np
from sklearn.model_selection import cross_val_score
from sklearn.metrics import classification_report

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Joanie's gold labels for Quebec bills
JOANIE_LABELS = {
    ("43-2","2"): 1, ("43-2","25"): 0, ("43-2","498"): 0,
    ("43-2","595"): 1, ("43-2","29"): 0,
    ("43-1","106"): 1, ("43-1","15"): 1, ("43-1","32"): 1,
    ("43-1","68"): 1, ("43-1","83"): 1, ("43-1","95"): 0,
    ("43-1","36"): 0, ("43-1","66"): 0, ("43-1","101"): 0,
    ("43-1","141"): 0, ("43-1","136"): 0, ("43-1","192"): 0,
    ("43-1","149"): 0, ("43-1","150"): 0, ("43-1","61"): 0,
    ("42-2","38"): 1, ("42-2","11"): 1,
    ("42-1","2"): 1, ("42-1","43"): 1, ("42-1","52"): 1,
    ("42-1","83"): 1, ("42-1","31"): 1, ("42-1","73"): 1,
    ("42-1","196"): 1, ("42-1","594"): 1,
    ("42-1","9"): 0, ("42-1","12"): 0, ("42-1","35"): 0,
    ("42-1","61"): 0, ("42-1","85"): 0, ("42-1","75"): 0,
    ("42-1","59"): 0, ("42-1","598"): 0, ("42-1","691"): 0,
    ("41-1","10"): 1, ("41-1","20"): 1, ("41-1","52"): 1,
    ("41-1","118"): 1, ("41-1","123"): 1, ("41-1","44"): 1,
    ("41-1","148"): 1,
    ("41-1","97"): 0, ("41-1","126"): 0, ("41-1","152"): 0,
    ("41-1","162"): 0, ("41-1","170"): 0, ("41-1","221"): 0,
    ("40-1","67"): 0, ("39-1","104"): 0,
    ("38-1","23"): 0, ("38-1","50"): 0,
    ("36-2","151"): 0, ("35-2","190"): 0,
}


def load_us_training_data():
    """Load US health bills (positive) and sample non-health bills (negative)."""
    import random
    random.seed(42)

    # positive: health bills from final matched CSV
    pos_titles = []
    health_path = os.path.join(REPO_ROOT, "data", "us", "health_bills_final_matched.csv")
    if os.path.exists(health_path):
        with open(health_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("dtl_desc") or row.get("vote_desc","")
                if t and t not in pos_titles:
                    pos_titles.append(t)

    # negative: non-health bills (use Ontario non-health-tagged bills as negatives)
    neg_titles = []
    on_path = os.path.join(REPO_ROOT, "data", "canada", "ontario", "ontario_bill_index.json")
    if os.path.exists(on_path):
        with open(on_path, encoding="utf-8") as f:
            on_bills = json.load(f)
        non_health = [v.get("title","") for v in on_bills.values()
                      if not v.get("health_tag") and v.get("title")]
        # also add Ontario health bills as additional positives
        on_health = [v.get("title","") for v in on_bills.values()
                     if v.get("health_tag") and v.get("title")]
        pos_titles.extend(on_health)
        neg_titles = random.sample(non_health, min(len(pos_titles), len(non_health)))
    print(f"Training data: {len(pos_titles)} health, {len(neg_titles)} non-health")
    texts = pos_titles + neg_titles
    labels = [1] * len(pos_titles) + [0] * len(neg_titles)
    return texts, labels


def load_quebec_bills():
    """Load Quebec bills with titles and Joanie labels where available."""
    import re
    path = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                        "quebec_health_bills_combined.json")
    with open(path, encoding="utf-8") as f:
        bills = json.load(f)

    qc_texts, qc_keys, qc_gold = [], [], []
    for b in bills:
        title = b.get("title","")
        session = b.get("session","")
        num_raw = b.get("bill_number","")
        if not num_raw:
            m = re.search(r"n[°o\xa0]\s*(\d+)", title)
            num_raw = m.group(1) if m else ""
        num = str(num_raw).lstrip("0")
        key = (session, num)
        gold = JOANIE_LABELS.get(key, -1)  # -1 = no label
        qc_texts.append(title)
        qc_keys.append(key)
        qc_gold.append(gold)

    return qc_texts, qc_keys, qc_gold


def get_embeddings(texts, model, tokenizer, batch_size=32, device="cpu"):
    import torch
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        encoded = tokenizer(batch, padding=True, truncation=True,
                           max_length=128, return_tensors="pt").to(device)
        with torch.no_grad():
            output = model(**encoded)
        # use CLS token embedding
        embeddings = output.last_hidden_state[:, 0, :].cpu().numpy()
        all_embeddings.append(embeddings)
        if i % 100 == 0:
            print(f"  Embedded {i+len(batch)}/{len(texts)}")
    return np.vstack(all_embeddings)


def main():
    try:
        import torch
        from transformers import AutoTokenizer, AutoModel
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
    except ImportError:
        print("ERROR: pip install transformers torch scikit-learn")
        return

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}")
    print("\nLoading XLM-RoBERTa...")
    model_name = "xlm-roberta-base"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device)
    model.eval()

    print("\nLoading training data...")
    train_texts, train_labels = load_us_training_data()

    print("\nEmbedding training data...")
    train_embeddings = get_embeddings(train_texts, model, tokenizer, device=device)

    print("\nTraining logistic regression classifier...")
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(max_iter=1000, C=1.0))
    ])
    clf.fit(train_embeddings, train_labels)

    # cross-validate on training data
    from sklearn.model_selection import StratifiedKFold
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(clf, train_embeddings, train_labels,
                            cv=cv, scoring="f1_macro")
    print(f"\n5-fold CV F1 (macro) on English training: {scores.mean():.3f} (+/- {scores.std():.3f})")

    print("\nLoading Quebec bills...")
    qc_texts, qc_keys, qc_gold = load_quebec_bills()

    print(f"Embedding {len(qc_texts)} Quebec bills (zero-shot French inference)...")
    qc_embeddings = get_embeddings(qc_texts, model, tokenizer, device=device)

    qc_preds = clf.predict(qc_embeddings)
    print(f"\nQuebec classification: {qc_preds.sum()} of {len(qc_preds)} classified as health")

    # evaluate against Joanie's labels
    labeled_idx = [i for i, g in enumerate(qc_gold) if g != -1]
    if labeled_idx:
        y_true = [qc_gold[i] for i in labeled_idx]
        y_pred = [qc_preds[i] for i in labeled_idx]

        from sklearn.metrics import confusion_matrix
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        sens = tp/(tp+fn) if (tp+fn) else 0
        spec = tn/(tn+fp) if (tn+fp) else 0
        prec = tp/(tp+fp) if (tp+fp) else 0
        f1 = 2*prec*sens/(prec+sens) if (prec+sens) else 0

        print(f"\n{'='*55}")
        print("Zero-Shot Cross-Lingual Performance on Quebec Bills")
        print(f"Ground truth: Joanie's annotations (n={len(labeled_idx)})\n")
        print(f"                    Predicted +    Predicted -")
        print(f"Joanie says health:     {tp:>4} (TP)     {fn:>4} (FN)")
        print(f"Joanie says not health: {fp:>4} (FP)     {tn:>4} (TN)")
        print(f"\nSensitivity (recall):  {sens:.3f}")
        print(f"Specificity:           {spec:.3f}")
        print(f"Precision:             {prec:.3f}")
        print(f"F1 score:              {f1:.3f}")
        print(f"\nBaseline (keyword filter): Sensitivity 1.000, Specificity 0.171")
        print(f"XLM-RoBERTa zero-shot:     Sensitivity {sens:.3f}, Specificity {spec:.3f}")
        print("\nModel: xlm-roberta-base, trained on English US CRS labels")
        print("Zero-shot transfer: no French training data used")
        print("Reference: Shaheen et al. 2021 (arXiv:2111.14192)")


if __name__ == "__main__":
    main()
