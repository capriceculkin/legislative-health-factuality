"""
check_ontario_bill_stages.py

Uses myparliament.ca to check whether each missing Ontario health bill
reached second reading (floor debate) or only first reading.

Outputs a categorized list of missing bills.
"""
import json, os, re, time, requests
from collections import defaultdict

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

with open(os.path.join(REPO, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)
with open(os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")) as f:
    seg = json.load(f)

health = {k: v for k, v in idx.items() if v.get("health_tag")}
missing = {k: v for k, v in health.items() if k not in seg}
print(f"Missing bills to check: {len(missing)}\n")

# Parliament/session lookup
def get_parl(year):
    y = int(year)
    if y <= 1987: return "33rd", "1st"
    if y <= 1990: return "34th", "1st"
    if y <= 1995: return "35th", "1st"
    if y <= 1999: return "36th", "2nd"
    if y <= 2003: return "37th", "2nd"
    if y <= 2007: return "38th", "2nd"
    if y <= 2011: return "39th", "2nd"
    if y <= 2014: return "40th", "2nd"
    if y <= 2018: return "41st", "2nd"
    if y <= 2022: return "42nd", "1st"
    if y <= 2025: return "43rd", "1st"
    return "44th", "1st"

H = {"User-Agent": "Mozilla/5.0 (academic research)"}

has_second_reading = []
first_reading_only = []
unknown = []

for bill_key, bill in sorted(missing.items()):
    year = bill_key[:4]
    bill_num = str(bill.get("bill_number", ""))
    title = bill.get("title", "")[:60]
    parl, sess = get_parl(year)
    
    # Search myparliament.ca
    search_url = f"https://myparliament.ca/provincial/on/bills?parliament={parl.lower().replace('th','').replace('rd','').replace('nd','').replace('st','')}&session={sess.replace('nd','').replace('st','').replace('rd','').replace('th','')}&bill={bill_num}"
    
    # Try direct search
    try:
        resp = requests.get(
            f"https://myparliament.ca/provincial/on/bills",
            params={"q": f"Bill {bill_num} {year}", "parliament": "ON"},
            headers=H, timeout=10
        )
        # Check if second reading mentioned
        text = resp.text
        if "Second Reading" in text and "Carried" in text:
            has_second_reading.append((bill_key, bill_num, title))
            print(f"✓ {bill_key}: Bill {bill_num} — HAS second reading")
        elif "First Reading" in text and "Second Reading" not in text:
            first_reading_only.append((bill_key, bill_num, title))
            print(f"✗ {bill_key}: Bill {bill_num} — first reading only")
        else:
            unknown.append((bill_key, bill_num, title))
            print(f"? {bill_key}: Bill {bill_num} — could not verify")
    except Exception as e:
        unknown.append((bill_key, bill_num, title))
        print(f"? {bill_key}: Bill {bill_num} — error: {e}")
    
    time.sleep(2)

print(f"\n\nSUMMARY:")
print(f"Has second reading (floor debate): {len(has_second_reading)}")
for k, n, t in has_second_reading:
    print(f"  {k}: Bill {n} | {t}")

print(f"\nFirst reading only (no floor debate): {len(first_reading_only)}")
for k, n, t in first_reading_only:
    print(f"  {k}: Bill {n} | {t}")

print(f"\nUnknown: {len(unknown)}")
