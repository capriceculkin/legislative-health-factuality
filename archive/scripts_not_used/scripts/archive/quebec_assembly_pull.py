# quebec_assembly_pull.py
# Collects all Assembly sitting day debate links for Quebec sessions 33-1 through 34-3
# (December 1985 to June 1994) by using Playwright to interact with the session and
# month dropdowns on the Assembly proceedings page, then clicking the correct
# Rechercher button to load the sitting day links for each month.
# This approach was discovered after confirming the page has two separate search forms
# and the correct one is identified by name: ctl00$ColCentre$ContenuColonneGauche$btnRechercher
# Output: data/canada/quebec_assembly/sitting_day_links.json

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import json
import os
import time

OUTPUT_DIR = "data/canada/quebec_assembly"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "sitting_day_links.json")

# All pre-1994 sessions with their base URLs and month ranges
# Month values are in YYYYMM format matching the dropdown option values
SESSIONS = [
    {
        "code": "33-1",
        "url": "https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/33-1/index.html",
        "months": [
            "198512", "198601", "198602", "198603", "198604", "198605",
            "198606", "198607", "198608", "198609", "198610", "198611",
            "198612", "198701", "198702", "198703", "198704", "198705",
            "198706", "198707", "198708", "198709", "198710", "198711",
            "198712", "198801", "198802", "198803"
        ]
    },
    {
        "code": "33-2",
        "url": "https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/33-2/index.html",
        "months": [
            "198803", "198804", "198805", "198806", "198807", "198808",
            "198809", "198810", "198811", "198812", "198901", "198902",
            "198903", "198904", "198905", "198906", "198907", "198908"
        ]
    },
    {
        "code": "34-1",
        "url": "https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/34-1/index.html",
        "months": [
            "198911", "198912", "199001", "199002", "199003", "199004",
            "199005", "199006", "199007", "199008", "199009", "199010",
            "199011", "199012", "199101", "199102", "199103", "199104",
            "199105", "199106", "199107", "199108", "199109", "199110",
            "199111", "199112", "199201", "199202", "199203"
        ]
    },
    {
        "code": "34-2",
        "url": "https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/34-2/index.html",
        "months": [
            "199210", "199211", "199212", "199301", "199302", "199303",
            "199304", "199305", "199306", "199307", "199308", "199309",
            "199310", "199311", "199312", "199401", "199402", "199403"
        ]
    },
    {
        "code": "34-3",
        "url": "https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/34-3/index.html",
        "months": [
            "199403", "199404", "199405", "199406"
        ]
    },
]

def get_links_for_month(page, session_url, month_value):
    # Loading the session index page
    page.goto(session_url, timeout=30000)
    page.wait_for_timeout(2000)

    # Selecting the session from the dropdown
    page.select_option(
        "select[name='ctl00$ColCentre$ContenuColonneGauche$ddlChoixSession']",
        session_url
    )
    page.wait_for_timeout(1500)

    # Selecting the month
    try:
        page.select_option(
            "select[name='ctl00$ColCentre$ContenuColonneGauche$ddlChoixMoisAnnee$MoisAnnee']",
            month_value
        )
    except Exception:
        return []
    page.wait_for_timeout(1000)

    # Clicking the correct Rechercher button (not the sidebar one)
    page.click("input[name='ctl00$ColCentre$ContenuColonneGauche$btnRechercher']")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Collecting all sitting day debate links
    anchors = page.query_selector_all("a")
    links = []
    for a in anchors:
        href = a.get_attribute("href") or ""
        text = a.inner_text().strip()
        if "journal-debats" in href and "assemblee-nationale" in href:
            links.append({"text": text, "url": "https://www.assnat.qc.ca" + href if href.startswith("/") else href})
    return links

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_links = {}

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for session in SESSIONS:
            code = session["code"]
            all_links[code] = []
            print(f"\nProcessing session {code}...")

            for month in session["months"]:
                links = get_links_for_month(page, session["url"], month)
                all_links[code].extend(links)
                print(f"  {month}: {len(links)} sitting days")
                # Saving progress after each month
                with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                    json.dump(all_links, f, indent=2, ensure_ascii=False)
                time.sleep(1)

        browser.close()

    total = sum(len(v) for v in all_links.values())
    print(f"\nDone. {total} total sitting day links saved to {OUTPUT_PATH}")