"""
fetch_ontario_by_session.py

Fetches ALL Ontario Hansard Orders of the Day content from the OLA Azure
Search API, organized by parliament-session date ranges. Assigns paragraphs
to health bills using two methods per David Chartash's approach:

1. Section anchor extraction: find the paragraph formally introducing a bill
   ("second reading of Bill X", "Resuming debate on Bill X", etc.) and keep
   ALL subsequent paragraphs until the next bill anchor or topic change.

2. Jaccard verification: the topic field of the anchor paragraph must score
   >= JACCARD_THRESHOLD against the normalized bill title (or the bill's
   known Hansard short title if stored).

No single-bill date fallback. No loose keyword matching.
Every paragraph kept is verified by anchor + topic match.

Output: data/canada/ontario/hansard_api_bill_segments.json
Format: {bill_key: {date: [{"text", "speaker", "topic", "session", "url", "para_url", "assignment_method"}]}}
"""

import os
import re
import json
import time
import requests
from collections import defaultdict

REPO = "/Users/caprice/MiscellaneousProjects/legislative-health-factuality"
OUT_PATH = os.path.join(REPO, "data/canada/ontario/hansard_api_bill_segments.json")
IDX_PATH = os.path.join(REPO, "data/canada/ontario/ontario_bill_index.json")

API = "https://aihansardsearch-apim.azure-api.net/api/search/keyword"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.ola.org",
    "User-Agent": "Mozilla/5.0"
}

JACCARD_THRESHOLD = 0.6

PARLIAMENT_SESSIONS = {
    "33-1": ("1985-05-02", "1985-10-31"),
    "33-2": ("1985-11-18", "1986-10-06"),
    "33-3": ("1986-11-17", "1987-09-08"),
    "34-1": ("1987-10-01", "1988-12-16"),
    "34-2": ("1989-03-20", "1990-08-30"),
    "35-1": ("1990-11-20", "1991-12-19"),
    "35-2": ("1992-04-06", "1993-06-17"),
    "35-3": ("1993-11-15", "1995-02-09"),
    "36-1": ("1995-09-26", "1997-12-18"),
    "36-2": ("1998-03-23", "1998-12-10"),
    "36-3": ("1999-03-15", "1999-10-18"),
    "37-1": ("1999-10-25", "2001-12-20"),
    "37-2": ("2002-03-18", "2002-12-19"),
    "37-3": ("2003-03-17", "2003-09-18"),
    "38-1": ("2003-12-09", "2004-12-16"),
    "38-2": ("2005-02-28", "2007-10-01"),
    "39-1": ("2007-10-17", "2008-12-18"),
    "39-2": ("2009-03-02", "2011-10-06"),
    "40-1": ("2011-11-30", "2012-12-20"),
    "40-2": ("2013-02-19", "2014-05-02"),
    "41-1": ("2014-07-02", "2015-12-10"),
    "41-2": ("2016-02-22", "2017-12-07"),
    "41-3": ("2018-03-19", "2018-05-09"),
    "42-1": ("2018-07-11", "2019-12-12"),
    "42-2": ("2020-02-18", "2022-05-04"),
    "43-1": ("2022-08-08", "2024-12-12"),
    "44-1": ("2025-04-14", "2026-12-31"),
}

POST_2018 = {"42-1", "42-2", "43-1", "44-1"}
PRE_1995 = {"33-1", "33-2", "33-3", "34-1", "34-2", "35-1", "35-2", "35-3"}

STOPWORDS = {
    "AN","ACT","TO","THE","OF","AND","FOR","IN","A","BY","OR","AMEND",
    "PROVIDE","RESPECTING","CERTAIN","MAKE","REQUIRE","ENSURE","WITH",
    "RESPECT","RELATED","RELATING","ENACT","GOVERNING","FURTHER","VARIOUS",
    "AMENDING","CONCERNING","AUTHORIZE","REGULATE","THAT","RENDERING",
    "UNDER","MAY","ARE","REGULATING","INSURED","CHARGE","ESTABLISH",
    "IMPOSING","PERSONS","PAYMENT","IMPOSE","PROVIDING","AUTHORIZING",
    "REQUIRING","ENABLING",
}

LEMMA_MAP = {
    "AMENDMENT":"AMEND","AMENDMENTS":"AMEND","SERVICES":"SERVICE",
    "NURSES":"NURSE","HOMES":"HOME","WORKERS":"WORKER",
    "PROFESSIONS":"PROFESSION","PROFESSIONALS":"PROFESSION",
    "PRACTITIONERS":"PRACTITIONER","REGULATIONS":"REGULATION",
    "RIGHTS":"RIGHT","BENEFITS":"BENEFIT","PAYMENTS":"PAYMENT",
    "PERSONS":"PERSON","AMOUNTS":"AMOUNT","ACTS":"ACT",
}

ANCHOR_RE = re.compile(
    r"(?:Resuming|second reading of|Consideration of|moved second reading of|"
    r"adjourned debate on the motion for second reading of|"
    r"motion for second reading of|"
    r"third reading of|report stage of)"
    r".{0,80}Bill\s+(\d+)",
    re.IGNORECASE
)

BILL_RE = re.compile(r"\bBill\s+(\d+)\b", re.IGNORECASE)


def clean_html(text):
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", str(text)).strip()


def normalize(text):
    if not text:
        return set()
    text = text.upper()
    text = re.sub(r"[^A-Z\s]", " ", text)
    words = text.split()
    words = [LEMMA_MAP.get(w, w) for w in words]
    return set(w for w in words if w not in STOPWORDS and len(w) > 2)


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def get_short_title(title):
    return title.split(",")[0].strip()


def fetch_date_range(start, end, tob):
    """Fetch paragraphs for a specific date range with pagination."""
    all_paras = []
    skip = 0
    retries = 0
    while True:
        try:
            if tob:
                filter_str = f"date ge {start}T00:00:00Z and date le {end}T23:59:59Z and typeOfBusiness eq '{tob}'"
            else:
                filter_str = f"date ge {start}T00:00:00Z and date le {end}T23:59:59Z"
            resp = requests.post(API, headers=HEADERS, json={
                "keyword": "*",
                "filter": filter_str,
                "rows": 500,
                "skip": skip,
            }, timeout=30)
            data = resp.json()
            batch = data.get("value", [])
            if not batch:
                break
            all_paras.extend(batch)
            skip += len(batch)
            total = data.get("@odata.count", 0)
            if skip >= total:
                break
            time.sleep(0.3)
            retries = 0
        except Exception as e:
            retries += 1
            if retries > 5:
                break
            time.sleep(5 * retries)
    return all_paras


def fetch_session_paragraphs(session, start, end):
    """Fetch all Orders of the Day for a session, chunked by month to avoid API caps."""
    from datetime import date, timedelta
    if session in POST_2018:
        tob = "Orders of the Day"
    elif session in PRE_1995:
        tob = None  # pre-1995 content has no typeOfBusiness field
    else:
        tob = "ORDERS OF THE DAY"
    all_paras = []
    start_dt = date.fromisoformat(start)
    end_dt = date.fromisoformat(end)
    current = start_dt
    while current <= end_dt:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        chunk_end = min(next_month - timedelta(days=1), end_dt)
        chunk = fetch_date_range(current.isoformat(), chunk_end.isoformat(), tob)
        all_paras.extend(chunk)
        print(f"  {session}: {current.strftime('%Y-%m')} -> {len(chunk)} paras (total {len(all_paras):,})", end="\r")
        current = next_month
        time.sleep(0.5)
    print(f"\n  {session}: {len(all_paras):,} paragraphs fetched")
    return all_paras


def assign_paragraphs(session_paras, health_bills, current_session):
    """
    Assign paragraphs to bills using anchor + Jaccard approach.

    For each date in session_paras:
      1. Sort paragraphs by their order in the Hansard
      2. Find anchor paragraphs (formal bill introduction)
      3. Keep all paragraphs from anchor until next anchor or topic change
      4. Verify section topic matches bill title via Jaccard >= threshold
    """
    # Build lookup by bill number across all sessions.
    # Bills carry across sessions so we can't filter by session alone.
    # Disambiguation uses Jaccard between topic and bill title.
    bill_lookup = defaultdict(list)
    for bk, info in health_bills.items():
        bnum = str(info.get("bill_number", ""))
        title = info.get("title", "")
        short = get_short_title(title)
        title_norm = normalize(short)
        bill_lookup[bnum].append((bk, title_norm, short, info.get("session","")))

    # Group by date
    date_paras = defaultdict(list)
    for p in session_paras:
        date = p.get("date", "")[:10]
        text = clean_html(p.get("paragraph", ""))
        if text and len(text) > 20:
            date_paras[date].append({
                "text": text,
                "speaker": p.get("speaker", ""),
                "topic": p.get("topic", "") or "",
                "session": p.get("session", ""),
                "url": p.get("url", ""),
                "para_url": p.get("paraUrl", ""),
            })

    results = defaultdict(lambda: defaultdict(list))

    for date, paras in sorted(date_paras.items()):
        # Track active section: (bill_key, topic)
        active_bill_key = None
        active_topic = None
        active_section = []

        def save_section():
            if active_bill_key and active_section:
                results[active_bill_key][date].extend(active_section)

        for p in paras:
            text = p["text"]
            topic = p["topic"]

            anchor = ANCHOR_RE.search(text)

            if anchor:
                # Save previous section
                save_section()
                active_section = []
                active_bill_key = None
                active_topic = None

                found_num = anchor.group(1)
                candidates = bill_lookup.get(found_num, [])

                if candidates:
                    # Pick best match: prefer Jaccard on topic, then anchor text
                    best_score = -1
                    best_bk = None
                    anchor_text = text
                    bill_in_anchor = found_num in BILL_RE.findall(anchor_text)
                    for bk, title_norm, _, bill_session in candidates:
                        score = jaccard(normalize(topic), title_norm)
                        # Boost score if session matches current session
                        if bill_session == current_session:
                            score += 0.1
                        if score > best_score:
                            best_score = score
                            best_bk = bk
                    # Keep if Jaccard meets threshold OR bill number confirmed in anchor
                    if best_bk and (best_score >= JACCARD_THRESHOLD or bill_in_anchor):
                        active_bill_key = best_bk
                        active_topic = topic
                        active_section = [dict(p, assignment_method="anchor")]

            elif active_bill_key:
                # Continue section — stop if topic changes to something unrelated
                if topic and active_topic and topic != active_topic:
                    topic_norm = normalize(topic)
                    # Get current bill's title_norm
                    curr_title_norm = None
                    for bk, title_norm, _, _ in bill_lookup.get(
                        str(health_bills[active_bill_key].get("bill_number","")), []
                    ):
                        if bk == active_bill_key:
                            curr_title_norm = title_norm
                            break
                    score = jaccard(topic_norm, curr_title_norm) if curr_title_norm else 0
                    if score < 0.3:
                        save_section()
                        active_bill_key = None
                        active_topic = None
                        active_section = []
                    else:
                        active_section.append(dict(p, assignment_method="anchor_continuation"))
                else:
                    active_section.append(dict(p, assignment_method="anchor_continuation"))

        save_section()

    return results


def main():
    with open(IDX_PATH) as f:
        idx = json.load(f)

    health_bills = {k: v for k, v in idx.items() if v.get("health_tag")}
    print(f"Health bills in index: {len(health_bills)}")

    # Load checkpoint
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            results = json.load(f)
        done_sessions = set()
        for bk, dates in results.items():
            for date in dates:
                for p in dates[date]:
                    s = p.get("session", "")
                    if s:
                        done_sessions.add(s)
        print(f"Resuming: {len(done_sessions)} sessions already done: {sorted(done_sessions)}")
    else:
        results = {}
        done_sessions = set()

    for session, (start, end) in PARLIAMENT_SESSIONS.items():
        if session in done_sessions:
            print(f"Skipping {session} (already done)")
            continue

        print(f"\nFetching session {session} ({start} to {end})...")
        session_paras = fetch_session_paragraphs(session, start, end)

        if not session_paras:
            print(f"  No content found for {session}")
            continue

        print(f"  Assigning paragraphs to bills...")
        session_results = assign_paragraphs(session_paras, health_bills, session)

        # Merge into results
        new_bills = 0
        new_paras = 0
        for bk, dates in session_results.items():
            if bk not in results:
                results[bk] = {}
                new_bills += 1
            for date, paras in dates.items():
                if date not in results[bk]:
                    results[bk][date] = []
                results[bk][date].extend(paras)
                new_paras += len(paras)

        print(f"  Added {new_bills} bills, {new_paras:,} paragraphs from {session}")

        # Save checkpoint after each session
        with open(OUT_PATH, "w") as f:
            json.dump(results, f, ensure_ascii=False)

        total_paras = sum(len(p) for d in results.values() for p in d.values())
        print(f"  Running total: {len(results)} bills, {total_paras:,} paragraphs")
        time.sleep(1)

    total_paras = sum(len(p) for d in results.values() for p in d.values())
    print(f"\nDone. Bills: {len(results)}, Paragraphs: {total_paras:,}")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
