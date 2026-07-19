"""
us_bill_sanity_check.py

David's sanity check (July 16): verify the actual bill universes so the 663
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
    if os.path.exists(qc_path):
        with open(qc_path, encoding="utf-8") as f:
            qc = json.load(f)
        total = sum(len(v) for v in qc.values())
        print(f"All Cheminement bills:           {total} across {len(qc)} sessions")
        print("Health-tagged:                   pending classifier (blocked on Joanie's keywords)")
    else:
        print("cheminement_all_sessions.json not found")


if __name__ == "__main__":
    main()

