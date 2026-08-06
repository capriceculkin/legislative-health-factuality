"""
fix_na_careers.py

Re-fetches bioguide pages for members still marked NA and tries
harder to extract occupation from the full biography text.

Usage: python3 scripts/fix_na_careers.py
"""
import os, json, re, asyncio
from collections import Counter
from playwright.async_api import async_playwright

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/us/member_careers.json")
BASE = "https://bioguide.congress.gov"

CAREER_MAP = {
    "lawyer": "law", "attorney": "law", "judge": "law", "solicitor": "law",
    "counsel": "law", "barrister": "law", "j.d.": "law", "ll.b.": "law",
    "ll.m.": "law", "law school": "law", "legal": "law",
    "physician": "medicine", "doctor": "medicine", "surgeon": "medicine",
    "dentist": "medicine", "dental": "medicine", "d.d.s": "medicine",
    "pharmacist": "medicine", "nurse": "medicine", "m.d.": "medicine",
    "optometrist": "medicine", "chiropractor": "medicine", "psychiatrist": "medicine",
    "businessman": "business", "merchant": "business", "banker": "business",
    "manufacturer": "business", "executive": "business", "real estate": "business",
    "developer": "business", "contractor": "business", "stockbroker": "business",
    "investment": "business", "chairman": "business", "m.b.a.": "business",
    "entrepreneur": "business", "accountant": "business", "insurance": "business",
    "film": "business", "production company": "business", "financier": "business",
    "retailer": "business", "salesman": "business", "trader": "business",
    "teacher": "education", "professor": "education", "educator": "education",
    "superintendent": "education", "principal": "education", "academic": "education",
    "librarian": "education", "coach": "education",
    "farmer": "agriculture", "rancher": "agriculture", "agriculturist": "agriculture",
    "livestock": "agriculture", "dairy": "agriculture", "cattle": "agriculture",
    "journalist": "journalism", "editor": "journalism", "publisher": "journalism",
    "reporter": "journalism", "writer": "journalism", "author": "journalism",
    "broadcaster": "journalism", "newspaper": "journalism",
    "military": "military", "soldier": "military", "veteran": "military",
    "pilot": "military", "air force": "military", "coast guard": "military",
    "navy": "military", "army": "military", "marine": "military",
    "minister": "publicservice", "clergyman": "publicservice", "pastor": "publicservice",
    "priest": "publicservice", "rabbi": "publicservice", "chaplain": "publicservice",
    "coordinator": "publicservice", "administrator": "publicservice",
    "social worker": "publicservice", "nonprofit": "publicservice",
    "engineer": "engineering", "architect": "engineering", "chemist": "engineering",
    "scientist": "engineering", "researcher": "engineering", "geologist": "engineering", "veterinarian": "medicine", "d.v.m.": "medicine", "veterinary": "medicine",
    "osteopath": "medicine", "d.o.": "medicine",
    "psychologist": "medicine", "therapist": "medicine",
    "realtor": "business", "lumber": "business", "oil": "business",
    "mining": "business", "construction": "business",
    "funeral": "business", "mortician": "business",
    "forester": "agriculture", "fisherman": "agriculture",
    "clergy": "publicservice", "deacon": "publicservice",
    "police": "publicservice", "law enforcement": "publicservice",
    "firefighter": "publicservice",
    "surveyor": "engineering", "geographer": "engineering", "staff": "publicservice", "staffer": "publicservice",
    "aide": "publicservice", "assistant": "publicservice",
    "organizer": "publicservice", "activist": "publicservice",
    "diplomat": "publicservice", "foreign service": "publicservice",
    "united nations": "publicservice","consultant": "business", "businesswoman": "business", "business owner": "business",
    "marketing": "business", "auctioneer": "business", "call center": "business",
    "flight attendant": "business", "corporate": "business",
    "community outreach": "publicservice", "outreach": "publicservice",
    "advocate": "publicservice", "foreign affairs": "publicservice",
    "ed.s.": "education", "ed.d.": "education",
    "m.p.a.": "publicservice", "m.p.p.": "publicservice",
    "m.s.f.s.": "publicservice", "ph.d.": "education", "doctorate": "education", "faculty": "education",
    "program director": "publicservice", "program manager": "publicservice",
    "trade unionist": "publicservice", "union": "publicservice",
    "electrician": "engineering", "plumber": "engineering", "carpenter": "engineering",
    "tradesman": "engineering", "mechanic": "engineering",
    "prosecutor": "law", "district attorney": "law", "public defender": "law",
    "meteorologist": "engineering", "scientist": "engineering",
    "entertainer": "other", "actor": "other", "musician": "other", "artist": "other",
    "radio": "journalism", "television": "journalism", "broadcaster": "journalism",
    "founder": "business", "director of": "publicservice", "sales representative": "business", "sales": "business",
    "mortgage broker": "business", "broker": "business",
    "financial": "business", "financ": "business",
    "m.div.": "publicservice", "seminary": "publicservice",
    "mission": "publicservice", "missionary": "publicservice",
    "youth camp": "publicservice", "camp director": "publicservice",
    "school board": "education", "postal": "publicservice",
    "postmaster": "publicservice", "national guard": "military", "naval": "military", "navy": "military",
    "advertising": "business", "public relations": "business",
    "mayor": "publicservice", "city council": "publicservice",
    "alderman": "publicservice", "freeholder": "publicservice",
    "county board": "publicservice", "tax preparation": "business", "tax preparer": "business",
    "senior citizens": "publicservice", "senior services": "publicservice",
    "secretary of state": "publicservice", "secretary of": "publicservice",
    "state treasurer": "publicservice", "comptroller": "publicservice",
    "m.a.": "education", "l.l.b.": "law",
    "broadcasting school": "journalism", "school of broadcasting": "journalism",
    "automobile dealer": "business", "auto dealer": "business", "dealership": "business",
    "energy corporation": "business", "energy company": "business",
    "legislature": "publicservice", "house of delegates": "publicservice",
    "state senate": "publicservice", "state assembly": "publicservice", "professional athlete": "other", "athlete": "other", "sports": "other",
    "board of aldermen": "publicservice",
}


def extract_career_from_text(text):
    bio_lower = text[:4000].lower()

    # check degree patterns first
    if "d.d.s" in bio_lower:
        return "medicine", ["dentist"]
    if "m.d." in bio_lower and "ph.d." not in bio_lower:
        return "medicine", ["physician"]
    if any(d in bio_lower for d in ["j.d.", "ll.b.", "ll.m."]):
        return "law", ["lawyer"]
    if "m.b.a." in bio_lower:
        return "business", ["businessman"]

    # scan for keywords
    found = []
    for keyword, category in CAREER_MAP.items():
        if keyword in bio_lower:
            found.append((keyword, category))

    if found:
        # return most specific match
        primary = found[0][1]
        return primary, [f[0] for f in found[:3]]

    return "NA", []


async def main():
    with open(OUTPUT_PATH) as f:
        careers = json.load(f)

    na_ids = [bid for bid, v in careers.items() if v.get("career") == "NA"]
    print(f"NA members to re-fetch: {len(na_ids)}")

    fixed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        await page.goto(BASE, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        for i, bid in enumerate(na_ids):
            try:
                await page.goto(
                    f"{BASE}/search/bio/{bid}",
                    wait_until="networkidle", timeout=30000
                )
                await page.wait_for_timeout(1000)
                text = await page.inner_text("body")

                career, occupations = extract_career_from_text(text)
                careers[bid]["career"] = career
                careers[bid]["occupations"] = occupations

                if career != "NA":
                    fixed += 1
                    print(f"  [{i+1}] {bid}: {career} ({occupations[:2]})")

                if (i+1) % 50 == 0:
                    with open(OUTPUT_PATH, "w") as f:
                        json.dump(careers, f, indent=2)
                    print(f"  Checkpoint: {i+1}/{len(na_ids)}, fixed {fixed} so far")

            except Exception as e:
                print(f"  [{i+1}] {bid}: error - {e}")

            await page.wait_for_timeout(300)

        await browser.close()

    with open(OUTPUT_PATH, "w") as f:
        json.dump(careers, f, indent=2)

    dist = Counter(v["career"] for v in careers.values())
    print(f"\nFixed: {fixed}/{len(na_ids)}")
    print("Final career distribution:")
    for career, count in dist.most_common():
        print(f"  {career}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
