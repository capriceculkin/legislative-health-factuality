from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import os
import json
import time

# Pulling bill stage data from Quebec's Cheminement des projets de loi
# Each bill page links directly to Assembly debates and committee sessions
# This gives us the real URLs we need for transcripts and votes

OUTPUT_DIR = "data/canada/quebec_bills"

# Legislature sessions to cover, working backward toward 1985
# 33e législature, 1re session started December 1985, matching our anchor date
SESSIONS = [
    "43-2", "43-1",
    "42-2", "42-1",
    "41-1",
    "40-1",
    "39-2", "39-1",
    "38-1",
    "37-2", "37-1",
    "36-2", "36-1",
    "35-2", "35-1",
    "34-3", "34-2", "34-1",
    "33-2", "33-1",
]

BASE = "https://www.assnat.qc.ca"

def get_bill_links(page, session_code):
    # Loading the cheminement index page for this session
    url = f"{BASE}/fr/travaux-parlementaires/projets-loi/rapport/projets-loi-{session_code}.html"
    page.goto(url, timeout=30000)
    page.wait_for_timeout(3000)

    all_bill_links = []

    while True:
        # Grabbing every link that points to an individual bill page on this page
        anchors = page.query_selector_all("a")
        for a in anchors:
            href = a.get_attribute("href")
            if href and f"projet-loi-" in href and f"-{session_code}.html" in href:
                full_url = BASE + href if not href.startswith("http") else href
                if full_url not in [b["url"] for b in all_bill_links]:
                    all_bill_links.append({"url": full_url})

        # Check if there is a next page button and click it
        next_btn = page.query_selector("a:has-text('Page suivante')")
        if next_btn:
            href = next_btn.get_attribute("href")
            if href and href != "#":
                next_btn.click()
                page.wait_for_timeout(2000)
            else:
                # JS pagination, click and wait for DOM update
                next_btn.click()
                page.wait_for_timeout(2000)
                # Check if we got new links
                new_anchors = page.query_selector_all("a")
                new_links = []
                for a in new_anchors:
                    href = a.get_attribute("href")
                    if href and f"projet-loi-" in href and f"-{session_code}.html" in href:
                        full_url = BASE + href if not href.startswith("http") else href
                        new_links.append(full_url)
                # If no new links appeared stop paginating
                existing = [b["url"] for b in all_bill_links]
                if all(l in existing for l in new_links):
                    break
        else:
            break

    print(f"Session {session_code}: found {len(all_bill_links)} bills")
    return all_bill_links

def get_bill_stages(page, bill_url):
    # Loading an individual bill's cheminement page
    page.goto(bill_url, timeout=30000)
    page.wait_for_timeout(3000)

    # Pulling the bill title
    title = ""
    try:
        title = page.query_selector("h1").inner_text().strip()
    except Exception:
        pass

    # Collecting all stage links
    # Assembly debates have assemblee-nationale in their URL
    # Committee debates have commissions in their URL
    # We want both but label them separately
    assembly_links = []
    committee_links = []

    anchors = page.query_selector_all("a")
    for a in anchors:
        href = a.get_attribute("href")
        label = a.inner_text().strip()
        if not href:
            continue
        full_url = BASE + href if not href.startswith("http") else href
        if "assemblee-nationale" in href and "journal-debats" in href:
            assembly_links.append({"label": label, "url": full_url})
        elif "commissions" in href and "journal-debats" in href:
            committee_links.append({"label": label, "url": full_url})

    return {
        "title": title,
        "bill_url": bill_url,
        "assembly_debates": assembly_links,
        "committee_debates": committee_links,
    }

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_data = {}

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for session_code in SESSIONS:
            print(f"\nStarting session {session_code}...")
            bill_links = get_bill_links(page, session_code)
            session_bills = []

            for bill_url in bill_links:
                # Pulling stage links for each individual bill
                bill_data = get_bill_stages(page, bill_url["url"])
                session_bills.append(bill_data)
                print(f"  {bill_data['title'][:60]} -> {len(bill_data['assembly_debates'])} assembly, {len(bill_data['committee_debates'])} committee links")
                # Being polite to the server
                time.sleep(1)

            all_data[session_code] = session_bills

            # Saving progress after each session in case of interruption
            out_path = os.path.join(OUTPUT_DIR, "cheminement_all_sessions.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            print(f"Saved progress after session {session_code}")

        browser.close()

    print(f"\nDone. All sessions saved to {out_path}")