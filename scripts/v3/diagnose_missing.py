#!/usr/bin/env python3
"""Read-only. For every bill-vote in segments_missing.json: which days were searched,
how much text each day has, and whether the bill number appears in the text of any
day from 4 days before to 1 day after the vote. Run from the project root."""
import datetime as dt, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
US = ROOT / "data" / "us"
BT = US / "v3" / "cache" / "bound_text"
miss = json.load(open(US / "v3" / "segments_missing.json", encoding="utf-8"))
print(f"bill-votes not found: {len(miss)}\n")
for b in miss:
    bk, vd = b.get("bill_key", ""), b.get("vote_date", "")
    m = re.search(r"HR(\d+)$", bk)
    pat = re.compile(r"\bH\.?\s?R\.?\s?" + (m.group(1) if m else "@@") + r"\b")
    print(f"{bk}  vote {vd}  edition {b.get('edition', '')}  units found per day: {b.get('units_available')}")
    d0 = dt.date.fromisoformat(vd)
    for k in range(-4, 2):
        d = (d0 + dt.timedelta(days=k)).isoformat()
        f = BT / f"{d}.json"
        if not f.exists():
            continue
        j = json.load(open(f, encoding="utf-8"))
        txt = "\n".join(j.get("lines", []))
        print(f"    {d} ({dt.date.fromisoformat(d).strftime('%a')}): source {j.get('source')}, {len(j.get('lines', []))} lines, "
              f"bill number mentioned {len(pat.findall(txt))} times")
    print()
