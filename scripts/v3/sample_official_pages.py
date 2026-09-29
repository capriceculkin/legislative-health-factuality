#!/usr/bin/env python3
"""Prints short samples of the official Ontario and Quebec bill pages and the Quebec
debate list, so the Canada day check can be matched to their real layout. Reads only."""
import html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
S = ROOT / "data" / "v3_status_cache"


def text(p):
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", p.read_text(encoding="utf-8", errors="ignore"))
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", raw))).strip()


for bk in ("37-1-Bill124", "36-1-Bill149", "36-2-Bill13"):
    p = S / "ontario" / f"{bk}.html"
    if p.exists():
        t = text(p)
        i = t.find("Stage")
        print(f"\n=== ONTARIO {bk} status table ===\n{t[max(0, i - 100): i + 1400]}")

segs = json.load(open(ROOT / "data/canada/quebec_assembly/v3/segments_index.json", encoding="utf-8"))
comb = json.load(open(ROOT / "data/canada/quebec_bills/quebec_health_bills_combined.json", encoding="utf-8"))
for bk in ("35-1-Bill116", "35-2-Bill190"):
    sess, n = bk.rsplit("-Bill", 1)
    e = next((x for x in comb if str(x.get("session")) == sess and str(x.get("bill_number", "")).strip() == n), {})
    print(f"\n=== QUEBEC {bk} ===")
    print("assembly_debates:", json.dumps(e.get("assembly_debates"), ensure_ascii=False)[:1200])
    print("our days:", sorted({x.get("date") for x in segs if x.get("bill_key") == bk}))
    p = S / "quebec" / f"{bk}.html"
    if p.exists():
        t = text(p)
        i = t.find("Présentation")
        print("bill page:", t[max(0, i - 50): i + 1400])
