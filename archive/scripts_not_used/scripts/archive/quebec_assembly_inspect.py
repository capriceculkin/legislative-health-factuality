from playwright.sync_api import sync_playwright

INDEX_URL = "https://www.assnat.qc.ca/fr/travaux-parlementaires/journaux-debats.html"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(INDEX_URL, timeout=30000)
    page.wait_for_timeout(4000)

    anchors = page.query_selector_all("a")
    links = set()
    for a in anchors:
        href = a.get_attribute("href")
        if href and "journal-debats" in href:
            links.add(href)

    print(f"Found {len(links)} journal-debats links after JS render:")
    for link in sorted(links)[:20]:
        print(link)

    browser.close()