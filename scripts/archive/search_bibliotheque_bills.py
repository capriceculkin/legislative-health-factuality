from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import json
import re
import time

OUTPUT_PATH = "data/canada/quebec_bills/pre1994_health_bills.json"

HEALTH_KEYWORDS = [
    "sante", "soins", "medecin", "hopital", "medicament",
    "pharmacie", "infirmier", "readaptation", "handicap",
    "toxicomanie", "tabac", "vaccination", "maternite",
    "psychiatrique", "RAMQ", "CLSC", "CHSLD", "assurance maladie",
]

TARGET_CHECKBOX_TEXTS = ["33-1", "33-2", "34-1", "34-2", "34-3"]

def parse_results(html):
    soup = BeautifulSoup(html, "lxml")
    bills = []
    rows = soup.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 2:
            filename = cells[0].get_text(strip=True)
            description = cells[1].get_text(strip=True)
            if filename.endswith(".pdf") and "F.pdf" in filename:
                match = re.search(r"(\d+[-\d]*_\d{4}[-\d]*_\d+)", filename)
                if match:
                    bills.append({
                        "filename": filename,
                        "description": description[:200],
                    })
    return bills

URL = "https://www.bibliotheque.assnat.qc.ca/fr/10347-recherche-%E2%80%93-projets-de-loi-du-quebec-1867"

all_bills = {}

with Stealth().use_sync(sync_playwright()) as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    for keyword in HEALTH_KEYWORDS:
        print(f"\nSearching: {keyword}")
        search_html = []

        def handle_response(response):
            if "dtisapi6.dll" in response.url:
                try:
                    search_html.append(response.text())
                except Exception:
                    pass

        page.on("response", handle_response)
        page.goto(URL, timeout=30000)
        page.wait_for_timeout(3000)

        search_frame = None
        for frame in page.frames:
            if "formulairerecherche" in frame.url.lower():
                search_frame = frame
                break

        if not search_frame:
            continue

        search_frame.fill("input[name='request']", keyword)
        page.wait_for_timeout(500)

        buttons = search_frame.query_selector_all("input[type='submit'], button, input[type='button']")
        buttons[0].click()
        page.wait_for_timeout(2000)

        all_checkboxes = search_frame.query_selector_all("input[type='checkbox']")
        for cb in all_checkboxes:
            val = cb.get_attribute("value") or ""
            for target in TARGET_CHECKBOX_TEXTS:
                if target in val:
                    cb.click()
                    page.wait_for_timeout(200)
                    break

        page.wait_for_timeout(500)
        buttons[2].click()
        page.wait_for_timeout(8000)

        if search_html:
            bills = parse_results(search_html[0])
            print(f"  Found {len(bills)} bills")
            for b in bills:
                fname = b["filename"]
                if fname not in all_bills:
                    all_bills[fname] = b
        
        page.remove_listener("response", handle_response)
        time.sleep(1)

    browser.close()

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(list(all_bills.values()), f, indent=2, ensure_ascii=False)

print(f"\nTotal unique health bills found: {len(all_bills)}")
print(f"Saved to {OUTPUT_PATH}")