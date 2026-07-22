"""
ensemble_classifier.py

Combines keyword filter and XLM-RoBERTa predictions using three ensemble strategies:
  - OR:  health if EITHER classifier says yes (maximizes sensitivity)
  - AND: health if BOTH classifiers say yes (maximizes specificity)
  - PROB: health if XLM-RoBERTa probability > threshold (tunable)

Evaluates each against Joanie's ground truth labels.
"""
import json, re, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JOANIE = {
    ("43-2","2"): 1, ("43-2","25"): 0, ("43-2","498"): 0,
    ("43-2","595"): 1, ("43-2","29"): 0,
    ("43-1","106"): 1, ("43-1","15"): 1, ("43-1","32"): 1,
    ("43-1","68"): 1, ("43-1","83"): 1, ("43-1","95"): 0,
    ("43-1","36"): 0, ("43-1","66"): 0, ("43-1","101"): 0,
    ("43-1","141"): 0, ("43-1","136"): 0, ("43-1","192"): 0,
    ("43-1","149"): 0, ("43-1","150"): 0, ("43-1","61"): 0,
    ("42-2","38"): 1, ("42-2","11"): 1,
    ("42-1","2"): 1, ("42-1","43"): 1, ("42-1","52"): 1,
    ("42-1","83"): 1, ("42-1","31"): 1, ("42-1","73"): 1,
    ("42-1","196"): 1, ("42-1","594"): 1,
    ("42-1","9"): 0, ("42-1","12"): 0, ("42-1","35"): 0,
    ("42-1","61"): 0, ("42-1","85"): 0, ("42-1","75"): 0,
    ("42-1","59"): 0, ("42-1","598"): 0, ("42-1","691"): 0,
    ("41-1","10"): 1, ("41-1","20"): 1, ("41-1","52"): 1,
    ("41-1","118"): 1, ("41-1","123"): 1, ("41-1","44"): 1,
    ("41-1","148"): 1,
    ("41-1","97"): 0, ("41-1","126"): 0, ("41-1","152"): 0,
    ("41-1","162"): 0, ("41-1","170"): 0, ("41-1","221"): 0,
    ("40-1","67"): 0, ("39-1","104"): 0,
    ("38-1","23"): 0, ("38-1","50"): 0,
    ("36-2","151"): 0, ("35-2","190"): 0,
}


def metrics(y_true, y_pred):
    tp = sum(1 for a,b in zip(y_true,y_pred) if a==1 and b==1)
    fp = sum(1 for a,b in zip(y_true,y_pred) if a==0 and b==1)
    tn = sum(1 for a,b in zip(y_true,y_pred) if a==0 and b==0)
    fn = sum(1 for a,b in zip(y_true,y_pred) if a==1 and b==0)
    sens = tp/(tp+fn) if (tp+fn) else 0
    spec = tn/(tn+fp) if (tn+fp) else 0
    prec = tp/(tp+fp) if (tp+fp) else 0
    f1   = 2*prec*sens/(prec+sens) if (prec+sens) else 0
    return tp, fp, tn, fn, sens, spec, prec, f1


def main():
    # Load keyword filter predictions
    kw_path = os.path.join(REPO, "data/canada/quebec_bills/quebec_health_bills.json")
    with open(kw_path, encoding="utf-8") as f:
        kw_bills = json.load(f)
    kw_set = set()
    for b in kw_bills:
        m = re.search(r"n[°o\xa0]\s*(\d+)", b.get("title",""))
        if m:
            kw_set.add((b.get("session",""), m.group(1)))

    # Load XLM-RoBERTa predictions
    xlmr_path = os.path.join(REPO, "data/dbpedia_pipeline/xlmr_predictions.json")
    with open(xlmr_path) as f:
        xlmr = json.load(f)
    # keys are "session-num"
    xlmr_set = set()
    xlmr_probs = {}
    for key, v in xlmr.items():
        parts = key.rsplit("-", 1)
        if len(parts) == 2:
            sk = (parts[0], parts[1])
            if v["pred"] == 1:
                xlmr_set.add(sk)
            xlmr_probs[sk] = v["prob"]

    print(f"Keyword filter: {len(kw_set)} bills")
    print(f"XLM-RoBERTa:   {len(xlmr_set)} bills")
    print(f"Joanie labels:  {len(JOANIE)} bills\n")

    y_true = []
    y_kw, y_xlmr, y_or, y_and = [], [], [], []

    for (session, num), label in JOANIE.items():
        key = (session, num)
        kw_pred   = 1 if key in kw_set else 0
        xlmr_pred = 1 if key in xlmr_set else 0
        y_true.append(label)
        y_kw.append(kw_pred)
        y_xlmr.append(xlmr_pred)
        y_or.append(1 if (kw_pred or xlmr_pred) else 0)
        y_and.append(1 if (kw_pred and xlmr_pred) else 0)

    print(f"{'='*60}")
    print(f"{'Method':<20} {'Sens':>6} {'Spec':>6} {'Prec':>6} {'F1':>6}  TP  FP  TN  FN")
    print(f"{'-'*60}")

    for name, preds in [
        ("Keyword only",    y_kw),
        ("XLM-RoBERTa",    y_xlmr),
        ("Ensemble OR",     y_or),
        ("Ensemble AND",    y_and),
    ]:
        tp,fp,tn,fn,sens,spec,prec,f1 = metrics(y_true, preds)
        print(f"{name:<20} {sens:>6.3f} {spec:>6.3f} {prec:>6.3f} {f1:>6.3f} "
              f"{tp:>3} {fp:>3} {tn:>3} {fn:>3}")

    print(f"\nNote: OR ensemble maximizes sensitivity (catches more health bills)")
    print(f"      AND ensemble maximizes specificity (fewer false positives)")


if __name__ == "__main__":
    main()
