"""
check_uncertain_topics.py
For uncertain bill-date assignments, queries the OLA API to get the actual
Hansard topic for those dates. This tells us definitively whether the
paragraphs are about the right bill.
"""
import json, re, requests, time
from collections import Counter

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
API = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
H = {"Content-Type": "application/json", "Origin": "https://www.ola.org", "User-Agent": "Mozilla/5.0"}

with open(f"{REPO}/data/canada/ontario/hansard_api_bill_segments.json") as f:
    seg = json.load(f)
with open(f"{REPO}/data/canada/ontario/ontario_bill_index.json") as f:
    idx = json.load(f)

BILL_RE = re.compile(r"Bill\s+(\d+)", re.IGNORECASE)

def title_keywords(title):
    words = re.sub(r"[^A-Za-z ]", "", title.upper()).split()
    stop = {"AN","ACT","TO","THE","OF","AND","FOR","IN","A","BY","OR","AMEND",
            "PROVIDE","RESPECTING","CERTAIN","MAKE","REQUIRE","ENSURE","WITH"}
    return [w for w in words if w not in stop and len(w) > 4][:6]

# Get uncertain bill-dates (no bill number in text, not clearly wrong)
RESUME_RE = re.compile(r"(?:Resuming|second reading of Bill|debate on Bill)\s+(\d+)", re.IGNORECASE)
uncertain = []
for bk, dates in seg.items():
    bnum = str(idx.get(bk, {}).get("bill_number", ""))
    title = idx.get(bk, {}).get("title", "")
    for date, paras in dates.items():
        all_text = " ".join(p if isinstance(p, str) else p.get("text", "") for p in paras)
        first = paras[0] if isinstance(paras[0], str) else paras[0].get("text", "")
        if bnum and bnum in BILL_RE.findall(all_text):
            continue  # verified correct
        resume = RESUME_RE.search(first)
        if resume and resume.group(1) != bnum:
            continue  # already caught as wrong
        uncertain.append((bk, bnum, title, date))

print(f"Uncertain date-sections: {len(uncertain)}")
print()

# For each uncertain case, query API to get actual topics
verified_via_topic = []
still_uncertain = []
wrong_via_topic = []

for bk, bnum, title, date in uncertain[:50]:  # Check first 50
    try:
        resp = requests.post(API, headers=H, json={
            "keyword": "*",
            "filter": f"date ge {date}T00:00:00Z and date le {date}T23:59:59Z and (typeOfBusiness eq 'ORDERS OF THE DAY' or typeOfBusiness eq 'Orders of the Day')",
            "rows": 10
        }, timeout=30)
        if resp.status_code == 429:
            print(f"  Rate limited, waiting 120s...")
            time.sleep(120)
            continue
        topics = Counter(r.get("topic", "") for r in resp.json().get("value", []))
        kws = title_keywords(title)
        
        # Check if any topic matches this bill's title
        matched_topic = None
        for topic in topics:
            if not topic:
                continue
            topic_upper = topic.upper()
            matches = [kw for kw in kws if kw in topic_upper]
            if len(matches) >= 2 or any(len(m) > 8 for m in matches):
                matched_topic = topic
                break
        
        if matched_topic:
            verified_via_topic.append((bk, bnum, title[:40], date, matched_topic))
            print(f"VERIFIED: {bk} | Bill {bnum} | topic='{matched_topic}'")
        else:
            # Check if topics are clearly about other bills
            topic_list = list(topics.most_common(2))
            still_uncertain.append((bk, bnum, title[:40], date, topic_list))
            print(f"UNCERTAIN: {bk} | Bill {bnum} | {title[:35]} | topics={topic_list[:1]}")
        
        time.sleep(4)
    except Exception as e:
        print(f"ERROR: {bk} | {e}")
        time.sleep(5)

print(f"\nResults for first 50:")
print(f"  Verified via topic match: {len(verified_via_topic)}")
print(f"  Still uncertain: {len(still_uncertain)}")

# Save results
out = {
    "verified_via_topic": [(bk, bnum, t, d, mt) for bk,bnum,t,d,mt in verified_via_topic],
    "still_uncertain": [(bk, bnum, t, d, str(tl)) for bk,bnum,t,d,tl in still_uncertain]
}
with open(f"{REPO}/data/canada/ontario/uncertain_topic_check.json", "w") as f:
    json.dump(out, f, indent=2)
print("Saved to data/canada/ontario/uncertain_topic_check.json")
