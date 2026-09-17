"""
fetch_final_19.py - Fetch all remaining 19 missing Ontario health bills.

Key insight: use faceted search to find exact dates for each topic,
then fetch paragraphs for those dates.
"""
import json, os, re, time, requests
from collections import defaultdict

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
API_URL = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
H = {"Content-Type":"application/json","Origin":"https://www.ola.org",
     "User-Agent":"Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36"}

with open(os.path.join(REPO,"data/canada/ontario/ontario_bill_index.json")) as f:
    idx=json.load(f)
with open(os.path.join(REPO,"data/canada/ontario/hansard_api_bill_segments.json")) as f:
    results=json.load(f)

health={k:v for k,v in idx.items() if v.get("health_tag")}
missing={k:v for k,v in health.items() if k not in results}
print(f"Missing: {len(missing)}")

def q(payload, attempt=0):
    try:
        r=requests.post(API_URL,headers=H,json=payload,timeout=30)
        if r.status_code==429:
            wait=180*(attempt+1); print(f"  429, wait {wait}s"); time.sleep(wait)
            return q(payload,attempt+1) if attempt<4 else []
        r.raise_for_status()
        return r.json().get("value",[])
    except Exception as e:
        print(f"  Error:{e}"); return []

def clean(text):
    return re.sub(r"<[^>]+>"," ",str(text or "")).strip()

def get_orders_date(date, tob="ORDERS OF THE DAY"):
    filt=f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z and typeOfBusiness eq '{tob}'"
    return q({"keyword":"*","filter":filt,"rows":500})

def get_dates_for_topic_range(topic_kw, yr_start, yr_end):
    """Find all dates where a topic keyword appears in Orders of the Day."""
    filt=(f"date ge {yr_start}-01-01T00:00:00Z and date le {yr_end}-12-31T23:59:59Z "
          f"and typeOfBusiness eq 'ORDERS OF THE DAY'")
    rows=q({"keyword":topic_kw,"filter":filt,"rows":500,"facets":["date"]})
    dates=set()
    for r in rows:
        d=r.get("date","")[:10]
        topic=str(r.get("topic",""))
        if topic_kw.upper() in topic.upper() or any(
            kw.upper() in topic.upper() for kw in topic_kw.split()[:3] if len(kw)>4):
            dates.add(d)
    return sorted(dates)

# Bill-specific strategies
# 1989 health professions — all under "REGULATED HEALTH PROFESSIONS ACT, 1991, AND COMPANION"
professions_bills = {k:v for k,v in missing.items() if "1989-Bill18" in k or 
                     k in ["1989-Bill182","1989-Bill193","1989-Bill195",
                            "1989-Bill196","1989-Bill202"]}

print(f"\n=== 1989 Health Professions Bills ({len(professions_bills)}) ===")
print("Searching for 'REGULATED HEALTH PROFESSIONS' topic dates 1990-1993...")

prof_dates = get_dates_for_topic_range("regulated health professions companion", "1990","1993")
time.sleep(5)
print(f"Found {len(prof_dates)} dates: {prof_dates[:5]}")

if not prof_dates:
    # Try broader search
    prof_dates = get_dates_for_topic_range("regulated health professions", "1990","1993")
    time.sleep(5)

for bill_key,bill in professions_bills.items():
    bill_num=str(bill.get("bill_number",""))
    print(f"\n{bill_key}: Bill {bill_num}")
    collected=defaultdict(list)
    
    for date in prof_dates[:10]:  # Check up to 10 dates
        paras=get_orders_date(date)
        time.sleep(4)
        topic_paras=[p for p in paras if "PROFESSION" in str(p.get("topic","")).upper()
                     or "HEALTH PROFESSIONS" in str(p.get("topic","")).upper()]
        if topic_paras:
            for p in topic_paras:
                t=clean(p.get("paragraph",""))
                s=p.get("speaker","")
                if t and len(t)>20:
                    collected[date].append({"text":t,"speaker":s})
    
    if collected:
        results[bill_key]=dict(collected)
        total=sum(len(v) for v in collected.values())
        print(f"  ADDED: {total} paras across {len(collected)} dates")
    else:
        print(f"  NOT FOUND")

# All other missing bills — search by title keywords across wider date range
other_missing={k:v for k,v in missing.items() if k not in professions_bills and k not in results}
print(f"\n=== Other Missing Bills ({len(other_missing)}) ===")

for bill_key,bill in sorted(other_missing.items()):
    if bill_key in results:
        continue
    bill_num=str(bill.get("bill_number",""))
    title=bill.get("title","")
    dates=bill.get("dates",[])
    year=bill_key[:4]
    
    # Extract good keywords
    words=re.sub(r"[^A-Za-z ]","",title.upper()).split()
    stop={"AN","ACT","TO","THE","OF","AND","FOR","IN","A","BY","OR","AMEND",
          "PROVIDE","RESPECTING","CERTAIN","MAKE","REQUIRE","ENSURE","WITH"}
    kws=[w for w in words if w not in stop and len(w)>5][:4]
    if not kws:
        print(f"\n{bill_key}: no keywords"); continue
    
    search_kw=" ".join(kws[:2])
    yr_start=str(int(year)-1); yr_end=str(int(year)+5)
    print(f"\n{bill_key}: Bill {bill_num} | searching '{search_kw}' ({yr_start}-{yr_end})")
    
    debate_dates=get_dates_for_topic_range(search_kw, yr_start, yr_end)
    time.sleep(4)
    print(f"  Candidate dates: {debate_dates[:5]}")
    
    collected=defaultdict(list)
    for date in debate_dates[:8]:
        paras=get_orders_date(date)
        if not paras:
            paras=get_orders_date(date,"Orders of the Day")
        time.sleep(4)
        
        matched=[]
        for p in paras:
            t=clean(p.get("paragraph",""))
            topic=str(p.get("topic",""))
            if f"Bill {bill_num}" in t or any(kw in topic.upper() for kw in kws[:2]):
                matched.append(p)
        
        if not matched and len([k for k,v in health.items() 
                                 if date in v.get("dates",[]) and k!=bill_key])==0:
            matched=paras  # single bill day fallback
        
        for p in matched:
            t=clean(p.get("paragraph",""))
            s=p.get("speaker","")
            if t and len(t)>20:
                collected[date].append({"text":t,"speaker":s})
        
        if collected.get(date):
            print(f"  {date}: {len(collected[date])} paras")
    
    if collected:
        results[bill_key]=dict(collected)
        total=sum(len(v) for v in collected.values())
        print(f"  ADDED: {total} paras")
    else:
        print(f"  NOT FOUND")

# Save
out=os.path.join(REPO,"data/canada/ontario/hansard_api_bill_segments.json")
with open(out,"w") as f:
    json.dump(results,f,ensure_ascii=False)

with open(os.path.join(REPO,"data/canada/ontario/ontario_bill_index.json")) as f:
    idx2=json.load(f)
health2=[k for k,v in idx2.items() if v.get("health_tag")]
covered=[k for k in health2 if k in results]
print(f"\nFinal coverage: {len(covered)}/{len(health2)} ({len(covered)/len(health2)*100:.1f}%)")
