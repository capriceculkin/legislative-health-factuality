#!/usr/bin/env python3
"""
para_join.py   (used by build_sentences_v3.py and apply_us_text_choices.py; changes no data file)

The section files keep the paragraphs exactly as the source prints them. Two sources break sentences across
paragraphs, and sentences were split inside each paragraph, so those sentences became two fragments:
  - US daily Record: inserted statements, letters and articles are printed with every line indented, and every
    indented line became its own paragraph; a page marker also cut paragraphs in two
    ("...bill claim it would dramatically" | "increase health costs, we in Texas know it won't.")
  - Quebec Journal des debats 1985-1994: the digitised pages start a new paragraph at every column or page break
    ("Mme la Presidente, on voit" | "loin, mises a part ces questions, ...")
join_groups() puts such paragraphs back together before the sentence split, joined by one space, only when both
are in the same source unit and carry the same tag (US), the first does not end a sentence (. ! ? : ; or a closing
quote or bracket after one) and:
  1. the second starts with a lowercase letter, or
  2. the first ends with a word that cannot end a sentence ("the", "of", "de", "la", "et", ...) and the second
     starts with a letter and is not a speaker's name, or
  3. (US only) the first is one full printed line (50 to 80 characters, not a heading, list lead-in, table row or
     time stamp) and the second continues it ("...the American Farm" | "Bureau Federation. Farmers are...").
Quebec 1985-1994 text also gets (fix_quebec_text): the OCR word corrections listed in
data/canada/quebec_assembly/v3/ocr_word_fixes.json (each one checked in its context, e.g. "parie" -> "parle"
where the speaker talks, "Bouierice" -> "Boulerice"), and words split by a line-end hyphen joined again
("parlemen- taires" -> "parlementaires") when the joined word is in the 1994+ debates.
US 1985-1993 (bound) text: a word split by a hyphen where a column ended is joined again when the joined word is in
the daily Record ("pa- tients" -> "patients"; scripts/step1_debate_text/us_words.txt), and the scanner's leftover misreadings listed in
data/us/v3/ocr_word_fixes.json are corrected (fix11: "<IL>" -> "(IL)", "CMr. WAXMAN]" -> "[Mr. WAXMAN]",
"subsection fb)" -> "subsection (b)", "Govern ment" -> "Government", "cllnical" -> "clinical").
A sentence keeps the number of the first paragraph of its group (US|bill|day|pN|sM), so tags and links still work.
"""
import json
import os
import re

TERMINAL = re.compile(r"[.!?:;…][\"'»”’)\]]*\s*$")
STAMP = re.compile(r"^n \(\d")                       # Quebec time stamps: "n (17 h 25 ? 17 h 28) n"
SPEAKER = re.compile(r"^(?:(?:Mr|Mrs|Ms|Miss|Dr)\.? (?:[A-Z][a-z]* )?[A-Z]{2,}|The (?:SPEAKER|CHAIRMAN|CHAIR|PRESIDING|"
                     r"ACTING|PRESIDENT|CLERK|VICE|SPEAKER pro)|\{time\}|(?:M|Mme|Mmes|MM)\. [^:]{1,60}:|"
                     r"(?:Le|La) (?:Président|Présidente|Vice-Président|Vice-Présidente|Secrétaire)[^:]{0,40}:)")
FUNC_END = {
    "en": {"the", "a", "an", "of", "and", "or", "to", "in", "for", "by", "with", "from", "on", "at", "as", "that",
           "which", "who", "whose", "than", "into", "under", "upon", "between", "our", "their", "its", "his", "her",
           "my", "your", "this", "these", "those", "is", "are", "was", "were", "be", "been", "has", "have", "had",
           "will", "would", "shall", "should", "could", "may", "might", "must", "not", "no", "such", "very"},
    "fr": {"le", "la", "les", "l'", "un", "une", "des", "de", "du", "d'", "et", "ou", "à", "au", "aux", "en", "dans",
           "par", "pour", "sur", "avec", "sans", "sous", "entre", "vers", "chez", "que", "qu'", "qui", "dont", "ce",
           "cet", "cette", "ces", "son", "sa", "ses", "leur", "leurs", "notre", "nos", "votre", "vos", "mon", "ma",
           "mes", "est", "sont", "a", "ont", "être", "été", "ne", "n'", "se", "s'", "il", "ils", "elle", "elles",
           "nous", "vous", "on", "très", "plus", "moins", "si", "mais", "car", "lorsque", "quand", "comme"},
}
LAST_WORD = re.compile(r"([A-Za-zÀ-ÿ]+'?)\s*$")


def _upper_share(s):
    letters = [c for c in s if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


def wrapped_line(a, b):
    """US: a is one full printed line that the next paragraph continues."""
    if not 50 <= len(a) <= 80:
        return False
    if a.startswith("{time}") or a.endswith("--") or a.endswith("]") or "Congressional Record" in a or "...." in a \
            or "Pursuant to House Resolution" in a or _upper_share(a) > 0.5:
        return False
    if SPEAKER.match(b) or _upper_share(b[:25]) > 0.6:
        return False
    if re.match(r"^\(?[0-9a-zA-Z]{1,4}\)\s|^\d+\.\s|^Sec\.|^SEC\.|^Subtitle|^Title|^TITLE", b):
        return False
    if re.search(r"\s{3,}\S", a) or re.search(r"\s{3,}\S", b[:40]):          # table rows
        return False
    return bool(b[:1].isupper() or b[:1] == "(" or b[:1].isdigit())


def continues(a, b, lang="en", wrapped=False):
    a, b = (a or "").rstrip(), (b or "").lstrip()
    if not a or not b or TERMINAL.search(a) or STAMP.match(b):
        return False
    if b[0].islower():
        return True
    m = LAST_WORD.search(a)
    if m and m.group(1).lower() in FUNC_END.get(lang, set()) and b[0].isalpha() and not SPEAKER.match(b):
        return True
    return wrapped and wrapped_line(a, b)


def join_groups(paras, lang="en", keys=None, wrapped=False):
    """paras: paragraph texts. keys: optional list (same length) of (unit, tag); paragraphs with different keys are
    never joined. Returns [(index of the group's first paragraph, joined text)]."""
    out = []
    for i, p in enumerate(paras):
        if out and (keys is None or keys[i] == keys[i - 1]) and continues(paras[i - 1], p, lang, wrapped):
            out[-1] = (out[-1][0], out[-1][1].rstrip() + " " + p.lstrip())
        else:
            out.append((i, p))
    return out


def expand_runs(runs):
    return [x for x, n in (runs or []) for _ in range(int(n))]


def us_keys(e, n):
    """(unit, tag) for each of the n paragraphs of a US bill-day, or None if the index does not cover them."""
    units, tags = expand_runs(e.get("para_units")), expand_runs(e.get("para_tags"))
    if len(units) != n or len(tags) != n:
        return None
    return list(zip(units, tags))


_US_HYPH = re.compile(r"\b([A-Za-z]+)- ([a-z]+)\b")


def load_us_words(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {w.strip() for w in f if w.strip()}
    except OSError:
        return None


def us_groups(e, paras, words=None, tally=None):
    """US paragraph groups. With words (scripts/step1_debate_text/us_words.txt, the words of the daily Record), a word that the
    1985-1993 bound pages split at a column end is joined again ("pa-" | "tients" -> "patients")."""
    keys = us_keys(e, len(paras))
    if keys is None:
        return list(enumerate(paras))
    groups = join_groups(paras, "en", keys, wrapped=True)
    if not words:
        return groups
    tally = tally if tally is not None else {}

    def hj(m):
        if (m.group(1) + m.group(2)).lower() in words:
            tally["hyphen_joined"] = tally.get("hyphen_joined", 0) + 1
            return m.group(1) + m.group(2)
        return m.group(0)
    return [(i, _US_HYPH.sub(hj, t) if "-block" in str(keys[i][0]) else t) for i, t in groups]


# ---------------------------------------------------------------- Quebec 1985-1994 text
_WORD = re.compile(r"[A-Za-zÀ-ÿ]+")
_HYPH = re.compile(r"([A-Za-zÀ-ÿ]+)-[ \t]+([a-zà-ÿ]+)")


def quebec_vocab(base, idx):
    """lowercase words that occur at least twice in the 1994+ debates (the dictionary for hyphen joins)."""
    from collections import Counter
    c = Counter()
    for e in idx:
        if e.get("source") == "bibliotheque_pre1994":
            continue
        try:
            with open(os.path.join(base, e["file"]), encoding="utf-8") as f:
                c.update(w.lower() for w in _WORD.findall(f.read()))
        except OSError:
            pass
    return {w for w, n in c.items() if n >= 2}


def load_ocr_fixes(path):
    by_file = {}
    try:
        with open(path, encoding="utf-8") as f:
            for x in json.load(f):
                by_file.setdefault(x["file"], []).append(x)
    except (OSError, ValueError):
        pass
    return by_file


def _hyphen_join(text, vocab, tally, pattern):
    def hj(m):
        a, b = m.group(1), m.group(2)
        if (a + b).lower() in vocab:
            tally["hyphen_joined"] = tally.get("hyphen_joined", 0) + 1
            return a + b
        return m.group(0)
    return pattern.sub(hj, text)


def apply_fixes(text, fixes, tally=None, name="ocr_fixed"):
    """corrections by position, last first, each only if the old text is still there; never across a paragraph
    break, so the paragraphs (and their tags) stay the same."""
    tally = tally if tally is not None else {}
    for x in sorted(fixes or [], key=lambda x: -x["offset"]):
        o = x["offset"]
        if text[o:o + len(x["old"])] == x["old"] and "\n\n" not in x["old"] + x["new"]:
            text = text[:o] + x["new"] + text[o + len(x["old"]):]
            tally[name] = tally.get(name, 0) + 1
        else:
            tally[name.replace("fixed", "not_found")] = tally.get(name.replace("fixed", "not_found"), 0) + 1
    return text


_FIXCACHE = {}


def fixes_for(path, file):
    """the corrections listed for one section file in a fixes list (loaded once)."""
    path = str(path)
    if path not in _FIXCACHE:
        _FIXCACHE[path] = load_ocr_fixes(path)
    return _FIXCACHE[path].get(file)


def fix_quebec_text(text, fixes, vocab, tally=None):
    """OCR word corrections (by position, each only if the old word is still there) and line-end hyphen joins
    inside a paragraph ("parlemen- taires")."""
    tally = tally if tally is not None else {}
    text = apply_fixes(text, fixes, tally, "ocr_fixed")
    return _hyphen_join(text, vocab, tally, _HYPH)


def quebec_groups(paras, vocab=None, tally=None):
    """paragraph groups for Quebec; with vocab (1985-1994 text), a word split by a hyphen at the paragraph break
    is joined again ("proposi-" | "tion du 14 decembre" -> "proposition du 14 decembre")."""
    tally = tally if tally is not None else {}
    groups = join_groups(paras, "fr")
    if vocab is None:
        return groups
    return [(i, _hyphen_join(t, vocab, tally, _HYPH)) for i, t in groups]
