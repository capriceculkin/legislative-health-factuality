"""
quebec_ngram_classifier.py

TF-IDF n-gram classifier trained on French Quebec bill titles + debate text
using Joanie's manual annotations as training data.

Usage: python3 scripts/quebec_ngram_classifier.py
"""
import json, re, os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.svm import LinearSVC
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report, confusion_matrix

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ALL confirmed NOT health across all Joanie reviews
NOT_HEALTH = {
    # July 16 original negatives
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
    # August 3 confirmed negatives (149 bills)
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
    # August 18 confirmed negatives (Joanie review of 100 bills)
    ("43-1","41"), ("43-1","104"), ("43-1","212"), ("43-1","591"),
    ("43-1","37"), ("42-2","8"), ("42-2","15"), ("42-1","20"),
    ("42-1","27"), ("42-1","37"), ("42-1","597"), ("41-1","42"),
    ("41-1","88"), ("41-1","99"), ("41-1","102"), ("41-1","154"),
    ("40-1","21"), ("40-1","22"), ("40-1","194"), ("40-1","210"),
    ("40-1","497"), ("39-2","48"), ("39-2","51"), ("39-2","68"),
    ("39-2","79"), ("39-2","216"), ("39-1","51"), ("39-1","58"),
    ("39-1","94"), ("39-1","217"), ("39-1","231"),
}

# Confirmed health from August 18 review (bills without comments = health)
CONFIRMED_HEALTH = {
    ("43-2","15"), ("43-2","16"), ("43-2","19"), ("43-2","23"), ("43-2","495"),
    ("43-1","3"), ("43-1","10"), ("43-1","11"), ("43-1","67"), ("43-1","103"),
    ("43-1","197"), ("43-1","398"), ("43-1","595"), ("43-1","790"),
    ("43-1","893"), ("43-1","894"), ("43-1","994"),
    ("42-2","19"), ("42-2","28"), ("42-2","29"), ("42-2","498"),
    ("42-1","7"), ("42-1","28"), ("42-1","29"), ("42-1","101"),
    ("42-1","105"), ("42-1","798"), ("42-1","898"),
    ("41-1","66"), ("41-1","81"), ("41-1","92"), ("41-1","115"),
    ("41-1","130"), ("41-1","157"), ("41-1","160"), ("41-1","189"), ("41-1","197"),
    ("40-1","7"), ("40-1","14"), ("40-1","30"), ("40-1","37"), ("40-1","52"),
    ("39-2","7"), ("39-2","16"), ("39-2","36"), ("39-2","53"), ("39-2","59"),
    ("39-2","74"), ("39-2","84"),
    ("39-1","7"), ("39-1","14"), ("39-1","21"), ("39-1","24"), ("39-1","26"),
    ("39-1","34"), ("39-1","43"), ("39-1","47"), ("39-1","49"), ("39-1","56"),
    ("39-1","59"), ("39-1","67"), ("39-1","106"), ("39-1","125"),
    ("39-1","127"), ("39-1","194"),
}


def get_debate_text(session, num, speaker_turns, bill_index):
    """Get first 300 words of debate text for a bill."""
    dates = bill_index.get((session, num), [])
    words = []
    for date in sorted(dates)[:3]:  # use up to 3 debate dates
        day = speaker_turns.get(date, {})
        for turn in day.get("turns", [])[:20]:
            text = turn.get("text", "")
            words.extend(text.split())
            if len(words) >= 300:
                break
        if len(words) >= 300:
            break
    return " ".join(words[:300])


def main():
    # Load cheminement for title lookup
    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/cheminement_all_sessions.json")) as f:
        cheminement = json.load(f)
    all_bills = {}
    for session, bills in cheminement.items():
        for b in bills:
            t = b.get("title", "")
            m = re.search(r"n[°o\xa0]\s*(\d+)", t)
            if m:
                all_bills[(session, m.group(1))] = t

    # Load speaker turns for debate text
    turns_path = os.path.join(REPO_ROOT, "data/canada/quebec_speaker_turns.json")
    with open(turns_path) as f:
        speaker_turns = json.load(f)

    # Build bill_index: (session, num) -> list of debate dates
    bill_index = {}
    for b in sum(cheminement.values(), []):
        t = b.get("title", "")
        s = b.get("session", "")
        m = re.search(r"n[°o\xa0]\s*(\d+)", t)
        if m and s:
            key = (s, m.group(1))
            # dates from speaker turns matching this session
            if key not in bill_index:
                bill_index[key] = []

    # Match speaker turn dates to bills via session
    for date_key in speaker_turns:
        # date format is YYYYMMDD
        year = int(date_key[:4]) if len(date_key) >= 4 else 0
        for (sess, num), dates in bill_index.items():
            # rough session-year matching
            sess_years = {
                "43-2": (2025, 2026), "43-1": (2022, 2025),
                "42-2": (2021, 2022), "42-1": (2018, 2021),
                "41-1": (2014, 2018), "40-1": (2012, 2014),
                "39-2": (2011, 2012), "39-1": (2009, 2011),
                "38-1": (2007, 2008), "37-2": (2006, 2007),
                "37-1": (2003, 2006), "36-2": (2001, 2003),
                "36-1": (1999, 2001), "35-2": (1996, 1998),
                "35-1": (1994, 1996), "34-2": (1992, 1994),
                "34-1": (1989, 1992), "33-2": (1988, 1989),
                "33-1": (1985, 1988),
            }
            yr = sess_years.get(sess, (0, 0))
            if yr[0] <= year <= yr[1]:
                dates.append(date_key)

    # Load keyword-filtered bills as positive training examples
    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills.json")) as f:
        filtered_bills = json.load(f)

    X_train, y_train = [], []

    # Positives: filtered bills not in NOT_HEALTH
    for b in filtered_bills:
        title = b.get("title", "")
        session = b.get("session", "")
        m = re.search(r"n[^\d]*(\d+)", title)
        num = m.group(1) if m else ""
        if title and session and num:
            key = (session, num)
            label = 0 if key in NOT_HEALTH else 1
            debate = get_debate_text(session, num, speaker_turns, bill_index)
            text = title + " " + debate
            era = "recent" if session >= "42" else "mid" if session >= "38" else "old"
            X_train.append(f"ERA_{era} " + title + " " + debate)
            y_train.append(label)

    n_health = sum(y_train)
    print(f"Training: {len(X_train)} examples ({n_health} health, {len(y_train)-n_health} not health)")

    # Add confirmed negatives from NOT_HEALTH that aren't already in training set
    trained_keys = set()
    for b in filtered_bills:
        title = b.get("title", "")
        session = b.get("session", "")
        m = re.search(r"n[^\d]*(\d+)", title)
        if m and session:
            trained_keys.add((session, m.group(1)))

    for (session, num) in NOT_HEALTH:
        if (session, num) not in trained_keys:
            title = all_bills.get((session, num), "")
            if title:
                debate = get_debate_text(session, num, speaker_turns, bill_index)
                text = title + " " + debate
                era = "recent" if session >= "42" else "mid" if session >= "38" else "old"
                X_train.append(f"ERA_{era} " + title + " " + debate)
                y_train.append(0)

    # Add confirmed health from August 18 review
    for (session, num) in CONFIRMED_HEALTH:
        if (session, num) not in trained_keys:
            title = all_bills.get((session, num), "")
            if title:
                debate = get_debate_text(session, num, speaker_turns, bill_index)
                text = title + " " + debate
                era = "recent" if session >= "42" else "mid" if session >= "38" else "old"
                X_train.append(f"ERA_{era} " + title + " " + debate)
                y_train.append(1)

    print(f"After all labels: {len(X_train)} examples ({sum(y_train)} health, {len(y_train)-sum(y_train)} not health)")

    # SVM with word + char n-grams
    clf = Pipeline([
        ("features", FeatureUnion([
            ("word", TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 3),
                max_features=10000,
                sublinear_tf=True,
            )),
            ("char", TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                max_features=10000,
                sublinear_tf=True,
            )),
        ])),
        ("svm", LinearSVC(C=1.0, class_weight="balanced", max_iter=2000))
    ])

    X = np.array(X_train)
    y = np.array(y_train)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(clf, X, y, cv=cv, scoring="f1_macro")
    print(f"5-fold CV F1 (macro): {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

    clf.fit(X, y)
    y_pred = clf.predict(X)
    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
    sens = tp / (tp + fn) if (tp + fn) > 0 else 0
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0
    print(f"In-sample performance (n={len(y)}):")
    print(f"  Sensitivity: {sens:.3f}  Specificity: {spec:.3f}  F1: {f1:.3f}")

    # Classify all Quebec bills
    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills_combined.json")) as f:
        all_quebec = json.load(f)

    predictions = {}
    classified_health = 0
    for b in all_quebec:
        title = b.get("title", "")
        session = b.get("session", "")
        m = re.search(r"n[°o\xa0]\s*(\d+)", title)
        if not m or not session:
            continue
        num = m.group(1)
        debate = get_debate_text(session, num, speaker_turns, bill_index)
        text = title + " " + debate
        pred = clf.predict([text])[0]
        prob = 0.5  # LinearSVC doesn't have predict_proba by default
        key = f"{session}-{num}"
        predictions[key] = {"pred": int(pred), "prob": prob, "title": title[:80]}
        if pred == 1:
            classified_health += 1

    out_path = os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ngram_predictions.json")
    with open(out_path, "w") as f:
        json.dump(predictions, f, indent=1)

    print(f"Classified {classified_health} of {len(predictions)} Quebec bills as health-related")
    print(f"Saved predictions to {out_path}")


if __name__ == "__main__":
    main()