# This script patches fetch_ontario_hansard_via_api.py
# Replaces Jaccard threshold matching with best-score hash table matching

import re

path = '/Users/caprice/MiscellaneousProjects/legislative-health-factuality/scripts/fetch_ontario_hansard_via_api.py'

with open(path) as f:
    c = f.read()

# Replace the topic_matches_bill function and the assignment logic in process_batch

old_funcs = '''def title_keywords(title):
    """Extract meaningful keywords from bill title for topic matching."""
    words = re.sub(r"[^A-Za-z ]", "", title.upper()).split()
    stop = {"AN", "ACT", "TO", "THE", "OF", "AND", "FOR", "IN", "A", "BY",
            "OR", "AMEND", "PROVIDE", "RESPECTING", "CERTAIN", "MAKE",
            "REQUIRE", "ENSURE", "WITH", "RESPECT", "RELATED", "RELATING"}
    return [w for w in words if w not in stop and len(w) > 4][:6]


def topic_matches_bill(topic, bill):
    """Jaccard similarity between normalized topic and bill short title."""
    if not topic:
        return False
    short = get_short_title_j(bill.get("title", ""))
    return jaccard_j(normalize_j(short), normalize_j(topic)) >= 0.6'''

new_funcs = '''STOPWORDS_HASH = {"AN", "ACT", "TO", "THE", "OF", "AND", "FOR", "IN", "A", "BY",
    "OR", "AMEND", "PROVIDE", "RESPECTING", "CERTAIN", "MAKE",
    "REQUIRE", "ENSURE", "WITH", "RESPECT", "RELATED", "RELATING",
    "CERTAIN", "OTHER", "MATTERS", "VARIOUS", "FURTHER", "PROVIDING"}


def build_bill_hash(bills):
    """Build hash table: bill_key -> set of title tokens for similarity matching."""
    bill_hash = {}
    for b in bills:
        title = b.get("title", "") or ""
        short = get_short_title_j(title)
        tokens = set(w for w in re.sub(r"[^A-Za-z ]", "", (title + " " + short).upper()).split()
                     if w not in STOPWORDS_HASH and len(w) > 3)
        bill_hash[b["bill_key"]] = tokens
    return bill_hash


def best_bill_match(topic, text, bills, bill_hash, min_score=0.25):
    """
    Find the best matching bill for a topic+text block using hash table token overlap.
    Returns (bill, score) or (None, 0) if no match above threshold.
    Scores both the topic field and the full text block.
    """
    if not topic and not text:
        return None, 0

    topic_tokens = set(w for w in re.sub(r"[^A-Za-z ]", "", topic.upper()).split()
                       if w not in STOPWORDS_HASH and len(w) > 3)
    text_tokens = set(w for w in re.sub(r"[^A-Za-z ]", "", text.upper()).split()
                      if w not in STOPWORDS_HASH and len(w) > 4)

    best_bill = None
    best_score = 0.0

    for b in bills:
        bill_tokens = bill_hash.get(b["bill_key"], set())
        if not bill_tokens:
            continue

        # Score 1: Jaccard between topic and bill title tokens
        topic_score = jaccard_j(topic_tokens, bill_tokens) if topic_tokens else 0.0

        # Score 2: token overlap between bill title tokens and full text block
        if text_tokens and bill_tokens:
            overlap = len(bill_tokens & text_tokens) / len(bill_tokens)
        else:
            overlap = 0.0

        # Combined score: topic match weighted higher since it's curated
        score = (topic_score * 0.7) + (overlap * 0.3)

        if score > best_score:
            best_score = score
            best_bill = b

    if best_score >= min_score:
        return best_bill, best_score
    return None, 0'''

if old_funcs in c:
    c = c.replace(old_funcs, new_funcs)
    print("functions replaced")
else:
    print("ERROR: old functions not found - check exact whitespace")

# Now replace the assignment logic in process_batch
old_assign = '''        for topic, paras in topic_paras.items():
            all_text = " ".join(p["text"] for p in paras)
            mentioned_bills = set(BILL_RE.findall(all_text))

            for b in bills_on_date:
                bill_key = b["bill_key"]
                bill_num = b["bill_number"]
                assignment_method = None

                # Method 1: Bill number explicitly mentioned in this topic's text
                if bill_num and bill_num in mentioned_bills:
                    assignment_method = "bill_number_in_text"

                # Method 2: Topic matches bill title keywords (2+ keywords)
                elif topic_matches_bill(topic, b):
                    assignment_method = "topic_keyword_match"

                if assignment_method:
                    if bill_key not in results:
                        results[bill_key] = {}
                    if date not in results[bill_key]:
                        results[bill_key][date] = []
                    # Add assignment method to each paragraph for audit
                    for p in paras:
                        results[bill_key][date].append({
                            "text": p["text"],
                            "speaker": p["speaker"],
                            "topic": topic,
                            "session": p.get("session",""),
                            "url": p.get("url",""),
                            "para_url": p.get("para_url",""),
                            "assignment_method": assignment_method
                        })
                    break  # Don't assign same topic to multiple bills'''

new_assign = '''        # Build hash table for bills on this date
        bill_hash = build_bill_hash(bills_on_date)

        for topic, paras in topic_paras.items():
            all_text = " ".join(p["text"] for p in paras)
            mentioned_bills = set(BILL_RE.findall(all_text))

            assignment_method = None
            matched_bill = None

            # Method 1: Bill number explicitly mentioned in this topic's text
            # This is the most reliable signal — check all bills on this date
            for b in bills_on_date:
                bill_num = b["bill_number"]
                if bill_num and bill_num in mentioned_bills:
                    matched_bill = b
                    assignment_method = "bill_number_in_text"
                    break

            # Method 2: Best hash table similarity match across title + text
            if not assignment_method:
                matched_bill, score = best_bill_match(topic, all_text, bills_on_date, bill_hash)
                if matched_bill:
                    assignment_method = f"hash_similarity:{score:.2f}"

            if assignment_method and matched_bill:
                bill_key = matched_bill["bill_key"]
                if bill_key not in results:
                    results[bill_key] = {}
                if date not in results[bill_key]:
                    results[bill_key][date] = []
                for p in paras:
                    results[bill_key][date].append({
                        "text": p["text"],
                        "speaker": p["speaker"],
                        "topic": topic,
                        "session": p.get("session",""),
                        "url": p.get("url",""),
                        "para_url": p.get("para_url",""),
                        "assignment_method": assignment_method
                    })'''

if old_assign in c:
    c = c.replace(old_assign, new_assign)
    print("assignment logic replaced")
else:
    print("ERROR: old assignment logic not found - check exact whitespace")

with open(path, 'w') as f:
    f.write(c)
print("done")
