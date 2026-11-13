"""
fetch_us_member_careers_playwright.py

Uses Playwright to scrape occupation/career data from bioguide.congress.gov
for US House members in our matched health bills.

Maps to same career categories as Harvard Dataverse ppb.csv:
law, medicine, business, education, agriculture, publicservice, journalism, military

Usage: python3 scripts/fetch_us_member_careers_playwright.py
"""
import os, json, time, re, asyncio
from collections import Counter
from playwright.async_api import async_playwright

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBER_LOOKUP_PATH = os.path.join(REPO_ROOT, "data/us/member_lookup.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/us/member_careers.json")

BASE = "https://bioguide.congress.gov"

CAREER_MAP = {
    "lawyer": "law", "attorney": "law", "judge": "law", "solicitor": "law",
    "counsel": "law", "barrister": "law",
    "physician": "medicine", "doctor": "medicine", "surgeon": "medicine",
    "dentist": "medicine", "pharmacist": "medicine", "nurse": "medicine",
    "businessman": "business", "merchant": "business", "banker": "business",
    "manufacturer": "business", "entrepreneur": "business", "executive": "business",
    "insurance": "business", "accountant": "business", "financier": "business",
    "teacher": "education", "professor": "education", "educator": "education",
    "superintendent": "education", "principal": "education", "academic": "education",
    "farmer": "agriculture", "rancher": "agriculture", "agriculturist": "agriculture",
    "journalist": "journalism", "editor": "journalism", "publisher": "journalism",
    "reporter": "journalism", "broadcaster": "journalism", "newspaper": "journalism",
    "military": "military", "soldier": "military", "veteran": "military",
    "officer": "military", "army": "military", "navy": "military",
    "minister": "publicservice", "clergyman": "publicservice", "pastor": "publicservice",
    "engineer": "engineering", "architect": "engineering",
    "politician": "publicservice", "government": "publicservice", "real estate": "business", "developer": "business", "chairman": "business",
    "chief executive": "business", "president of": "business", "m.b.a.": "business",
    "film": "business", "production": "business", "investment": "business",
    "stockbroker": "business", "contractor": "business", "salesman": "business",
    "d.d.s.": "medicine", "m.d.": "medicine", "dental": "medicine",
    "j.d.": "law", "ll.b.": "law", "ll.m.": "law",
    "coordinator": "publicservice", "administrator": "publicservice",
    "social worker": "publicservice", "nonprofit": "publicservice",
    "writer": "journalism", "author": "journalism",
    "pilot": "military", "air force": "military", "coast guard": "military",
    "chemist": "engineering", "scientist": "engineering", "researcher": "engineering",
}


def map_career(occupation_str):
    if not occupation_str:
        return "NA"
    occ_lower = occupation_str.lower()
    for keyword, category in CAREER_MAP.items():
        if keyword in occ_lower:
            return category
    return "other"


async def scrape_member(page, bioguide_id):
    """Scrape a single member's bioguide page."""
    url = f"{BASE}/search/bio/{bioguide_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)

        text = await page.inner_text("body")

        # scan full bio text for career keywords directly
        bio_section = text[:3000].lower()
        occupations = []

        # degree patterns indicating profession
        if "d.d.s" in bio_section or "dentist" in bio_section:
            occupations.append("dentist")
        if "m.d." in bio_section and "physician" not in occupations:
            occupations.append("physician")
        if "j.d." in bio_section or "ll.b." in bio_section or "ll.m." in bio_section:
            occupations.append("lawyer")
        if "m.b.a." in bio_section:
            occupations.append("businessman")

        # direct keyword scan of full bio paragraph
        keyword_checks = [
            "lawyer", "attorney", "judge", "solicitor", "counsel",
            "physician", "doctor", "surgeon", "pharmacist", "nurse",
            "dentist", "dental",
            "businessman", "merchant", "banker", "manufacturer", "executive",
            "real estate", "developer", "contractor", "stockbroker", "investment",
            "chairman", "chief executive", "president of",
            "teacher", "professor", "educator", "superintendent",
            "farmer", "rancher", "agriculturist",
            "journalist", "editor", "publisher", "reporter", "writer", "author",
            "military", "soldier", "veteran", "pilot", "air force", "coast guard",
            "minister", "clergyman", "pastor",
            "engineer", "architect", "chemist", "scientist", "researcher",
            "coordinator", "administrator", "social worker", "nonprofit",
            "film", "production company",
        ]
        for keyword in keyword_checks:
            if keyword in bio_section and keyword not in occupations:
                occupations.append(keyword)
                break

        primary_career = "NA"
        for occ in occupations:
            mapped = map_career(occ)
            if mapped != "NA":
                primary_career = mapped
                break

        return {
            "bioguide_id": bioguide_id,
            "occupations": occupations[:5],
            "career": primary_career,
        }

    except Exception as e:
        return {"bioguide_id": bioguide_id, "career": "NA", "occupations": [], "error": str(e)}


async def main():
    print("Loading member lookup...")
    with open(MEMBER_LOOKUP_PATH, encoding="utf-8") as f:
        member_lookup = json.load(f)

    # get all unique bioguide IDs
    bioguide_ids = set()
    for congress, members in member_lookup.get("by_congress", {}).items():
        for m in members:
            bid = m.get("bioguide_id", "")
            if bid:
                bioguide_ids.add(bid)

    print(f"Unique members: {len(bioguide_ids)}")

    # load existing
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
        # only keep entries that actually have career data
        existing = {k: v for k, v in existing.items() if v.get("career") != "NA" or v.get("occupations")}
        print(f"Resuming: {len(existing)} already fetched with data")

    todo = [bid for bid in bioguide_ids if bid not in existing]
    print(f"To scrape: {len(todo)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        # first visit homepage to get cookies
        await page.goto(BASE, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        for i, bid in enumerate(todo):
            result = await scrape_member(page, bid)
            existing[bid] = result

            if result["career"] != "NA":
                print(f"  [{i+1}] {bid}: {result['career']} ({result['occupations'][:2]})")

            if (i+1) % 100 == 0:
                with open(OUTPUT_PATH, "w") as f:
                    json.dump(existing, f, indent=2)
                print(f"  Checkpoint saved: {i+1}/{len(todo)}")

            await page.wait_for_timeout(300)

        await browser.close()

    with open(OUTPUT_PATH, "w") as f:
        json.dump(existing, f, indent=2)

    careers = Counter(v["career"] for v in existing.values())
    print(f"\nTotal fetched: {len(existing)}")
    print("Career distribution:")
    for career, count in careers.most_common(10):
        print(f"  {career}: {count}")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
