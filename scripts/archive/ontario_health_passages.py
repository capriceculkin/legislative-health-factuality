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
    vectorizer, clf = train_classifier()

    print("Loading Ontario passages...")
    with open(PASSAGES_PATH) as f:
        passages = json.load(f)
    print(f"Loaded {len(passages)} passages")

    # Building representative text per bill, scoped to session year
    bill_texts = {}
    bill_passage_counts = {}
    for p in passages:
        bn = p["scoped_bill_id"]
        if bn not in bill_texts:
            bill_texts[bn] = p["passage"]
            bill_passage_counts[bn] = 1
        elif bill_passage_counts[bn] < 5:
            bill_texts[bn] += " " + p["passage"]
            bill_passage_counts[bn] += 1

    bill_list = list(bill_texts.keys())
    print(f"Found {len(bill_list)} unique Ontario bill numbers")

    # Truncating to keep vectorizer from hanging
    bill_texts = {k: v[:3000] for k, v in bill_texts.items()}
    texts_to_classify = [bill_texts[b] for b in bill_list]

    X_ontario = vectorizer.transform(texts_to_classify)
    predictions = clf.predict(X_ontario)

    # Building the set of health-related scoped bill IDs
    health_bills_ontario = set(bill_list[i] for i in range(len(bill_list)) if predictions[i] == 1)
    print(f"Classified {len(health_bills_ontario)} Ontario bills as health-related")

    # Writing health passages to output file incrementally
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("[\n")
        first = True
        count = 0
        for p in passages:
            if p["scoped_bill_id"] in health_bills_ontario:
                if not first:
                    f.write(",\n")
                f.write(json.dumps(p, ensure_ascii=False))
                first = False
                count += 1
        f.write("\n]")

    print(f"Saved {count} health passages to {OUTPUT_PATH}")
    print("\nSample health-related Ontario bill IDs:")
    for b in sorted(health_bills_ontario)[:20]:
        print(f"  {b}")