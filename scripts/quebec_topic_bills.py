"""
quebec_topic_bills.py

Filters Quebec factuality scores to COVID, MAiD, and abortion/procreation bills.
"""
import json, re, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(f"{REPO}/data/dbpedia_pipeline/quebec/factuality_scores.json") as f:
    scores = json.load(f)

with open(f"{REPO}/data/canada/quebec_bills/cheminement_all_sessions.json") as f:
    cheminement = json.load(f)

# build date to title lookup from cheminement debate URLs
date_to_title = {}
for session, bills in cheminement.items():
    for b in bills:
        title = b.get("title", "")
        for debate in b.get("assembly_debates", []):
            url = debate.get("url", "")
            m = re.search(r"/(\d{4})(\d{2})(\d{2})/", url)
            if m:
                date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                date_to_title[date] = title

print(f"Date-to-title lookup: {len(date_to_title)} dates")
print(f"Factuality scores: {len(scores)} dates")
matched = sum(1 for d in scores if d in date_to_title)
print(f"Dates with title match: {matched}")
print()

TOPICS = {
    "COVID-19": [
        "covid", "coronavirus", "urgence sanitaire", "pandémie",
        "vaccination", "confinement", "état d'urgence sanitaire",
    ],
    "Medically Assisted Death": [
        "soins de fin de vie", "aide médicale à mourir",
        "mourir dans la dignité", "fin de vie",
    ],
    "Abortion/Procreation": [
        "procréation assistée", "avortement",
        "interruption de grossesse", "reproductif",
    ],
}

overall = [v["factuality_score"] for v in scores.values() if v["total_sentences"] > 0]
print(f"Quebec overall mean: {sum(overall)/len(overall):.4f} (n={len(overall)})")
print()

for topic, keywords in TOPICS.items():
    topic_dates = []
    for date, v in scores.items():
        if v["total_sentences"] == 0:
            continue
        title = date_to_title.get(date, "").lower()
        if any(kw.lower() in title for kw in keywords):
            topic_dates.append((date, v["factuality_score"], date_to_title.get(date, "")))

    if topic_dates:
        mean = sum(x[1] for x in topic_dates) / len(topic_dates)
        diff = mean - sum(overall)/len(overall)
        print(f"{topic}: n={len(topic_dates)}, mean={mean:.4f} ({diff:+.4f} vs overall)")
        seen_bills = set()
        for date, score, title in sorted(topic_dates):
            if title not in seen_bills:
                print(f"  Bill: {title[:70]}")
                seen_bills.add(title)
            print(f"  Date: {date}, factuality: {score:.4f}")
    else:
        print(f"{topic}: no bills found by keyword filter")
    print()

# also check what titles exist around COVID dates (2020-2022)
print("Sample titles from 2020-2022 Quebec debates:")
for date, title in sorted(date_to_title.items()):
    if "2020" <= date <= "2022" and title:
        print(f"  {date}: {title[:70]}")
