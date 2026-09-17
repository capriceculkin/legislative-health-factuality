import json, requests, time, re
from collections import Counter

REPO='/Users/caprice/MiscellaneousProjects/legislative-health-factuality'
API='https://aihansardsearch-apim.azure-api.net/api/search/keyword'
H={'Content-Type':'application/json','Origin':'https://www.ola.org','User-Agent':'Mozilla/5.0'}

with open(f'{REPO}/data/canada/ontario/ontario_bill_index.json') as f: idx=json.load(f)
with open(f'{REPO}/data/canada/ontario/hansard_api_bill_segments.json') as f: seg=json.load(f)

health={k:v for k,v in idx.items() if v.get('health_tag')}
missing={k:v for k,v in health.items() if k not in seg}
print(f'Missing: {len(missing)}\n')

results={}
for bill_key,bill in sorted(missing.items()):
    bill_num=str(bill.get('bill_number',''))
    year=bill_key[:4]
    yr_s=str(int(year)-1); yr_e=str(int(year)+5)
    try:
        resp=requests.post(API,headers=H,json={
            'keyword':f'Bill {bill_num}',
            'filter':f'date ge {yr_s}-01-01T00:00:00Z and date le {yr_e}-12-31T23:59:59Z',
            'rows':200
        },timeout=30)
        if resp.status_code==429:
            time.sleep(180)
            resp=requests.post(API,headers=H,json={
                'keyword':f'Bill {bill_num}',
                'filter':f'date ge {yr_s}-01-01T00:00:00Z and date le {yr_e}-12-31T23:59:59Z',
                'rows':200
            },timeout=30)
        rows=[r for r in resp.json().get('value',[])
              if f'Bill {bill_num}' in str(r.get('paragraph',''))]
        tobs=Counter(r.get('typeOfBusiness','') for r in rows)
        dates=Counter(r.get('date','')[:10] for r in rows)
        print(f'{bill_key}: Bill {bill_num}')
        print(f'  types: {dict(tobs.most_common(3))}')
        print(f'  dates: {dict(list(dates.most_common(3)))}')
        results[bill_key]={'types':dict(tobs),'dates':dict(dates)}
    except Exception as e:
        print(f'{bill_key}: ERROR {e}')
    time.sleep(6)

with open(f'{REPO}/data/canada/ontario/missing_bill_locations.json','w') as f:
    json.dump(results,f,indent=2)
print('\nSaved to missing_bill_locations.json')
