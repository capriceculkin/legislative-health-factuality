import json, requests
from collections import Counter

with open('data/canada/ontario/ontario_bill_index.json') as f:
    idx = json.load(f)
with open('data/canada/ontario/hansard_api_bill_segments.json') as f:
    seg = json.load(f)

health = {k:v for k,v in idx.items() if v.get('health_tag')}
missing = {k:v for k,v in health.items() if k not in seg}

# Check a 2017 and 2021 missing bill
for year in ['2017', '2021', '2013']:
    candidates = [k for k in missing if year in k]
    if not candidates:
        continue
    bill_key = candidates[0]
    bill = missing[bill_key]
    date = bill['dates'][0]
    print(f"\nBill: {bill_key} | {bill['title'][:50]}")
    print(f"Date: {date} | Bill number: {bill.get('bill_number')}")

    API_URL = 'https://aihansardsearch-apim.azure-api.net/api/search/keyword'
    HEADERS = {'Content-Type': 'application/json', 'Origin': 'https://www.ola.org', 'User-Agent': 'Mozilla/5.0'}
    
    resp = requests.post(API_URL, headers=HEADERS, json={
        'keyword': str(bill.get('bill_number', '')),
        'filter': 'date ge ' + date + 'T00:00:00Z and date le ' + date + 'T23:59:59Z',
        'rows': 20
    })
    data = resp.json()
    print('Total results:', data.get('@odata.count', 0))
    types = Counter(r.get('typeOfBusiness', '') for r in data.get('value', []))
    print('typeOfBusiness values:', dict(types))
    for r in data.get('value', [])[:3]:
        print(' ', r.get('typeOfBusiness', ''), '|', r.get('topic', '')[:50])
