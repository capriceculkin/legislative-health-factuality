"""
repull_speeches_html.py

Re-pulls all US Congressional Record speech files using the GovInfo HTML
endpoint instead of PDF. This permanently solves the 3-column PDF extraction
problem since the HTML version is already in correct reading order.

URL pattern:
  https://api.govinfo.gov/packages/{packageId}/granules/{granuleId}/htm

For multi-granule dates (like 2006-12-09 with 3 granules), combines all
granule texts into one file in order.

Resume-safe: skips dates where the file already exists AND is large enough
to be real content (>10,000 chars). Use --force to re-pull everything.

Usage:
  python3 scripts/repull_speeches_html.py          # skip already-good files
  python3 scripts/repull_speeches_html.py --force  # re-pull everything
  python3 scripts/repull_speeches_html.py --test 2006-12-09  # one date
"""

import os
import sys
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOVINFO_KEY")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEECH_DIR = os.path.join(REPO_ROOT, "data", "us", "congressional_record_speeches")
GRANULE_INDEX_PATH = os.path.join(REPO_ROOT, "data", "us", "congressional_record_granule_index.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality project)"}
BASE = "https://api.govinfo.gov"


def fetch_granule_html(package_id, granule_id):
    url = f"{BASE}/packages/{package_id}/granules/{granule_id}/htm"
    resp = requests.get(url, params={"api_key": KEY}, headers=HEADERS, timeout=30)
    if resp.status_code == 400:
        # older GPO-CRECB packages don't have HTM, fall back to PDF
        return fetch_granule_pdf_as_text(package_id, granule_id)
    resp.raise_for_status()
    return resp.text


def fetch_granule_pdf_as_text(package_id, granule_id):
    """Fallback for older packages that only have PDF. Uses pdfplumber with
    explicit column-boundary detection based on page width."""
    import io
    import pdfplumber
    from collections import Counter

    url = f"{BASE}/packages/{package_id}/granules/{granule_id}/pdf"
    resp = requests.get(url, params={"api_key": KEY}, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    pages = []
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        page_width = pdf.pages[0].width if pdf.pages else 612
        col_boundaries = [page_width / 3, 2 * page_width / 3]

        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["size"])
            if not words:
                continue
            sizes = Counter(round(w["size"], 1) for w in words)
            body_size = sizes.most_common(1)[0][0]
            body_words = [w for w in words if abs(w["size"] - body_size) < 0.5]

            cols = [[], [], []]
            for w in body_words:
                if w["x0"] < col_boundaries[0]:
                    cols[0].append(w)
                elif w["x0"] < col_boundaries[1]:
                    cols[1].append(w)
                else:
                    cols[2].append(w)

            page_text = []
            for col in cols:
                col = sorted(col, key=lambda w: (round(w["top"]), w["x0"]))
                lines, cy, cl = [], None, []
                for w in col:
                    y = round(w["top"])
                    if cy is not None and abs(y - cy) > 3:
                        lines.append(" ".join(cl)); cl = []
                    cy = y; cl.append(w["text"])
                if cl: lines.append(" ".join(cl))
                page_text.extend(lines)

            pages.append("\n".join(page_text))

    return "\n\n".join(pages)


def html_to_text(html):
    # if it's already plain text (PDF fallback), return as-is
    if not html.strip().startswith("<"):
        return html.strip()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def pull_date(date, entry, force=False):
    out_path = os.path.join(SPEECH_DIR, f"{date}.txt")

    if not force and os.path.exists(out_path):
        size = os.path.getsize(out_path)
        if size > 10000:
            return "skipped", size

    package_id = entry.get("packageId")
    granule_id = entry.get("granuleId")

    if not package_id or not granule_id:
        return "no_granule", 0

    granule_ids = granule_id if isinstance(granule_id, list) else [granule_id]

    parts = []
    for gid in granule_ids:
        try:
            html = fetch_granule_html(package_id, gid)
            text = html_to_text(html)
            parts.append(f"--- {gid} ---\n{text}")
            time.sleep(0.3)
        except Exception as e:
            parts.append(f"--- {gid} ERROR: {e} ---")

    combined = "\n\n".join(parts)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(combined)

    return "ok", len(combined)


def main():
    force = "--force" in sys.argv
    test_date = None
    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        if idx + 1 < len(sys.argv):
            test_date = sys.argv[idx + 1]

    with open(GRANULE_INDEX_PATH, encoding="utf-8") as f:
        index = json.load(f)

    if test_date:
        if test_date not in index:
            print(f"{test_date} not in granule index")
            return
        status, size = pull_date(test_date, index[test_date], force=True)
        print(f"{test_date}: {status}, {size:,} chars")
        out = os.path.join(SPEECH_DIR, f"{test_date}.txt")
        with open(out, encoding="utf-8") as f:
            print("\nFirst 800 chars:")
            print(f.read(800))
        return

    dates = sorted(index.keys())
    print(f"Total dates in granule index: {len(dates)}")
    print(f"Force re-pull: {force}\n")

    ok = skipped = errors = 0
    for date in dates:
        status, size = pull_date(date, index[date], force=force)
        if status == "ok":
            print(f"  {date}: {size:,} chars")
            ok += 1
        elif status == "skipped":
            skipped += 1
        else:
            print(f"  {date}: {status}")
            errors += 1
        time.sleep(0.5)

    print(f"\nDone: {ok} pulled, {skipped} skipped (already good), {errors} errors")


if __name__ == "__main__":
    main()
