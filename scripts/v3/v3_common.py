"""
v3_common.py
Shared helpers for the v3 rebuild scripts. Nothing in this file touches the network.

Every script in scripts/v3/ imports from here so that Ontario, Quebec and the US
use the same topic normalization, the same anchor rules, the same language
detector and the same atomic file writes.
"""
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter

# --------------------------------------------------------------------------- paths


def _find_repo():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "data")) and os.path.isdir(os.path.join(d, "scripts")):
            return d
        d = os.path.dirname(d)
    return os.getcwd()


REPO = os.environ.get("LHF_REPO") or _find_repo()
GITHUB_BLOB = "https://github.com/capriceculkin/legislative-health-factuality/blob/main/"


def rp(*parts):
    return os.path.join(REPO, *parts)


def rel(path):
    return os.path.relpath(path, REPO).replace(os.sep, "/")


def github_url(path):
    return GITHUB_BLOB + rel(path)


def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path, indent=None):
    """Atomic write. A crash or Ctrl+C can never leave a half-written file,
    which is how data/dbpedia_pipeline/ontario/dbpedia_results.json ended up
    truncated at character 27,740,307 on Sept 24."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def sha(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- text basics


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def clean_html(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(t or ""))).strip()


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


EN_STOP = set("""a an and are as at be by for from has have in into is it its of on or that the this to was
were will with act acts amend amending amendment amendments bill certain respecting respect related relating
various further other matters provide providing make ensure require law laws statute statutes ontario""".split())
FR_STOP = set("""a au aux avec ce ces dans de des du en et la le les leur leurs loi lois modifiant modifier
concernant visant ou par pour sur un une diverses certaines autres dispositions projet quebec""".split())


def content_tokens(text, lang="en", min_len=3):
    t = strip_accents(text or "").lower()
    toks = re.findall(r"[a-z0-9]+", t)
    stop = EN_STOP if lang == "en" else FR_STOP
    return [w for w in toks if len(w) >= min_len and w not in stop]


# --------------------------------------------------------------------------- Ontario topics and sessions

PROCEDURAL_TOPICS = {
    "", "ORDERS OF THE DAY", "BUSINESS OF THE HOUSE", "FIRST READINGS", "SECOND READINGS", "THIRD READINGS",
    "INTRODUCTION OF BILLS", "DEFERRED VOTES", "DEFERRED VOTE", "HOUSE IN COMMITTEE OF THE WHOLE",
    "COMMITTEE OF THE WHOLE HOUSE", "HOUSE IN COMMITTEE OF THE WHOLE HOUSE", "ROYAL ASSENT", "MOTIONS",
    "GOVERNMENT MOTIONS", "PETITIONS", "ORAL QUESTIONS", "QUESTION PERIOD", "STATEMENTS BY THE MINISTRY",
    "STATEMENTS BY THE MINISTRY AND RESPONSES", "MEMBERS STATEMENTS", "REPORTS BY COMMITTEES",
    "INTRODUCTION OF VISITORS", "VISITORS", "TIME ALLOCATION", "HOUSE SITTINGS", "ANSWERS TO WRITTEN QUESTIONS",
    "OPPOSITION DAY", "PRIVATE MEMBERS PUBLIC BUSINESS", "LEGISLATIVE ASSEMBLY", "POINTS OF ORDER",
    "POINT OF ORDER", "ADJOURNMENT DEBATE", "LATE SHOW", "TABLING OF SESSIONAL PAPERS",
    "NOTICE OF DISSATISFACTION", "WEARING OF PINS", "DEFERRED VOTES AND ROYAL ASSENT", "PRIVATE BILLS",
    "SPEAKER S RULING", "SPEAKERS RULING", "RESPONSES", "ORDERS OF THE DAY CONTINUED",
}
# Topics whose paragraphs are question period or statements: anchors found there are never trusted.
QP_TOPICS = {"ORAL QUESTIONS", "QUESTION PERIOD", "MEMBERS STATEMENTS", "STATEMENTS BY THE MINISTRY",
             "STATEMENTS BY THE MINISTRY AND RESPONSES", "PETITIONS", "RESPONSES"}
NO_SPLIT_TOPICS = {"ROYAL ASSENT", "DEFERRED VOTES AND ROYAL ASSENT"}


def norm_topic(topic):
    t = (topic or "").strip()
    t = t.split(" / ")[0]  # bilingual headings after 2018: keep the English half
    t = strip_accents(t).upper()
    t = re.sub(r"\((CONTINUED|CONTINUATION|CONT D|CONT'D|SUITE)\)", " ", t)
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def is_procedural_topic(nt):
    return nt in PROCEDURAL_TOPICS


_URL_SESS = re.compile(r"(?:parliament|legislature)-(\d+)/session-(\d+)", re.I)


def url_session(url):
    """Session taken from the OLA URL itself, e.g. .../parliament-33/session-1/1986-01-14/hansard -> 33-1.
    This is the ground truth label. It replaces the hand-written PARLIAMENT_SESSIONS table."""
    m = _URL_SESS.search(url or "")
    return f"{int(m.group(1))}-{int(m.group(2))}" if m else None


def api_session(val):
    m = re.search(r"(\d{2})\D+(\d{1,2})", str(val or ""))
    return f"{int(m.group(1))}-{int(m.group(2))}" if m else None


# --------------------------------------------------------------------------- Ontario anchors
# An anchor is a procedural sentence that names the bill being taken up.
# Only anchors are allowed to create a bill-to-heading link. A bill number that
# merely appears in a speech or in a Business of the House statement is not evidence.

_BILL = r"(?:the\s+following\s+bill:?\s*)?Bill\s+(?P<num>\d+)"
EN_ANCHOR_RES = [
    ("first", re.compile(r"moved\s+first\s+reading\s+of\s+" + _BILL, re.I)),
    ("second", re.compile(r"moved\s+second\s+reading\s+of\s+" + _BILL, re.I)),
    ("third", re.compile(r"moved\s+third\s+reading\s+of\s+" + _BILL, re.I)),
    ("second_resumed", re.compile(r"resum(?:ing|ed)\s+the\s+(?:adjourned\s+)?debate[^.]{0,160}?motion\s+for\s+"
                                  r"second\s+reading\s+of\s+" + _BILL, re.I)),
    ("third_resumed", re.compile(r"resum(?:ing|ed)\s+the\s+(?:adjourned\s+)?debate[^.]{0,160}?motion\s+for\s+"
                                 r"third\s+reading\s+of\s+" + _BILL, re.I)),
    ("committee_whole", re.compile(r"committee\s+of\s+the\s+whole(?:\s+house)?\s+on\s+" + _BILL, re.I)),
    ("list_item", re.compile(r"^\s*Bill\s+(?P<num>\d+),\s+An\s+Act\b", re.I)),
]
_NAME = r"[A-Z][\w'\u2019\-]+(?:\s+[A-Z][\w'\u2019\-]+){0,3}"
PROCEDURAL_START = re.compile(
    r"^\s*(?:(?:Hon\.\s+)?(?:(?:Mr|Mrs|Ms|Miss|Mme|M|Dr)\.?\s+)?" + _NAME + r"\s+moved\b"
    r"|Resum(?:ing|ed)\b|Bill\s+\d+,\s+An\s+Act\b|(?:The\s+)?House\s+(?:resolved\s+itself\s+into|in)\s+committee)")
LONG_TITLE_RE = re.compile(r"Bill\s+(?P<num>\d+),\s+(?P<title>An\s+Act\b[^;]{5,400}?)(?:\.\s|\.$|;|$)", re.I)


def find_anchors_en(text, speaker="", topic="", type_of_business=""):
    """Return anchors in the first 400 characters of a paragraph.
    strong = the paragraph is itself procedural (starts with 'X moved', 'Resuming', 'Bill N, An Act',
    or the API labels the speaker 'Procedure') and it is not in question period or statements."""
    head = (text or "")[:400]
    spk = (speaker or "").strip().lower()
    procedural = bool(PROCEDURAL_START.match(head)) or spk == "procedure"
    nt, ntob = norm_topic(topic), norm_topic(type_of_business)
    in_qp = nt in QP_TOPICS or ntob in QP_TOPICS
    out = []
    for stage, rx in EN_ANCHOR_RES:
        m = rx.search(head)
        if not m:
            continue
        if stage == "list_item" and nt in NO_SPLIT_TOPICS:
            continue
        num = int(m.group("num"))
        title = ""
        for lt in LONG_TITLE_RE.finditer(text or ""):
            if int(lt.group("num")) == num:
                title = re.sub(r"\s+", " ", lt.group("title")).strip()
                break
        out.append({"stage": stage, "bill_number": num, "strong": procedural and not in_qp,
                    "pos": m.start(), "long_title": title})
    # one anchor per bill number per paragraph, keep the earliest
    best = {}
    for a in sorted(out, key=lambda x: x["pos"]):
        best.setdefault(a["bill_number"], a)
    return list(best.values())


# --------------------------------------------------------------------------- health lexicon (EN + FR)

HEALTH_TERMS = [
    # English
    "health", "hospital", "hospitals", "medical", "medicare", "physician", "physicians", "doctor", "doctors",
    "nurse", "nurses", "nursing", "drug", "drugs", "pharmac", "patient", "patients", "mental", "dental",
    "dentist", "ambulance", "long-term care", "long term care", "home care", "community care", "disease",
    "midwi", "chiropod", "optomet", "psycholog", "laborator", "blood", "organ donation", "gift of life",
    "tobacco", "smoke-free", "smoking", "vaping", "addiction", "opioid", "cancer", "epidemic", "pandemic",
    "covid", "immuniz", "vaccin", "coroner", "public health", "insured service", "ohip", "health insurance",
    "denturist", "physiotherap", "massage therap", "naturopath", "homeopath", "psychotherap", "dietitian",
    "audiolog", "occupational therap", "respiratory therap", "fluorid", "quarantine", "retirement home",
    "nursing home", "homes for the aged", "homemakers", "medical assistance in dying", "health care",
    # French (accents stripped before matching)
    "sante", "hopital", "hopitaux", "medic", "medecin", "infirmi", "medicament", "dentaire", "ambulan",
    "soins", "maladie", "sage-femme", "sages-femmes", "laboratoire", "organes", "tabac", "dependance",
    "epidemi", "pandemi", "assurance maladie", "assurance-maladie", "services sociaux", "chsld",
    "aide medicale a mourir", "fin de vie", "urgence sanitaire", "procreation", "radioprotection",
]
_HEALTH_RES = [(t, re.compile(r"\b" + re.escape(t))) for t in HEALTH_TERMS]


def health_hits(text):
    s = strip_accents(text or "").lower()
    return sorted({t for t, rx in _HEALTH_RES if rx.search(s)})


# --------------------------------------------------------------------------- language ID
# Two structurally different detectors: a function-word/diacritic count and the lingua model.
# If both are available and agree, that label is used. If they disagree, or the text is too
# short, the label is inherited from the surrounding paragraph.

EN_FUNC = set("""the of and to in is that for it with as was on be by this are have not but from at which or
an will they we their has been were would there can all its our you he she these those""".split())
FR_FUNC = set("""le la les de des du un une et est que qui pour dans pas sur au aux ce cette ces nous vous il
elle ils elles sont avec par mais ont sa son ses leur leurs plus ne se en je""".split())
_FR_CONTR = re.compile(r"(?<![a-z\u00e0-\u00ff])(?:l|d|qu|n|s|c|j)['\u2019][a-z\u00e0-\u00ff]")
_ACCENTS = re.compile(r"[\u00e0\u00e2\u00e7\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef\u00f4\u00fb\u00f9\u00fc\u00ff\u0153]")


def lang_heuristic(text):
    low = (text or "").lower()
    toks = re.findall(r"[a-z\u00e0-\u00ff]+", low)
    en = sum(t in EN_FUNC for t in toks)
    fr = sum(t in FR_FUNC for t in toks) + len(_FR_CONTR.findall(low))
    fr_score = fr + 0.5 * min(len(_ACCENTS.findall(low)), 6)
    total = en + fr_score
    if total < 2:
        return None, 0.0
    diff = (fr_score - en) / total
    if diff > 0.3:
        return "fr", round(diff, 3)
    if diff < -0.3:
        return "en", round(-diff, 3)
    return None, round(abs(diff), 3)


_LINGUA = None


def _lingua():
    global _LINGUA
    if _LINGUA is None:
        try:
            from lingua import Language, LanguageDetectorBuilder
            _LINGUA = (LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.FRENCH).build(), Language)
        except Exception:
            _LINGUA = False
    return _LINGUA


def lang_lingua(text):
    L = _lingua()
    if not L:
        return None
    det, Language = L
    r = det.detect_language_of(text or "")
    return {Language.ENGLISH: "en", Language.FRENCH: "fr"}.get(r)


def detect_lang(text, fallback):
    """Returns (lang, method). method is one of agree, heuristic_only, lingua_only,
    disagree_inherited, inherited."""
    h, _ = lang_heuristic(text)
    g = lang_lingua(text) if len(text or "") >= 15 else None
    if h and g:
        return (h, "agree") if h == g else (fallback, "disagree_inherited")
    if h:
        return h, "heuristic_only"
    if g:
        return g, "lingua_only"
    return fallback, "inherited"


# --------------------------------------------------------------------------- bill mention regexes


def fr_bill_re(num):
    return re.compile(r"projet\s+de\s+loi\s+(?:n\s*[\u00b0\u00bao]\.?\s*|num[\u00e9e]ro\s+)?" + str(int(num)) + r"(?!\d)",
                      re.I)


def en_bill_re(num):
    return re.compile(r"\bBill\s+(?:No\.\s*)?" + str(int(num)) + r"(?!\d)", re.I)


US_TYPES = [
    ("hjres", r"H\.?\s*J\.?\s*Res\.?"), ("hconres", r"H\.?\s*Con\.?\s*Res\.?"), ("hres", r"H\.?\s*Res\.?"),
    ("sjres", r"S\.?\s*J\.?\s*Res\.?"), ("sconres", r"S\.?\s*Con\.?\s*Res\.?"), ("sres", r"S\.?\s*Res\.?"),
    ("hr", r"H\.?\s*R\.?"), ("s", r"S\.?"),
]
_US_TYPE_RX = dict(US_TYPES)


def parse_us_bill(s):
    s0 = (s or "").strip()
    compact = re.sub(r"[\s.]", "", s0).lower()
    m = re.match(r"^(hjres|hconres|hres|sjres|sconres|sres|hr|s)(\d+)$", compact)
    if m:
        return m.group(1), int(m.group(2))
    for t, rx in US_TYPES:
        m = re.search(r"(?<![A-Za-z.])" + rx + r"\s*(\d+)\b", s0, re.I)
        if m:
            return t, int(m.group(1))
    return None, None


def us_bill_mention_re(btype, num):
    """OCR tolerant: matches H.R. 6164, H. R. 6164, H.R.6164, (H.R. 6164), <H.R. 6164."""
    return re.compile(r"(?<![A-Za-z.])" + _US_TYPE_RX[btype] + r"\s*" + str(int(num)) + r"(?!\d)", re.I)


# --------------------------------------------------------------------------- dates found anywhere in a record

_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}
_ISO = re.compile(r"\b(19[89]\d|20[0-3]\d)-(0[1-9]|1[0-2])-([0-3]\d)\b")
_LONG = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
                   r"\s+(\d{1,2}),\s+(\d{4})\b", re.I)


def dates_in(obj):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    out = {f"{a}-{b}-{c}" for a, b, c in _ISO.findall(s)}
    for mo, d, y in _LONG.findall(s):
        out.add(f"{int(y):04d}-{_MONTHS[mo.lower()]:02d}-{int(d):02d}")
    return out


def first_long_date(text):
    m = _LONG.search(text or "")
    if not m:
        return None
    mo, d, y = m.groups()
    return f"{int(y):04d}-{_MONTHS[mo.lower()]:02d}-{int(d):02d}"


def counter_top(c, n=5):
    return "; ".join(f"{k} ({v})" for k, v in Counter(c).most_common(n))
