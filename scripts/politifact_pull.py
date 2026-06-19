import requests
from bs4 import BeautifulSoup
import csv
import time

OUTPUT_PATH = "data/politifact/health_claims.csv"
BASE_URL = "https://www.politifact.com/factchecks/list/"

def parse_page(page_num):
    params = {"category": "health-care", "page": page_num}
    resp = requests.get(BASE_URL, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.find_all("li", class_="o-listicle__item")
    rows = []
    for item in items:
        speaker_tag = item.find("a", class_="m-statement__name")
        quote_tag = item.find("div", class_="m-statement__quote")
        meter_tag = item.find("div", class_="m-statement__meter")
        desc_tag = item.find("div", class_="m-statement__desc")

        speaker = speaker_tag.get_text(strip=True) if speaker_tag else ""
        claim_link = quote_tag.find("a")["href"] if quote_tag and quote_tag.find("a") else ""
        claim_text = quote_tag.get_text(strip=True) if quote_tag else ""
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
    for page in range(1, 11):  # start with 10 pages, expand once confirmed working
        print(f"Pulling page {page}")
        rows = parse_page(page)
        if not rows:
            print("No more results, stopping.")
            break
        all_rows.extend(rows)
        time.sleep(1)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["speaker", "claim", "rating", "context", "url"])
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Saved {len(all_rows)} claims to {OUTPUT_PATH}")