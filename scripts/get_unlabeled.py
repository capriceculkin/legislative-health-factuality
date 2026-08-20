import json, re

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"

JOANIE_LABELED = {
    ("43-2","2"), ("43-2","25"), ("43-2","498"), ("43-2","595"), ("43-2","29"),
    ("43-1","106"), ("43-1","15"), ("43-1","32"), ("43-1","68"), ("43-1","83"),
    ("43-1","95"), ("43-1","36"), ("43-1","66"), ("43-1","101"), ("43-1","141"),
    ("43-1","136"), ("43-1","192"), ("43-1","213"), ("43-1","149"), ("43-1","150"),
    ("43-1","61"),
    ("42-2","38"), ("42-2","11"),
    ("42-1","2"), ("42-1","43"), ("42-1","52"), ("42-1","83"), ("42-1","31"),
    ("42-1","73"), ("42-1","196"), ("42-1","594"),
    ("42-1","9"), ("42-1","12"), ("42-1","35"), ("42-1","61"), ("42-1","85"),
    ("42-1","75"), ("42-1","59"), ("42-1","598"), ("42-1","691"),
    ("41-1","10"), ("41-1","20"), ("41-1","52"), ("41-1","118"), ("41-1","123"),
    ("41-1","44"), ("41-1","148"),
    ("41-1","97"), ("41-1","126"), ("41-1","152"), ("41-1","162"), ("41-1","170"),
    ("41-1","221"),
    ("40-1","67"), ("39-1","104"), ("38-1","23"), ("38-1","50"),
    ("36-2","151"), ("35-2","190"),
}

with open(f"{REPO}/data/canada/quebec_bills/quebec_health_bills_combined.json") as f:
    all_bills = json.load(f)

with open(f"{REPO}/data/canada/quebec_bills/quebec_health_bills.json") as f:
    kw_bills = json.load(f)

kw_set = set()
for b in kw_bills:
    s = b.get("session", "")
    m = re.search(r"[Pp]rojet de loi n[°o\xa0]\s*(\d+)", b.get("title", ""))
    if s and m:
        kw_set.add((s, m.group(1)))

unlabeled = []
for b in all_bills:
    s = b.get("session", "")
    m = re.search(r"[Pp]rojet de loi n[°o\xa0]\s*(\d+)", b.get("title", ""))
    if not m or not s:
        continue
    key = (s, m.group(1))
    if key not in JOANIE_LABELED and key in kw_set:
        unlabeled.append((s, m.group(1), b.get("title", "")[:100]))

print(f"Unlabeled bills flagged as health by keyword filter: {len(unlabeled)}")
for i, (s, n, t) in enumerate(unlabeled[:100]):
    # URL format: projet-loi-[num]-[session with - replaced by -]
    session_url = s.replace("-", "-")
    url = f"https://www.assnat.qc.ca/fr/travaux-parlementaires/projets-loi/projet-loi-{n}-{s}.html"
    print(f"{i+1}. {s} Bill {n}: {t}")
    print(f"   {url}")