import json, requests, time
from collections import Counter, defaultdict

API_URL = 'https://aihansardsearch-apim.azure-api.net/api/search/keyword'
H = {'Content-Type': 'application/json', 'Origin': 'https://www.ola.org', 'User-Agent': 'Mozilla/5.0'}

with open('data/canada/ontario/ontario_bill_index.json') as f:
    idx = json.load(f)
with open('data/canada/ontario/hansard_api_bill_segments.json') as f:
    seg = json.load(f)

health = {k:v for k,v in idx.items() if v.get('health_tag')}
missing = {k:v for k,v in health.items() if k not in seg}
print(f'Missing bills: {len(missing)}')

bill_to_topic = {}
for bill_key, bill in list(missing.items()):
    num = str(bill.get('bill_number', ''))
    if not num:
        continue
    for attempt in range(3):
        try:
            resp = requests.post(API_URL, headers=H, json={
            'keyword': 'Bill ' + num,
            'rows': 5
            }, timeout=30)
            if resp.status_code == 429:
                print(f'  Rate limited, waiting 60s...')
                time.sleep(60)
                continue
            data = resp.json()
            break
        except Exception as e:
            print(f'  Error: {e}, retrying...')
            time.sleep(10)
    else:
        print(f'{bill_key}: failed after 3 attempts')
        continue
    data = resp.json()
    topics = Counter(r.get('topic','') for r in data.get('value',[]) if r.get('topic'))
    dates = set(r.get('date','')[:10] for r in data.get('value',[]))
    bill_dates = set(bill.get('dates', []))
    matching_dates = dates & bill_dates
    if topics and matching_dates:
        best_topic = topics.most_common(1)[0][0]
        bill_to_topic[bill_key] = best_topic
        print(f'{bill_key} -> "{best_topic}" (on {len(matching_dates)} matching dates)')
    else:
        print(f'{bill_key}: no Orders of the Day found (total={data.get("@odata.count",0)})')
    time.sleep(3)

print(f'\nMapped: {len(bill_to_topic)}/{len(missing)}')
with open('data/canada/ontario/missing_bill_topics.json', 'w') as f:
    json.dump(bill_to_topic, f, indent=2)
print('Saved to data/canada/ontario/missing_bill_topics.json')
