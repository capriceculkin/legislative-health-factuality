"""
build_classifier_2x2.py

Builds the 2x2 classifier performance table David requested.

Ground truth: Joanie's manual annotations from the July 16 email
  - She reviewed 15 random bills + first 200 from the full list
  - Labels: "Relevant", "Same", "Probably", "Not relevant", "Unrelated" etc.

Prediction: whether the bill appears in quebec_health_bills_combined.json
  (i.e. whether our keyword/committee filter included it)

Reports: TP, FP, TN, FN, Sensitivity (recall), Specificity, Precision, F1
"""

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMBINED_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                              "quebec_health_bills.json")

# Joanie's annotations from the July 16 email review
# Format: (session, bill_number_or_title_fragment, joanie_label)
# Labels normalized: True = health-related, False = not health-related
# Source: Joanie's inline annotations in the Quebec Health Bill List email

JOANIE_ANNOTATIONS = {
    # Random sample of 15 (from email body)
    ("36-2", "modifiant la Loi sur les services de santé et les services sociaux concernant la prestation sécurisée"): True,   # "This is relevant"
    ("34-1", "75"): False,   # "focuses on justice system during COVID, not relevant"
    ("33-1", "92"): False,   # "completely unrelated"
    ("43-1", "95"): False,   # "childcare, not health related" (services de garde)
    ("43-2", "595"): True,   # "Relevant - assistance personnelle autodirigée"
    ("34-1", "115"): False,  # "What I found is unrelated"
    ("33-1", "130"): False,  # "Unrelated"
    ("35-2", "tabac"): True,  # "Relevant - Loi sur le tabac"
    ("33-1", "27"): False,   # "broadening definition quite a bit, may not want"
    ("36-1", "mandat des administrateurs"): True,  # "relevant, management in healthcare"
    ("39-1", "Wales Home"): False,  # "Unrelated"
    ("33-1", "250"): False,  # "Unrelated"
    ("37-2", "saines habitudes de vie"): True,  # "Relevant"
    ("41-1", "santé financière"): False,  # bill 14, pension fund health
    ("33-2", "137"): False,  # "What I found is unrelated"

    # From her review of first 200 (selected clear labels only)
    # "yes" / "relevant" / "same" = True
    # "no" / "unrelated" / "not relevant" / "probably not" = False
    ("43-2", "2"): True,     # "relevant"
    ("43-1", "130"): True,   # "relevant - paliative care"
    ("43-1", "15"): True,    # "relevant"
    ("43-1", "32"): True,    # "relevant - indigenous healthcare"
    ("43-1", "68"): True,    # "relevant - reduce admin burden on doctors"
    ("43-1", "83"): True,    # "relevant - medicine in public network"
    ("42-2", "38"): True,    # "yes - soins de fin de vie"
    ("42-2", "11"): True,    # "yes"
    ("42-1", "2"): True,     # "yes - cannabis"
    ("42-1", "43"): True,    # "yes - nurses"
    ("42-1", "52"): True,    # "yes - complaints regime"
    ("42-1", "83"): True,    # "yes - assurance maladie"
    ("42-1", "31"): True,    # "yes - pharmacie"
    ("42-1", "73"): True,    # "yes - IVF"
    ("42-1", "196"): True,   # "yes - quality of care ratios"
    ("41-1", "10"): True,    # "yes"
    ("41-1", "20"): True,    # "yes - medecine de famille"
    ("41-1", "52"): True,    # "yes - soins de fin de vie"
    ("41-1", "118"): True,   # "yes - laboratoires medicaux"
    ("41-1", "123"): True,   # "yes - sante et services sociaux"
    ("41-1", "44"): True,    # "yes - tabagisme"
    ("41-1", "148"): True,   # "yes - medicaments generiques"
    ("43-1", "36"): False,   # "not sure - recouvrement"
    ("43-1", "66"): False,   # "not sure, justice related"
    ("43-1", "101"): False,  # "doesn't seem relevant - lois du travail"
    ("43-1", "141"): False,  # "childcare, probably not"
    ("42-1", "9"): False,    # "probably not - socioeconomique"
    ("42-1", "12"): False,   # "no - gratuité scolaire"
    ("42-1", "35"): False,   # "no - publicité foncière"
    ("42-1", "61"): False,   # "probably not - relance économie"
    ("42-1", "85"): False,   # "no - élection municipale"
    ("42-1", "75"): False,   # "justice system, no"
    ("42-1", "188"): False,  # "no"
    ("41-1", "97"): False,   # "régimes de retraite"
    ("41-1", "126"): False,  # "santé financière - pension"
    ("41-1", "152"): False,  # "lois du travail"
    ("41-1", "162"): False,  # "bâtiment"
    ("41-1", "170"): False,  # "permis d'alcool"
    ("41-1", "221"): False,  # "cannabis corporation"
    ("42-1", "59"): False,   # "santé + sécurité + travail = workplace safety, no"
    ("42-1", "598"): False,  # "alcohol sale, no"
    ("42-1", "691"): False,  # "transportation"
    ("43-1", "61"): False,   # "transportation"
    ("43-1", "136"): False,  # "unrelated"
    ("43-1", "192"): False,  # "school safety, probably not"
    ("43-1", "213"): False,  # "nope - random municipality"
    ("43-1", "149"): False,  # "nope - random"
    ("43-1", "150"): False,  # "nope - instruction publique"
    ("43-2", "29"): False,   # "nope - voting"
    ("43-1", "106"): True,   # "relevant - access to medical services"
}


def load_predicted_positives():
    with open(COMBINED_PATH, encoding="utf-8") as f:
        bills = json.load(f)
    # set of (session, bill_number) tuples in the filtered list
    positives = set()
    for b in bills:
        s = b.get("session", "")
        n = b.get("bill_number", "")
        if s and n:
            positives.add((s, str(n)))
    return positives


def main():
    predicted_positives = load_predicted_positives()
    print(f"Total bills in classifier output: {len(predicted_positives)}")

    TP = FP = TN = FN = 0
    unclear = 0

    for (session, bill_id), joanie_says_health in JOANIE_ANNOTATIONS.items():
        # try to match by bill number
        key = (session, str(bill_id))
        predicted_positive = key in predicted_positives

        # if bill_id is a title fragment, try to find by partial match
        if not any(s == session for s, n in predicted_positives) or not bill_id.isdigit():
            unclear += 1
            continue

        if joanie_says_health and predicted_positive:
            TP += 1
        elif joanie_says_health and not predicted_positive:
            FN += 1
        elif not joanie_says_health and predicted_positive:
            FP += 1
        elif not joanie_says_health and not predicted_positive:
            TN += 1

    total = TP + FP + TN + FN
    sensitivity = TP / (TP + FN) if (TP + FN) > 0 else 0
    specificity = TN / (TN + FP) if (TN + FP) > 0 else 0
    precision   = TP / (TP + FP) if (TP + FP) > 0 else 0
    f1 = 2 * precision * sensitivity / (precision + sensitivity) if (precision + sensitivity) > 0 else 0
    accuracy = (TP + TN) / total if total > 0 else 0

    print(f"\n{'='*50}")
    print("2x2 Classifier Performance Table")
    print(f"Ground truth: Joanie's manual annotations (n={total})")
    print(f"Prediction: Keyword/committee filter\n")
    print(f"                    Predicted +    Predicted -")
    print(f"Joanie says health:     {TP:>4} (TP)     {FN:>4} (FN)")
    print(f"Joanie says not health: {FP:>4} (FP)     {TN:>4} (TN)")
    print(f"\nSensitivity (recall):  {sensitivity:.3f}  ({TP}/{TP+FN})")
    print(f"Specificity:           {specificity:.3f}  ({TN}/{TN+FP})")
    print(f"Precision:             {precision:.3f}  ({TP}/{TP+FP})")
    print(f"F1 score:              {f1:.3f}")
    print(f"Accuracy:              {accuracy:.3f}  ({TP+TN}/{total})")
    print(f"\nSkipped (title-only or ambiguous labels): {unclear}")
    print(f"\nNote: High sensitivity is the priority for this study since")
    print(f"false negatives (missed health bills) are more costly than")
    print(f"false positives (non-health bills included).")


if __name__ == "__main__":
    main()
