import json, requests
from collections import Counter

with open('data/canada/ontario/ontario_bill_index.json') as f:
    idx = json.load(f)
with open('data/canada/ontario/hansard_api_bill_segments.json') as f:
    segments = json.load(f)

health_bills = {k:v for k,v in idx.items() if v.get('health_tag')}
uncovered_2021 = [(k,v) for k,v in health_bills.items() if k not in segments and '2021' in k]

bill_key, bill = uncovered_2021[0]
print('Bill:', bill_key)
print('Title:', bill['title'][:60])
print('Dates:', bill['dates'][:3])
date = bill['dates'][0]

API_URL = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
HEADERS = {"Content-Type": "application/json", "Origin": "https://www.ola.org",
           "User-Agent": "Mozilla/5.0"}

resp = requests.post(API_URL, headers=HEADERS, json={
    "keyword": "*",
    "filter": "date ge " + date + "T00:00:00Z and date le " + date + "T23:59:59Z and typeOfBusiness eq 'ORDERS OF THE DAY'",
    "rows": 20
})
data = resp.json()
count = data.get('@odata.count', 0)
print('API results for', date, ':', count)
topics = Counter(r.get('topic','') for r in data.get('value',[]))
print('Topics:', dict(list(topics.items())[:5]))
