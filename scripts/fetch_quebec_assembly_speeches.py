"""
fetch_quebec_assembly_speeches.py

Fetches the real Assembly floor debate transcripts for every Quebec health
bill from the Cheminement data. The Cheminement JSON already has the URLs
under each bill's assembly_debates field, pointing to Journal des debats
pages on assnat.qc.ca.

This is the REAL speech data for Quebec (not the CSSS committee files).
Each page is one sitting day's Assembly debate, saved as plain text.

Output: data/canada/quebec_assembly/
  - {YYYYMMDD}.txt for each unique sitting day fetched
  - fetch_log.json  resume tracking

Usage: python3 scripts/fetch_quebec_assembly_speeches.py

Note: assnat.qc.ca requires a browser-like User-Agent, confirmed working
from the pilot run on July 16.
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMINEMENT_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                                "cheminement_all_sessions.json")
HEALTH_BILLS_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                                 "quebec_health_bills_combined.json")
OUT_DIR = os.path.join(REPO_ROOT, "data", "canada", "quebec_assembly")
LOG_PATH = os.path.join(OUT_DIR, "fetch_log.json")

os.makedirs(OUT_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality project)"}


def url_to_date(url):
    """
    Extract date from assnat.qc.ca journal URL.
    e.g. .../journal-debats/20260224/428417.html -> 20260224
    """
    m = re.search(r"/journal-debats/(\d{8})/", url)
    return m.group(1) if m else None


def extract_text_from_html(html):
    """
    Strip HTML and return clean plain text of the debate transcript.
    Targets the main content div used by assnat.qc.ca.
    """
    soup = BeautifulSoup(html, "html.parser")

    # assnat.qc.ca: transcript content has no wrapping id, sits inside Wrap.
    # Strategy: take Wrap, strip all known nav/header/footer sections by id.
    content = soup.find("div", id="Wrap") or soup.find("body")

    if not content:
        return soup.get_text(separator="\n")

    for remove_id in [
        "enteteUtilitaire", "skip", "Banniere",
        "NavigationPrincipaleConteneur", "NavPrincipaleNiveau1",
        "Calendrier", "BlocSurLesTours", "listeDrapeaux",
        "NavigationPrincipaleNiveau2Conteneur", "NavPrincipaleNiveau2",
        "FilAriane", "divAncreSousNavigation", "SousNavigation",
        "utilitairesAssemblee", "ClearPiedPage", "PiedDePage", "bInfolettre",
    ]:
        tag = content.find(id=remove_id)
        if tag:
            tag.decompose()

    for tag in content.find_all(["script", "style", "nav", "header",
                                  "footer", "button", "form", "select"]):
        tag.decompose()

    text = content.get_text(separator="\n")
    # collapse whitespace runs
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def main():
    log = {}
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            log = json.load(f)
        already_done = sum(1 for v in log.values() if v == "ok")
        print(f"Resuming: {already_done} pages already fetched")

    # load health bills to restrict to only health-relevant debates
    health_bill_numbers = set()
    if os.path.exists(HEALTH_BILLS_PATH):
        with open(HEALTH_BILLS_PATH, encoding="utf-8") as f:
            health_bills = json.load(f)
        # health_bills is a list with 'title' field like
        # "Projet de loi n° 11, Loi modifiant..."
        for b in health_bills:
            title = b.get("title", "")
            m = re.search(r"[Pp]rojet de loi n[°o\xa0]\s*(\d+)", title)
            if m:
                health_bill_numbers.add(m.group(1))
        print(f"Loaded {len(health_bill_numbers)} health bill numbers to filter on")

    with open(CHEMINEMENT_PATH, encoding="utf-8") as f:
        cheminement = json.load(f)

    # collect all unique assembly debate URLs for health bills
    urls_to_fetch = {}  # url -> bill_number for provenance
    for session, bills in cheminement.items():
        for bill in bills:
            # get bill number from title
            title = bill.get("title", "")
            m = re.search(r"[Pp]rojet de loi n[°o]\s*(\d+)", title)
            bill_num = m.group(1) if m else None

            # only fetch for health bills (if we have health bills loaded)
            if health_bill_numbers and bill_num and bill_num not in health_bill_numbers:
                continue

            for debate in bill.get("assembly_debates", []):
                url = debate.get("url")
                if url and url not in urls_to_fetch:
                    urls_to_fetch[url] = bill_num or "unknown"

    print(f"Total unique Assembly debate URLs to fetch: {len(urls_to_fetch)}")
    todo = {url: bn for url, bn in urls_to_fetch.items() if log.get(url) != "ok"}
    print(f"Still to fetch this run: {len(todo)}\n")

    fetched = 0
    errors = 0

    for url, bill_num in todo.items():
        date = url_to_date(url)
        if not date:
            print(f"  Skipping (no date parseable): {url}")
            log[url] = "no_date"
            continue

        out_path = os.path.join(OUT_DIR, f"{date}.txt")

        # skip if this date's file is already saved (another bill's debate
        # on the same day would be in the same transcript)
        if os.path.exists(out_path):
            log[url] = "ok"
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=25)
            resp.raise_for_status()
            text = extract_text_from_html(resp.text)

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)

            log[url] = "ok"
            fetched += 1
            print(f"  [{fetched}] {date} (Bill {bill_num}) -> {len(text)} chars")

        except Exception as e:
            log[url] = f"error: {e}"
            errors += 1
            print(f"  ERROR {date}: {e}")

        # save log periodically
        if (fetched + errors) % 20 == 0:
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=2)

        time.sleep(1.2)  # polite to assnat.qc.ca

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    saved = sorted(f for f in os.listdir(OUT_DIR) if f.endswith(".txt"))
    print(f"\n{'='*60}")
    print(f"Fetched this run:          {fetched}")
    print(f"Errors this run:           {errors}")
    print(f"Total .txt files on disk:  {len(saved)}")
    if saved:
        print(f"Date range:                {saved[0].replace('.txt','')} "
              f"to {saved[-1].replace('.txt','')}")
    print(f"Log saved to: {LOG_PATH}")


if __name__ == "__main__":
    main()
