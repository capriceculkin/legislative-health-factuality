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
    # Original 35 (July 16 email)
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
    # 149 confirmed negatives (Joanie August 3 review — all except 37-1 Bill 197)
    ("41-1","38"), ("43-1","75"), ("38-1","96"), ("39-1","198"),
    ("39-1","29"), ("41-1","193"), ("42-1","796"), ("42-1","193"),
    ("36-1","148"), ("43-1","109"), ("43-1","96"), ("42-1","391"),
    ("39-1","2"), ("39-1","79"), ("35-2","412"), ("43-1","81"),
    ("39-2","18"), ("36-1","136"), ("39-1","10"), ("35-2","22"),
    ("38-1","191"), ("43-2","200"), ("41-1","791"), ("36-1","151"),
    ("37-1","212"), ("38-1","190"), ("41-1","498"), ("39-2","496"),
    ("42-1","795"), ("42-1","217"), ("36-2","156"), ("42-1","497"),
    ("36-2","49"), ("37-1","227"), ("38-1","46"), ("43-1","593"),
    ("35-2","71"), ("41-1","109"), ("36-2","146"), ("42-1","66"),
    ("37-2","24"), ("36-2","61"), ("40-1","492"), ("42-1","18"),
    ("43-1","699"), ("39-1","53"), ("37-2","9"), ("42-1","70"),
    ("39-1","80"), ("42-1","790"), ("35-2","43"), ("36-2","74"),
    ("41-1","896"), ("36-2","97"), ("36-2","32"), ("39-2","77"),
    ("38-1","58"), ("42-1","30"), ("40-1","6"), ("39-1","196"),
    ("41-1","899"), ("35-2","83"), ("36-2","152"), ("38-1","73"),
    ("37-1","90"), ("42-2","36"), ("39-1","62"), ("43-1","110"),
    ("37-1","46"), ("36-1","51"), ("38-1","61"), ("42-1","1"),
    ("39-2","197"), ("37-1","42"), ("39-2","205"), ("35-2","272"),
    ("36-1","24"), ("35-2","69"), ("41-1","210"), ("38-1","47"),
    ("39-1","205"), ("38-1","39"), ("36-1","177"), ("36-1","41"),
    ("36-2","62"), ("39-1","5"), ("41-1","186"), ("35-2","431"),
    ("35-2","244"), ("42-1","210"), ("43-1","795"), ("41-1","30"),
    ("41-1","400"), ("41-1","793"), ("36-1","149"), ("42-2","892"),
    ("36-2","210"), ("36-2","196"), ("35-2","107"), ("39-1","226"),
    ("43-1","9"), ("41-1","56"), ("38-1","57"), ("37-2","26"),
    ("36-1","208"), ("41-1","690"), ("35-2","45"), ("43-2","17"),
    ("38-1","41"), ("35-2","279"), ("40-1","45"), ("35-2","423"),
    ("41-1","12"), ("37-2","52"), ("36-2","121"), ("41-1","890"),
    ("43-2","4"), ("37-1","88"), ("35-2","212"), ("43-1","48"),
    ("41-1","40"), ("36-2","66"), ("37-1","9"), ("39-1","115"),
    ("42-2","191"), ("39-1","121"), ("42-1","100"), ("35-2","197"),
    ("42-1","17"), ("41-1","113"), ("41-1","128"), ("35-2","148"),
    ("41-1","997"), ("38-1","48"), ("36-1","153"), ("39-2","202"),
    ("39-2","29"), ("37-1","29"), ("36-1","40"), ("36-2","119"),
    ("36-1","222"), ("35-1","231"), ("35-2","32"), ("41-1","89"),
    ("39-1","210"), ("39-1","36"), ("42-2","990"), ("37-1","203"),
    ("39-1","6"), 
}


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

    # Add 149 confirmed negatives from Joanie's August 3 review
    NEW_NEGATIVES = {
        ("41-1","38"), ("43-1","75"), ("38-1","96"), ("39-1","198"),
        ("39-1","29"), ("41-1","193"), ("42-1","796"), ("42-1","193"),
        ("36-1","148"), ("43-1","109"), ("43-1","96"), ("42-1","391"),
        ("39-1","2"), ("39-1","79"), ("35-2","412"), ("43-1","81"),
        ("39-2","18"), ("36-1","136"), ("39-1","10"), ("35-2","22"),
        ("38-1","191"), ("43-2","200"), ("41-1","791"), ("36-1","151"),
        ("37-1","212"), ("38-1","190"), ("41-1","498"), ("39-2","496"),
        ("42-1","795"), ("42-1","217"), ("36-2","156"), ("42-1","497"),
        ("36-2","49"), ("37-1","227"), ("38-1","46"), ("43-1","593"),
        ("35-2","71"), ("41-1","109"), ("36-2","146"), ("42-1","66"),
        ("37-2","24"), ("36-2","61"), ("40-1","492"), ("42-1","18"),
        ("43-1","699"), ("39-1","53"), ("37-2","9"), ("42-1","70"),
        ("39-1","80"), ("42-1","790"), ("35-2","43"), ("36-2","74"),
        ("41-1","896"), ("36-2","97"), ("36-2","32"), ("39-2","77"),
        ("38-1","58"), ("42-1","30"), ("40-1","6"), ("39-1","196"),
        ("41-1","899"), ("35-2","83"), ("36-2","152"), ("38-1","73"),
        ("37-1","90"), ("42-2","36"), ("39-1","62"), ("43-1","110"),
        ("37-1","46"), ("36-1","51"), ("38-1","61"), ("42-1","1"),
        ("39-2","197"), ("37-1","42"), ("39-2","205"), ("35-2","272"),
        ("36-1","24"), ("35-2","69"), ("41-1","210"), ("38-1","47"),
        ("39-1","205"), ("38-1","39"), ("36-1","177"), ("36-1","41"),
        ("36-2","62"), ("39-1","5"), ("41-1","186"), ("35-2","431"),
        ("35-2","244"), ("42-1","210"), ("43-1","795"), ("41-1","30"),
        ("41-1","400"), ("41-1","793"), ("36-1","149"), ("42-2","892"),
        ("36-2","210"), ("36-2","196"), ("35-2","107"), ("39-1","226"),
        ("43-1","9"), ("41-1","56"), ("38-1","57"), ("37-2","26"),
        ("36-1","208"), ("41-1","690"), ("35-2","45"), ("43-2","17"),
        ("38-1","41"), ("35-2","279"), ("40-1","45"), ("35-2","423"),
        ("41-1","12"), ("37-2","52"), ("36-2","121"), ("41-1","890"),
        ("43-2","4"), ("37-1","88"), ("35-2","212"), ("43-1","48"),
        ("41-1","40"), ("36-2","66"), ("37-1","9"), ("39-1","115"),
        ("42-2","191"), ("39-1","121"), ("42-1","100"), ("35-2","197"),
        ("42-1","17"), ("41-1","113"), ("41-1","128"), ("35-2","148"),
        ("41-1","997"), ("38-1","48"), ("36-1","153"), ("39-2","202"),
        ("39-2","29"), ("37-1","29"), ("36-1","40"), ("36-2","119"),
        ("36-1","222"), ("35-1","231"), ("35-2","32"), ("41-1","89"),
        ("39-1","210"), ("39-1","36"), ("42-2","990"), ("37-1","203"),
    }
    for (session, num) in NEW_NEGATIVES:
        title = all_bills.get((session, num), "")
        if title:
            X_train.append(title)
            y_train.append(0)
    print(f"After new negatives: {len(X_train)} examples ({sum(y_train)} health, {len(y_train)-sum(y_train)} not health)")

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
