# ontario_health_passages.py
# Filters the Ontario bill passages to health-related bills using the
# TF-IDF Random Forest classifier trained on confirmed US health bills.
# Extracts unique bill titles/numbers from the passages, classifies each,
# then filters the full passage set to only health-related bills.
# Output: data/canada/ontario_health_passages.json

import json
import re
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
import csv
import random
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
CONGRESS_KEY = os.getenv("CONGRESS_KEY")

PASSAGES_PATH = "data/canada/ontario_bill_passages.json"
HEALTH_BILLS_PATH = "data/us/health_bills_final_matched.csv"
ROLLCALLS_PATH = "data/us/voteview/house_rollcalls_1985_present.csv"
POLICY_AREAS_PATH = "data/us/policy_areas.json"
SUMMARIES_CACHE_PATH = "data/us/bill_summaries_cache.json"
OUTPUT_PATH = "data/canada/ontario_health_passages.json"

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def load_health_bills():
    bills = {}
    with open(HEALTH_BILLS_PATH) as f:
        for row in csv.DictReader(f):
            bill = row["bill_number"]
            congress = row["congress"]
            desc = row.get("vote_desc", "") or row.get("dtl_desc", "")
            if bill not in bills:
                bills[bill] = {"congress": congress, "desc": desc}
    return bills

def load_non_health_bills(n=400):
    with open(POLICY_AREAS_PATH) as f:
        policy_areas = json.load(f)
    non_health = []
    seen = set()
    with open(ROLLCALLS_PATH) as f:
        for row in csv.DictReader(f):
            congress = row.get("congress", "")
            bill = row.get("bill_number", "")
            key = f"{congress}_{bill}"
            desc = row.get("vote_desc", "") or row.get("dtl_desc", "")
            area = policy_areas.get(key, "")
            if area and area != "Health" and area not in ("", "NONE_CONFIRMED") and bill not in seen and desc:
                non_health.append({"bill": bill, "congress": congress, "desc": desc})
                seen.add(bill)
    random.seed(42)
    return random.sample(non_health, min(n, len(non_health)))

def train_classifier():
    print("Training health bill classifier...")
    health_bills = load_health_bills()
    non_health_bills = load_non_health_bills(n=len(health_bills))

    with open(SUMMARIES_CACHE_PATH) as f:
        raw_cache = json.load(f)
    cache = {k: strip_html(v) for k, v in raw_cache.items()}

    health_texts = []
    for bill, info in health_bills.items():
        key = f"{info['congress']}_{bill}"
        summary = cache.get(key, "")
        health_texts.append(f"{info['desc']} {summary}".strip())

    non_health_texts = []
    for b in non_health_bills:
        key = f"{b['congress']}_{b['bill']}"
        summary = cache.get(key, "")
        non_health_texts.append(f"{b['desc']} {summary}".strip())

    texts = health_texts + non_health_texts
    labels = [1] * len(health_texts) + [0] * len(non_health_texts)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=1000, stop_words="english", sublinear_tf=True)
    X = vectorizer.fit_transform(texts)
    clf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    clf.fit(X, labels)
    print("Classifier trained.")
    return vectorizer, clf

if __name__ == "__main__":
    # Train the classifier
    vectorizer, clf = train_classifier()

    # Load all Ontario passages
    print("Loading Ontario passages...")
    with open(PASSAGES_PATH) as f:
        passages = json.load(f)
    print(f"Loaded {len(passages)} passages")

    # Get unique bill numbers from passages
    unique_bills = list(set(p["bill_number"] for p in passages))
    print(f"Found {len(unique_bills)} unique Ontario bill numbers")

    # Classify each unique bill number using the passage text as a proxy
    # Building a representative text for each bill from its passages
    bill_texts = {}
    for p in passages:
        bn = p["bill_number"]
        if bn not in bill_texts:
            bill_texts[bn] = p["passage"]
        else:
            # Concatenate up to a few passages for richer signal
            if len(bill_texts[bn]) < 2000:
                bill_texts[bn] += " " + p["passage"]

    bill_list = list(bill_texts.keys())
    texts_to_classify = [bill_texts[b] for b in bill_list]

    X_ontario = vectorizer.transform(texts_to_classify)
    predictions = clf.predict(X_ontario)

    health_bills_ontario = set(bill_list[i] for i in range(len(bill_list)) if predictions[i] == 1)
    print(f"Classified {len(health_bills_ontario)} Ontario bills as health-related")

    # Filter passages to only health-related bills
    health_passages = [p for p in passages if p["bill_number"] in health_bills_ontario]
    print(f"Filtered to {len(health_passages)} health-related passages")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(health_passages, f, indent=2, ensure_ascii=False)
    print(f"Saved to {OUTPUT_PATH}")

    # Print sample
    print("\nSample health-related Ontario bill numbers found:")
    for b in sorted(health_bills_ontario)[:20]:
        print(f"  Bill {b}")