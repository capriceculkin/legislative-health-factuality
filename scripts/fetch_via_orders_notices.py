"""
fetch_via_orders_notices.py

For each missing bill, searches Orders and Notices papers to find
the actual floor debate dates, then fetches Hansard text via OLA API.

Orders and Notices are accessible at:
https://www.ola.org/en/legislative-business/house-documents/parliament-XX/session-X/YYYY-MM-DD/orders-notices
"""
import json, os, re, time, requests
from collections import defaultdict
from datetime import datetime, timedelta

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

with open(os.path.join(REPO, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)
with open(os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")) as f:
    results = json.load(f)

health = {k: v for k, v in idx.items() if v.get("health_tag")}
missing = {k: v for k, v in health.items() if k not in results}
print(f"Missing: {len(missing)}")

API_URL = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
H_API = {
    "Content-Type": "application/json",
    "Origin": "https://www.ola.org",
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36"
}
H_WEB = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Parliament session date ranges
PARL_SESSIONS = [
    ("33", "1", "1985-05-02", "1987-09-08"),
    ("34", "1", "1987-10-01", "1990-08-30"),
    ("35", "1", "1990-11-20", "1995-02-09"),
    ("36", "1", "1995-09-26", "1999-02-18"),
    ("36", "2", "1999-03-30", "1999-10-18"),
    ("37", "1", "1999-10-25", "2003-09-18"),
    ("37", "2", "2003-11-19", "2007-08-27"),
    ("38", "1", "2003-12-09", "2005-09-28"),
    ("38", "2", "2005-10-12", "2007-10-01"),
    ("39", "1", "2007-10-17", "2008-03-05"),
    ("39", "2", "2008-04-17", "2011-10-06"),
    ("40", "1", "2011-11-30", "2012-10-15"),
    ("40", "2", "2013-02-19", "2014-05-02"),
    ("41", "1", "2014-07-02", "2016-03-10"),
    ("41", "2", "2016-04-19", "2018-05-09"),
    ("42", "1", "2018-07-11", "2022-05-04"),
    ("43", "1", "2022-08-08", "2025-01-28"),
    ("44", "1", "2025-04-14", "2026-12-31"),
]

def get_parl_session(date_str):
    for parl, sess, start, end in PARL_SESSIONS:
        if start <= date_str <= end:
            return parl, sess
    return None, None

def fetch_orders_notices(parl, sess, date_str):
    url = f"https://ola.org/en/legislative-business/house-documents/parliament-{parl}/session-{sess}/{date_str}/orders-notices"
    try:
        resp = requests.get(url, headers=H_WEB, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 1000:
            return resp.text
    except:
        pass
    return ""

def bill_in_orders(html, bill_num):
    """Check if Bill X appears in Orders of the Day section of orders-notices HTML."""
    # Find Orders of the Day section
    ood_match = re.search(r"ORDERS OF THE DAY|ORDER DU JOUR", html, re.IGNORECASE)
    if not ood_match:
        return False
    ood_text = html[ood_match.start():]
    # Check for Bill number
    return bool(re.search(rf"\bBill\s+{bill_num}\b", ood_text, re.IGNORECASE))

def get_all_sitting_dates(parl, sess, start, end):
    """Generate weekday dates in a parliament session range."""
    dates = []
    current = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while current <= end_dt:
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates

def fetch_api_orders(date, bill_num):
    """Fetch Orders of the Day paragraphs for a specific date."""
    paras = []
    for tob in ["ORDERS OF THE DAY", "Orders of the Day"]:
        filt = f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z and typeOfBusiness eq '{tob}'"
        try:
            resp = requests.post(API_URL, headers=H_API,
                                 json={"keyword": "*", "filter": filt, "rows": 500}, timeout=30)
            if resp.status_code == 429:
                time.sleep(180)
                resp = requests.post(API_URL, headers=H_API,
                                     json={"keyword": "*", "filter": filt, "rows": 500}, timeout=30)
            if resp.ok:
                paras.extend(resp.json().get("value", []))
        except:
            pass
        time.sleep(3)
    return paras

def clean_html(text):
    return re.sub(r"<[^>]+>", " ", str(text or "")).strip()

found_total = 0

for bill_key, bill in sorted(missing.items()):
    bill_num = str(bill.get("bill_number", ""))
    title = bill.get("title", "")
    dates = bill.get("dates", [])
    print(f"\n{bill_key}: Bill {bill_num} | {title[:50]}")

    # Find the parliament/session from the bill's dates
    parl, sess = None, None
    for d in dates:
        p, s = get_parl_session(d)
        if p:
            parl, sess = p, s
            break

    if not parl:
        # Try year of bill key
        year = bill_key[:4]
        for p, s, start, end in PARL_SESSIONS:
            if start[:4] <= year <= end[:4]:
                parl, sess = p, s
                break

    if not parl:
        print(f"  Could not determine parliament/session")
        continue

    print(f"  Parliament {parl}, Session {sess}")

    # Strategy: scan Orders and Notices for the session to find actual debate dates
    # Use the bill's known dates as starting points, then check nearby dates
    debate_dates = []

    for known_date in dates[:3]:
        # Check known date and ±30 days
        known_dt = datetime.strptime(known_date, "%Y-%m-%d")
        for delta in range(-60, 61):
            check_dt = known_dt + timedelta(days=delta)
            if check_dt.weekday() >= 5:
                continue
            check_date = check_dt.strftime("%Y-%m-%d")
            html = fetch_orders_notices(parl, sess, check_date)
            time.sleep(0.5)
            if html and bill_in_orders(html, bill_num):
                debate_dates.append(check_date)
                print(f"  Found in Orders and Notices: {check_date}")

    debate_dates = sorted(set(debate_dates))

    if not debate_dates:
        print(f"  No Orders and Notices found for Bill {bill_num}")
        continue

    # Now fetch Hansard text for those debate dates
    collected = defaultdict(list)
    for date in debate_dates:
        paras = fetch_api_orders(date, bill_num)
        if paras:
            # Filter to paragraphs mentioning this bill
            matched = []
            for p in paras:
                text = clean_html(p.get("paragraph", ""))
                if f"Bill {bill_num}" in text or f"bill {bill_num}" in text.lower():
                    matched.append(p)
            if not matched:
                matched = paras  # Take all if single bill day
            for p in matched:
                t = clean_html(p.get("paragraph", ""))
                s = p.get("speaker", "")
                if t and len(t) > 20:
                    collected[date].append({"text": t, "speaker": s})
            print(f"  {date}: {len(collected.get(date,[]))} paragraphs")

    if collected:
        results[bill_key] = dict(collected)
        total = sum(len(v) for v in collected.values())
        print(f"  --> ADDED: {total} paras across {len(collected)} dates")
        found_total += 1
    else:
        print(f"  --> Could not retrieve text")

    # Save incrementally
    out = os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")
    with open(out, "w") as f:
        json.dump(results, f, ensure_ascii=False)

print(f"\nFound: {found_total}/{len(missing)}")
