"""
fetch_ontario_fsob.py  (v2 - multi-era parser)

Downloads and parses Final Status of Business PDFs for Ontario parliaments
33rd (1985) onward. Covers three distinct vote-recording eras:

  Era 1 (parliaments 33-35, 1985-1995):
    "* Carried [date]" = recorded division, passed
    "* Lost [date]" or "* Negatived" = recorded division, failed
    "Royal Assent [date]" (no asterisk) = passed by voice vote
    "Third Reading [date]" + Royal Assent = passed

  Era 2 (parliament 36+, 1995-present):
    "Carried on division" = recorded division, passed
    "Lost on division"   = recorded division, failed
    "Royal Assent [date]" without division = voice vote passage

Both recorded divisions and voice vote outcomes are captured so the
pass/fail record is complete for every bill that reached third reading.

Output: data/canada/ontario/ontario_fsob_votes.json
Usage: python3 scripts/fetch_ontario_fsob.py
"""

import os, re, json, time, io
import requests
import pdfplumber

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(REPO_ROOT, "data", "canada", "ontario", "ontario_fsob_votes.json")
BILL_INDEX_PATH = os.path.join(REPO_ROOT, "data", "canada", "ontario", "ontario_bill_index.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (research; Yale legislative-health-factuality project)"}
BASE_URL = "https://www.ola.org/sites/default/files/common/pdf/FSOB%20and%20Journals/{p}-{s}-FSOB.pdf"

PARLIAMENT_SESSIONS = [
    (33,1),(33,2),(33,3),
    (34,1),(34,2),
    (35,1),(35,2),(35,3),
    (36,1),(36,2),(36,3),
    (37,1),(37,2),(37,3),(37,4),
    (38,1),(38,2),
    (39,1),(39,2),
    (40,1),(40,2),
    (41,1),(41,2),(41,3),
    (42,1),(42,2),
    (43,1),
]

# Era 1: asterisk notation (pre-1995)
ASTERISK_CARRIED = re.compile(r"\*\s*Carried", re.IGNORECASE)
ASTERISK_LOST    = re.compile(r"\*\s*(?:Lost|Negatived)", re.IGNORECASE)

# Era 2: division notation (1995+)
DIV_CARRIED = re.compile(r"Carried\s+on\s+division", re.IGNORECASE)
DIV_LOST    = re.compile(r"Lost\s+on\s+division",    re.IGNORECASE)

# All eras: Royal Assent = passed (any method)
ROYAL_ASSENT = re.compile(r"Royal\s+Assent", re.IGNORECASE)

# Third reading present at all = bill reached final vote
THIRD_READING = re.compile(r"Third\s+Reading", re.IGNORECASE)

# Royal Assent date capture
ROYAL_DATE = re.compile(r"Royal\s+Assent\s+([\w]+\.?\s+\d+)", re.IGNORECASE)


def classify_bill(text):
    """Return (outcome, method) for a bill's text block."""
    if DIV_CARRIED.search(text):
        return "carried", "recorded_division"
    if DIV_LOST.search(text):
        return "lost", "recorded_division"
    if ASTERISK_CARRIED.search(text):
        return "carried", "asterisk_division"
    if ASTERISK_LOST.search(text):
        return "lost", "asterisk_division"
    if ROYAL_ASSENT.search(text):
        return "carried", "voice_vote_royal_assent"
    if THIRD_READING.search(text):
        # third reading recorded but no Royal Assent = failed at third reading
        return "lost", "third_reading_no_assent"
    return None, None


def parse_fsob(text, parliament, session):
    """
    Parse bill outcomes from FSOB text across all eras and formats.

    Rather than trying to find section boundaries (which differ across
    40 years of format changes), we scan the full text for:
      1. Bill number anchors in any format:
         - "Bill 124," (pre-2022 format)
         - "^124 " at line start (43-1 table format)
      2. Within each bill block, look for outcome phrases
    """
    records = []
    seen = set()

    # Strategy: find all bill number positions then extract text between them
    # Matches both "Bill 124," and table-format "^124 Title"
    bill_positions = []
    for m in re.finditer(
        r"(?m)(?:^Bill\s+(\d+)[,\.]|^(\d+)\s+(?:An Act|A Bill|Loi))",
        text
    ):
        num = m.group(1) or m.group(2)
        if num:
            bill_positions.append((m.start(), num))

    for i, (start, bill_number) in enumerate(bill_positions):
        if bill_number in seen:
            continue
        seen.add(bill_number)

        # get text up to next bill entry
        end = bill_positions[i+1][0] if i+1 < len(bill_positions) else start + 2000
        block = text[start:end]

        outcome, method = classify_bill(block)
        if not outcome:
            continue

        # extract title from first line after bill number
        title_match = re.search(
            r"(?:Bill\s+\d+[,\.]\s*|^\d+\s+)(.{5,150}?)(?:\n|/Loi)",
            block, re.DOTALL
        )
        title = re.sub(r"\s+", " ", title_match.group(1)).strip()[:120] if title_match else ""
        ra_match = ROYAL_DATE.search(block)

        records.append({
            "bill_number": bill_number,
            "parliament": parliament,
            "session": session,
            "title_snippet": title,
            "outcome": outcome,
            "vote_method": method,
            "royal_assent": ra_match.group(1).strip() if ra_match else None,
        })

    return records

    for block in bill_blocks:
        m = re.match(r"Bill\s+(\d+)[,\.\s]+(.{0,120})", block, re.DOTALL)
        if not m:
            continue
        bill_number = m.group(1)
        if bill_number in seen:
            continue
        seen.add(bill_number)

        title_raw = re.sub(r"\s+", " ", m.group(2)).strip()
        title = title_raw[:120]

        outcome, method = classify_bill(block)
        if not outcome:
            continue

        ra_match = ROYAL_DATE.search(block)

        records.append({
            "bill_number": bill_number,
            "parliament": parliament,
            "session": session,
            "title_snippet": title,
            "outcome": outcome,
            "vote_method": method,
            "royal_assent": ra_match.group(1).strip() if ra_match else None,
        })

    return records


def fetch_and_parse(parliament, session):
    url = BASE_URL.format(p=parliament, s=session)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    pdf_bytes = resp.content

    text_pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_pages.append(t)
    full_text = "\n".join(text_pages)

    records = parse_fsob(full_text, parliament, session)
    return records, url


def main():
    existing = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        done = sum(1 for v in existing.values() if v.get("records") is not None)
        print(f"Resuming: {done} sessions already processed")

    bill_index = {}
    if os.path.exists(BILL_INDEX_PATH):
        with open(BILL_INDEX_PATH, encoding="utf-8") as f:
            bill_index = json.load(f)

    all_records = []

    for parliament, session in PARLIAMENT_SESSIONS:
        key = f"{parliament}-{session}"
        if key in existing and existing[key].get("records") is not None:
            all_records.extend(existing[key]["records"])
            print(f"  {key}: {len(existing[key]['records'])} records (cached)")
            continue

        print(f"Fetching {key}...", end=" ", flush=True)
        try:
            records, url = fetch_and_parse(parliament, session)
            print(f"{len(records)} bills with outcomes")
            existing[key] = {"parliament": parliament, "session": session,
                             "source_url": url, "records": records}
            all_records.extend(records)
        except Exception as e:
            print(f"ERROR: {e}")
            existing[key] = {"error": str(e), "records": []}

        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        time.sleep(1.0)

    # Summary
    carried = [r for r in all_records if r["outcome"] == "carried"]
    lost    = [r for r in all_records if r["outcome"] == "lost"]
    recorded = [r for r in all_records if "division" in r.get("vote_method","")]
    voice    = [r for r in all_records if "voice" in r.get("vote_method","") or "assent" in r.get("vote_method","")]

    # Era breakdown
    by_method = {}
    for r in all_records:
        m = r.get("vote_method","unknown")
        by_method[m] = by_method.get(m, 0) + 1

    # Health cross-reference
    era_map = {33:1985,34:1985,35:1989,36:1993,37:1997,
               38:2001,39:2005,40:2009,41:2013,42:2017,43:2021}
    health_with_vote = 0
    for r in all_records:
        era = era_map.get(r["parliament"], 1985)
        if f"{era}-Bill{r['bill_number']}" in bill_index:
            if bill_index[f"{era}-Bill{r['bill_number']}"].get("health_tag"):
                health_with_vote += 1

    print(f"\n{'='*60}")
    print(f"Total bills with outcomes:          {len(all_records)}")
    print(f"  Carried:                          {len(carried)}")
    print(f"  Lost:                             {len(lost)}")
    print(f"  Recorded division:                {len(recorded)}")
    print(f"  Voice vote / Royal Assent:        {len(voice)}")
    print(f"By method: {by_method}")
    print(f"Health-tagged bills with outcome:   {health_with_vote}")
    print(f"Saved to: {OUT_PATH}")


if __name__ == "__main__":
    main()
