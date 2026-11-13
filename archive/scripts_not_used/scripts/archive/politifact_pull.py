# politifact_pull.py
# Scrapes PolitiFact's health care fact-check listings and saves each claim
# as a row in a CSV file with the speaker, claim text, truth rating, context,
# and source URL. The resulting dataset serves as a calibration set for the
# factuality scoring method, since these claims already have professional
# fact-checker verdicts attached to them that can be used as a ground truth
# baseline before applying any scoring to unlabeled legislative speech.
# Currently pulls 10 pages of results, approximately 300 claims.
# Output: data/politifact/health_claims.csv

import requests
from bs4 import BeautifulSoup
import csv
import time

# Where the labeled health claims will be saved
OUTPUT_PATH = "data/politifact/health_claims.csv"

# PolitiFact's fact-check listing endpoint, filtered to the health-care category
BASE_URL = "https://www.politifact.com/factchecks/list/"

def parse_page(page_num):
    # Requesting one page of health-care fact-checks from PolitiFact
    params = {"category": "health-care", "page": page_num}
    resp = requests.get(BASE_URL, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, "lxml")

    # Each fact-check is a list item with the class o-listicle__item
    items = soup.find_all("li", class_="o-listicle__item")
    rows = []
    for item in items:
        # Pulling the speaker name, claim text, truth rating, context, and source link
        # from each fact-check entry using PolitiFact's consistent HTML class structure
        speaker_tag = item.find("a", class_="m-statement__name")
        quote_tag = item.find("div", class_="m-statement__quote")
        meter_tag = item.find("div", class_="m-statement__meter")
        desc_tag = item.find("div", class_="m-statement__desc")

        speaker = speaker_tag.get_text(strip=True) if speaker_tag else ""
        claim_link = quote_tag.find("a")["href"] if quote_tag and quote_tag.find("a") else ""
        claim_text = quote_tag.get_text(strip=True) if quote_tag else ""

        # The rating (True, Mostly True, Half True, Mostly False, False, Pants on Fire)
        # is stored as the alt text of the meter image rather than as plain text
        rating_img = meter_tag.find("img") if meter_tag else None
        rating = rating_img["alt"] if rating_img and rating_img.has_attr("alt") else ""
        context = desc_tag.get_text(strip=True) if desc_tag else ""

        rows.append({
            "speaker": speaker,
            "claim": claim_text,
            "rating": rating,
            "context": context,
            "url": "https://www.politifact.com" + claim_link if claim_link else ""
        })
    return rows

if __name__ == "__main__":
    all_rows = []
    for page in range(1, 11):
        print(f"Pulling page {page}")
        rows = parse_page(page)

        # Stopping early if a page comes back empty, meaning we have reached the end
        if not rows:
            print("No more results, stopping.")
            break
        all_rows.extend(rows)

        # Pausing between requests to stay polite to PolitiFact's server
        time.sleep(1)

    # Saving all claims to a single CSV file
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["speaker", "claim", "rating", "context", "url"])
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Saved {len(all_rows)} claims to {OUTPUT_PATH}")