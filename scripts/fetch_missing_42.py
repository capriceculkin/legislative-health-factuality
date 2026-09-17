"""
fetch_missing_42.py

All 42 missing Ontario bills had second reading floor debate confirmed
by myparliament.ca. This script fetches their debate text using
aggressive multi-strategy matching.
"""
import json, os, re, time, requests
from collections import defaultdict

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
API_URL = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
H = {
    "Content-Type": "application/json",
    "Origin": "https://www.ola.org",
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36"
}

with open(os.path.join(REPO, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)
with open(os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")) as f:
    results = json.load(f)

health = {k: v for k, v in idx.items() if v.get("health_tag")}
missing = {k: v for k, v in health.items() if k not in results}
print(f"Missing bills to fetch: {len(missing)}")

# All health bills date lookup
date_to_bills = defaultdict(list)
for bill_key, v in health.items():
    for d in v.get("dates", []):
        date_to_bills[d].append(bill_key)

BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)

def clean_html(text):
    return re.sub(r"<[^>]+>", " ", str(text or "")).strip()

def query_api(payload, attempt=0):
    try:
        resp = requests.post(API_URL, headers=H, json=payload, timeout=30)
        if resp.status_code == 429:
            wait = 120 * (attempt + 1)
            print(f"  Rate limited {wait}s...")
            time.sleep(wait)
            return query_api(payload, attempt+1) if attempt < 4 else []
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception as e:
        print(f"  Error: {e}")
        return []

def get_orders(date, tob="ORDERS OF THE DAY"):
    filt = f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z and typeOfBusiness eq '{tob}'"
    return query_api({"keyword": "*", "filter": filt, "rows": 500})

def search_bill_keyword(bill_num, date):
    """Search specifically for 'Bill X' in Orders of the Day on a date."""
    filt = (f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z "
            f"and (typeOfBusiness eq 'ORDERS OF THE DAY' or typeOfBusiness eq 'Orders of the Day')")
    return query_api({"keyword": f"Bill {bill_num}", "filter": filt, "rows": 200})

def extract_kws(title):
    words = re.sub(r"[^A-Za-z ]", "", title.upper()).split()
    stop = {"AN","ACT","TO","THE","OF","AND","FOR","IN","A","BY","OR",
            "AMEND","PROVIDE","RESPECTING","CERTAIN","MAKE","REQUIRE","ENSURE"}
    return [w for w in words if w not in stop and len(w) > 4][:6]

found_total = 0

for bill_key, bill in sorted(missing.items()):
    bill_num = str(bill.get("bill_number",""))
    title = bill.get("title","")
    dates = bill.get("dates",[])
    kws = extract_kws(title)

    print(f"\n{bill_key}: Bill {bill_num} | {title[:50]}")

    collected = defaultdict(list)

    for date in dates:
        other_bills = [k for k in date_to_bills[date] if k != bill_key]
        is_single = len(other_bills) == 0

        # Strategy 1: keyword search for "Bill X" in Orders of the Day
        paras = search_bill_keyword(bill_num, date)
        time.sleep(3)

        if paras:
            # Filter to paras actually about this bill
            matched = []
            for p in paras:
                text = clean_html(p.get("paragraph",""))
                topic = str(p.get("topic",""))
                # Direct bill number mention
                if f"Bill {bill_num}" in text or f"bill {bill_num}" in text.lower():
                    matched.append(p)
                # Topic keyword match
                elif kws and any(kw in topic.upper() for kw in kws):
                    matched.append(p)
            if matched:
                print(f"  {date}: {len(matched)} paras via bill keyword search")
                for p in matched:
                    t = clean_html(p.get("paragraph",""))
                    s = p.get("speaker","")
                    if t and len(t) > 20:
                        collected[date].append({"text": t, "speaker": s})
                continue

        # Strategy 2: All Orders of the Day, topic keyword match or single-bill fallback
        for tob in ["ORDERS OF THE DAY", "Orders of the Day"]:
            all_paras = get_orders(date, tob)
            time.sleep(3)
            if not all_paras:
                continue

            matched = []
            topics_present = set(p.get("topic","") for p in all_paras)

            # Match by topic keywords
            for topic in topics_present:
                if topic and kws and any(kw in str(topic).upper() for kw in kws):
                    matched.extend([p for p in all_paras if p.get("topic") == topic])

            # Single-bill date: take all
            if not matched and is_single:
                matched = all_paras

            if matched:
                print(f"  {date} ({tob}): {len(matched)} paras via topic/fallback")
                for p in matched:
                    t = clean_html(p.get("paragraph",""))
                    s = p.get("speaker","")
                    if t and len(t) > 20:
                        collected[date].append({"text": t, "speaker": s})
                break

        if not collected.get(date):
            print(f"  {date}: 0 matched")

    if collected:
        results[bill_key] = dict(collected)
        total = sum(len(v) for v in collected.values())
        print(f"  --> ADDED: {total} paras across {len(collected)} dates")
        found_total += 1
    else:
        print(f"  --> STILL NOT FOUND")

print(f"\nFound: {found_total}/{len(missing)} bills")

out = os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")
with open(out, "w") as f:
    json.dump(results, f, ensure_ascii=False)
print(f"Saved to {out}")
