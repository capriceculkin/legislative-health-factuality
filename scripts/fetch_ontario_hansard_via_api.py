"""
fetch_ontario_hansard_via_api.py - REBUILT VERSION

Key changes from previous version:
- Stores topic field with each paragraph
- Uses topic-to-bill matching as primary assignment method
- Bill number mention as secondary verification
- No single-bill fallback (was causing wrong assignments)
- Only assigns paragraphs when topic matches bill title OR bill number in text
- Stores assignment_method for audit trail

Output: data/canada/ontario/hansard_api_bill_segments.json
Format: {bill_key: {date: [{"text": str, "speaker": str, "topic": str, "assignment_method": str}]}}
"""
import json, os, re, time, requests
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

with open(os.path.join(REPO, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)

# Build date -> health bills mapping
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

out_path = os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")
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



STOPWORDS_J = {
    "AN","ACT","TO","THE","OF","AND","FOR","IN","A","BY","OR","AMEND",
    "PROVIDE","RESPECTING","CERTAIN","MAKE","REQUIRE","ENSURE","WITH",
    "RESPECT","RELATED","RELATING","ENACT","GOVERNING","FURTHER","VARIOUS",
    "AMENDING","CONCERNING","AUTHORIZE","REGULATE","THAT","RENDERING",
    "UNDER","MAY","ARE","REGULATING","INSURED","CHARGE","ESTABLISH",
    "IMPOSING","PERSONS","PAYMENT","IMPOSE","PROVIDING","AUTHORIZING",
    "REQUIRING","ENABLING",
}
LEMMA_MAP_J = {
    "AMENDMENT":"AMEND","AMENDMENTS":"AMEND","SERVICES":"SERVICE",
    "NURSES":"NURSE","HOMES":"HOME","WORKERS":"WORKER",
    "PROFESSIONS":"PROFESSION","REGULATIONS":"REGULATION",
    "RIGHTS":"RIGHT","BENEFITS":"BENEFIT","PERSONS":"PERSON",
    "AMOUNTS":"AMOUNT","ACTS":"ACT",
}

def normalize_j(text):
    if not text: return set()
    text = text.upper()
    text = re.sub(r"[^A-Z\s]", " ", text)
    words = text.split()
    words = [LEMMA_MAP_J.get(w, w) for w in words]
    return set(w for w in words if w not in STOPWORDS_J and len(w) > 2)

def get_short_title_j(title):
    return title.split(",")[0].strip()

def jaccard_j(a, b):
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)
BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)


def clean_html(text):
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", str(text)).strip()


STOPWORDS_HASH = {"AN", "ACT", "TO", "THE", "OF", "AND", "FOR", "IN", "A", "BY",
    "OR", "AMEND", "PROVIDE", "RESPECTING", "CERTAIN", "MAKE",
    "REQUIRE", "ENSURE", "WITH", "RESPECT", "RELATED", "RELATING",
    "CERTAIN", "OTHER", "MATTERS", "VARIOUS", "FURTHER", "PROVIDING"}


def build_bill_hash(bills):
    """Build hash table: bill_key -> set of title tokens for similarity matching."""
    bill_hash = {}
    for b in bills:
        title = b.get("title", "") or ""
        short = get_short_title_j(title)
        tokens = set(w for w in re.sub(r"[^A-Za-z ]", "", (title + " " + short).upper()).split()
                     if w not in STOPWORDS_HASH and len(w) > 3)
        bill_hash[b["bill_key"]] = tokens
    return bill_hash


def best_bill_match(topic, text, bills, bill_hash, min_score=0.25):
    """
    Find the best matching bill for a topic+text block using hash table token overlap.
    Returns (bill, score) or (None, 0) if no match above threshold.
    Scores both the topic field and the full text block.
    """
    if not topic and not text:
        return None, 0

    topic_tokens = set(w for w in re.sub(r"[^A-Za-z ]", "", topic.upper()).split()
                       if w not in STOPWORDS_HASH and len(w) > 3)
    text_tokens = set(w for w in re.sub(r"[^A-Za-z ]", "", text.upper()).split()
                      if w not in STOPWORDS_HASH and len(w) > 4)

    best_bill = None
    best_score = 0.0

    for b in bills:
        bill_tokens = bill_hash.get(b["bill_key"], set())
        if not bill_tokens:
            continue

        # Score 1: Jaccard between topic and bill title tokens
        topic_score = jaccard_j(topic_tokens, bill_tokens) if topic_tokens else 0.0

        # Score 2: token overlap between bill title tokens and full text block
        if text_tokens and bill_tokens:
            overlap = len(bill_tokens & text_tokens) / len(bill_tokens)
        else:
            overlap = 0.0

        # Combined score: topic match weighted higher since it's curated
        score = (topic_score * 0.7) + (overlap * 0.3)

        if score > best_score:
            best_score = score
            best_bill = b

    if best_score >= min_score:
        return best_bill, best_score
    return None, 0


def fetch_batch(dates, attempt=0):
    """Fetch ORDERS OF THE DAY paragraphs for a batch of dates (both capitalizations)."""
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
    """
    Assign paragraphs to bills using topic matching and bill number mention.
    NO single-bill fallback — only assign when we have positive evidence.
    Stores topic and assignment_method for audit trail.
    """
    # Group paragraphs by date and topic
    date_topic_paras = defaultdict(lambda: defaultdict(list))
    for para in paragraphs:
        date = para.get("date", "")[:10]
        topic = para.get("topic", "") or ""
        text = clean_html(para.get("paragraph", ""))
        speaker = para.get("speaker", "")
        session = para.get("session", "")
        url = para.get("url", "")
        para_url = para.get("paraUrl", "")
        if text and len(text) > 20:
            date_topic_paras[date][topic].append({
                "text": text,
                "speaker": speaker,
                "topic": topic,
                "session": session,
                "url": url,
                "para_url": para_url,
            })

    for date in dates:
        bills_on_date = date_to_bills[date]
        topic_paras = date_topic_paras.get(date, {})

        # Build hash table for bills on this date
        bill_hash = build_bill_hash(bills_on_date)

        for topic, paras in topic_paras.items():
            all_text = " ".join(p["text"] for p in paras)
            mentioned_bills = set(BILL_RE.findall(all_text))

            assignment_method = None
            matched_bill = None

            # Method 1: Bill number explicitly mentioned in this topic's text
            # This is the most reliable signal — check all bills on this date
            for b in bills_on_date:
                bill_num = b["bill_number"]
                if bill_num and bill_num in mentioned_bills:
                    matched_bill = b
                    assignment_method = "bill_number_in_text"
                    break

            # Method 2: Best hash table similarity match across title + text
            if not assignment_method:
                matched_bill, score = best_bill_match(topic, all_text, bills_on_date, bill_hash)
                if matched_bill:
                    assignment_method = f"hash_similarity:{score:.2f}"

            if assignment_method and matched_bill:
                bill_key = matched_bill["bill_key"]
                if bill_key not in results:
                    results[bill_key] = {}
                if date not in results[bill_key]:
                    results[bill_key][date] = []
                for p in paras:
                    results[bill_key][date].append({
                        "text": p["text"],
                        "speaker": p["speaker"],
                        "topic": topic,
                        "session": p.get("session",""),
                        "url": p.get("url",""),
                        "para_url": p.get("para_url",""),
                        "assignment_method": assignment_method
                    })


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
