"""
build_ontario_hansard_bill_mapping.py

Scrapes Ontario Hansard pages (ola.org without www, following redirects)
to extract Bill number → full title mappings for all health bill dates.

Uses the pattern "Bill X, An Act..." which appears in Hansard when bills
are introduced, debated, or referenced.

Output: data/canada/ontario/hansard_bill_number_mapping.json
  {date: {bill_number: full_title}}
"""
import urllib.request, re, json, time, os
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO_ROOT, "data/canada/ontario/ontario_bill_index.json")) as f:
    idx = json.load(f)

def get_parl_sess(date):
    if date < "1987-09-10": return (33, 1)
    if date < "1990-09-20": return (34, 1)
    if date < "1995-06-08": return (35, 1)
    if date < "1996-10-28": return (36, 1)
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

health_dates = set()
for v in idx.values():
    if v.get("health_tag"):
        for d in v.get("dates", []):
            health_dates.add(d)

print(f"Health dates to scrape: {len(health_dates)}")

# Load existing mapping if resuming
out_path = os.path.join(REPO_ROOT, "data/canada/ontario/hansard_bill_number_mapping.json")
if os.path.exists(out_path):
    with open(out_path) as f:
        bill_mapping = json.load(f)
    print(f"Resuming: {len(bill_mapping)} dates already mapped")
else:
    bill_mapping = {}

BILL_RE = re.compile(
    r"Bill\s+(\d+),\s+(An Act[^\/\n<]{5,150}?)(?:\s*/|\.|<|\n)",
    re.IGNORECASE
)

errors = 0
fetched = 0
skipped = 0

for date in sorted(health_dates):
    if date in bill_mapping:
        skipped += 1
        continue

    p, s = get_parl_sess(date)
    url = f"https://ola.org/en/legislative-business/house-documents/parliament-{p}/session-{s}/{date}/hansard"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (academic research)"}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")

        bills = BILL_RE.findall(html)
        if bills:
            bill_mapping[date] = {}
            for num, title in bills:
                title_clean = re.sub(r"\s+", " ", title).strip()
                if num not in bill_mapping[date]:
                    bill_mapping[date][num] = title_clean

        fetched += 1

        if fetched % 50 == 0:
            print(f"  {fetched} fetched | {skipped} skipped | {errors} errors | {sum(len(v) for v in bill_mapping.values())} total mappings")
            with open(out_path, "w") as f:
                json.dump(bill_mapping, f, ensure_ascii=False)

        time.sleep(0.5)

    except Exception as e:
        errors += 1
        if errors <= 10:
            print(f"  Error {date}: {e}")
        time.sleep(1)

print(f"\nDone: {fetched} fetched, {skipped} skipped, {errors} errors")
print(f"Total dates mapped: {len(bill_mapping)}")
print(f"Total bill-title pairs: {sum(len(v) for v in bill_mapping.values())}")

with open(out_path, "w") as f:
    json.dump(bill_mapping, f, ensure_ascii=False)
print(f"Saved to {out_path}")
