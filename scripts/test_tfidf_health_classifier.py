# test_tfidf_health_classifier.py
# Full TF-IDF decision tree classifier for health bill identification,
# built following David Chartash's suggestion from the June 24 meeting.
# Phase 1 (runs immediately): trains on vote descriptions already in hand.
# Phase 2 (overnight): fetches real bill summaries from Congress.gov for
# richer training text, then retrains and compares performance.
# Intended as a proof of concept before applying to the Quebec corpus
# where no CRS-equivalent classification exists.

import csv
import json
import random
import os
import time
import requests
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import numpy as np

load_dotenv()
CONGRESS_KEY = os.getenv("CONGRESS_KEY")

HEALTH_BILLS_PATH = "data/us/health_bills_final_matched.csv"
ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"
POLICY_AREAS_PATH = "data/us/policy_areas.json"
SUMMARIES_CACHE_PATH = "data/us/bill_summaries_cache.json"

# ── Phase 1: load vote descriptions ──────────────────────────────────────────

def load_health_titles():
    titles = {}
    with open(HEALTH_BILLS_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            bill = row["bill_number"]
            congress = row["congress"]
            text = row.get("vote_desc", "") or row.get("dtl_desc", "")
            if bill not in titles and text:
                titles[bill] = {"text": text, "congress": congress}
    print(f"Loaded {len(titles)} unique health bills")
    return titles

def load_non_health_titles(n=400):
    with open(POLICY_AREAS_PATH) as f:
        policy_areas = json.load(f)

    non_health = []
    seen = set()
    with open(ROLLCALLS_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            congress = row.get("congress", "")
            bill = row.get("bill_number", "")
            key = f"{congress}_{bill}"
            desc = row.get("vote_desc", "") or row.get("dtl_desc", "")
            area = policy_areas.get(key, "")
            if area and area != "Health" and area != "" and bill not in seen and desc:
                non_health.append({"text": desc, "congress": congress, "bill": bill})
                seen.add(bill)

    random.seed(42)
    sampled = random.sample(non_health, min(n, len(non_health)))
    print(f"Loaded {len(sampled)} non-health bills for negative class")
    return sampled

# ── Phase 2: fetch Congress.gov summaries ─────────────────────────────────────

def parse_bill_number(bill_number):
    # Splitting bill number into type and number for the Congress.gov API
    import re
    match = re.match(r"^([A-Z]+)(\d+)$", bill_number)
    if not match:
        return None, None
    type_map = {
        "HR": "hr", "HRES": "hres", "HJRES": "hjres", "HCONRES": "hconres",
        "S": "s", "SRES": "sres", "SJRES": "sjres", "SCONRES": "sconres"
    }
    bill_type = type_map.get(match.group(1))
    return bill_type, match.group(2)

def fetch_summary(congress, bill_number):
    bill_type, number = parse_bill_number(bill_number)
    if not bill_type:
        return ""
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{number}/summaries"
    params = {"api_key": CONGRESS_KEY, "format": "json"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            summaries = data.get("summaries", [])
            if summaries:
                # Taking the most recent summary
                return summaries[-1].get("text", "")
    except requests.RequestException:
        pass
    return ""

def load_or_fetch_summaries(health_bills, non_health_bills):
    # Loading from cache if available, otherwise fetching from API
    cache = {}
    if os.path.exists(SUMMARIES_CACHE_PATH):
        with open(SUMMARIES_CACHE_PATH) as f:
            cache = json.load(f)

    all_bills = [(b, info["congress"], "health") for b, info in health_bills.items()]
    all_bills += [(b["bill"], b["congress"], "non") for b in non_health_bills]

    fetched = 0
    for bill, congress, label in all_bills:
        key = f"{congress}_{bill}"
        if key not in cache:
            summary = fetch_summary(congress, bill)
            cache[key] = summary
            fetched += 1
            if fetched % 25 == 0:
                print(f"Fetched {fetched} summaries...")
                with open(SUMMARIES_CACHE_PATH, "w") as f:
                    json.dump(cache, f)
            time.sleep(0.5)

    with open(SUMMARIES_CACHE_PATH, "w") as f:
        json.dump(cache, f)
    print(f"Summary cache complete, {len(cache)} entries")
    return cache

# ── Training and evaluation ──────────────────────────────────────────────────

def run_classifier(texts, labels, label_name="vote descriptions"):
    print(f"\n{'='*60}")
    print(f"Training on: {label_name}")
    print(f"Total samples: {len(texts)} ({labels.count(1)} health, {labels.count(0)} non-health)")
    print(f"{'='*60}")

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=1000, stop_words="english")
    X = vectorizer.fit_transform(texts)

    # 5-fold stratified cross-validation for a more reliable accuracy estimate
    clf = DecisionTreeClassifier(max_depth=10, random_state=42)
    cv_scores = cross_val_score(clf, X, labels, cv=StratifiedKFold(n_splits=5), scoring="f1_macro")
    print(f"\n5-fold cross-validated F1 (macro): {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

    # Final fit on full data to get feature importances and misclassified examples
    clf.fit(X, labels)
    y_pred = clf.predict(X)

    print("\nClassification Report (full training set):")
    print(classification_report(labels, y_pred, target_names=["Non-Health", "Health"]))

    # Top terms
    feature_names = vectorizer.get_feature_names_out()
    importances = clf.feature_importances_
    top_indices = importances.argsort()[-30:][::-1]
    print("\nTop 30 most distinctive terms for health bills:")
    for i in top_indices:
        if importances[i] > 0:
            print(f"  {feature_names[i]}: {importances[i]:.4f}")

    # Misclassified examples
    misclassified = [(texts[i], labels[i], y_pred[i]) for i in range(len(texts)) if labels[i] != y_pred[i]]
    print(f"\nMisclassified examples ({len(misclassified)} total):")
    for text, true, pred in misclassified[:10]:
        true_label = "Health" if true == 1 else "Non-Health"
        pred_label = "Health" if pred == 1 else "Non-Health"
        print(f"  [{true_label} -> {pred_label}]: {text[:80]}")

    return vectorizer, clf

# ── Quebec French title test ──────────────────────────────────────────────────

def test_on_quebec_titles(vectorizer, clf):
    quebec_path = "data/canada/quebec_bills/cheminement_all_sessions.json"
    if not os.path.exists(quebec_path):
        print("\nQuebec Cheminement data not found, skipping French title test")
        return

    with open(quebec_path) as f:
        data = json.load(f)

    titles = []
    for session, bills in data.items():
        for bill in bills:
            title = bill.get("title", "")
            if title:
                titles.append(title)

    if not titles:
        print("\nNo Quebec bill titles found")
        return

    print(f"\n{'='*60}")
    print(f"Applying classifier to {len(titles)} Quebec bill titles (French)")
    print(f"Note: classifier was trained on English text, results are indicative only")
    print(f"{'='*60}")

    X_quebec = vectorizer.transform(titles)
    predictions = clf.predict(X_quebec)
    predicted_health = [(titles[i], ) for i in range(len(titles)) if predictions[i] == 1]

    print(f"\nBills classified as health-related: {len(predicted_health)} of {len(titles)}")
    print("\nSample predicted health bills:")
    for t in predicted_health[:20]:
        print(f"  {t[0][:100]}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    health_bills = load_health_titles()
    non_health_bills = load_non_health_titles(n=len(health_bills))

    # Phase 1: run on vote descriptions immediately
    health_texts = [info["text"] for info in health_bills.values()]
    non_health_texts = [b["text"] for b in non_health_bills]
    texts = health_texts + non_health_texts
    labels = [1] * len(health_texts) + [0] * len(non_health_texts)

    vectorizer, clf = run_classifier(texts, labels, label_name="vote descriptions")

    # Test on Quebec titles using the English-trained classifier
    test_on_quebec_titles(vectorizer, clf)

    # Phase 2: fetch summaries and retrain
    print(f"\n{'='*60}")
    print("Phase 2: fetching Congress.gov bill summaries for richer training text")
    print("This will take a while. Progress is saved every 25 bills.")
    print(f"{'='*60}")

    summary_cache = load_or_fetch_summaries(health_bills, non_health_bills)

    health_summaries = []
    non_health_summaries = []
    health_labels2 = []
    non_health_labels2 = []

    for bill, info in health_bills.items():
        key = f"{info['congress']}_{bill}"
        text = summary_cache.get(key, "") or info["text"]
        health_summaries.append(text)
        health_labels2.append(1)

    for b in non_health_bills:
        key = f"{b['congress']}_{b['bill']}"
        text = summary_cache.get(key, "") or b["text"]
        non_health_summaries.append(text)
        non_health_labels2.append(0)

    texts2 = health_summaries + non_health_summaries
    labels2 = health_labels2 + non_health_labels2

    vectorizer2, clf2 = run_classifier(texts2, labels2, label_name="Congress.gov summaries")

    # Test Quebec again with the summary-trained classifier
    print("\nApplying summary-trained classifier to Quebec titles:")
    test_on_quebec_titles(vectorizer2, clf2)