# test_tfidf_health_classifier.py
# Full TF-IDF classifier for health bill identification following David Chartash's
# suggestion from the June 24 meeting. Uses the 384 confirmed US health bills
# (CRS policy area = Health) as the positive class and a matched sample of
# non-health voted bills as the negative class.
# Improvements over the first version:
#   - HTML stripped from all summaries before training
#   - Bill title concatenated with summary for richer training text
#   - Random Forest instead of single decision tree
#   - 5-fold stratified cross-validation for reliable accuracy estimate
#   - Misclassified examples printed with full context
#   - Quebec French title test applied to both classifiers for comparison

import csv
import json
import random
import os
import re
import time
import requests
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report
import numpy as np

load_dotenv()
CONGRESS_KEY = os.getenv("CONGRESS_KEY")

HEALTH_BILLS_PATH = "data/us/health_bills_final_matched.csv"
ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"
POLICY_AREAS_PATH = "data/us/policy_areas.json"
SUMMARIES_CACHE_PATH = "data/us/bill_summaries_cache.json"

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def load_health_bills():
    bills = {}
    with open(HEALTH_BILLS_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            bill = row["bill_number"]
            congress = row["congress"]
            desc = row.get("vote_desc", "") or row.get("dtl_desc", "")
            if bill not in bills:
                bills[bill] = {"congress": congress, "desc": desc}
    print(f"Loaded {len(bills)} unique health bills")
    return bills

def load_non_health_bills(n=400):
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
            if area and area != "Health" and area not in ("", "NONE_CONFIRMED") and bill not in seen and desc:
                non_health.append({"bill": bill, "congress": congress, "desc": desc})
                seen.add(bill)
    random.seed(42)
    sampled = random.sample(non_health, min(n, len(non_health)))
    print(f"Loaded {len(sampled)} non-health bills")
    return sampled

def fetch_summary(congress, bill_number):
    type_map = {
        "HR": "hr", "HRES": "hres", "HJRES": "hjres", "HCONRES": "hconres",
        "S": "s", "SRES": "sres", "SJRES": "sjres", "SCONRES": "sconres"
    }
    match = re.match(r"^([A-Z]+)(\d+)$", bill_number)
    if not match:
        return ""
    bill_type = type_map.get(match.group(1))
    if not bill_type:
        return ""
    number = match.group(2)
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{number}/summaries"
    params = {"api_key": CONGRESS_KEY, "format": "json"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            summaries = resp.json().get("summaries", [])
            if summaries:
                return strip_html(summaries[-1].get("text", ""))
    except requests.RequestException:
        pass
    return ""

def fetch_title(congress, bill_number):
    type_map = {
        "HR": "hr", "HRES": "hres", "HJRES": "hjres", "HCONRES": "hconres",
        "S": "s", "SRES": "sres", "SJRES": "sjres", "SCONRES": "sconres"
    }
    match = re.match(r"^([A-Z]+)(\d+)$", bill_number)
    if not match:
        return ""
    bill_type = type_map.get(match.group(1))
    if not bill_type:
        return ""
    number = match.group(2)
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{number}"
    params = {"api_key": CONGRESS_KEY, "format": "json"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("bill", {}).get("title", "")
    except requests.RequestException:
        pass
    return ""

def load_or_build_cache(health_bills, non_health_bills):
    cache = {}
    if os.path.exists(SUMMARIES_CACHE_PATH):
        with open(SUMMARIES_CACHE_PATH) as f:
            raw = json.load(f)
        # Clean HTML on load
        cache = {k: strip_html(v) for k, v in raw.items()}

    all_bills = [(b, info["congress"]) for b, info in health_bills.items()]
    all_bills += [(b["bill"], b["congress"]) for b in non_health_bills]

    fetched = 0
    for bill, congress in all_bills:
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
    return cache

def build_text(bill, info_or_dict, cache, is_health=True):
    if is_health:
        congress = info_or_dict["congress"]
        desc = info_or_dict["desc"]
    else:
        congress = info_or_dict["congress"]
        desc = info_or_dict["desc"]
    key = f"{congress}_{bill}"
    summary = cache.get(key, "")
    # Concatenating title-like description with summary for richer signal
    return f"{desc} {summary}".strip()

def run_classifier(texts, labels, label_name):
    print(f"\n{'='*60}")
    print(f"Training on: {label_name}")
    print(f"Total: {len(texts)} ({labels.count(1)} health, {labels.count(0)} non-health)")
    print(f"{'='*60}")

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=1000,
        stop_words="english",
        sublinear_tf=True  # dampens effect of very frequent terms
    )
    X = vectorizer.fit_transform(texts)

    clf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(clf, X, labels, cv=cv, scoring="f1_macro")
    print(f"\n5-fold cross-validated F1 (macro): {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

    clf.fit(X, labels)
    y_pred = clf.predict(X)
    print("\nClassification Report (full training set):")
    print(classification_report(labels, y_pred, target_names=["Non-Health", "Health"]))

    feature_names = vectorizer.get_feature_names_out()
    importances = clf.feature_importances_
    top_idx = importances.argsort()[-30:][::-1]
    print("\nTop 30 most distinctive terms:")
    for i in top_idx:
        if importances[i] > 0:
            print(f"  {feature_names[i]}: {importances[i]:.4f}")

    misses = [(texts[i], labels[i], y_pred[i]) for i in range(len(texts)) if labels[i] != y_pred[i]]
    print(f"\nMisclassified examples ({len(misses)} total):")
    for text, true, pred in misses[:10]:
        tl = "Health" if true == 1 else "Non-Health"
        pl = "Health" if pred == 1 else "Non-Health"
        print(f"  [{tl} -> {pl}]: {text[:100]}")

    return vectorizer, clf

def test_on_quebec(vectorizer, clf, label):
    path = "data/canada/quebec_bills/cheminement_all_sessions.json"
    if not os.path.exists(path):
        print("\nQuebec data not found")
        return
    with open(path) as f:
        data = json.load(f)
    titles = [b.get("title", "") for bills in data.values() for b in bills if b.get("title")]
    if not titles:
        return
    X_qc = vectorizer.transform(titles)
    preds = clf.predict(X_qc)
    predicted = [titles[i] for i in range(len(titles)) if preds[i] == 1]
    print(f"\n{label}: {len(predicted)}/{len(titles)} Quebec bills classified as health-related")
    for t in predicted[:20]:
        print(f"  {t[:100]}")

if __name__ == "__main__":
    health_bills = load_health_bills()
    non_health_bills = load_non_health_bills(n=len(health_bills))

    # Phase 1: vote descriptions only
    health_desc = [info["desc"] for info in health_bills.values()]
    non_health_desc = [b["desc"] for b in non_health_bills]
    texts1 = health_desc + non_health_desc
    labels1 = [1] * len(health_desc) + [0] * len(non_health_desc)
    v1, clf1 = run_classifier(texts1, labels1, "vote descriptions only")
    test_on_quebec(v1, clf1, "Vote-description classifier")

    # Phase 2: clean summaries + description concatenated
    print("\nBuilding summary cache...")
    cache = load_or_build_cache(health_bills, non_health_bills)

    health_texts2 = [build_text(b, info, cache, True) for b, info in health_bills.items()]
    non_health_texts2 = [build_text(b["bill"], b, cache, False) for b in non_health_bills]
    texts2 = health_texts2 + non_health_texts2
    labels2 = [1] * len(health_texts2) + [0] * len(non_health_texts2)
    v2, clf2 = run_classifier(texts2, labels2, "clean summaries + descriptions (Random Forest)")
    test_on_quebec(v2, clf2, "Summary-trained classifier")