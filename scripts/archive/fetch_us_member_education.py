"""
fetch_us_member_education.py

Fetches occupation/career data from the Congressional Biographical Directory
(bioguide.congress.gov) for US House members who appear in our matched health bills.

Maps to same career categories as Harvard Dataverse ppb.csv:
law, medicine, business, education, agriculture, publicservice, journalism, military

Usage: python3 scripts/fetch_us_member_education.py
"""
import os, json, csv, time, requests
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHED_PATH = os.path.join(REPO_ROOT, "data/us/health_bills_final_matched.csv")
MEMBER_LOOKUP_PATH = os.path.join(REPO_ROOT, "data/us/member_lookup.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/us/member_careers.json")

BIOGUIDE_API = "https://bioguide.congress.gov/search/bio"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality)"}

# map bioguide occupation terms to Harvard Dataverse categories
CAREER_MAP = {
    "lawyer": "law", "attorney": "law", "judge": "law", "solicitor": "law",
    "physician": "medicine", "doctor": "medicine", "surgeon": "medicine",
    "dentist": "medicine", "pharmacist": "medicine", "nurse": "medicine",
    "businessman": "business", "merchant": "business", "banker": "business",
    "manufacturer": "business", "entrepreneur": "business", "executive": "business",
    "teacher": "education", "professor": "education", "educator": "education",
    "superintendent": "education", "principal": "education",
    "farmer": "agriculture", "rancher": "agriculture", "agriculturist": "agriculture",
    "journalist": "journalism", "editor": "journalism", "publisher": "journalism",
    "reporter": "journalism", "broadcaster": "journalism",
    "military": "military", "soldier": "military", "veteran": "military",
    "minister": "publicservice", "clergyman": "publicservice", "pastor": "publicservice",
    "engineer": "engineering", "architect": "engineering",
    "accountant": "business", "insurance": "business",
    "politician": "publicservice", "government": "publicservice",
}


def map_career(occupation_str):
    """Map bioguide occupation string to Harvard Dataverse career category."""
    if not occupation_str:
        return "NA"
    occ_lower = occupation_str.lower()
    for keyword, category in CAREER_MAP.items():
        if keyword in occ_lower:
            return category
    return "other"


def fetch_bioguide(bioguide_id):
    """Fetch member bio from bioguide API."""
    url = f"https://bioguide.congress.gov/search/bio/{bioguide_id}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return None


def main():
    print("Loading member lookup...")
    with open(MEMBER_LOOKUP_PATH, encoding="utf-8") as f:
        member_lookup = json.load(f)

    # get all unique bioguide IDs from members in our congresses
    bioguide_ids = set()
    for congress, members in member_lookup.get("by_congress", {}).items():
        for m in members:
            bid = m.get("bioguide_id", "")
            if bid:
                bioguide_ids.add(bid)

    print(f"Unique members across all congresses: {len(bioguide_ids)}")

    # load existing results
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
        print(f"Resuming: {len(existing)} already fetched")

    todo = [bid for bid in bioguide_ids if bid not in existing]
    print(f"To fetch: {len(todo)}")

    for i, bid in enumerate(todo):
        data = fetch_bioguide(bid)

        if data:
            # extract occupation from jobPositions
            occupations = []
            for pos in data.get("jobPositions", []):
                title = pos.get("congressAffiliation", {}).get("title", "")
                occ = pos.get("job", {}).get("name", "")
                if occ and "congress" not in occ.lower() and "representative" not in occ.lower():
                    occupations.append(occ)

            # also check direct professions field
            professions = [p.get("name", "") for p in data.get("professions", [])]
            all_occs = occupations + professions

            primary_career = "NA"
            for occ in all_occs:
                mapped = map_career(occ)
                if mapped != "other" and mapped != "NA":
                    primary_career = mapped
                    break
            if primary_career == "NA" and all_occs:
                primary_career = map_career(all_occs[0])

            existing[bid] = {
                "bioguide_id": bid,
                "occupations": all_occs[:5],
                "career": primary_career,
                "name": data.get("usCongressBioId", bid),
            }
        else:
            existing[bid] = {"bioguide_id": bid, "career": "NA", "occupations": []}

        if (i+1) % 50 == 0:
            with open(OUTPUT_PATH, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"  [{i+1}/{len(todo)}] saved checkpoint")

        time.sleep(0.3)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(existing, f, indent=2)

    # summary
    careers = Counter(v["career"] for v in existing.values())
    print(f"\nTotal members fetched: {len(existing)}")
    print("Career distribution:")
    for career, count in careers.most_common(10):
        print(f"  {career}: {count}")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
