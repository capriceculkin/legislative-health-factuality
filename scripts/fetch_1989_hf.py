from datasets import load_dataset
import json, re
from collections import defaultdict

REPO='/Users/caprice/MiscellaneousProjects/legislative-health-factuality'
with open(f'{REPO}/data/canada/ontario/ontario_bill_index.json') as f: idx=json.load(f)
with open(f'{REPO}/data/canada/ontario/hansard_api_bill_segments.json') as f: seg=json.load(f)

health={k:v for k,v in idx.items() if v.get('health_tag')}
missing={k:v for k,v in health.items() if k not in seg}
print(f'Missing: {len(missing)}')

# Get all dates for missing bills
target_dates=set(d for v in missing.values() for d in v.get('dates',[]))
print(f'Target dates: {len(target_dates)}')

# Map date -> missing bill keys
date_to_missing=defaultdict(list)
for k,v in missing.items():
    for d in v.get('dates',[]):
        date_to_missing[d].append(k)

ds=load_dataset('a2aj/hansard',split='train',streaming=True)
collected=defaultdict(list)
TOBS={'ORDERS OF THE DAY','Orders of the Day',
      "PRIVATE MEMBERS' PUBLIC BUSINESS","Private Members' Public Business"}

for r in ds:
    if r.get('Date') not in target_dates: continue
    if r.get('OrderofBusiness') not in TOBS: continue
    text=str(r.get('Intervention',''))
    if len(text)<50: continue
    collected[r['Date']].append({
        'text':text,'speaker':r.get('PersonSpeaking',''),
        'subject':r.get('SubjectofBusiness','')
    })

print(f'Dates with content: {len(collected)}')
for d,rows in sorted(collected.items()):
    subjects=set(r['subject'] for r in rows)
    bills=date_to_missing[d]
    print(f'  {d}: {len(rows)} rows | bills: {bills} | subjects: {list(subjects)[:2]}')

# Assign and save
for d,rows in collected.items():
    for bill_key in date_to_missing[d]:
        if bill_key not in seg:
            if bill_key not in seg:
                seg[bill_key]={}
            seg[bill_key][d]=[{'text':r['text'],'speaker':r['speaker']} for r in rows]

with open(f'{REPO}/data/canada/ontario/hansard_api_bill_segments.json','w') as f:
    json.dump(seg,f,ensure_ascii=False)

health2=[k for k,v in idx.items() if v.get('health_tag')]
covered=[k for k in health2 if k in seg]
print(f'Coverage: {len(covered)}/{len(health2)} ({len(covered)/len(health2)*100:.1f}%)')
