"""
fetch_quebec_vote_outcomes.py

Fetches vote outcomes for Quebec health bills from each bill's own
Cheminement page on assnat.qc.ca. The page renders via JavaScript and
shows structured stage-by-stage vote tallies including:
  "Adoption (Vote: For 63, Against 27, Abstentions 0)"

This works for ALL sessions from 1985 onward since every bill has its
own page at the URL stored in quebec_health_bills.json under bill_url.

Output: data/canada/quebec_bills/"quebec_health_bills_combined.json"
Usage: python3 scripts/fetch_quebec_vote_outcomes.py
"""

import os
import re
import json
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_BILLS_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                                  "quebec_health_bills_combined.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "canada", "quebec_bills",
                           "quebec_vote_outcomes_combined.json")

# Patterns matching FRENCH rendered page text (assnat.qc.ca is in French)
# "Adoption du principe\nSéance du 24 octobre 2025 (Vote : Pour 60, Contre 27, Abstention 0)"
ADOPTION_VOTE_PATTERN = re.compile(
    r"(?:Adoption)(?:\s+(?:du principe|finale))?\s*\n[^\n]{0,300}?"
    r"[Vv]ote\s*[:\s]+Pour\s+(\d+)[,\s]+Contre\s+(\d+)[,\s]+Abstention\s+(\d+)",
    re.DOTALL
)

# Fallback: any vote line - take the last one (most likely adoption)
VOTE_LINE_PATTERN = re.compile(
    r"[Vv]ote\s*[:\s]+Pour\s+(\d+)[,\s]+Contre\s+(\d+)[,\s]+Abstention\s+(\d+)"
)

# Sanction = passed in French
ASSENT_PATTERN = re.compile(
    r"Date de la sanction\s*[:\xa0]+\s*(\d+ \w+ \d{4})"
    r"|Date of assent\s*[:\xa0]+\s*([A-Z][a-z]+ \d+, \d{4})",
    re.IGNORECASE
)
def parse_vote_outcome(page_text, bill_url):
    """Extract adoption vote tally and outcome from rendered page text."""
    result = {
        "bill_url": bill_url,
        "outcome": None,
        "vote_for": None,
        "vote_against": None,
        "vote_abstention": None,
        "assent_date": None,
        "raw_match": None,
    }

    # check for date of assent (most reliable passed indicator)
    assent = ASSENT_PATTERN.search(page_text)
    if assent:
        result["assent_date"] = (assent.group(1) or assent.group(2) or "").strip()
        result["outcome"] = "passed"

    # look for the adoption vote tally
    # the rendered text for the stage reads like:
    # "Adoption\nMeeting of October 24, 2025 (This step was taken on October 25,
    #  2025 (Vote: For 63, Against 27, Abstentions 0))"
    adoption_match = ADOPTION_VOTE_PATTERN.search(page_text)
    if adoption_match:
        result["vote_for"] = int(adoption_match.group(1))
        result["vote_against"] = int(adoption_match.group(2))
        result["vote_abstention"] = int(adoption_match.group(3))
        result["raw_match"] = adoption_match.group(0)[:200]
        if result["outcome"] is None:
            result["outcome"] = "passed" if result["vote_for"] > result["vote_against"] else "failed"
    else:
        # fallback: find any vote line and take the last one (most likely adoption)
        all_votes = VOTE_LINE_PATTERN.findall(page_text)
        if all_votes:
            last = all_votes[-1]
            result["vote_for"] = int(last[0])
            result["vote_against"] = int(last[1])
            result["vote_abstention"] = int(last[2])
            if result["outcome"] is None:
                result["outcome"] = "passed" if result["vote_for"] > result["vote_against"] else "failed"
            # if no vote found and no assent, bill likely died in session
            if result["outcome"] is None:
                result["outcome"] = "died_in_session"

    return result


def main():
    with open(HEALTH_BILLS_PATH, encoding="utf-8") as f:
        health_bills = json.load(f)

    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"Resuming: {len(existing)} bills already fetched")

    todo = [b for b in health_bills if b.get("bill_url") and b["bill_url"] not in existing]
    print(f"Health bills to fetch: {len(todo)} of {len(health_bills)}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()

        for i, bill in enumerate(todo):
            url = bill["bill_url"]
            title = bill.get("title", "")[:60]

            try:
                page.goto(url, timeout=30000, wait_until="networkidle")
                try:
                    page.wait_for_selector(
                        ":text('Date de la sanction'), :text('Date of assent')",
                        timeout=10000
                    )
                except:
                    pass
                page.wait_for_timeout(1000)
                text = page.inner_text("body")
                
                text = page.inner_text("body")
                if "sanction" not in text.lower() or "Date de la sanction" not in text:
                 # fallback to full page content
                    text = page.content()  # gets raw HTML

                result = parse_vote_outcome(text, url)
                result["title"] = bill.get("title", "")
                result["session"] = bill.get("session", "")
                existing[url] = result

                status = f"{result['outcome']} (For {result['vote_for']}, Against {result['vote_against']})" \
                         if result["vote_for"] is not None else result["outcome"] or "no vote found"
                print(f"  [{i+1}/{len(todo)}] {title[:50]}: {status}")

            except Exception as e:
                print(f"  [{i+1}/{len(todo)}] ERROR: {url}: {e}")
                existing[url] = {"bill_url": url, "error": str(e), "outcome": None}

            if (i + 1) % 20 == 0:
                with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)

            time.sleep(1.5)

        browser.close()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    passed = sum(1 for v in existing.values() if v.get("outcome") == "passed")
    failed = sum(1 for v in existing.values() if v.get("outcome") == "failed")
    no_vote = sum(1 for v in existing.values() if not v.get("outcome"))

    print(f"\n{'='*60}")
    print(f"Total bills processed:     {len(existing)}")
    print(f"  Passed:                  {passed}")
    print(f"  Failed:                  {failed}")
    print(f"  No vote found:           {no_vote}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()