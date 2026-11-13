import re, requests, pdfplumber, io

HEADERS = {"User-Agent": "Mozilla/5.0"}
DIV_CARRIED = re.compile(r"Carried\s+on\s+division", re.IGNORECASE)
DIV_LOST    = re.compile(r"Lost\s+on\s+division", re.IGNORECASE)
ROYAL_ASSENT = re.compile(r"Royal\s+Assent", re.IGNORECASE)
THIRD_READING = re.compile(r"Third\s+Reading", re.IGNORECASE)

def classify(text):
    if DIV_CARRIED.search(text): return "carried", "division"
    if DIV_LOST.search(text): return "lost", "division"
    if ROYAL_ASSENT.search(text): return "carried", "royal_assent"
    if THIRD_READING.search(text): return "lost", "third_reading"
    return None, None

url = "https://www.ola.org/sites/default/files/common/pdf/FSOB%20and%20Journals/42-1-FSOB.pdf"
resp = requests.get(url, headers=HEADERS, timeout=30)
with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
    text = ""
    for page in pdf.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"

print(f"Total text chars: {len(text)}")
print(f"'Carried on division' occurrences: {len(DIV_CARRIED.findall(text))}")
print(f"'Royal Assent' occurrences: {len(ROYAL_ASSENT.findall(text))}")
print(f"'Bill N,' pattern matches: {len(re.findall(r'Bill\s+\d+[,\.]', text))}")
print(f"Table number pattern matches: {len(re.findall(r'(?m)^\d+\s+(?:An Act|A Bill|Loi)', text))}")

# Show first 5 bill matches
print("\nFirst 5 bill anchors found:")
for i, m in enumerate(re.finditer(r"(?m)(?:^Bill\s+(\d+)[,\.]|^(\d+)\s+(?:An Act|A Bill|Loi))", text)):
    num = m.group(1) or m.group(2)
    context = text[m.start():m.start()+200].replace("\n", " ")
    print(f"  Bill {num}: {context[:120]}")
    if i >= 4:
        break
