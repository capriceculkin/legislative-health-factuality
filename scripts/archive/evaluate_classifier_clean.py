"""
evaluate_classifier_clean.py

Proper train/test evaluation with no data leakage:
- Train on: keyword filter bills + August 3 negatives (original training data)
- Test on: Joanie's August 18 labels (held-out ground truth, never seen in training)

This gives an honest estimate of classifier performance on unseen bills.
"""
import json, re, os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.svm import LinearSVC
from sklearn.metrics import confusion_matrix, f1_score

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── TRAINING DATA (July 16 + August 3 reviews only) ──────────────────────────

TRAIN_NEGATIVES = {
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
}

# ── TEST DATA (August 18 review — held out completely from training) ──────────

TEST_LABELS = {
    ("43-2","15"): 0, ("43-2","16"): 1, ("43-2","19"): 1,
    ("43-2","23"): 1, ("43-2","495"): 1,
    ("43-1","3"): 1, ("43-1","10"): 1, ("43-1","11"): 1,
    ("43-1","37"): 0, ("43-1","41"): 0, ("43-1","67"): 1,
    ("43-1","103"): 1, ("43-1","104"): 0, ("43-1","197"): 1,
    ("43-1","212"): 0, ("43-1","398"): 1, ("43-1","591"): 0,
    ("43-1","595"): 1, ("43-1","790"): 1, ("43-1","893"): 1,
    ("43-1","894"): 1, ("43-1","994"): 1,
    ("42-2","8"): 0, ("42-2","15"): 0, ("42-2","19"): 1,
    ("42-2","28"): 1, ("42-2","29"): 1, ("42-2","498"): 1,
    ("42-1","7"): 1, ("42-1","20"): 0, ("42-1","27"): 0,
    ("42-1","28"): 1, ("42-1","29"): 1, ("42-1","37"): 0,
    ("42-1","101"): 1, ("42-1","105"): 1, ("42-1","597"): 0,
    ("42-1","798"): 1, ("42-1","898"): 1,
    ("41-1","42"): 0, ("41-1","66"): 1, ("41-1","81"): 1,
    ("41-1","88"): 0, ("41-1","92"): 1, ("41-1","99"): 0,
    ("41-1","102"): 0, ("41-1","115"): 1, ("41-1","130"): 1,
    ("41-1","154"): 0, ("41-1","157"): 1, ("41-1","160"): 1,
    ("41-1","189"): 1, ("41-1","197"): 1,
    ("40-1","7"): 1, ("40-1","14"): 1, ("40-1","21"): 0,
    ("40-1","22"): 0, ("40-1","30"): 1, ("40-1","37"): 1,
    ("40-1","52"): 1, ("40-1","194"): 0, ("40-1","210"): 0,
    ("40-1","497"): 0,
    ("39-2","7"): 1, ("39-2","16"): 1, ("39-2","36"): 1,
    ("39-2","48"): 0, ("39-2","51"): 0, ("39-2","53"): 1,
    ("39-2","59"): 1, ("39-2","68"): 0, ("39-2","74"): 1,
    ("39-2","79"): 0, ("39-2","84"): 1, ("39-2","216"): 0,
    ("39-1","7"): 1, ("39-1","14"): 1, ("39-1","21"): 1,
    ("39-1","24"): 1, ("39-1","26"): 1, ("39-1","34"): 1,
    ("39-1","43"): 1, ("39-1","47"): 1, ("39-1","49"): 1,
    ("39-1","51"): 0, ("39-1","56"): 1, ("39-1","58"): 0,
    ("39-1","59"): 1, ("39-1","67"): 1, ("39-1","94"): 0,
    ("39-1","106"): 1, ("39-1","125"): 1, ("39-1","127"): 1,
    ("39-1","194"): 1, ("39-1","217"): 0, ("39-1","231"): 0,
}


def get_debate_text(session, num, speaker_turns, sess_years):
    """Get first 300 words of debate text for a bill."""
    yr_range = sess_years.get(session, (0, 0))
    words = []
    for date_key in sorted(speaker_turns.keys()):
        year = int(date_key[:4]) if len(date_key) >= 4 else 0
        if yr_range[0] <= year <= yr_range[1]:
            day = speaker_turns[date_key]
            for turn in day.get("turns", [])[:20]:
                words.extend(turn.get("text", "").split())
                if len(words) >= 300:
                    break
        if len(words) >= 300:
            break
    return " ".join(words[:300])


def main():
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

    print("Loading data...")
    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/cheminement_all_sessions.json")) as f:
        cheminement = json.load(f)
    all_bills = {}
    for session, bills in cheminement.items():
        for b in bills:
            t = b.get("title", "")
            m = re.search(r"n[°o\xa0]\s*(\d+)", t)
            if m:
                all_bills[(session, m.group(1))] = t

    with open(os.path.join(REPO_ROOT, "data/canada/quebec_speaker_turns.json")) as f:
        speaker_turns = json.load(f)

    with open(os.path.join(REPO_ROOT, "data/canada/quebec_bills/quebec_health_bills.json")) as f:
        filtered_bills = json.load(f)

    # ── BUILD TRAINING SET ────────────────────────────────────────────────────
    print("Building training set...")
    X_train, y_train = [], []
    train_keys = set()

    for b in filtered_bills:
        title = b.get("title", "")
        session = b.get("session", "")
        m = re.search(r"n[^\d]*(\d+)", title)
        num = m.group(1) if m else ""
        if not (title and session and num):
            continue
        key = (session, num)
        if key in TEST_LABELS:
            continue  # strictly exclude test bills from training
        label = 0 if key in TRAIN_NEGATIVES else 1
        debate = get_debate_text(session, num, speaker_turns, sess_years)
        X_train.append(title + " " + debate)
        y_train.append(label)
        train_keys.add(key)

    for (session, num) in TRAIN_NEGATIVES:
        key = (session, num)
        if key in train_keys or key in TEST_LABELS:
            continue
        title = all_bills.get(key, "")
        if title:
            debate = get_debate_text(session, num, speaker_turns, sess_years)
            X_train.append(title + " " + debate)
            y_train.append(0)
            train_keys.add(key)

    print(f"Train: {len(X_train)} examples ({sum(y_train)} health, {len(y_train)-sum(y_train)} not health)")

    # ── BUILD TEST SET ────────────────────────────────────────────────────────
    print("Building test set...")
    X_test, y_test, test_keys_list = [], [], []

    for (session, num), label in TEST_LABELS.items():
        title = all_bills.get((session, num), "")
        if not title:
            continue
        debate = get_debate_text(session, num, speaker_turns, sess_years)
        X_test.append(title + " " + debate)
        y_test.append(label)
        test_keys_list.append((session, num))

    print(f"Test:  {len(X_test)} examples ({sum(y_test)} health, {len(y_test)-sum(y_test)} not health)")

    # ── TRAIN CLASSIFIER ──────────────────────────────────────────────────────
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

    clf.fit(X_train, y_train)

    # ── EVALUATE ON HELD-OUT TEST SET ─────────────────────────────────────────
    y_pred = clf.predict(X_test)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    sens = tp / (tp + fn) if (tp + fn) > 0 else 0
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0

    print(f"\n{'='*60}")
    print(f"HELD-OUT TEST RESULTS (n={len(y_test)})")
    print(f"{'='*60}")
    print(f"Sensitivity: {sens:.3f}  Specificity: {spec:.3f}")
    print(f"Precision:   {prec:.3f}  F1:          {f1:.3f}")
    print(f"TP:{tp}  FP:{fp}  TN:{tn}  FN:{fn}")

    # Show errors
    print(f"\nFalse positives (predicted health, actually not):")
    for i, (s, n) in enumerate(test_keys_list):
        if y_test[i] == 0 and y_pred[i] == 1:
            print(f"  {s}-{n}: {all_bills.get((s,n),'')[:80]}")

    print(f"\nFalse negatives (predicted not health, actually health):")
    for i, (s, n) in enumerate(test_keys_list):
        if y_test[i] == 1 and y_pred[i] == 0:
            print(f"  {s}-{n}: {all_bills.get((s,n),'')[:80]}")


if __name__ == "__main__":
    main()
