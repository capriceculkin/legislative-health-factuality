#!/usr/bin/env python3
"""
patch_extractor.py   (edits scripts/step1_debate_text/extract_predications_v3.py; keeps a backup)

Three corrections to how a claim's subject and object are taken from a sentence, found reading 100 random claims:
  1. Words glued together. Punctuation is left out of a subject or object, and the space went with it:
     "not-for-profit" -> "notforprofit", "Donc, M. le President, une" -> "DoncM. le Presidentune". Now kept words are
     joined with the sentence's own spacing; a dropped comma or dash becomes a space, and a word joined by hyphens
     keeps its hyphens.
  2. An opening phrase taken as the object: "In fact, costs dropped to 3.9 percent" gave the object "fact",
     "At present, ... operates in New York" gave "present". When the verb has no direct object, the object is now
     taken only from a phrase that comes after the verb ("to 3.9 percent", "in New York City").
  3. A speaker label or a form of address taken as the subject: "Mr. Speaker, this legislation will harm patients"
     gave "Mr. Speaker"; "Le Vice-President: Je vais ..." gave "Le Vice-President". A subject followed by a colon,
     or an address ("Mr. Speaker", "M. le President") followed by a comma, is skipped and the next subject is used.
Nothing else in the extractor changes (root verb only, the same excluded verbs, pronouns removed, hedging and
negation flagged as before).
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "extract_predications_v3.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
P = ROOT / "scripts" / "step1_debate_text" / "extract_predications_v3.py"
MARK = "PATCHED_CLAIM_SPANS_2026_10_07"
s = P.read_text(encoding="utf-8")
if MARK in s:
    print("extract_predications_v3.py already patched")
    sys.exit(0)

OLD_SPAN = '''    keep.sort(key=lambda t: t.i)
    if len(keep) > max_tokens:
        keep = [t for t in keep if abs(t.i - tok.i) <= 6]
    return "".join(t.text_with_ws for t in keep).strip()
'''
NEW_SPAN = f'''    keep.sort(key=lambda t: t.i)
    if len(keep) > max_tokens:
        keep = [t for t in keep if abs(t.i - tok.i) <= 6]
    # {MARK}: join with the sentence's own spacing; a left-out comma or dash becomes a space, and a word joined
    # by hyphens ("not-for-profit") keeps its hyphens
    out = ""
    for k, t in enumerate(keep):
        if k:
            prev = keep[k - 1]
            if t.i == prev.i + 1:
                out += prev.whitespace_
            else:
                gap = [t.doc[j] for j in range(prev.i + 1, t.i)]
                if not prev.whitespace_ and all(g.text in HYPHENS and not g.whitespace_ for g in gap):
                    out += "".join(g.text for g in gap)
                else:
                    out += " "
        out += t.text
    return " ".join(out.split())
'''
OLD_EX = '''    subj = next((c for c in root.children if c.dep_ in SUBJ), None)
    if subj is None:
        return None
    obj = next((c for c in root.children if c.dep_ in OBJ), None)
    if obj is None:
        for c in root.children:
            if lang == "en" and c.dep_ == "prep":'''
NEW_EX = '''    # PATCHED_CLAIM_SPANS_2026_10_07: a speaker label ("Le Vice-President:") or a form of address followed by a
    # comma ("Mr. Speaker, this legislation ...") is not the subject
    subj = next((c for c in root.children if c.dep_ in SUBJ and not label_or_address(c)), None)
    if subj is None:
        return None
    obj = next((c for c in root.children if c.dep_ in OBJ), None)
    if obj is None:
        for c in root.children:
            if c.i < root.i:          # an opening phrase ("In fact,", "At present,") is not the object
                continue
            if lang == "en" and c.dep_ == "prep":'''
OLD_PRON = '''def is_pron(tok, text, lang):'''
NEW_PRON = '''HYPHENS = {"-", "\\u2010", "\\u2011"}
ADDRESS = re.compile(r"^(?:(?:Mr|Mrs|Ms|Madam|Madame)\\.?\\s+(?:Speaker|Chairman|Chairwoman|Chair|President|Clerk)"
                     r"(?:\\s+pro\\s+tempore)?|(?:M\\.|Mme|Monsieur|Madame)\\s+(?:le|la)\\s+(?:Pr\\u00e9sidente?|"
                     r"Vice-Pr\\u00e9sidente?))$", re.I)


def label_or_address(tok):
    """True for a subject that is a speaker label (followed by a colon) or a form of address followed by a comma."""
    # the colon or comma is often attached to the subject itself ("Le President:"), so look after its last word
    words = [t for t in tok.subtree if not (t.pos_ == "PUNCT" or t.dep_ == "punct")] or [tok]
    end = max(t.i for t in words)
    nxt = tok.doc[end + 1] if end + 1 < len(tok.doc) else None
    if nxt is None:
        return False
    if nxt.text == ":":
        return True
    text = " ".join(tok.doc[min(t.i for t in words):end + 1].text.split())
    return nxt.text == "," and bool(ADDRESS.match(text))


def is_pron(tok, text, lang):'''
for old, new in ((OLD_SPAN, NEW_SPAN), (OLD_EX, NEW_EX), (OLD_PRON, NEW_PRON)):
    if s.count(old) != 1:
        sys.exit(f"extract_predications_v3.py is not in the expected form (looking for {old.strip()[:50]!r}); "
                 "nothing changed. Send this output to Claude.")
    s = s.replace(old, new)
if "\nimport re\n" not in s:
    s = s.replace("import os\n", "import os\nimport re\n", 1)
compile(s, str(P), "exec")
backup = P.with_name("extract_predications_v3_before_spans_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")
print(f"patched scripts/step1_debate_text/extract_predications_v3.py (backup {backup.name})")
