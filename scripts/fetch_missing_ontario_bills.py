"""
fetch_missing_ontario_bills.py

Targeted fetch for the 55 Ontario health bills missing from the API segments.
For each missing bill, tries all its dates with multiple matching strategies.

Strategy:
1. Search by bill number in Orders of the Day on each date
2. Search by bill title keywords in Orders of the Day
3. Search by bill number in ALL content on each date
4. Take any Orders of the Day content on single-bill dates

Updates: data/canada/ontario/hansard_api_bill_segments.json
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
print(f"Missing bills: {len(missing)}")

# All health bill dates for reference
date_to_bills = defaultdict(list)
for bill_key, v in health.items():
    for d in v.get("dates", []):
        date_to_bills[d].append(bill_key)

BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)

def clean_html(text):
    return re.sub(r"<[^>]+>", " ", str(text or "")).strip()

def query(payload, attempt=0):
    try:
        resp = requests.post(API_URL, headers=H, json=payload, timeout=30)
        if resp.status_code == 429:
            wait = 120 * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            return query(payload, attempt + 1) if attempt < 3 else []
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception as e:
        print(f"  Error: {e}")
        return []

def get_orders_of_day(date, extra_filter=""):
    date_f = f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z"
    tob_f = "(typeOfBusiness eq 'ORDERS OF THE DAY' or typeOfBusiness eq 'Orders of the Day')"
    filt = f"({date_f}) and {tob_f}"
    if extra_filter:
        filt += f" and {extra_filter}"
    return query({"keyword": "*", "filter": filt, "rows": 200})

def extract_title_keywords(title):
    words = re.sub(r"[^A-Za-z ]", "", title.upper()).split()
    stop = {"AN", "ACT", "TO", "THE", "OF", "AND", "FOR", "IN", "A", "BY",
            "OR", "AMEND", "PROVIDE", "RESPECTING", "RELATING", "CERTAIN"}
    return [w for w in words if w not in stop and len(w) > 4][:5]

found = 0
for bill_key, bill in sorted(missing.items()):
    bill_num = str(bill.get("bill_number", ""))
    title = bill.get("title", "")
    dates = bill.get("dates", [])
    title_kws = extract_title_keywords(title)

    print(f"\n{bill_key}: Bill {bill_num} | {title[:50]}")
    print(f"  Dates: {dates[:3]}")

    collected_paras = []

    for date in dates:
        other_bills_on_date = [k for k in date_to_bills[date] if k != bill_key]
        is_single_bill = len(other_bills_on_date) == 0

        # Strategy 1: All Orders of the Day on date
        paras = get_orders_of_day(date)
        time.sleep(5)

        if paras:
            # Filter to paragraphs mentioning this bill number or matching title
            matched = []
            all_text = " ".join(clean_html(p.get("paragraph", "")) for p in paras)
            mentioned = set(BILL_RE.findall(all_text))

            if bill_num and bill_num in mentioned:
                # Bill number mentioned — take paras that mention it
                for p in paras:
                    para_text = clean_html(p.get("paragraph", ""))
                    if f"Bill {bill_num}" in para_text or f"bill {bill_num}" in para_text.lower():
                        matched.append(p)
                if not matched:
                    # Bill number in combined text but not individual paras — take by topic
                    topic_upper = ""
                    topics = set(p.get("topic", "") for p in paras)
                    for topic in topics:
                        if topic and any(kw in topic.upper() for kw in title_kws):
                            matched.extend([p for p in paras if p.get("topic") == topic])

            elif is_single_bill:
                # Only one health bill on this date — take all Orders of the Day
                matched = paras

            else:
                # Try topic keyword matching
                topics = set(p.get("topic", "") for p in paras)
                for topic in topics:
                    if topic and any(kw in topic.upper() for kw in title_kws):
                        matched.extend([p for p in paras if p.get("topic") == topic])

            if matched:
                print(f"  {date}: found {len(matched)} paragraphs")
                for p in matched:
                    text = clean_html(p.get("paragraph", ""))
                    speaker = p.get("speaker", "")
                    if text and len(text) > 20:
                        collected_paras.append({"text": text, "speaker": speaker, "date": date})
            else:
                print(f"  {date}: 0 matched (total Orders of Day: {len(paras)})")
        else:
            print(f"  {date}: 0 Orders of the Day results")

    if collected_paras:
        # Group by date
        by_date = defaultdict(list)
        for p in collected_paras:
            by_date[p["date"]].append({"text": p["text"], "speaker": p["speaker"]})
        results[bill_key] = dict(by_date)
        total = sum(len(v) for v in by_date.values())
        print(f"  --> ADDED: {total} paragraphs across {len(by_date)} dates")
        found += 1
    else:
        print(f"  --> NO FLOOR DEBATE FOUND")

print(f"\n\nDone. Found floor debate for {found}/{len(missing)} missing bills.")
print(f"Still missing: {len(missing) - found}")

out_path = os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")
with open(out_path, "w") as f:
    json.dump(results, f, ensure_ascii=False)
print(f"Saved to {out_path}")
