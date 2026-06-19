import requests
from bs4 import BeautifulSoup
import os
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INDEX_URL = "https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/43-3/journal-debats/index.html"
OUTPUT_DIR = "data/canada/quebec"
BASE = "https://www.assnat.qc.ca"

def get_all_links():
    resp = requests.get(INDEX_URL, timeout=15, verify=False)
    soup = BeautifulSoup(resp.text, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "journal-debats" in href and href.endswith(".html"):
            full_url = href if href.startswith("http") else BASE + href
            links.append(full_url)
    return list(set(links))

def fetch_transcript(url):
    resp = requests.get(url, timeout=15, verify=False)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "lxml")
        text = soup.get_text(separator="\n", strip=True)
        filename = url.split("/")[-1].replace(".html", ".txt")
        out_path = os.path.join(OUTPUT_DIR, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Saved {filename}")

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    links = get_all_links()
    print(f"Found {len(links)} transcript links")
    for link in links:
        fetch_transcript(link)
        time.sleep(1)