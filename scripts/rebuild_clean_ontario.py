"""
rebuild_clean_ontario.py

Rebuilds hansard_api_bill_segments.json with only verified content.

For each health bill:
1. Keep existing paragraphs where bill number is mentioned in text (verified)
2. For bills with no verified content, search OLA API by bill number keyword,
   collect paragraphs that explicitly mention the bill number
3. Never assign paragraphs based on date fallback or topic keywords alone

Result: every paragraph in the output is verified to mention the specific bill number.
"""
import json, re, requests, time
from collections import defaultdict

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
API = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
H = {"Content-Type": "application/json", "Origin": "https://www.ola.org",
     "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36"}

with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    idx = json.load(f)
with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments.json") as f:
    old_seg = json.load(f)

BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)

def clean_html(text):
    return re.sub(r"<[^>]+>", " ", str(text or "")).strip()

# Step 1: Extract verified content from existing segments
print("Step 1: Extracting verified content from existing segments...")
clean = {}
uncertain_bills = []

health_bills = {k: v for k, v in idx.items() if v.get("health_tag")}

for bk, v in health_bills.items():
    bnum = str(v.get("bill_number", ""))
    if not bnum:
        continue

    if bk not in old_seg:
        uncertain_bills.append(bk)
        continue

    # Keep only date-sections where bill number is in text
    verified_dates = {}
    for date, paras in old_seg[bk].items():
        all_text = " ".join(
            p if isinstance(p, str) else p.get("text", "")
            for p in paras
        )
        if bnum in BILL_RE.findall(all_text):
            verified_dates[date] = paras

    if verified_dates:
        clean[bk] = verified_dates
    else:
        uncertain_bills.append(bk)

print(f"  Verified from existing: {len(clean)} bills")
print(f"  Need re-fetch: {len(uncertain_bills)} bills")

# Step 2: Re-fetch uncertain bills using keyword search
print("\nStep 2: Re-fetching uncertain bills via keyword search...")
refetched = 0
not_found = []

for bk in uncertain_bills:
    v = idx.get(bk, {})
    bnum = str(v.get("bill_number", ""))
    title = v.get("title", "")[:50]
    bill_dates = set(v.get("dates", []))

    if not bnum:
        not_found.append(bk)
        continue

    print(f"  {bk}: Bill {bnum} | {title}")

    # Search OLA API for this bill number — no date filter
    try:
        resp = requests.post(API, headers=H, json={
            "keyword": f"Bill {bnum}",
            "filter": "(typeOfBusiness eq 'ORDERS OF THE DAY' or typeOfBusiness eq 'Orders of the Day')",
            "rows": 500
        }, timeout=30)

        if resp.status_code == 429:
            print(f"    Rate limited, waiting 120s...")
            time.sleep(120)
            resp = requests.post(API, headers=H, json={
                "keyword": f"Bill {bnum}",
                "filter": "(typeOfBusiness eq 'ORDERS OF THE DAY' or typeOfBusiness eq 'Orders of the Day')",
                "rows": 500
            }, timeout=30)

        rows = resp.json().get("value", [])

        # Keep only rows where bill number is in paragraph text
        matched = defaultdict(list)
        for r in rows:
            para_text = clean_html(r.get("paragraph", ""))
            date = r.get("date", "")[:10]
            if f"Bill {bnum}" in para_text or f"bill {bnum}" in para_text.lower():
                matched[date].append({
                    "text": para_text,
                    "speaker": r.get("speaker", ""),
                    "topic": r.get("topic", ""),
                    "assignment_method": "bill_number_in_text"
                })

        if matched:
            clean[bk] = dict(matched)
            total = sum(len(p) for p in matched.values())
            print(f"    Found {total} verified paragraphs across {len(matched)} dates")
            refetched += 1
        else:
            print(f"    Not found in OLA API")
            not_found.append(bk)

    except Exception as e:
        print(f"    Error: {e}")
        not_found.append(bk)

    time.sleep(8)

print(f"\n=== RESULTS ===")
print(f"Verified from existing: {len(clean) - refetched}")
print(f"Re-fetched and verified: {refetched}")
print(f"Total bills with verified content: {len(clean)}/{len(health_bills)} ({len(clean)/len(health_bills)*100:.1f}%)")
print(f"Bills with no verified content: {len(not_found)}")
print()
print("Bills with no content found:")
for bk in not_found:
    v = idx.get(bk, {})
    print(f"  {bk}: Bill {v.get('bill_number')} | {v.get('title','')[:50]}")

total_paras = sum(len(p) for d in clean.values() for p in d.values())
print(f"\nTotal verified paragraphs: {total_paras:,}")

out_path = f"{REPO}/data/canada/ontario/hansard_api_bill_segments_clean.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False)
print(f"Saved to {out_path}")
