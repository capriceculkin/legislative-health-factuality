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
import unicodedata

INPUT_PATH = "data/canada/quebec_bills/cheminement_all_sessions.json"
OUTPUT_PATH = "data/canada/quebec_bills/quebec_health_bills.json"

HEALTH_KEYWORDS = [
    "sante", "soins", "medical", "medicament", "pharmacie",
    "assurance maladie", "services sociaux", "infirmier", "infirmiere",
    "hopital", "clinique", "medecin", "chirurgie", "dentaire",
    "readaptation", "handicap", "mental", "toxicomanie", "alcool",
    "sage-femme", "obstetrique", "ambulance",
    "RAMQ", "regime assurance maladie", "etablissement sante", "centre hospitalier",
    "CLSC", "CHSLD", "residence aines", "bien-etre", "aines", "vieillissement",
    "protection jeunesse", "deficience", "nutrition", "tabac", "cannabis",
    "vaccination", "epidemie", "pandemie", "maternite", "perinatal",
    "therapeutique", "psychiatrique", "depression", "COVID", "vaccin",
    "COVID-19", "coronavirus",
    "docteur", "medecins", "acces aux services", "systeme de sante",
    "services de sante", "services medicaux", "soins de fin de vie",
    "professions de sante", "aide medicale", "sante publique", "sante mentale",
    "sante et services sociaux", "renseignements de sante", "surveillance sanitaire",
    "hebergement", "centre de sante", "centre d'hebergement", "soins de longue duree",
    "autonomie", "assistance personnelle", "maltraitance", "vulnerabilite",
    "ainees", "infirmiers", "douleur", "maladie", "soin",
    # Joanie additions (July 16 review)
    "aide medicale a mourir",
    "sites d'injection supervisee", "consommation supervisee",
    "procreation assistee", "pause-vaccin", "vaccin", "vaccination",
    "urgence sanitaire", "état d'urgence",
    "consommation supervisée", "injection supervisée",
    "autonomie des personnes aînées", "aînés",
    "santé sexuelle", "sexuelle et reproductive",
    "funéraires", "soins funéraires",
    "cannabis", "substances psychoactives",
    "maltraitance", "proches aidants",
    "médicaments", "approvisionnement en médicaments",
    "procréation assistée",
]

EXCLUSION_KEYWORDS = [
    "mesures fiscales", "harmonisation", "discours sur le budget", "point sur la situation",
    "sports de combat", "permis d'alcool", "infractions en matiere de boissons",
    "conventions collectives", "partenariat entre le gouvernement", "municipalites",
    "loteries", "concours publicitaires", "appareils d'amusement", "code municipal",
    "loi electorale", "regime de retraite des enseignants", "regime de retraite des employes",
    "mise en oeuvre de certaines mesures du partenariat", "valeurs fondamentales",
    "alienations relatives", "maison robert", "charte des droits", "environnement sain",
    "droit fondamental", "charte des droits et libertes",
    "partenariat 2020-2024", "partenariat 2024", "placement syndical",
    "industrie de la construction", "stationnement payant", "hebergement touristique",
    "promotion internationale", "pratiques de commerce", "societe des alcools",
    "droits des locataires", "locataires aines", "ville de montreal metropole",
    "ville de quebec capitale", "eeyou istchee", "gouvernement regional",
    "nation crie", "organisation gouvernementale en matiere d'economie",
    "transactions d'emprunt", "instruments financiers",
    "securite des barrages", "vehicules zero emission",
    "communautes urbaines", "greve ou de lock-out", "permis d'alcool et d'autres",
    "commissions scolaires", "office des ressources humaines", "remuneration des dirigeants",
    "immeuble situe",
    # Joanie exclusions (July 16 review)
    "veterinaire",                       # vet care, explicitly out
    "sante financiere",                  # "financial health" of pension funds
    "regimes de retraite", "regime de retraite",  # retirement bills generally
    "sante et la securite du travail", "sante et de securite du travail",  # workplace safety
    "services de garde",                 # childcare, not health per Joanie
    "securite routiere",                 # road safety
    "eleves en classe",                  # school-safety bills
    "constituant en corporation",        # hospital-as-corporation bills (Wales Home etc.)
    "(prive)",                           # private bills, excluded per Joanie
    "assurance autonomie",                    # Bill 67, not health per Joanie
    "autonomie et les pouvoirs de la Ville",  # municipal autonomy bills
    "statut de capitale nationale",           # municipal bills
    "santé et de sécurité du travail",        # workplace safety (different from santé)
    "confiance du public envers le système de justice",  # justice bill 25
    "régimes de retraite",                    
]


def normalize(text):
    return unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8').lower()

def is_health_by_title(title):
    normalized_title = normalize(title)
    if any(normalize(ex) in normalized_title for ex in EXCLUSION_KEYWORDS):
        return False
    return any(normalize(kw) in normalized_title for kw in HEALTH_KEYWORDS)

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
