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
        # Joanie August 18 review
    ("43-2","15"): 0,
    ("43-2","16"): 1,
    ("43-2","19"): 1,
    ("43-2","23"): 1,
    ("43-2","495"): 1,
    ("43-1","3"): 1,
    ("43-1","10"): 1,
    ("43-1","11"): 1,
    ("43-1","37"): 0,
    ("43-1","41"): 0,
    ("43-1","67"): 1,
    ("43-1","103"): 1,
    ("43-1","104"): 0,
    ("43-1","197"): 1,
    ("43-1","212"): 0,
    ("43-1","398"): 1,
    ("43-1","591"): 0,
    ("43-1","595"): 1,
    ("43-1","790"): 1,
    ("43-1","893"): 1,
    ("43-1","894"): 1,
    ("43-1","994"): 1,
    ("42-2","8"): 0,
    ("42-2","15"): 0,
    ("42-2","19"): 1,
    ("42-2","28"): 1,
    ("42-2","29"): 1,
    ("42-2","498"): 1,
    ("42-1","7"): 1,
    ("42-1","20"): 0,
    ("42-1","27"): 0,
    ("42-1","28"): 1,
    ("42-1","29"): 1,
    ("42-1","37"): 0,
    ("42-1","101"): 1,
    ("42-1","105"): 1,
    ("42-1","597"): 0,
    ("42-1","798"): 1,
    ("42-1","898"): 1,
    ("41-1","42"): 0,
    ("41-1","66"): 1,
    ("41-1","81"): 1,
    ("41-1","88"): 0,
    ("41-1","92"): 1,
    ("41-1","99"): 0,
    ("41-1","102"): 0,
    ("41-1","115"): 1,
    ("41-1","130"): 1,
    ("41-1","154"): 0,
    ("41-1","157"): 1,
    ("41-1","160"): 1,
    ("41-1","189"): 1,
    ("41-1","197"): 1,
    ("40-1","7"): 1,
    ("40-1","14"): 1,
    ("40-1","21"): 0,
    ("40-1","22"): 0,
    ("40-1","30"): 1,
    ("40-1","37"): 1,
    ("40-1","52"): 1,
    ("40-1","194"): 0,
    ("40-1","210"): 0,
    ("40-1","497"): 0,
    ("39-2","7"): 1,
    ("39-2","16"): 1,
    ("39-2","36"): 1,
    ("39-2","48"): 0,
    ("39-2","51"): 0,
    ("39-2","53"): 1,
    ("39-2","59"): 1,
    ("39-2","68"): 0,
    ("39-2","74"): 1,
    ("39-2","79"): 0,
    ("39-2","84"): 1,
    ("39-2","216"): 0,
    ("39-1","7"): 1,
    ("39-1","14"): 1,
    ("39-1","21"): 1,
    ("39-1","24"): 1,
    ("39-1","26"): 1,
    ("39-1","34"): 1,
    ("39-1","43"): 1,
    ("39-1","47"): 1,
    ("39-1","49"): 1,
    ("39-1","51"): 0,
    ("39-1","56"): 1,
    ("39-1","58"): 0,
    ("39-1","59"): 1,
    ("39-1","67"): 1,
    ("39-1","94"): 0,
    ("39-1","106"): 1,
    ("39-1","125"): 1,
    ("39-1","127"): 1,
    ("39-1","194"): 1,
    ("39-1","217"): 0,
    ("39-1","231"): 0,
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

        # Load n-gram predictions
    ngram_path = os.path.join(REPO, "data/dbpedia_pipeline/ngram_predictions.json")
    with open(ngram_path) as f:
        ngram_preds = json.load(f)
    ngram_set = set()
    for key, v in ngram_preds.items():
        parts = key.rsplit("-", 1)
        if len(parts) == 2:
            sk = (parts[0], parts[1])
            if v["pred"] == 1:
                ngram_set.add(sk)

    print(f"Keyword filter: {len(kw_set)} bills")
    print(f"XLM-RoBERTa:   {len(xlmr_set)} bills")
    print(f"Joanie labels:  {len(JOANIE)} bills\n")

    y_true = []
    y_kw, y_xlmr, y_or, y_and = [], [], [], []
    y_kw_ngram, y_triple = [], []

    for (session, num), label in JOANIE.items():
        key = (session, num)
        kw_pred   = 1 if key in kw_set else 0
        xlmr_pred = 1 if key in xlmr_set else 0
        ngram_pred = 1 if key in ngram_set else 0
        y_true.append(label)
        y_kw.append(kw_pred)
        y_xlmr.append(xlmr_pred)
        y_or.append(1 if (kw_pred or xlmr_pred) else 0)
        y_and.append(1 if (kw_pred and xlmr_pred) else 0)
        y_kw_ngram.append(1 if (kw_pred and ngram_pred) else 0)
        y_triple.append(1 if (kw_pred and xlmr_pred and ngram_pred) else 0)

    print(f"{'='*60}")
    print(f"{'Method':<20} {'Sens':>6} {'Spec':>6} {'Prec':>6} {'F1':>6}  TP  FP  TN  FN")
    print(f"{'-'*60}")

    

    for name, preds in [
        ("Keyword only",    y_kw),
        ("XLM-RoBERTa",    y_xlmr),
        ("KW+Ngram AND",    y_kw_ngram),
        ("Ensemble OR",     y_or),
        ("Ensemble AND",    y_and),
        ("Triple AND",      y_triple),
    ]:
        tp,fp,tn,fn,sens,spec,prec,f1 = metrics(y_true, preds)
        print(f"{name:<20} {sens:>6.3f} {spec:>6.3f} {prec:>6.3f} {f1:>6.3f} "
              f"{tp:>3} {fp:>3} {tn:>3} {fn:>3}")

    print(f"\nNote: OR ensemble maximizes sensitivity (catches more health bills)")
    print(f"      AND ensemble maximizes specificity (fewer false positives)")


if __name__ == "__main__":
    main()
