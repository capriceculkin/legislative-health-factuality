"""
build_classifier_2x2.py

2x2 classifier performance table using Joanie's July 16 annotations
as ground truth vs the keyword/committee filter prediction.
"""
import json, os, re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Joanie's clear yes/no labels from the July 16 email
# (session, bill_number_as_string): True=health, False=not health
JOANIE = {
    ("43-2","2"): True, ("43-2","25"): False, ("43-2","498"): False,
    ("43-2","595"): True, ("43-2","29"): False,
    ("43-1","106"): True, ("43-1","15"): True, ("43-1","32"): True,
    ("43-1","68"): True, ("43-1","83"): True, ("43-1","95"): False,
    ("43-1","36"): False, ("43-1","66"): False, ("43-1","101"): False,
    ("43-1","141"): False, ("43-1","136"): False, ("43-1","192"): False,
    ("43-1","213"): False, ("43-1","149"): False, ("43-1","150"): False,
    ("43-1","61"): False,
    ("42-2","38"): True, ("42-2","11"): True,
    ("42-1","2"): True, ("42-1","43"): True, ("42-1","52"): True,
    ("42-1","83"): True, ("42-1","31"): True, ("42-1","73"): True,
    ("42-1","196"): True, ("42-1","594"): True,
    ("42-1","9"): False, ("42-1","12"): False, ("42-1","35"): False,
    ("42-1","61"): False, ("42-1","85"): False, ("42-1","75"): False,
    ("42-1","59"): False, ("42-1","598"): False, ("42-1","691"): False,
    ("41-1","10"): True, ("41-1","20"): True, ("41-1","52"): True,
    ("41-1","118"): True, ("41-1","123"): True, ("41-1","44"): True,
    ("41-1","148"): True,
    ("41-1","97"): False, ("41-1","126"): False, ("41-1","152"): False,
    ("41-1","162"): False, ("41-1","170"): False, ("41-1","221"): False,
    ("40-1","67"): False,
    ("39-1","104"): False,
    ("38-1","23"): False, ("38-1","50"): False,
    ("36-2","151"): False,
    ("35-2","190"): False,
}

def main():
    # load the UPDATED filter output (post-Joanie feedback = 262 bills)
    health_path = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                               "quebec_health_bills.json")
    with open(health_path, encoding="utf-8") as f:
        bills = json.load(f)

    # build predicted positive set
    predicted = set()
    for b in bills:
        s = b.get("session","")
        title = b.get("title","")
        m = re.search(r"[Pp]rojet de loi n[°o\xa0]\s*(\d+)", title)
        if s and m:
            predicted.add((s, m.group(1)))

    TP = FP = TN = FN = 0
    for (session, num), joanie_health in JOANIE.items():
        key = (session, num.lstrip("0"))
        pred_pos = key in predicted
        if joanie_health and pred_pos:     TP += 1
        elif joanie_health and not pred_pos: FN += 1
        elif not joanie_health and pred_pos: FP += 1
        else:                               TN += 1

    total = TP+FP+TN+FN
    sens = TP/(TP+FN) if (TP+FN) else 0
    spec = TN/(TN+FP) if (TN+FP) else 0
    prec = TP/(TP+FP) if (TP+FP) else 0
    f1   = 2*prec*sens/(prec+sens) if (prec+sens) else 0
    acc  = (TP+TN)/total if total else 0

    print(f"\n{'='*50}")
    print("2x2 Classifier Performance (post-Joanie keyword update)")
    print(f"Ground truth: Joanie's manual annotations (n={total})\n")
    print(f"                    Predicted +    Predicted -")
    print(f"Joanie says health:     {TP:>4} (TP)     {FN:>4} (FN)")
    print(f"Joanie says not health: {FP:>4} (FP)     {TN:>4} (TN)")
    print(f"\nSensitivity (recall):  {sens:.3f}  ({TP}/{TP+FN})")
    print(f"Specificity:           {spec:.3f}  ({TN}/{TN+FP})")
    print(f"Precision:             {prec:.3f}  ({TP}/{TP+FP})")
    print(f"F1 score:              {f1:.3f}")
    print(f"Accuracy:              {acc:.3f}  ({TP+TN}/{total})")

if __name__ == "__main__":
    main()
