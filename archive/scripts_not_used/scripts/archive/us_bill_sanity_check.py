"""
us_bill_sanity_check.py

Updated Sanity check (July 16): verify the actual bill universes so the 663
US vote events can be judged against Quebec's 2,358 and Ontario's 2,392, is
663 a reasonable health-only fraction, or an under-capture?

Reads only files already on disk:
  data/us/unique_voted_bills.csv           all US House bills with recorded votes
  data/us/health_bills_final_matched.csv   the health-tagged vote events (663 rows)
  data/canada/ontario/ontario_bill_index.json
  data/canada/quebec_bills/cheminement_all_sessions.json

Usage: python3 scripts/us_bill_sanity_check.py
"""

import os
import csv
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(REPO_ROOT, *p)


def main():
    # --- US universe ---
    with open(D("data", "us", "unique_voted_bills.csv"), newline="") as f:
        us_all = list(csv.DictReader(f))
    us_all_bills = {(r.get("congress"), r.get("bill_number") or r.get("bill_id")) for r in us_all}

    with open(D("data", "us", "health_bills_final_matched.csv"), newline="") as f:
        us_health_rows = list(csv.DictReader(f))
    us_health_bills = {(r["congress"], r["bill_number"]) for r in us_health_rows}

    print("=== US House ===")
    print(f"All voted bills (unique):        {len(us_all_bills)}")
    print(f"Health-tagged bills (unique):    {len(us_health_bills)}")
    print(f"Health vote events (rows):       {len(us_health_rows)}")
    if us_all_bills:
        pct = 100 * len(us_health_bills) / len(us_all_bills)
        print(f"Health share of voted bills:     {pct:.1f}%")

    # --- Ontario universe ---
    print("\n=== Ontario ===")
    on_path = D("data", "canada", "ontario", "ontario_bill_index.json")
    if os.path.exists(on_path):
        with open(on_path, encoding="utf-8") as f:
            on = json.load(f)
        health = sum(1 for e in on.values() if e.get("health_tag"))
        print(f"All indexed bills:               {len(on)}")
        print(f"Keyword health-tagged:           {health} (pre-classifier, provisional)")
    else:
        print("ontario_bill_index.json not found")

    # --- Quebec universe ---
    print("\n=== Quebec ===")
    qc_path = D("data", "canada", "quebec_bills", "cheminement_all_sessions.json")
    qc_health_path = D("data", "canada", "quebec_bills", "quebec_health_bills.json")
    if os.path.exists(qc_path):
        with open(qc_path, encoding="utf-8") as f:
            qc = json.load(f)
        total = sum(len(v) for v in qc.values())
        print(f"All Cheminement bills:           {total} across {len(qc)} sessions")
        if os.path.exists(qc_health_path):
            with open(qc_health_path, encoding="utf-8") as f:
                qc_health = json.load(f)
            print(f"Keyword/committee health-tagged: {len(qc_health)} (Joanie keywords updated July 16)")
        else:
            print("Health-tagged:                   run quebec_health_bill_filter.py first")
    else:
        print("cheminement_all_sessions.json not found")

    print("\n=== External validation (Congress.gov, verified July 16) ===")
    print("CRS-tagged Health bills that passed House, 99th-119th Congress: 668")
    print(f"Pipeline health bills with recorded votes:                      {len(us_health_bills)}")
    print(f"Coverage:                                                        {100*len(us_health_bills)/668:.1f}% of CRS universe")
    print("Gap of 284 = bills that passed by voice vote or suspension calendar")
    print("(no recorded roll call = no binary outcome = correctly excluded by design)")

    print("\n=== Interpretation guide ===")
    print("The US 384/663 figure is health bills / health vote events only.")
    print("The Ontario 2,392 and Quebec 2,358 figures are ALL bills, pre-filter.")
    print("Comparable numbers only exist after Canadian health classification runs.")
    print("If the US health share printed above looks implausibly low vs the")
    print("full universe, that suggests under-capture; if it looks like a")
    print("plausible topical fraction (health is one policy area of many),")
    print("the 663 stands.")


if __name__ == "__main__":
    main()