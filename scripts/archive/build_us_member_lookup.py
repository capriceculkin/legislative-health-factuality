"""
build_us_member_lookup.py

Builds a lookup table of US House members who voted on our health bills,
with party affiliation at the time of the vote, gender, birthday, and state.

Uses:
- legislators-historical.yaml and legislators-current.yaml for term history
- health_bills_final_matched.csv for the bills and congresses we care about
- VoteView ICPSR IDs to join member votes to biography

Usage: python3 scripts/build_us_member_lookup.py
"""
import os, json, csv, yaml
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/us/member_lookup.json")


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def congress_to_years(congress_num):
    """Convert congress number to start/end years."""
    start = 1787 + (congress_num * 2)
    return start, start + 2


def get_party_for_congress(member, congress_num):
    """Get a member's party during a specific congress."""
    start_year, end_year = congress_to_years(congress_num)
    start_date = f"{start_year}-01-03"
    end_date = f"{end_year}-01-03"

    for term in member.get("terms", []):
        if term.get("type") != "rep":
            continue
        term_start = term.get("start", "")
        term_end = term.get("end", "9999")
        # check if this term overlaps with the congress
        if term_start <= end_date and term_end >= start_date:
            return term.get("party", "")
    return ""


def main():
    print("Loading YAML files...")
    historical = load_yaml(os.path.join(REPO_ROOT, "data/us/legislators-historical.yaml"))
    current = load_yaml(os.path.join(REPO_ROOT, "data/us/legislators-current.yaml"))
    all_members = historical + current
    print(f"Total members loaded: {len(all_members)}")

    # build lookup by bioguide_id and icpsr_id
    by_bioguide = {}
    by_icpsr = {}
    for m in all_members:
        ids = m.get("id", {})
        bio_id = ids.get("bioguide", "")
        icpsr_id = str(ids.get("icpsr", ""))
        bio = m.get("bio", {})
        name = m.get("name", {})

        record = {
            "bioguide_id": bio_id,
            "icpsr_id": icpsr_id,
            "first_name": name.get("first", ""),
            "last_name": name.get("last", ""),
            "full_name": f"{name.get('first','')} {name.get('last','')}".strip(),
            "birthday": bio.get("birthday", ""),
            "gender": bio.get("gender", ""),
            "terms": m.get("terms", []),
        }

        if bio_id:
            by_bioguide[bio_id] = record
        if icpsr_id and icpsr_id != "None":
            by_icpsr[icpsr_id] = record

    print(f"By bioguide: {len(by_bioguide)} | By ICPSR: {len(by_icpsr)}")

    # load which congresses we care about from matched bills
    congresses_needed = set()
    with open(os.path.join(REPO_ROOT, "data/us/health_bills_final_matched.csv"), newline="") as f:
        for row in csv.DictReader(f):
            congresses_needed.add(int(row["congress"]))

    print(f"Congresses in our data: {sorted(congresses_needed)}")

    # build congress-level member lookup
    # for each congress, find all House members and their party
    congress_members = {}
    for congress_num in sorted(congresses_needed):
        start_year, end_year = congress_to_years(congress_num)
        start_date = f"{start_year}-01-03"
        end_date = f"{end_year}-01-03"

        members_in_congress = []
        for m in all_members:
            for term in m.get("terms", []):
                if term.get("type") != "rep":
                    continue
                if term.get("start", "") <= end_date and term.get("end", "9999") >= start_date:
                    ids = m.get("id", {})
                    name = m.get("name", {})
                    bio = m.get("bio", {})
                    members_in_congress.append({
                        "bioguide_id": ids.get("bioguide", ""),
                        "icpsr_id": str(ids.get("icpsr", "")),
                        "full_name": f"{name.get('first','')} {name.get('last','')}".strip(),
                        "party": term.get("party", ""),
                        "state": term.get("state", ""),
                        "district": str(term.get("district", "")),
                        "gender": bio.get("gender", ""),
                        "birthday": bio.get("birthday", ""),
                    })
                    break

        congress_members[str(congress_num)] = members_in_congress
        print(f"  Congress {congress_num}: {len(members_in_congress)} House members")

    # save full lookup
    output = {
        "by_bioguide": by_bioguide,
        "by_icpsr": by_icpsr,
        "by_congress": congress_members,
    }

    # save by_bioguide and by_icpsr without full term lists (too large)
    compact = {
        "by_congress": congress_members,
        "by_icpsr": {
            k: {kk: vv for kk, vv in v.items() if kk != "terms"}
            for k, v in by_icpsr.items()
        }
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(compact, f, indent=2)

    print(f"\nSaved to {OUTPUT_PATH}")
    total_members = sum(len(v) for v in congress_members.values())
    print(f"Total member-congress records: {total_members}")


if __name__ == "__main__":
    main()
