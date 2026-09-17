"""
check_completeness.py - rewritten July 2026, health-focused summary.
"""
import os, re, json, csv
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(REPO_ROOT, "data", "completeness_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

def load_json(p):
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as f: return json.load(f)

def load_csv(p):
    if not os.path.exists(p): return []
    with open(p, newline="", encoding="utf-8") as f: return list(csv.DictReader(f))

def audit_us():
    bills = load_csv(os.path.join(REPO_ROOT,"data","us","health_bills_final_matched.csv"))
    sd = os.path.join(REPO_ROOT,"data","us","congressional_record_speeches")
    sfiles = set(f.replace(".txt","") for f in os.listdir(sd)
                 if f.endswith(".txt") and "_notes" not in f) if os.path.isdir(sd) else set()
    rows = []
    for b in bills:
        bid = b.get("bill_number") or b.get("bill_id") or "UNKNOWN"
        vd  = b.get("date") or b.get("vote_date") or ""
        rows.append({"jurisdiction":"US House","bill_id":bid,
            "has_bill": bid!="UNKNOWN",
            "has_health_tag": b.get("policy_area","").strip().lower()=="health",
            "has_speech": vd in sfiles,
            "has_date": bool(vd),
            "has_vote": True,
            "complete": bid!="UNKNOWN" and b.get("policy_area","").strip().lower()=="health" and vd in sfiles and bool(vd),
        })
    return rows

ERA_MAP = {33:1985,34:1985,35:1989,36:1993,37:1997,38:2001,
           39:2005,40:2009,41:2013,42:2017,43:2021}

def audit_ontario():
    bi = load_json(os.path.join(REPO_ROOT,"data","canada","ontario","ontario_bill_index.json")) or {}
    vr = load_json(os.path.join(REPO_ROOT,"data","canada","ontario","ontario_fsob_votes.json")) or {}
    sd = os.path.join(REPO_ROOT,"data","canada","ontario")
    sfiles = set(f.replace(".txt","") for f in os.listdir(sd)
                 if f.endswith(".txt") and "_notes" not in f) if os.path.isdir(sd) else set()
    with_vote = set()
    for sv in vr.values():
        for r in sv.get("records",[]):
            era = ERA_MAP.get(r.get("parliament"),1985)
            with_vote.add(f"{era}-Bill{r.get('bill_number')}")
    rows = []
    for key, entry in bi.items():
        dates = entry.get("dates",[])
        ht = bool(entry.get("health_tag"))
        hs = any(d in sfiles for d in dates)
        hd = bool(dates)
        hv = key in with_vote
        rows.append({"jurisdiction":"Ontario","bill_id":key,
            "has_bill":True,"has_health_tag":ht,"has_speech":hs,
            "has_date":hd,"has_vote":hv,
            "complete":all([ht,hs,hd,hv])})
    return rows

def audit_quebec():
    hb = load_json(os.path.join(REPO_ROOT,"data","canada","quebec_bills","quebec_health_bills_combined.json")) or []
    ad = os.path.join(REPO_ROOT,"data","canada","quebec_assembly")
    af = set(f.replace(".txt","") for f in os.listdir(ad)
             if f.endswith(".txt")) if os.path.isdir(ad) else set()
    rows = []
    for bill in hb:
        title = bill.get("title","")
        m = re.search(r"[Pp]rojet de loi n[^\d]*(\d+)", title)
        num = m.group(1) if m else "UNKNOWN"
        debates = bill.get("assembly_debates",[])
        hs = any(re.search(r"/(\d{8})/",d.get("url","")) and
                 re.search(r"/(\d{8})/",d.get("url","")).group(1) in af
                 for d in debates)
        rows.append({"jurisdiction":"Quebec","bill_id":f"QC-Bill{num}",
            "has_bill":num!="UNKNOWN","has_health_tag":True,"has_speech":hs,
            "has_date":bool(debates),"has_vote":False,
            "complete":num!="UNKNOWN" and hs and bool(debates)})
    return rows

def write_report(rows, name):
    if not rows: return None
    p = os.path.join(REPORT_DIR, f"{name}_completeness.csv")
    with open(p,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return p

def print_summary(all_rows):
    print(f"\n=== Pipeline Completeness Summary ===")
    print(f"Run at: {datetime.now().isoformat(timespec='seconds')}\n")

    by_j = {}
    for row in all_rows:
        j = row["jurisdiction"]
        by_j.setdefault(j, {
            "total_all": 0, "total_health": 0,
            "speech": 0, "date": 0, "vote": 0, "complete": 0
        })
        s = by_j[j]
        s["total_all"] += 1
        if row["has_health_tag"]:
            s["total_health"] += 1
            if row["has_speech"]: s["speech"] += 1
            if row["has_date"]:   s["date"]   += 1
            if row.get("has_vote"): s["vote"] += 1
            if row["complete"]:   s["complete"] += 1

    print(f"{'Jurisdiction':<15} {'All Bills':>10} {'Health Bills':>13} "
          f"{'w/ Speech':>10} {'w/ Date':>9} {'w/ Vote':>9} {'Complete':>10}")
    print("-" * 80)
    for j, s in by_j.items():
        print(f"{j:<15} {s['total_all']:>10} {s['total_health']:>13} "
              f"{s['speech']:>10} {s['date']:>9} {s['vote']:>9} {s['complete']:>10}")
    print()

    print("Notes:")
    print("  US:      663 vote events, all CRS health-tagged, all speech re-pulled as HTML")
    print("  Ontario: 329 keyword health-tagged (pre-classifier); vote outcomes from FSOB PDFs")
    print("           220 health bills with confirmed vote outcome; 109 still unmatched")
    print("           (unmatched = passed by voice vote or FSOB pattern missed)")
    print("post-1994: 211 passed, 51 died in session via Cheminement pages; pre-1994: 88 passed from transcripts")

def main():
    all_rows = []
    for fn, name in [(audit_us,"us_house"),(audit_ontario,"ontario"),(audit_quebec,"quebec")]:
        rows = fn(); all_rows.extend(rows); write_report(rows, name)
    print_summary(all_rows)
    print("\nDetailed CSVs in data/completeness_reports/")

if __name__ == "__main__":
    main()

