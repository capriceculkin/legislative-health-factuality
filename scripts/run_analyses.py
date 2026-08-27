"""
run_analyses.py

Runs all sub-analyses for US and Ontario factuality scores:
1. Logistic regression: passage ~ factuality + jurisdiction + controls
2. Government vs opposition factuality comparison
3. COVID natural experiment (pre/post March 2020)
4. Temporal trends and pre/post 2015-2016 breakpoint

Usage: python3 scripts/run_analyses.py
"""
import os, json
import numpy as np
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def avg(lst): return sum(lst)/len(lst) if lst else None
def std(lst):
    if len(lst) < 2: return 0
    m = avg(lst)
    return (sum((x-m)**2 for x in lst)/(len(lst)-1))**0.5

def load_us():
    with open(os.path.join(REPO_ROOT, "data/dbpedia_pipeline/us/factuality_scores.json")) as f:
        scores = json.load(f)
    records = []
    for date, v in scores.items():
        if v["total_sentences"] == 0:
            continue
        result = v.get("vote_result", "").lower()
        passed = 1 if result in ["passed", "yea"] else (0 if result in ["failed", "nay"] else None)
        if passed is None:
            continue
        records.append({
            "date": date,
            "year": int(date[:4]),
            "factuality": v["factuality_score"],
            "passed": passed,
            "jurisdiction": "us",
            "total_sentences": v["total_sentences"],
        })
    return records

def load_ontario():
    with open(os.path.join(REPO_ROOT, "data/dbpedia_pipeline/ontario/factuality_scores_per_bill.json")) as f:
        scores = json.load(f)
    records = []
    for bill_key, v in scores.items():
        outcome = v.get("outcome", "").lower()
        passed = 1 if outcome in ["carried", "passed"] else (0 if outcome in ["lost", "failed", "defeated"] else None)
        if passed is None:
            continue
        dates = v.get("dates", [])
        if not dates:
            continue
        year = int(dates[-1][:4]) if dates else 0
        records.append({
            "date": dates[0],
            "year": year,
            "factuality": v["factuality_score"],
            "passed": passed,
            "jurisdiction": "ontario",
            "total_sentences": v["total_claim_sentences"],
        })
    return records

def load_quebec():
    with open(os.path.join(REPO_ROOT, "data/dbpedia_pipeline/quebec/factuality_scores.json")) as f:
        scores = json.load(f)
    records = []
    for date, v in scores.items():
        if v["total_sentences"] == 0:
            continue
        result = (v.get("vote_result") or "").lower()
        passed = 1 if result in ["passed"] else (0 if result in ["failed", "lost", "defeated"] else None)
        if passed is None:
            continue
        records.append({
            "date": date,
            "year": int(date[:4]) if date else 0,
            "factuality": v["factuality_score"],
            "passed": passed,
            "jurisdiction": "quebec",
            "total_sentences": v["total_sentences"],
        })
    return records


def analysis_1_regression(us, ontario, quebec):
    """Simple logistic regression: passage ~ factuality + jurisdiction"""
    print("\n" + "="*60)
    print("ANALYSIS 1: Factuality and Bill Passage")
    print("="*60)

    all_records = us + ontario + quebec

    # simple comparison: mean factuality by outcome
    for juris, records in [("US", us), ("Ontario", ontario), ("Quebec", quebec), ("Combined", all_records)]:
        passed_f = [r["factuality"] for r in records if r["passed"] == 1]
        failed_f = [r["factuality"] for r in records if r["passed"] == 0]
        diff = avg(passed_f) - avg(failed_f) if (passed_f and failed_f) else None
        print(f"\n{juris}:")
        print(f"  Passed bills:  mean factuality = {avg(passed_f):.4f} (n={len(passed_f)})")
        failed_avg = avg(failed_f)
        if failed_avg is not None:
            print(f"  Failed bills:  mean factuality = {failed_avg:.4f} (n={len(failed_f)})")
        else:
            print(f"  Failed bills:  n/a (no failed bills in corpus)")
        if diff is not None:
            print(f"  Difference:    {diff:+.4f} ({'higher factuality → passage' if diff > 0 else 'lower factuality → passage'})")

    # try logistic regression if sklearn available
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        X = np.array([[r["factuality"], 
                       1 if r["jurisdiction"]=="ontario" else 0,
                       1 if r["jurisdiction"]=="quebec" else 0]
                      for r in all_records])
        y = np.array([r["passed"] for r in all_records])

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = LogisticRegression(random_state=42)
        clf.fit(X_scaled, y)

        print(f"\nLogistic regression (n={len(all_records)}):")
        print(f"  Factuality coefficient:   {clf.coef_[0][0]:+.4f}")
        print(f"  Ontario jurisdiction:     {clf.coef_[0][1]:+.4f}")
        print(f"  Intercept:               {clf.intercept_[0]:+.4f}")
        print(f"  (positive coef = higher factuality → more likely to pass)")
    except ImportError:
        print("\n  (sklearn not available for logistic regression)")


def analysis_2_gov_vs_opposition(us, ontario, quebec):
    """Government vs opposition factuality — using year and jurisdiction as proxy"""
    print("\n" + "="*60)
    print("ANALYSIS 2: Temporal Factuality Trends")
    print("="*60)

    print("\nNote: Speaker-level gov/opposition breakdown requires")
    print("merging with speaker_turns data — showing year trends instead.\n")

    for juris, records in [("US", us), ("Ontario", ontario), ("Quebec", quebec)]:
        by_year = defaultdict(list)
        for r in records:
            by_year[r["year"]].append(r["factuality"])

        years = sorted(by_year.keys())
        print(f"{juris} mean factuality by decade:")
        decades = defaultdict(list)
        for year, scores in by_year.items():
            decade = (year // 10) * 10
            decades[decade].extend(scores)
        for decade in sorted(decades.keys()):
            print(f"  {decade}s: {avg(decades[decade]):.4f} (n={len(decades[decade])})")


def analysis_3_covid(us, ontario, quebec):
    """COVID natural experiment: pre/post March 2020"""
    print("\n" + "="*60)
    print("ANALYSIS 3: COVID Natural Experiment (Pre/Post March 2020)")
    print("="*60)

    for juris, records in [("US", us), ("Ontario", ontario), ("Quebec", quebec)]:
        pre = [r["factuality"] for r in records if r["year"] < 2020]
        post_covid = [r["factuality"] for r in records if r["year"] >= 2020]
        covid_year = [r["factuality"] for r in records if r["year"] == 2020]

        print(f"\n{juris}:")
        print(f"  Pre-COVID (before 2020):  {avg(pre):.4f} (n={len(pre)})")
        print(f"  Post-COVID (2020+):       {avg(post_covid):.4f} (n={len(post_covid)})")
        if pre and post_covid:
            diff = avg(post_covid) - avg(pre)
            print(f"  Change:                   {diff:+.4f} ({'increased' if diff > 0 else 'decreased'} after COVID)")
        print(f"  2020 specifically:        {avg(covid_year):.4f} (n={len(covid_year)})")


def analysis_4_breakpoint(us, ontario, quebec):
    """Pre/post political transitions: 2016 US, 2015 Canada"""
    print("\n" + "="*60)
    print("ANALYSIS 4: Political Transition Breakpoints")
    print("="*60)

    print("\nUS — pre/post 2016 election:")
    us_pre = [r["factuality"] for r in us if r["year"] < 2017]
    us_post = [r["factuality"] for r in us if r["year"] >= 2017]
    print(f"  Pre-2017:  {avg(us_pre):.4f} (n={len(us_pre)})")
    print(f"  Post-2017: {avg(us_post):.4f} (n={len(us_post)})")
    if us_pre and us_post:
        print(f"  Change:    {avg(us_post)-avg(us_pre):+.4f}")

    print("\nOntario — pre/post 2015 federal election:")
    on_pre = [r["factuality"] for r in ontario if r["year"] < 2016]
    on_post = [r["factuality"] for r in ontario if r["year"] >= 2016]
    print(f"  Pre-2016:  {avg(on_pre):.4f} (n={len(on_pre)})")
    print(f"  Post-2016: {avg(on_post):.4f} (n={len(on_post)})")
    if on_pre and on_post:
        print(f"  Change:    {avg(on_post)-avg(on_pre):+.4f}")

    # seesaw effect: factuality by governing party
    print("\nOntario — factuality by era (government changes):")
    ontario_eras = {
        "PC 1985-1987": (1985, 1987),
        "Liberal 1987-1990": (1987, 1990),
        "NDP 1990-1995": (1990, 1995),
        "PC 1995-2003": (1995, 2003),
        "Liberal 2003-2018": (2003, 2018),
        "PC 2018-present": (2018, 2030),
    }
    for era_name, (start, end) in ontario_eras.items():
        era_f = [r["factuality"] for r in ontario if start <= r["year"] < end]
        if era_f:
            print(f"  {era_name}: {avg(era_f):.4f} (n={len(era_f)})")
    print("\nQuebec — factuality by governing party era:")
    quebec_eras = {
        "PQ 1985-1985": (1985, 1985),
        "Liberal 1985-1994": (1985, 1994),
        "PQ 1994-2003": (1994, 2003),
        "Liberal 2003-2012": (2003, 2012),
        "PQ 2012-2014": (2012, 2014),
        "Liberal 2014-2018": (2014, 2018),
        "CAQ 2018-present": (2018, 2030),
    }
    
    for era_name, (start, end) in quebec_eras.items():
        era_f = [r["factuality"] for r in quebec if start <= r["year"] < end]
        if era_f:
            print(f"  {era_name}: {avg(era_f):.4f} (n={len(era_f)})")


def main():
    print("Loading US factuality scores...")
    us = load_us()
    print(f"US records: {len(us)}")

    print("Loading Ontario factuality scores...")
    ontario = load_ontario()
    print(f"Ontario records: {len(ontario)}")

    print("Loading Quebec factuality scores...")
    quebec = load_quebec()
    print(f"Quebec records: {len(quebec)}")

    analysis_1_regression(us, ontario, quebec)
    analysis_2_gov_vs_opposition(us, ontario, quebec)
    analysis_3_covid(us, ontario, quebec)
    analysis_4_breakpoint(us, ontario, quebec)

    print("\n" + "="*60)
    print("All analyses complete.")
    print("="*60)


if __name__ == "__main__":
    main()
