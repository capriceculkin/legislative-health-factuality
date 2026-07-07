# quebec_health_bill_filter.py
# Filters the Quebec Cheminement dataset to health-related bills using two signals:
# 1. Bill title contains health-related French keywords
# 2. Bill passed through the Commission de la sante et des services sociaux (csss)
# at any stage, as indicated by "csss" appearing in any committee debate link.
# Follows David Chartash's suggestion from the July 5 meeting to start with
# health-in-the-name and committee routing approaches before a full classifier.
# Output: data/canada/quebec_bills/quebec_health_bills.json

import json
import os

INPUT_PATH = "data/canada/quebec_bills/cheminement_all_sessions.json"
OUTPUT_PATH = "data/canada/quebec_bills/quebec_health_bills.json"

HEALTH_KEYWORDS = [
    "sante", "soins", "medical", "medicament", "pharmacie",
    "assurance maladie", "services sociaux", "infirmier", "infirmiere",
    "hopital", "clinique", "medecin", "chirurgie", "dentaire",
    "readaptation", "handicap", "mental", "toxicomanie", "alcool", "sage-femme", "obstetrique", "ambulance",
    "RAMQ", "regime assurance maladie", "etablissement sante", "centre hospitalier",
    "CLSC", "CHSLD", "residence aines", "bien-etre", "aines", "vieillissement",
    "protection jeunesse", "deficience", "nutrition", "tabac", "cannabis",
    "vaccination", "epidemie", "pandemie", "maternite", "perinatal",
    "therapeutique", "psychiatrique", "depression", "COVID", "vaccin", "COVID-19", "coronavirus",
    "docteur"
]


EXCLUSION_KEYWORDS = [
    "mesures fiscales",
    "harmonisation",
    "discours sur le budget",
    "point sur la situation",
]

def is_health_by_title(title):
    title_lower = title.lower()
    if any(ex.lower() in title_lower for ex in EXCLUSION_KEYWORDS):
        return False
    return any(kw.lower() in title_lower for kw in HEALTH_KEYWORDS)

def is_health_by_committee(bill):
    for link in bill.get("committee_debates", []):
        url = link.get("url", "")
        if "csss" in url.lower():
            return True
    return False

if __name__ == "__main__":
    with open(INPUT_PATH) as f:
        data = json.load(f)

    health_bills = []
    total = 0
    by_title = 0
    by_committee = 0
    by_both = 0

    for session, bills in data.items():
        for bill in bills:
            total += 1
            title = bill.get("title", "")
            title_match = is_health_by_title(title)
            committee_match = is_health_by_committee(bill)

            if title_match or committee_match:
                bill["session"] = session
                bill["matched_by_title"] = title_match
                bill["matched_by_committee"] = committee_match
                health_bills.append(bill)

                if title_match and committee_match:
                    by_both += 1
                elif title_match:
                    by_title += 1
                else:
                    by_committee += 1

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(health_bills, f, indent=2, ensure_ascii=False)

    print(f"Total bills in Cheminement: {total}")
    print(f"Health bills found: {len(health_bills)}")
    print(f"  Matched by title only: {by_title}")
    print(f"  Matched by committee only: {by_committee}")
    print(f"  Matched by both: {by_both}")
    print(f"Saved to {OUTPUT_PATH}")
    print()
    print("Sample health bills:")
    for b in health_bills[:15]:
        print(f"  [{b['session']}] {b['title'][:80]}")