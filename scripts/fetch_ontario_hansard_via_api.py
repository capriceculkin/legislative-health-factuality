"""
fetch_ontario_hansard_via_api.py

Fetches bill-specific Ontario Hansard text using the OLA Azure Search API.
Batches 3 dates per request. Tries both ORDERS OF THE DAY capitalizations.
Stores speaker with each paragraph for party attribution.

Output: data/canada/ontario/hansard_api_bill_segments.json
"""
import json, os, re, time, requests
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_URL = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.ola.org",
    "Referer": "https://www.ola.org/",
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36"
}

BATCH_SIZE = 3
SLEEP_BETWEEN = 30
SLEEP_ON_429 = 180

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)

date_to_bills = defaultdict(list)
for bill_key, v in idx.items():
    if v.get("health_tag"):
        for d in v.get("dates", []):
            date_to_bills[d].append({
                "bill_key": bill_key,
                "bill_number": str(v.get("bill_number", "")),
                "title": v.get("title", "")
            })

health_dates = sorted(date_to_bills.keys())
print(f"Health bill dates: {len(health_dates)}")

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/hansard_api_bill_segments.json")
if os.path.exists(out_path):
    with open(out_path) as f:
        results = json.load(f)
    print(f"Resuming: {len(results)} bill_keys already done")
else:
    results = {}

done_dates = set()
for bill_key, date_data in results.items():
    for date in date_data:
        done_dates.add(date)

remaining = [d for d in health_dates if d not in done_dates]
print(f"Remaining dates: {len(remaining)}")

BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)


def clean_html(text):
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", str(text)).strip()


def fetch_batch(dates, attempt=0):
    """Fetch Orders of the Day paragraphs for a batch of dates.
    Tries both capitalizations: ORDERS OF THE DAY and Orders of the Day."""
    date_filters = " or ".join(
        f"(date ge {d}T00:00:00Z and date le {d}T23:59:59Z)"
        for d in dates
    )
    combined = []
    for tob in ["ORDERS OF THE DAY", "Orders of the Day"]:
        payload = {
            "keyword": "*",
            "filter": f"({date_filters}) and typeOfBusiness eq '{tob}'",
            "rows": 500
        }
        try:
            resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
            if resp.status_code == 429:
                wait = SLEEP_ON_429 * (attempt + 1)
                print(f"  429 rate limit, waiting {wait}s...")
                time.sleep(wait)
                if attempt < 3:
                    return fetch_batch(dates, attempt + 1)
                return []
            resp.raise_for_status()
            combined.extend(resp.json().get("value", []))
        except Exception as e:
            print(f"  Error ({tob}): {e}")
    return combined


def process_batch(dates, paragraphs):
    date_topic_paras = defaultdict(lambda: defaultdict(list))
    for para in paragraphs:
        date = para.get("date", "")[:10]
        topic = para.get("topic", "")
        text = clean_html(para.get("paragraph", ""))
        speaker = para.get("speaker", "")
        if text and len(text) > 20:
            date_topic_paras[date][topic].append({
                "text": text,
                "speaker": speaker,
                "date": date
            })

    for date in dates:
        bills_on_date = date_to_bills[date]
        bill_nums_on_date = {b["bill_number"] for b in bills_on_date if b["bill_number"]}
        topic_paras = date_topic_paras.get(date, {})

        for topic, paras in topic_paras.items():
            all_text = " ".join(p["text"] for p in paras)
            mentioned_bills = set(BILL_RE.findall(all_text))

            matched_bill = None
            for bill_num in mentioned_bills:
                if bill_num in bill_nums_on_date:
                    for b in bills_on_date:
                        if b["bill_number"] == bill_num:
                            matched_bill = b["bill_key"]
                            break
                if matched_bill:
                    break

            # Single bill on date
            if not matched_bill and len(bills_on_date) == 1:
                matched_bill = bills_on_date[0]["bill_key"]

            # Omnibus health professions topic
            if not matched_bill and topic:
                topic_upper = topic.upper()
                if any(kw in topic_upper for kw in ["HEALTH PROFESSIONS", "REGULATED HEALTH", "PROFESSION"]):
                    for b in bills_on_date:
                        if "profession" in b["title"].lower():
                            if b["bill_key"] not in results:
                                results[b["bill_key"]] = {}
                            if date not in results[b["bill_key"]]:
                                results[b["bill_key"]][date] = []
                            results[b["bill_key"]][date].extend(
                                [{"text": p["text"], "speaker": p.get("speaker", "")} for p in paras]
                            )

            # Topic keyword matching
            if not matched_bill and topic:
                topic_upper = topic.upper()
                for b in bills_on_date:
                    title_words = set(b["title"].upper().split()[:6]) - {
                        "AN", "ACT", "TO", "THE", "OF", "AND", "FOR", "IN", "A"
                    }
                    if any(w in topic_upper for w in title_words if len(w) > 4):
                        matched_bill = b["bill_key"]
                        break

            if matched_bill:
                if matched_bill not in results:
                    results[matched_bill] = {}
                if date not in results[matched_bill]:
                    results[matched_bill][date] = []
                results[matched_bill][date].extend(
                    [{"text": p["text"], "speaker": p.get("speaker", "")} for p in paras]
                )


total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE
processed = 0

for i in range(0, len(remaining), BATCH_SIZE):
    batch = remaining[i:i + BATCH_SIZE]
    paragraphs = fetch_batch(batch)

    if paragraphs:
        process_batch(batch, paragraphs)

    processed += 1

    if processed % 10 == 0:
        total_paras = sum(
            len(paras)
            for date_data in results.values()
            for paras in date_data.values()
        )
        print(f"  Batch {processed}/{total_batches} | Bills: {len(results)} | Paragraphs: {total_paras:,}")
        with open(out_path, "w") as f:
            json.dump(results, f, ensure_ascii=False)

    time.sleep(SLEEP_BETWEEN)

print(f"\nDone. Bills mapped: {len(results)}")
total_paras = sum(
    len(paras)
    for date_data in results.values()
    for paras in date_data.values()
)
print(f"Total paragraphs: {total_paras:,}")

with open(out_path, "w") as f:
    json.dump(results, f, ensure_ascii=False)
print(f"Saved to {out_path}")
