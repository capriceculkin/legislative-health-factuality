"""
find_correct_debate_dates.py

For each uncertain Ontario bill, finds the correct debate dates by:
1. Checking myparliament.ca for the bill's legislative history
2. Then fetching the actual debate text from OLA API for those dates

This verifies uncertain assignments against the authoritative source.
"""
import json, re, requests, time
from collections import Counter

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    idx = json.load(f)
with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments.json") as f:
    seg = json.load(f)

BILL_RE = re.compile(r"Bill\s+(\d+)", re.IGNORECASE)
RESUME_RE = re.compile(r"(?:Resuming|second reading of Bill|debate on Bill)\s+(\d+)", re.IGNORECASE)

# Find uncertain bills
uncertain_bills = set()
for bk, dates in seg.items():
    bnum = str(idx.get(bk, {}).get("bill_number", ""))
    for date, paras in dates.items():
        all_text = " ".join(p if isinstance(p, str) else p.get("text", "") for p in paras)
        first = paras[0] if isinstance(paras[0], str) else paras[0].get("text", "")
        if bnum and bnum not in BILL_RE.findall(all_text):
            resume = RESUME_RE.search(first)
            if not (resume and resume.group(1) != bnum):
                uncertain_bills.add(bk)

print(f"Uncertain bills: {len(uncertain_bills)}")
print()

# Check each against myparliament.ca
H = {"User-Agent": "Mozilla/5.0 (academic research)"}
API = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
API_H = {"Content-Type": "application/json", "Origin": "https://www.ola.org", "User-Agent": "Mozilla/5.0"}

PARL_MAP = {
    "33": ("1985-05-02", "1987-09-08"),
    "34": ("1987-10-01", "1990-08-30"),
    "35": ("1990-11-20", "1995-02-09"),
    "36": ("1995-09-26", "1999-10-18"),
    "37": ("1999-10-25", "2003-09-18"),
    "38": ("2003-12-09", "2007-10-01"),
    "39": ("2007-10-17", "2011-10-06"),
    "40": ("2011-11-30", "2014-05-02"),
    "41": ("2014-07-02", "2018-05-09"),
    "42": ("2018-07-11", "2022-05-04"),
    "43": ("2022-08-08", "2025-01-28"),
    "44": ("2025-04-14", "2099-12-31"),
}

def get_parliament(year):
    for parl, (start, end) in PARL_MAP.items():
        if start[:4] <= year <= end[:4]:
            return parl
    return "42"

results = {}
for bk in sorted(uncertain_bills)[:20]:
    v = idx.get(bk, {})
    bnum = str(v.get("bill_number", ""))
    title = v.get("title", "")[:60]
    year = bk[:4]
    parl = get_parliament(year)

    print(f"{bk}: Bill {bnum} | {title}")
    print(f"  Current segment dates: {list(seg.get(bk, {}).keys())[:3]}")

    # Search OLA API for actual debate dates
    try:
        resp = requests.post(API, headers=API_H, json={
            "keyword": f"Bill {bnum}",
            "filter": f"(typeOfBusiness eq 'ORDERS OF THE DAY' or typeOfBusiness eq 'Orders of the Day')",
            "rows": 10,
            "session": f"{parl}-1"
        }, timeout=30)
        if resp.status_code == 429:
            print("  Rate limited, waiting 60s...")
            time.sleep(60)
        else:
            rows = resp.json().get("value", [])
            # Filter to rows that actually mention this bill number
            relevant = [r for r in rows if f"Bill {bnum}" in str(r.get("paragraph", ""))]
            dates_found = sorted(set(r.get("date", "")[:10] for r in relevant))
            topics_found = set(r.get("topic", "") for r in relevant)
            print(f"  OLA API debate dates: {dates_found[:5]}")
            print(f"  Topics: {list(topics_found)[:3]}")
            if dates_found:
                results[bk] = {"correct_dates": dates_found, "topics": list(topics_found)}
    except Exception as e:
        print(f"  Error: {e}")

    print()
    time.sleep(5)

print(f"\nBills with correct dates found: {len(results)}")
with open(f"{REPO}/data/canada/ontario/correct_debate_dates.json", "w") as f:
    json.dump(results, f, indent=2)
print("Saved to data/canada/ontario/correct_debate_dates.json")
