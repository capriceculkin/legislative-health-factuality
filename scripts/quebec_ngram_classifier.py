"""
quebec_ngram_classifier.py

TF-IDF n-gram classifier trained directly on French Quebec bill titles
using Joanie's manual annotations as training data. This is the classifier
David suggested - learning n-gram patterns from expert labels rather than
hand-curating keyword lists.

Usage: python3 scripts/quebec_ngram_classifier.py
"""

import json, re, os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score
from sklearn.metrics import confusion_matrix

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Joanie explicit NOT health (flagged July 16 email)
NOT_HEALTH = {
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
# All 262 filtered bills used as training: explicit not-health=0, rest=1 (implicit yes from silence)


def main():
    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/cheminement_all_sessions.json")) as f:
        cheminement = json.load(f)

    # build title lookup
    all_bills = {}
    for session, bills in cheminement.items():
        for b in bills:
            t = b.get("title", "")
            m = re.search(r"n[°o\xa0]\s*(\d+)", t)
            if m:
                all_bills[(session, m.group(1))] = t

    # build training set: all 262 filtered bills
    # Joanie reviewed the list and flagged not-health ones explicitly
    # silence = implicit yes
    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills.json")) as f:
        filtered_bills = json.load(f)

    X_train, y_train = [], []
    for b in filtered_bills:
        title = b.get("title", "")
        session = b.get("session", "")
        m = re.search(r"n[^\d]*(\d+)", title)
        num = m.group(1) if m else ""
        if title and session and num:
            label = 0 if (session, num) in NOT_HEALTH else 1
            X_train.append(title)
            y_train.append(label)

    n_health = sum(y_train)
    print(f"Training: {len(X_train)} examples ({n_health} health, {len(y_train)-n_health} not health)")

    # TF-IDF with unigrams, bigrams, trigrams on French titles
    clf = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            analyzer="word",
            sublinear_tf=True,
            strip_accents=None,  # keep French accents
        )),
       ("lr", LogisticRegression(max_iter=1000, C=0.1, solver="lbfgs", class_weight="balanced"))
    ])
    clf.fit(X_train, y_train)

    scores = cross_val_score(clf, X_train, y_train, cv=5, scoring="f1_macro")
    print(f"5-fold CV F1 (macro): {scores.mean():.3f} (+/- {scores.std():.3f})")

    # top discriminative n-grams
    feat_names = clf.named_steps["tfidf"].get_feature_names_out()
    coefs = clf.named_steps["lr"].coef_[0]
    top_idx = np.argsort(coefs)
    print("\nTop health n-grams (learned from Joanie's French labels):")
    for i in reversed(top_idx[-15:]):
        print(f"  {feat_names[i]}: {coefs[i]:.3f}")
    print("\nTop NON-health n-grams:")
    for i in top_idx[:10]:
        print(f"  {feat_names[i]}: {coefs[i]:.3f}")

    # evaluate on training set (in-sample, limited by n=59)
    preds = clf.predict(X_train)
    tn, fp, fn, tp = confusion_matrix(y_train, preds).ravel()
    sens = tp/(tp+fn) if (tp+fn) else 0
    spec = tn/(tn+fp) if (tn+fp) else 0
    prec = tp/(tp+fp) if (tp+fp) else 0
    f1   = 2*prec*sens/(prec+sens) if (prec+sens) else 0
    print(f"\nIn-sample performance (n={len(X_train)}):")
    print(f"  Sensitivity: {sens:.3f}  Specificity: {spec:.3f}  F1: {f1:.3f}")

    # classify all Quebec bills
    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills_combined.json")) as f:
        all_qc = json.load(f)

    titles = [b.get("title", "") for b in all_qc]
    predictions = clf.predict(titles)
    probabilities = clf.predict_proba(titles)[:, 1]
    n_health_pred = predictions.sum()
    print(f"\nClassified {n_health_pred} of {len(titles)} Quebec bills as health-related")

    # save predictions
    results = {}
    for b, pred, prob in zip(all_qc, predictions, probabilities):
        session = b.get("session", "")
        t = b.get("title", "")
        m = re.search(r"n[°o\xa0]\s*(\d+)", t)
        num = m.group(1) if m else ""
        if session and num:
            results[f"{session}-{num}"] = {
                "pred": int(pred),
                "prob": round(float(prob), 3),
                "title": t[:80]
            }

    out_path = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ngram_predictions.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved predictions to {out_path}")


if __name__ == "__main__":
    main()
