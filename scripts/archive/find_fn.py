import json, re, os

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

JOANIE_HEALTH = {
    ("43-2","2"), ("43-2","595"),
    ("43-1","106"), ("43-1","15"), ("43-1","32"), ("43-1","68"), ("43-1","83"),
    ("42-2","38"), ("42-2","11"),
    ("42-1","2"), ("42-1","43"), ("42-1","52"), ("42-1","83"), ("42-1","31"),
    ("42-1","73"), ("42-1","196"), ("42-1","594"),
    ("41-1","10"), ("41-1","20"), ("41-1","52"), ("41-1","118"),
    ("41-1","123"), ("41-1","44"), ("41-1","148"),
}

with open(f"{REPO}/data/canada/quebec_bills/quebec_health_bills.json") as f:
    bills = json.load(f)
keyword_set = set()
for b in bills:
    s = b.get("session", "")
    m = re.search(r"[Pp]rojet de loi n[°o\xa0]\s*(\d+)", b.get("title", ""))
    if s and m:
        keyword_set.add((s, m.group(1)))

with open(f"{REPO}/data/dbpedia_pipeline/xlmr_predictions.json") as f:
    xlmr = json.load(f)
xlmr_pos = set()
for k, v in xlmr.items():
    if v.get("pred") == 1:
        parts = k.rsplit("-", 1)
        if len(parts) == 2:
            xlmr_pos.add(tuple(parts))

print("False negatives (Joanie=health, AND ensemble misses):")
for key in JOANIE_HEALTH:
    sess, num = key
    in_kw = key in keyword_set
    in_xlmr = key in xlmr_pos
    if not (in_kw and in_xlmr):
        print(f"  {sess}-{num}: keyword={in_kw}, xlmr={in_xlmr}")
