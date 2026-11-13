import requests

url = "https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/43-2/journal-debats/20260401/431619.html"
resp = requests.get(url, timeout=20)
text = resp.text
idx = text.lower().find("adoption finale")
print(text[max(0, idx - 200):idx + 500])
