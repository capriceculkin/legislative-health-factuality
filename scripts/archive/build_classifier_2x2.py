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

     # Joanie August 18 review 
    ("43-2","15"): True,
    ("43-2","16"): True,
    ("43-2","19"): True,
    ("43-2","23"): True,
    ("43-2","495"): True,
    ("43-1","3"): True,
    ("43-1","10"): True,
    ("43-1","11"): True,
    ("43-1","37"): False,
    ("43-1","41"): False,
    ("43-1","67"): True,
    ("43-1","103"): True,
    ("43-1","104"): False,
    ("43-1","197"): True,
    ("43-1","212"): False,
    ("43-1","398"): True,
    ("43-1","591"): False,
    ("43-1","595"): True,
    ("43-1","790"): True,
    ("43-1","893"): True,
    ("43-1","894"): True,
    ("43-1","994"): True,
    ("42-2","8"): False,
    ("42-2","15"): False,
    ("42-2","19"): True,
    ("42-2","28"): True,
    ("42-2","29"): True,
    ("42-2","498"): True,
    ("42-1","7"): True,
    ("42-1","20"): False,
    ("42-1","27"): False,
    ("42-1","28"): True,
    ("42-1","29"): True,
    ("42-1","37"): False,
    ("42-1","101"): True,
    ("42-1","105"): True,
    ("42-1","597"): False,
    ("42-1","798"): True,
    ("42-1","898"): True,
    ("41-1","42"): False,
    ("41-1","66"): True,
    ("41-1","81"): True,
    ("41-1","88"): False,
    ("41-1","92"): True,
    ("41-1","99"): False,
    ("41-1","102"): False,
    ("41-1","115"): True,
    ("41-1","130"): True,
    ("41-1","154"): False,
    ("41-1","157"): True,
    ("41-1","160"): True,
    ("41-1","189"): True,
    ("41-1","197"): True,
    ("40-1","7"): True,
    ("40-1","14"): True,
    ("40-1","21"): False,
    ("40-1","22"): False,
    ("40-1","30"): True,
    ("40-1","37"): True,
    ("40-1","52"): True,
    ("40-1","194"): False,
    ("40-1","210"): False,
    ("40-1","497"): False,
    ("39-2","7"): True,
    ("39-2","16"): True,
    ("39-2","36"): True,
    ("39-2","48"): False,
    ("39-2","51"): False,
    ("39-2","53"): True,
    ("39-2","59"): True,
    ("39-2","68"): False,
    ("39-2","74"): True,
    ("39-2","79"): False,
    ("39-2","84"): True,
    ("39-2","216"): False,
    ("39-1","7"): True,
    ("39-1","14"): True,
    ("39-1","21"): True,
    ("39-1","24"): True,
    ("39-1","26"): True,
    ("39-1","34"): True,
    ("39-1","43"): True,
    ("39-1","47"): True,
    ("39-1","49"): True,
    ("39-1","51"): False,
    ("39-1","56"): True,
    ("39-1","58"): False,
    ("39-1","59"): True,
    ("39-1","67"): True,
    ("39-1","94"): False,
    ("39-1","106"): True,
    ("39-1","125"): True,
    ("39-1","127"): True,
    ("39-1","194"): True,
    ("39-1","217"): False,
    ("39-1","231"): False,
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

    print("\nFalse positives (in filter but Joanie says NOT health):")
    for (session, num), joanie_health in JOANIE.items():
        if not joanie_health:
            key = (session, num.lstrip("0"))
            if key in predicted:
                print(f"  {session} Bill {num}")
    
    print("\nTrue negatives (not in filter, Joanie says NOT health):")
    for (session, num), joanie_health in JOANIE.items():
        if not joanie_health:
            key = (session, num.lstrip("0"))
            if key not in predicted:
                print(f"  {session} Bill {num}")

if __name__ == "__main__":
    main()
