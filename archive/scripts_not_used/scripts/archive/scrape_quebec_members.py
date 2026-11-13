"""
scrape_quebec_members.py

Scrapes Quebec National Assembly member biographies using the correct
URL patterns discovered from the actual page HTML.

Usage: python3 scripts/scrape_quebec_members.py
"""
import os, json, time, re, requests
from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/canada/quebec_members_recent.json")
BASE = "https://www.assnat.qc.ca"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality)"}

# correct letter index pages from actual HTML
INDEX_PAGES = [
    "https://www.assnat.qc.ca/fr/membres/notices/index.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-b.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-c.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-d.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-ef.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-g.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-hi.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-jk.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-l.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-m.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-no.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-p.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-qr.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-s.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-tu.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-vz.html",
]


def get_member_links(index_url):
    """Get all member profile links from an index page."""
    try:
        resp = requests.get(index_url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # member links go to /fr/deputes/ or /fr/patrimoine/anciens-parlementaires/
            if "/fr/deputes/" in href and href.endswith("/index.html"):
                full = BASE + href if href.startswith("/") else href
                links.append((a.text.strip(), full, "(en fonction)" in a.parent.get_text()))
        return links
    except Exception as e:
        print(f"  Error fetching index {index_url}: {e}")
        return []


def scrape_member_page(name, url, is_current):
    """Scrape individual member page for party and career info."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        member = {
            "name": name,
            "url": url,
            "is_current": is_current,
        }

        # extract years mentioned
        years = re.findall(r"\b(19[5-9]\d|20[012]\d)\b", text)
        if years:
            member["years_active"] = sorted(set(years))

        # extract party
        parties = [
            "Coalition avenir Québec", "Parti québécois", "Parti libéral du Québec",
            "Québec solidaire", "Action démocratique du Québec",
            "Union nationale", "Parti créditiste"
        ]
        for party in parties:
            if party.lower() in text.lower():
                member["party"] = party
                break

        # extract birth year
        birth = re.search(r"(?:Né|Née|naissance)[^\d]*(\d{4})", text)
        if birth:
            member["year_of_birth"] = birth.group(1)

        # extract profession/career
        prof = re.search(r"(?:Profession|profession|Carrière|carrière)\s*:?\s*([^\n\.]+)", text)
        if prof:
            member["career"] = prof.group(1).strip()[:100]

        return member
    except Exception as e:
        return {"name": name, "url": url, "error": str(e)}


def main():
    all_members = []
    visited = set()

    for index_url in INDEX_PAGES:
        letter = index_url.split("index")[-1].replace(".html","").replace("-","") or "a"
        print(f"Index {letter}...", end=" ", flush=True)

        links = get_member_links(index_url)
        # filter to those active 1985+ (current members and recent ones)
        # we'll filter by year after scraping
        new_links = [(n, u, c) for n, u, c in links if u not in visited]
        print(f"{len(new_links)} members")
        visited.update(u for _, u, _ in new_links)

        for name, url, is_current in new_links:
            member = scrape_member_page(name, url, is_current)
            all_members.append(member)
            time.sleep(0.2)

        time.sleep(0.5)

    # filter to members active 1985+
    recent = []
    for m in all_members:
        years = m.get("years_active", [])
        if m.get("is_current") or any(int(y) >= 1985 for y in years):
            recent.append(m)

    print(f"\nTotal scraped: {len(all_members)}")
    print(f"Active 1985+: {len(recent)}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(recent, f, indent=2, ensure_ascii=False)
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
