"""
build_ontario_bill_title_mapping.py

Scrapes Ontario Votes and Proceedings documents for all health bill dates
to extract bill number → full legal title mappings.

This allows matching SubjectofBusiness short titles in the HuggingFace
Hansard dataset to specific bills in the bill index.

Output: data/canada/ontario/bill_title_mapping.json
  {parliament_session: {bill_number: full_title}}
"""
import json, os, re, time, urllib.request
from bs4 import BeautifulSoup
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)

# Get all health bill dates and their parliament/session
# Parliament/session mapping for Ontario
def get_parliament_session(date):
    year = int(date[:4])
    if date < "1985-06-26": return (33, 1)
    if date < "1987-09-10": return (33, 1)
    if date < "1990-09-20": return (34, 1)
    if date < "1991-04-06": return (35, 1)
    if date < "1995-09-26": return (35, 1)
    if date < "1999-04-20": return (36, 1)
    if date < "1999-10-25": return (36, 2)
    if date < "1999-04-20": return (36, 2)
    if date < "1999-10-25": return (37, 1)
    if date < "2003-10-23": return (37, 2)
    if date < "2004-04-20": return (38, 1)
    if date < "2007-10-10": return (38, 2)
    if date < "2008-03-18": return (39, 1)
    if date < "2011-10-06": return (39, 2)
    if date < "2012-04-17": return (40, 1)
    if date < "2014-06-12": return (40, 2)
    if date < "2016-09-12": return (41, 1)
    if date < "2018-06-07": return (41, 2)
    if date < "2022-06-02": return (42, 1)
    return (43, 1)

def parliament_to_str(parl):
    ordinals = {33:'33rd',34:'34th',35:'35th',36:'36th',37:'37th',
                38:'38th',39:'39th',40:'40th',41:'41st',42:'42nd',43:'43rd'}
    sessions = {1:'1st',2:'2nd',3:'3rd'}
    p, s = parl
    return f"parliament-{p}/session-{s}"

health_dates = set()
for v in idx.values():
    if v.get("health_tag"):
        for d in v.get("dates", []):
            health_dates.add(d)

health_dates = {d for d in health_dates if d >= '1995-01-01'}
print(f"Post-1995 health dates to scrape: {len(health_dates)}")

# Group dates by parliament/session
date_by_parl = defaultdict(set)
for d in health_dates:
    parl = get_parliament_session(d)
    date_by_parl[parl].add(d)

print(f"Parliament/sessions: {len(date_by_parl)}")

# Only need to scrape multi-bill dates
from collections import defaultdict as dd2
date_health_bills = dd2(list)
for bill_key, v in idx.items():
    if v.get("health_tag"):
        for d in v.get("dates", []):
            date_health_bills[d].append(bill_key)


health_dates = {d for d in health_dates if d >= '1995-01-01'}
print(f"Post-1995 health dates to scrape: {len(health_dates)}")

# Scrape V&P for each date
bill_mapping = {}  # {date: {bill_number: full_title}}
errors = 0
fetched = 0

for parl, dates in sorted(date_by_parl.items()):
    parl_str = parliament_to_str(parl)
    for date in sorted(dates):
        url = f"https://www.ola.org/en/legislative-business/house-documents/{parl_str}/{date}/votes-proceedings"
        try:
            req = urllib.request.urlopen(url, timeout=15)
            html = req.read().decode('utf-8', errors='replace')
            soup = BeautifulSoup(html, 'lxml')
            text = soup.get_text()

            # Extract bill number → full title
            bills = re.findall(r'Bill\s+(\d+),\s+(An Act[^\.]{5,150}\.)', text, re.IGNORECASE)
            if bills:
                bill_mapping[date] = {}
                for num, title in bills:
                    # Clean up whitespace
                    title_clean = re.sub(r'\s+', ' ', title).strip()
                    bill_mapping[date][num] = title_clean

            fetched += 1
            if fetched % 50 == 0:
                print(f"  Fetched {fetched}/{len(health_dates)} | Mapped: {len(bill_mapping)} dates")
            time.sleep(0.3)

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error {date}: {e}")

print(f"\nDone: {fetched} fetched, {errors} errors, {len(bill_mapping)} dates mapped")

# Sample output
for date, bills in list(bill_mapping.items())[:2]:
    print(f"\n{date}:")
    for num, title in list(bills.items())[:3]:
        print(f"  Bill {num}: {title[:60]}")

out_path = os.path.join(REPO_ROOT, "data/canada/ontario/bill_title_mapping.json")
with open(out_path, "w") as f:
    json.dump(bill_mapping, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_path}")
