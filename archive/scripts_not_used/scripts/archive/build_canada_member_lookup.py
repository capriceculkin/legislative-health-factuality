"""
build_canada_member_lookup.py

Builds a consistent member lookup for Ontario and Quebec legislators,
joining the Harvard Dataverse ppb.csv (1792-2018) with scraped data
from ola.org (Ontario) and assnat.qc.ca (Quebec).

Fields consistent with US member_lookup.json:
- full_name, party, gender, year_of_birth, career, province, district, year

Usage: python3 scripts/build_canada_member_lookup.py
"""
import os, json, csv
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PPB_PATH = os.path.join(REPO_ROOT, "data/canada/ppb.csv")
ON_PATH = os.path.join(REPO_ROOT, "data/canada/ontario_members.json")
QC_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_members_recent.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/canada/member_lookup.json")


def normalize_name(name):
    """Normalize name for matching across sources."""
    return name.lower().strip().replace("-", " ").replace(",", "").replace(".", "")


def main():
    # load Harvard Dataverse ppb.csv
    print("Loading Harvard Dataverse ppb.csv...")
    ppb = []
    with open(PPB_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("province") in ["Ontario", "Quebec"]:
                ppb.append({
                    "full_name": row.get("first_last", "").replace("_", " ").title(),
                    "normalized_name": normalize_name(row.get("first_last", "").replace("_", " ")),
                    "province": row.get("province", ""),
                    "district": row.get("district", ""),
                    "gender": row.get("gender", ""),
                    "year_of_birth": row.get("year_of_birth", ""),
                    "career": row.get("career", ""),
                    "religion": row.get("religion", ""),
                    "year": row.get("year", ""),
                    "party": row.get("candidate_votes", ""),  # party in electoral data
                    "source": "harvard_dataverse",
                })
    print(f"  Harvard Dataverse: {len(ppb)} Ontario+Quebec records")

    # load Ontario scraped data
    print("Loading Ontario scraped data...")
    with open(ON_PATH, encoding="utf-8") as f:
        ontario = json.load(f)
    ontario_records = []
    for m in ontario:
        ontario_records.append({
            "full_name": m.get("name", "").replace(",", "").strip(),
            "normalized_name": normalize_name(m.get("name", "").replace(",", "")),
            "province": "Ontario",
            "district": m.get("riding", ""),
            "party": m.get("party", ""),
            "url": m.get("url", ""),
            "source": "ola.org",
        })
    print(f"  Ontario: {len(ontario_records)} MPPs")

    # load Quebec scraped data
    qc_records = []
    if os.path.exists(QC_PATH):
        print("Loading Quebec scraped data...")
        with open(QC_PATH, encoding="utf-8") as f:
            quebec = json.load(f)
        for m in quebec:
            qc_records.append({
                "full_name": m.get("name", ""),
                "normalized_name": normalize_name(m.get("name", "")),
                "province": "Quebec",
                "party": m.get("party", ""),
                "career": m.get("career", ""),
                "year_of_birth": m.get("year_of_birth", ""),
                "years_active": m.get("years_active", []),
                "is_current": m.get("is_current", False),
                "url": m.get("url", ""),
                "source": "assnat.qc.ca",
            })
        print(f"  Quebec: {len(qc_records)} members")
    else:
        print("  Quebec scraper not yet complete - skipping")

    # merge: start with Harvard Dataverse as base,
    # enrich with party info from scraped data where missing
    print("\nMerging sources...")

    # build name->party lookup from scraped data
    on_party_by_name = {normalize_name(m["full_name"]): m["party"] for m in ontario_records}
    qc_party_by_name = {normalize_name(m["full_name"]): m["party"] for m in qc_records}

    # enrich Harvard Dataverse records with party from scraped data
    for record in ppb:
        norm = record["normalized_name"]
        prov = record["province"]
        if prov == "Ontario" and norm in on_party_by_name:
            record["party"] = on_party_by_name[norm]
        elif prov == "Quebec" and norm in qc_party_by_name:
            record["party"] = qc_party_by_name[norm]

    # combine all records
    all_records = ppb + ontario_records + qc_records

    # organize by province and year for easy lookup
    by_province = defaultdict(list)
    for r in all_records:
        by_province[r["province"]].append(r)

    output = {
        "ontario": ontario_records,
        "quebec": ppb + qc_records,
        "combined": all_records,
        "stats": {
            "ontario_total": len(ontario_records),
            "quebec_total": len([r for r in ppb if r["province"] == "Quebec"]) + len(qc_records),
            "harvard_dataverse_records": len(ppb),
            "scraped_ontario": len(ontario_records),
            "scraped_quebec": len(qc_records),
        }
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to {OUTPUT_PATH}")
    print(f"Stats: {output['stats']}")

    # career breakdown for Quebec (most complete)
    from collections import Counter
    qc_careers = Counter(r.get("career","") for r in ppb if r["province"] == "Quebec" and r.get("career"))
    print("\nQuebec career distribution (Harvard Dataverse):")
    for c, n in qc_careers.most_common(8):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()
