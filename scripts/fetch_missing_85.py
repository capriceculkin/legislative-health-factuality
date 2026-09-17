"""
fetch_missing_85.py

For the 85 bills missing from the clean corpus, fetches their
debate text by:
1. Fetching ALL Orders of the Day for each bill's index dates (no keyword filter)
2. Filtering client-side to only paragraphs that mention the bill number
3. Only keeping paragraphs with explicit bill number mention

This avoids the broken keyword+filter API issue.
Updates hansard_api_bill_segments_clean.json
"""
import json, re, requests, time
from collections import defaultdict

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
API = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
H = {"Content-Type": "application/json", "Origin": "https://www.ola.org",
     "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36"}

with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    idx = json.load(f)
with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments_clean.json") as f:
    clean = json.load(f)

BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)

def clean_html(text):
    return re.sub(r"<[^>]+>", " ", str(text or "")).strip()

health = {k: v for k, v in idx.items() if v.get("health_tag")}
missing = {k: v for k, v in health.items() if k not in clean}
print(f"Missing bills: {len(missing)}")

found = 0
still_missing = []

for bk, bill in sorted(missing.items()):
    bnum = str(bill.get("bill_number", ""))
    title = bill.get("title", "")[:50]
    dates = bill.get("dates", [])

    if not bnum or not dates:
        still_missing.append(bk)
        continue

    print(f"\n{bk}: Bill {bnum} | {title}")

    collected = defaultdict(list)

    for date in dates[:5]:  # Check up to 5 dates per bill
        for tob in ["ORDERS OF THE DAY", "Orders of the Day"]:
            try:
                resp = requests.post(API, headers=H, json={
                    "keyword": "*",
                    "filter": f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z and typeOfBusiness eq '{tob}'",
                    "rows": 500
                }, timeout=30)

                if resp.status_code == 429:
                    print(f"  Rate limited on {date}, waiting 120s...")
                    time.sleep(120)
                    resp = requests.post(API, headers=H, json={
                        "keyword": "*",
                        "filter": f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z and typeOfBusiness eq '{tob}'",
                        "rows": 500
                    }, timeout=30)

                rows = resp.json().get("value", [])

                for r in rows:
                    text = clean_html(r.get("paragraph", ""))
                    # Only keep if bill number explicitly mentioned
                    if f"Bill {bnum}" in text or f"bill {bnum}" in text.lower():
                        collected[date].append({
                            "text": text,
                            "speaker": r.get("speaker", ""),
                            "topic": r.get("topic", ""),
                            "assignment_method": "bill_number_in_text"
                        })

                time.sleep(3)

            except Exception as e:
                print(f"  Error {date} ({tob}): {e}")

        if collected.get(date):
            print(f"  {date}: {len(collected[date])} verified paragraphs")

        time.sleep(2)

    if collected:
        clean[bk] = dict(collected)
        total = sum(len(p) for p in collected.values())
        print(f"  ADDED: {total} paragraphs across {len(collected)} dates")
        found += 1
    else:
        print(f"  NOT FOUND in any date")
        still_missing.append(bk)

print(f"\n=== RESULTS ===")
print(f"Newly found: {found}/{len(missing)}")
print(f"Total coverage: {len(clean)}/{len(health)} ({len(clean)/len(health)*100:.1f}%)")
total = sum(len(p) for d in clean.values() for p in d.values())
print(f"Total verified paragraphs: {total:,}")
print(f"\nStill missing ({len(still_missing)}):")
for bk in still_missing:
    v = idx.get(bk, {})
    print(f"  {bk}: Bill {v.get('bill_number')} | {v.get('title','')[:50]}")

out = f"{REPO}/data/canada/ontario/hansard_api_bill_segments_clean.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False)
print(f"\nSaved to {out}")
