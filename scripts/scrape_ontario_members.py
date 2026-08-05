"""
scrape_ontario_members.py

Scrapes Ontario MPP biographical data from the Legislative Assembly of Ontario
website (ola.org). Covers all MPPs since 1867 with name, riding, party.

Usage: python3 scripts/scrape_ontario_members.py
"""
import os, json, time, re, requests
from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data/canada/ontario_members.json")
BASE = "https://www.ola.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality)"}
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def get_members_from_index(letter):
    url = f"{BASE}/en/members/last-name/{letter}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        members = []
        table = soup.find("table")
        if not table:
            return []
        for row in table.find_all("tr")[1:]:  # skip header
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            a = cols[0].find("a")
            if not a:
                continue
            name = a.text.strip()
            href = a.get("href", "")
            riding = cols[1].text.strip()
            party = cols[2].text.strip()
            members.append({
                "name": name,
                "url": BASE + href if href.startswith("/") else href,
                "riding": riding,
                "party": party,
            })
        return members
    except Exception as e:
        print(f"  Error on letter {letter}: {e}")
        return []


def scrape_member_profile(member):
    """Fetch individual MPP profile for additional bio details."""
    try:
        resp = requests.get(member["url"], headers=HEADERS, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        # extract years served
        years = re.findall(r"\b(19[5-9]\d|20[012]\d)\b", text)
        if years:
            member["years_active"] = sorted(set(years))

        # extract birth year
        birth = re.search(r"born[^\d]*(\d{4})|(\d{4})[^\d]*–", text, re.IGNORECASE)
        if birth:
            member["year_of_birth"] = birth.group(1) or birth.group(2)

        # extract profession
        prof = re.search(r"(?:Occupation|Profession|Career)\s*:?\s*([^\n]+)", text, re.IGNORECASE)
        if prof:
            member["career"] = prof.group(1).strip()[:100]

    except Exception as e:
        member["profile_error"] = str(e)
    return member


def main():
    all_members = []
    visited = set()

    for letter in LETTERS:
        print(f"Letter {letter.upper()}...", end=" ", flush=True)
        members = get_members_from_index(letter)
        new = [m for m in members if m["url"] not in visited]
        visited.update(m["url"] for m in new)
        all_members.extend(new)
        print(f"{len(new)} members")
        time.sleep(0.3)

    print(f"\nTotal MPPs found: {len(all_members)}")

    # filter to 1985+ by fetching profiles for recent ones
    # party names for post-1985 Ontario parliaments
    recent_parties = [
        "Progressive Conservative", "Ontario Liberal", "New Democratic",
        "Liberal", "NDP", "Independent", "Green"
    ]

    # scrape profiles for members that might be post-1985
    # to get year data — sample first then filter
    print("Saving index data first...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_members, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(all_members)} Ontario MPPs to {OUTPUT_PATH}")
    print("Party breakdown:")
    from collections import Counter
    parties = Counter(m["party"] for m in all_members)
    for p, n in parties.most_common(10):
        print(f"  {p}: {n}")


if __name__ == "__main__":
    main()
