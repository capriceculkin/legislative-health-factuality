#!/usr/bin/env python3
"""
extract_predications_v3.py

Bilingual version of extract_predications.py. The old script loaded one spaCy model
per jurisdiction, so French sentences in Ontario were parsed by the English model
("Tout a l'heure je vous --ai--> parler", which Spotlight then linked to
Artificial_intelligence) and English sentences in Quebec by the French model.

Here each sentence goes to the model for its own language (the lang field written by
build_sentences_v3.py), and every predication keeps language, bill_key, session and
date. The Spotlight step then uses the matching Spotlight server per predication
(see patch_dbpedia_v3.py).

Rules kept from the original extractor: root verb only, existential roots excluded
(be/have/do; etre/avoir/faire), subject from nsubj/nsubjpass/csubj, object from
dobj/obj/iobj or a prepositional/oblique object, pronoun subjects and objects removed,
subject and object must differ, hedging and negation flagged.

This is a reimplementation, so spot check 50 predications per language (Joanie for the
French ones) before the Spotlight run.

    python3 scripts/step1_debate_text/extract_predications_v3.py ontario|quebec|us|all
"""
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v3_common import rp, load_json, save_json

MODELS = {"en": "en_core_web_lg", "fr": "fr_core_news_lg"}
EXCLUDE_ROOT = {"en": {"be", "have", "do"}, "fr": {"\u00eatre", "avoir", "faire"}}
SUBJ = {"nsubj", "nsubjpass", "csubj", "nsubj:pass", "csubj:pass"}
OBJ = {"dobj", "obj", "iobj"}
OBL = {"obl", "obl:arg", "obl:mod", "obl:agent"}
DROP = {"relcl", "acl", "acl:relcl", "appos", "punct", "cc", "conj", "advcl", "parataxis", "mark", "dep"}
PRON = {
    "en": {"i", "me", "my", "mine", "we", "us", "our", "ours", "you", "your", "yours", "he", "him", "his", "she",
           "her", "hers", "it", "its", "they", "them", "their", "theirs", "this", "that", "these", "those", "who",
           "whom", "which", "what", "there", "here", "one", "someone", "somebody", "everyone", "everybody",
           "anyone", "anybody", "nobody", "none", "something", "anything", "everything", "nothing", "all", "some",
           "each", "both", "myself", "ourselves", "yourself", "yourselves", "himself", "herself", "itself",
           "themselves"},
    "fr": {"je", "j'", "me", "m'", "moi", "tu", "te", "toi", "il", "elle", "on", "nous", "vous", "ils", "elles",
           "le", "la", "les", "lui", "leur", "eux", "se", "s'", "soi", "ce", "c'", "cela", "\u00e7a", "ceci", "celui",
           "celle", "ceux", "celles", "qui", "que", "qu'", "quoi", "dont", "lequel", "laquelle", "lesquels",
           "lesquelles", "y", "en", "tout", "tous", "toutes", "rien", "personne", "quelqu'un", "chacun", "aucun",
           "certains", "plusieurs", "l'un", "l'autre"},
}
HEDGE = {"en": {"may", "might", "could", "would", "should", "possibly", "perhaps", "probably", "likely", "suggest",
                "appear", "seem", "believe", "think"},
         "fr": {"pouvoir", "devoir", "peut-\u00eatre", "probablement", "sembler", "para\u00eetre", "croire", "penser",
                "pourrait", "pourraient", "devrait", "devraient", "sans doute", "vraisemblablement"}}
NEG_FR = {"ne", "n'", "pas", "jamais", "plus", "aucunement", "nullement"}


# PATCHED_CLAIMS_V17_2026_10_08: subject, verb and object rules worked out on 1,380 real parsed sentences
# (fix15 and fix16 folded in). See outputs/audit/claim_rules_v17.txt for what each rule does.
HYPHENS = {"-", "‐", "‑"}
ADDRESS = re.compile(r"^(?:(?:Mr|Mrs|Ms|Madam|Madame)\.?\s+(?:Speaker|Chairman|Chairwoman|Chair|President|Clerk)"
                     r"(?:\s+pro\s+tempore)?|(?:M\.|Mme|Monsieur|Madame)\s+(?:le|la)\s+(?:Présidente?|"
                     r"Vice-Présidente?))$", re.I)
RECOVER = {"appos", "dep", "conj", "nsubj", "nsubjpass", "nsubj:pass", "nmod", "npadvmod", "flat"}
NOUNISH = {"NOUN", "PROPN", "PRON", "NUM"}
OBJ_HEAD = {"NOUN", "PROPN", "PRON", "NUM", "X", "SYM", "VERB"}
FILLER = {"en": set(), "fr": {"là"}}
PRON["fr"] = PRON["fr"] | {"l'", "l’", "j’", "m’", "s’", "c’", "qu’"}
# phrases that are never part of a claim (discourse words); a child whose words are exactly one of these is left out
IDIOM = {
    "en": {"in fact", "of course", "for example", "for instance", "in addition", "in particular", "in general",
           "in other words", "at present", "at least", "after all", "by the way", "in turn", "as well", "indeed",
           "however", "therefore", "moreover", "furthermore", "also", "again", "still", "really", "please"},
    "fr": {"en fait", "d'ailleurs", "d’ailleurs", "par ailleurs", "entre autres", "en effet", "en même temps",
           "dans le fond", "de la même façon", "de toute façon", "par exemple", "en outre", "au fond",
           "bien sûr", "en tout cas", "quand même", "là", "donc", "alors", "aussi", "d'abord", "d’abord",
           "finalement", "justement", "évidemment", "malheureusement", "notamment", "effectivement",
           "à cet égard", "en ce sens", "en terminant", "au contraire", "par contre", "en somme", "peut-être"},
}
# heads of prepositional phrases that are time, counts or set phrases, not what the verb is about
TIME = {
    "en": {"year", "years", "month", "months", "week", "weeks", "day", "days", "time", "times", "minute", "minutes",
           "hour", "hours", "today", "tonight", "tomorrow", "yesterday", "morning", "afternoon", "evening", "night",
           "moment", "decade", "decades", "century", "session", "period", "ago", "january", "february", "march",
           "april", "may", "june", "july", "august", "september", "october", "november", "december", "monday",
           "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "end", "beginning", "start", "fact",
           "addition", "regard", "respect", "order", "terms", "way", "part", "case", "event", "spite", "light",
           "behalf", "view", "result", "entirety", "trouble", "point", "sense", "favor", "favour", "front", "place", "advance",
           "particular", "general", "short", "sum"},
    "fr": {"an", "ans", "année", "années", "mois", "jour", "jours", "semaine", "semaines", "heure", "heures",
           "minute", "minutes", "temps", "moment", "fois", "matin", "soir", "soirée", "nuit", "siècle",
           "décennie", "session", "période", "janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre", "décembre", "lundi", "mardi", "mercredi",
           "jeudi", "vendredi", "samedi", "dimanche", "aujourd'hui", "aujourd’hui", "fait", "cause", "lieu",
           "fonction", "vertu", "effet", "façon", "manière", "terme", "termes", "cas", "suite", "part",
           "ailleurs", "outre", "fond", "sens", "date", "papier", "égard", "point", "plan", "niveau", "matière",
           "cadre", "rapport", "raison", "titre", "faveur", "contre", "lors", "attendant", "début", "fin",
           "instant", "occasion", "ordre"},
}
TIME_PREP = {"en": {"during", "since", "until", "till", "throughout", "ago", "after", "before", "despite"},
             "fr": {"depuis", "pendant", "durant", "avant", "après", "dès", "jusqu'", "jusque", "jusqu’",
                    "lors", "malgré", "selon", "quant"}}
NEG_FR_REAL = {"pas", "jamais", "plus", "aucunement", "nullement", "point", "guère", "rien", "personne",
               "aucun", "aucune", "nul", "nulle", "ni"}
MODAL_FR = {"pouvoir", "devoir", "vouloir", "aller", "savoir", "falloir"}
LINK = {"cause", "raison", "suite", "faveur", "moyen", "lieu", "vertu", "fonction", "part", "titre"}
# PATCHED_CLAIMS_V19: rules for the error types found in the 100-claim spot check (claim_rules_v19.txt)
LEGAL_EN = re.compile(r"\b(?:is|are)\s+(?:hereby\s+|further\s+)?(?:amended|repealed|redesignated)\b|\bby\s+(?:striking|inserting)\b")
LEGAL_EN_CS = re.compile(r"\bCurrent Law\b|^\W*SEC\.\s*\d")         # case matters: "under current law" is speech
LEAD_PREP = re.compile(r"^(?:dans|à|au|aux|de|du|des|par|pour|sur|sous|avec|selon|in|on|at|for|with|by|from|under|of)\s", re.I)
STATUTE_SUBJ = re.compile(r"^\W*\d+[a-z]?\(|\d+[a-z]?\([a-z0-9]{1,4}\)")
CAPS_RUN = re.compile(r"\b[A-Z]{4,}\s+[A-Z]{4,}\b")
REL_SUBJ = {"en": re.compile(r"\b(?:whom|which|whose|who)\b", re.I),
            "fr": re.compile(r"\b(?:dont|lequel|laquelle|lesquels|lesquelles|auquel|auxquels|duquel)\b", re.I)}
QUANT_FR = {"plupart", "majorité", "nombre", "ensemble", "moitié", "tiers", "quart", "partie", "totalité", "reste",
            "minorité", "centaine", "dizaine", "millier", "million", "milliard", "pourcentage", "proportion", "série",
            "foule", "groupe", "multitude", "infinité", "quantité", "masse", "majorite", "%"}
LVC_FR = {"place", "considération", "compte", "charge", "oeuvre", "œuvre", "vigueur", "cause", "question", "évidence",
          "valeur", "marche", "fin", "part", "partie", "suite", "lieu", "face", "note", "acte", "connaissance",
          "conscience", "parole", "position", "soin", "appel", "recours", "confiance", "effet", "foi", "peur", "besoin",
          "raison", "tort", "envie", "honte", "preuve", "attention", "garde", "avantage", "mesure", "état", "cours", "jour",
          "pied", "fonction", "défaut"}
TELL_EN = {"tell", "inform", "remind", "assure", "warn", "notify", "advise", "promise", "convince", "persuade", "teach",
           "reassure", "show"}
PREVENT_EN = {"prevent", "stop", "keep", "protect", "prohibit", "ban", "discourage", "bar", "block", "deter", "exclude",
              "exempt", "shield", "save", "free", "release", "spare", "preclude"}
FACT_HEAD = {"fait", "fact", "idée", "idea", "notion", "possibilité", "possibility"}
QTY = re.compile(r"^[$€£]?\s?[\d.,]+\s*(?:%|percent|per cent|\$)?$", re.I)
ENUM = re.compile(r"^(?:[A-Za-z]{1,2}|[ivxlcdmIVXLCDM]{1,5}|\d{1,3})$")


def norm(s):
    return " ".join(s.lower().replace("’", "'").split())


def filler(tok, lang):
    doc = tok.doc
    joined = (not tok.whitespace_ and tok.i + 1 < len(doc) and doc[tok.i + 1].text in HYPHENS) or (
        tok.i > 0 and doc[tok.i - 1].text in HYPHENS and not doc[tok.i - 1].whitespace_)
    return tok.lower_ in FILLER.get(lang, set()) and not joined


def name_span(tok):
    """(start, end) of a word's own name: the words right next to it in its subtree (hyphenated words kept whole)."""
    inside = {t.i for t in tok.subtree
              if not (t.pos_ == "PUNCT" or t.dep_ == "punct") or (t.text in HYPHENS and not t.whitespace_)}
    inside.add(tok.i)
    start, end = tok.i, tok.i
    while start - 1 in inside:
        start -= 1
    while end + 1 in inside:
        end += 1
    return start, end


def label_info(tok):
    """("label", end) for a speaker label followed by a colon, ("address", end) for a form of address followed by a
    comma, (None, end) otherwise."""
    doc = tok.doc
    start, end = name_span(tok)
    j = end + 1
    if j < len(doc) and doc[j].text == "(":          # "Le Vice-President (M. Bissonnet):"
        depth = 0
        while j < len(doc):
            depth += doc[j].text == "("
            depth -= doc[j].text == ")"
            if depth == 0:
                break
            j += 1
        j += 1
    if j < len(doc) and doc[j].text == ":":
        return "label", end
    if j < len(doc) and doc[j].text == "," and ADDRESS.match(" ".join(doc[start:end + 1].text.split())):
        return "address", end
    words = [t for t in tok.subtree if not (t.pos_ == "PUNCT" or t.dep_ == "punct")] or [tok]
    last = max(t.i for t in words)
    if last + 1 < len(doc) and doc[last + 1].text == ":":
        return "label", end
    return None, end


def label_or_address(tok):
    return label_info(tok)[0] is not None


def is_address(tok):
    start, end = name_span(tok)
    return bool(ADDRESS.match(" ".join(tok.doc[start:end + 1].text.split())))


def is_idiom(tok, lang):
    words = [t for t in tok.subtree if not (t.pos_ == "PUNCT" or t.dep_ == "punct")]
    return bool(words) and norm(" ".join(t.text for t in words)) in IDIOM.get(lang, set())


def heading(tok):
    """A statute heading or list marker taken as the subject: "(A) Eligibility ...", "COMPLETION OF FUNCTIONS"."""
    start, end = name_span(tok)
    doc = tok.doc
    if any(".--" in t.text or ".-" in t.text or t.text in ("--", ".--") for t in tok.subtree if t.i <= end + 1):
        return True
    if any(re.search(r"-(?:The|A|An|In|This|Each|Any|No|Not)$", t.text) or re.search(r"-(?:The|A|An|In|This|Each|Any|No|Not)$",
                                                                                         t.text + (doc[t.i + 1].text if t.i + 1 < len(doc) and not t.whitespace_ else ""))
           for t in doc[start:end + 1]):
        return True
    if doc[start].i != tok.i and doc[start].text.lower() in ("i", "ii", "iii", "iv", "vi", "vii", "viii", "ix"):
        return True
    caps = [t for t in tok.doc[start:end + 1] if t.text.isalpha() and len(t.text) >= 6 and t.text.isupper()]
    return len(caps) >= 2


def vocative(tok, root):
    """"The honourable member for Oriole, please resume ...": a name before a comma, with a verb giving an order."""
    start, end = name_span(tok)
    doc = tok.doc
    if end + 1 >= len(doc) or doc[end + 1].text != ",":
        return False
    if is_address(tok):
        return True
    has_aux = any(c.dep_ in ("aux", "auxpass", "aux:pass", "aux:tense") for c in root.children)
    return root.tag_ == "VB" and not has_aux


THIRD = {"en": {"he", "she", "it", "they"}, "fr": {"il", "elle", "ils", "elles"}}


def finite(root):
    for c in [root] + [c for c in root.children if c.dep_.startswith("aux")]:
        if "Fin" in c.morph.get("VerbForm"):
            return c
    return None


def agrees(subj, root):
    """False when a pronoun cannot be the subject of this verb ("nous a permis": "nous" goes with "avons")."""
    if subj.pos_ != "PRON":
        return True
    v = finite(root)
    if v is None:
        return True
    for f in ("Person", "Number"):
        a, b = subj.morph.get(f), v.morph.get(f)
        if a and b and a != b:
            return False
    return True


def topic(tok):
    first = next(iter(tok.subtree))
    return first.lower_ in ("quant", "concernant") or norm(first.text) == "as"


def span_text(tok, max_tokens=15, lang=None, subject=False, keep_conj=False):
    keep = []
    if tok.dep_ in ("prep", "agent") and lang == "en":
        g = next((g for g in tok.children if g.dep_ == "pobj"), None)
        if g is not None:
            inner = span_text(g, max_tokens, lang)
            pre = " ".join(c.text for c in tok.children if c.dep_ == "advmod" and c.i < tok.i and c.lower_ in ("only", "not"))
            return ((pre + " ") if pre else "") + tok.text + " " + inner if inner else ""

    def walk(t):
        keep.append(t)
        for ch in t.children:
            if subject and t is tok and ch.i < tok.i and ch.dep_ not in ("det", "case", "amod", "compound", "nummod",
                                                                      "poss", "flat", "flat:name", "fixed", "det:poss",
                                                                      "quantmod", "nmod:poss") \
                    and (next(iter(ch.subtree)).pos_ in ("ADP", "SCONJ", "CCONJ")
                         or ch.dep_ in ("npadvmod", "advmod", "obl:mod", "nmod:tmod", "mark", "cc")):
                continue                             # "dans l'essentiel, ce projet de loi", "last year": not the subject
            if subject and t is tok and ch.i > tok.i and next(iter(ch.subtree)).i > 0 \
                    and tok.doc[next(iter(ch.subtree)).i - 1].text == "," \
                    and (ch.dep_ in ("npadvmod", "advmod", "appos", "amod", "acl", "nmod:tmod", "obl:mod", "parataxis", "dep")
                         or (lang == "en" and ch.dep_ == "prep")):
                continue                             # "This bill, thanks to ..., meets": set off by commas
            if ch.dep_ in ("mark", "case") and t is not tok and ch.i > tok.i:
                keep.extend(ch.subtree)              # "le meme langage que celui": keep the small words inside
                continue
            if keep_conj and t is tok and ch.dep_ == "conj" and ch.i > tok.i:
                walk(ch)                             # "la pauvrete et la mauvaise sante forment": both are the subject
                continue
            if ch.dep_ in ("conj", "cc") and t.text[:1].isupper() and (
                    ch.text[:1].isupper() if ch.dep_ == "conj" else any(
                        g.dep_ == "conj" and g.text[:1].isupper() and g.i > ch.i for g in t.children)):
                walk(ch)                             # "Health Resources and Services Administration": one name
                continue
            if ch.dep_ in ("acl",) and ch.i == t.i + 1 and not [g for g in ch.children if g.dep_ != "punct"]:
                keep.append(ch)                      # "par annee perdue", "Les modifications proposees"
                continue
            if ch.dep_ in DROP:
                continue
            if lang and (is_idiom(ch, lang) or filler(ch, lang)):
                continue
            if is_address(ch) and ch.i != tok.i:     # "l'Association des hopitaux du Quebec, Mme la Presidente,"
                continue
            walk(ch)
    walk(tok)
    keep.sort(key=lambda t: t.i)
    # no small word dangling at either end ("assurances satisfactory to the Secretary that", "que l'honorable depute")
    while len(keep) > 1 and keep[-1] is not tok and (keep[-1].pos_ in ("SCONJ", "CCONJ", "ADP", "DET", "PUNCT")
                                                    or keep[-1].dep_ in ("punct", "cc", "mark", "case")):
        keep.pop()
    while len(keep) > 1 and keep[0] is not tok and (keep[0].pos_ in ("SCONJ", "CCONJ", "PUNCT")
                                                   or keep[0].dep_ in ("punct", "cc", "mark")):
        keep.pop(0)
    if len(keep) > max_tokens:
        # first cut at the first comma after the head ("the practice of cashing in on accumulated sick days, of ...")
        comma = next((j for j in range(tok.i + 1, keep[-1].i) if tok.doc[j].text in (",", ";")), None)
        if comma is not None and len([t for t in keep if t.i < comma]) >= 2:
            keep = [t for t in keep if t.i < comma]
    if len(keep) > max_tokens:
        # leave out whole phrases, the farthest from the head first, so no phrase is cut in the middle
        ids = {t.i for t in keep}
        kids = sorted((c for c in keep if c.head.i in ids and c.i != tok.i and c.head.i == tok.i),
                      key=lambda c: -abs(c.i - tok.i))
        for c in kids:
            if len(ids) <= max_tokens:
                break
            if c.dep_ in ("det", "case", "compound", "amod", "nummod", "poss", "flat", "flat:name", "fixed"):
                continue
            ids -= {t.i for t in c.subtree}
        keep = [t for t in keep if t.i in ids]
        if len(keep) > max_tokens:
            keep = [t for t in keep if abs(t.i - tok.i) <= 6]
    # join with the sentence's own spacing; a left-out comma or dash becomes a space; hyphenated words stay whole
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
    out = " ".join(out.split())
    out = out.strip(" ,;:«»\"'`-()[]")
    words = out.split()
    while len(words) > 1 and words[-1].lower() in ("over", "above", "in", "on", "for", "with", "by", "from", "at", "into",
                                                    "under", "about", "as", "of", "to", "the", "a", "an", "and", "or",
                                                    "dans", "sur", "pour", "par", "avec", "de", "du", "des", "et", "ou"):
        words.pop()
    return " ".join(words)


def is_pron(tok, text, lang):
    return tok.pos_ == "PRON" or tok.lower_ in PRON[lang] or text.lower() in PRON[lang]


def adjunct(prep, head, lang):
    """A prepositional phrase that tells when, how long, or is a set phrase ("in fact", "a cause"), not what about."""
    if head is None or head.pos_ not in OBJ_HEAD or (head.pos_ == "VERB" and head.tag_ != "VBG"):
        return True
    p = norm(prep.text) if prep is not None else ""
    if p in TIME_PREP.get(lang, set()):
        return True
    if head.pos_ == "NUM" or head.lower_ in TIME.get(lang, set()) or head.lemma_.lower() in TIME.get(lang, set()):
        return True
    if any(c.dep_ == "nummod" and c.i < head.i and head.lower_ in TIME.get(lang, set()) for c in head.children):
        return True
    return False


def after_colon(root, tok):
    """True when a colon or opening quote stands between the verb and this word (the speech starts there)."""
    a, b = sorted((root.i, tok.i))
    doc = root.doc
    for j in range(a + 1, b):
        if doc[j].text in ("«", "“"):
            return True
        if doc[j].text == ":" and j + 1 < len(doc) and (doc[j + 1].text in ("«", "“", '"', "``", "`")
                                                         or doc[j + 1].text[:1].isupper()):
            return True
    return False


def pick_object(verb, lang, after_only, skip=()):
    """(object token, text, path) for one verb: its direct object, else a prepositional phrase after it."""
    objs = [c for c in verb.children if c.dep_ in OBJ and c not in skip and not filler(c, lang) and not is_idiom(c, lang)
            and (c.pos_ in OBJ_HEAD or (c.pos_ in ("ADJ", "DET", "ADV") and any(
                g.dep_.split(":")[0] in ("prep", "nmod", "obl", "pobj") for g in c.children))) and not after_colon(verb, c)]
    objs.sort(key=lambda c: (c.dep_ == "iobj", c.i))
    if objs:
        o = objs[0]
        text = span_text(o, lang=lang)
        # "e-cigarettes" split into three objects: put the hyphenated word back together
        nxt = o
        while True:
            j = nxt.i + 1
            sib = next((c for c in verb.children if c.i == j and c.dep_ in OBJ), None)
            if sib is None or nxt.whitespace_:
                break
            text += sib.text if not text.endswith(sib.text) else ""
            nxt = sib
        return o, text, "obj"
    # a verb whose real object is a clause ("proposait que le Quebec se dote ...") or a pronoun ("made them happy")
    # gets no object from a prepositional phrase, which would only say where or how
    def clause_object(c):
        if c.dep_ != "ccomp" or c.i < verb.i:
            return False
        if lang == "fr":
            return True
        return not any(verb.doc[j].text in (",", ";", "--") for j in range(verb.i + 1, next(iter(c.subtree)).i))
    if any(clause_object(c) for c in verb.children) or any(c.dep_ in OBJ and c.pos_ == "PRON" for c in verb.children):
        return None, None, None
    cands = []
    for c in verb.children:
        if after_only and c.i < verb.i:          # an opening phrase ("In fact,", "At present,") is not the object
            continue
        if c in skip or after_colon(verb, c) or is_idiom(c, lang) or filler(c, lang):
            continue
        if lang == "en" and c.dep_ in ("prep", "agent"):
            g = next((g for g in c.children if g.dep_ == "pobj"), None)
            if g is not None and not adjunct(c, g, lang):
                cands.append((1, c.i, g, span_text(c, lang=lang)))
        elif c.dep_ in OBL:
            case = next((g for g in c.children if g.dep_ == "case"), None)
            if not adjunct(case, c, lang):
                rank = {"obl:arg": 0, "obl:agent": 1, "obl": 1}.get(c.dep_, 2)
                cands.append((rank, c.i, c, span_text(c, lang=lang)))
    if cands:
        cands.sort(key=lambda x: (x[0], x[1]))
        tok, text = cands[0][2], cands[0][3]
        first = next(iter(tok.subtree)).i
        for c in verb.children:
            if c.dep_ in OBL and c.i < tok.i and c.lemma_.lower() in LINK and max(t.i for t in c.subtree) == first - 1:
                text = span_text(c, lang=lang) + " " + text
        return tok, text, "prep"
    return None, None, None


def verb_words(verb, lang, extra=()):
    """The verb as written, with its particle ("pushed through") and French reflexive ("s'eleve")."""
    ws = [verb] + [c for c in verb.children if c.dep_ in ("prt", "compound:prt")]
    if lang == "fr":
        ws += [c for c in verb.children if c.dep_ in ("expl:comp", "expl:pass", "expl", "expl:pv") and c.i == verb.i - 1]
        ws += [c for c in verb.children if c.dep_ == "aux:caus" and c.i < verb.i]      # "faire valoir", "fait diminuer"
    ws += list(extra)
    ws = sorted(set(ws), key=lambda t: t.i)
    out = ""
    for k, t in enumerate(ws):
        out += ("" if k == 0 or (ws[k - 1].i + 1 == t.i and not ws[k - 1].whitespace_) else " ") + t.text
    return out


def clause_text(head, max_tokens=15, keep_mark=False):
    """The words of a clause in order ("he wouldn't survive 24 hours"), cut at the first comma, at most 15 words."""
    toks = [t for t in head.subtree if not (t.pos_ == "PUNCT" or t.dep_ == "punct") or t.text in HYPHENS or "'" in t.text]
    if not keep_mark:
        while toks and toks[0].dep_ == "mark" and toks[0].head is head:
            toks.pop(0)
    if not toks:
        return ""
    doc = head.doc
    out = []
    for t in toks:
        if out and any(doc[j].text in (",", ";", ":") for j in range(out[-1].i + 1, t.i)):
            break
        if out and t.dep_ == "cc" and t.head.head is head and t.head.dep_ == "conj":
            break                            # "... administre a cet animal et pour lequel ...": the first part only
        out.append(t)
        if len(out) >= max_tokens:
            break
    while len(out) > 1 and (out[-1].pos_ in ("ADP", "CCONJ", "SCONJ", "DET", "PRON") and out[-1].lower_ in (
            "et", "ou", "and", "or", "pour", "de", "à", "par", "lequel", "laquelle", "qui", "que", "dont", "the", "a",
            "to", "of", "for", "which", "that", "in", "on") or out[-1].dep_ in ("cc", "case", "mark")):
        out.pop()
    txt = ""
    for k, t in enumerate(out):
        txt += ("" if k == 0 else (out[k - 1].whitespace_ if t.i == out[k - 1].i + 1 else " ")) + t.text
    return " ".join(txt.split()).strip(" ,;:«»\"'`()[]")


def verb_number(root):
    v = finite(root)
    return v.morph.get("Number") if v is not None else []


def chain_of(x, lang):
    """The words that join a second verb to the first: "seeks to strip", "vise a donner", "veulent se retrouver"."""
    out = [x] + [c for c in x.children if c.dep_ in ("aux", "mark", "prt", "compound:prt") and c.i < x.i
                 and c.lower_ in ("to", "de", "d'", "d’", "à")]
    if lang == "fr":
        out += [c for c in x.children if c.dep_ in ("expl:comp", "expl:pv", "expl", "expl:pass") and c.i < x.i]
    return out


recovered_tail = []


def _extract_one(sent, lang):
    root = sent.root
    if root.pos_ not in ("VERB", "AUX") or root.lemma_.lower() in EXCLUDE_ROOT[lang]:
        return None
    if lang == "fr" and (root.lemma_.lower() in ("falloir", "voilà", "voici") or root.lower_ in ("voilà", "voici")
                         or (root.lemma_.lower() == "agir" and any(c.lower_ in ("s'", "s’", "se") for c in root.children))):
        return None                          # "il faut", "il s'agit", "voila": no one does anything to anything
    if "Imp" in root.morph.get("Mood"):
        return None                          # an order ("votez pour le principe") has no subject
    # subject: of the subjects of the verb, the one nearest before it, leaving out speaker labels, forms of address,
    # names called out ("Friends, ..."), topics ("Quant a ..."), statute headings and filler words
    cands = [c for c in root.children if c.dep_ in SUBJ]
    ok = [c for c in cands if not label_or_address(c) and not filler(c, lang) and not vocative(c, root)
          and not topic(c) and not heading(c)]
    ok = [c for c in ok if agrees(c, root)]
    before = [c for c in ok if c.i < root.i]
    subj = before[-1] if before else (ok[0] if ok else None)
    if lang == "fr" and subj is not None and len(before) > 1 and subj.pos_ == "PRON" and subj.lower_ in THIRD["fr"]:
        named = [c for c in before[:-1] if c.pos_ in ("NOUN", "PROPN")
                 and not any(g.dep_ in ("conj", "appos") for g in c.children)]
        if named:
            subj = named[-1]                 # "Les maires des villes ..., ils sont venus": the name is the subject
    if subj is None:
        # "Mr. Chair, communities ... continue": the real subject hangs off the address
        for c in cands:
            kind, end = label_info(c)
            if kind == "address":
                subj = next((g for g in c.children if g.dep_ in RECOVER and end < g.i < root.i
                             and g.pos_ in NOUNISH and not label_or_address(g)), None)
                if subj is not None:
                    more = [g for g in c.children if g.dep_ in RECOVER and g.i > subj.i and g.i < root.i]
                    if more and (more[0].i == max(t.i for t in subj.subtree) + 1 or (
                            lang == "fr" and more[0].dep_ == "conj" and any(g.dep_ == "cc" for g in more[0].children)
                            and next(iter(more[0].subtree)).i == max(t.i for t in subj.subtree) + 1)):
                        recovered_tail[:] = [more[0]]
            if subj is not None:
                break
    if subj is None:
        return None
    tail = list(recovered_tail)
    recovered_tail[:] = []
    keep_conj = False
    if lang == "fr" and subj.pos_ in ("NOUN", "PROPN") and subj.lemma_.lower() not in QUANT_FR \
            and not any(c.dep_ == "nummod" for c in subj.children):
        sn, vn = subj.morph.get("Number"), verb_number(root)
        if sn and vn and sn != vn and not tail:
            if sn == ["Sing"] and vn == ["Plur"] and any(c.dep_ == "conj" and c.i > subj.i for c in subj.children):
                keep_conj = True             # "X et Y forment": both are the subject
            else:
                return None                  # the verb does not go with this word: the parse put the subject elsewhere
    start = name_span(subj)[0]
    doc0 = subj.doc
    if start >= 2 and doc0[start - 1].text in HYPHENS and not doc0[start - 1].whitespace_ and not doc0[start - 2].whitespace_:
        return None                          # "Coeur" out of "l'Hopital du Sacre-Coeur": half a name
    # object: the verb's own object; else, when the verb hands over to another ("seeks to strip", "doivent
    # permettre"), that verb's object; else a prepositional phrase after the verb, with its preposition
    content, chain = root, []
    obj, o, path = pick_object(root, lang, after_only=True)
    x0 = next((x for x in root.children if x.dep_ == "xcomp" and x.i > root.i and x.pos_ == "VERB"), None)
    if path == "obj" and x0 is not None and obj is not None and obj.i > x0.i:
        xo, xt, xp = pick_object(x0, lang, after_only=True)
        if xo is None or xp != "obj":
            xo, xt, xp = obj, o, path        # the parser hung the second verb's object on the first
        content, chain = x0, chain_of(x0, lang)
        obj, o, path = xo, xt, xp
    if lang == "fr" and root.lemma_.lower() in MODAL_FR:
        # "le gouvernement pourra designer, par reglement, les maladies": the parser often hangs the object on the
        # modal verb; the claim is about the second verb
        x = next((x for x in root.children if x.dep_ == "xcomp" and x.i > root.i and x.pos_ == "VERB"), None)
        if x is not None:
            xo, xt, xp = pick_object(x, lang, after_only=True)
            if xp != "obj":
                dep = next((c for c in root.children if c.dep_ in ("dep", "obj") and c.i > x.i and c.pos_ in ("NOUN", "PROPN")
                            and not after_colon(root, c)), None)
                if dep is not None:
                    xo, xt, xp = dep, span_text(dep, lang=lang), "obj"
            if xo is not None and (xp == "obj" or path != "obj"):
                content = x
                chain = [x] + [c for c in x.children if c.dep_ in ("mark",) and c.i < x.i] + \
                        [c for c in x.children if c.dep_.startswith("aux") and root.i < c.i < x.i] + \
                        [c for c in x.children if c.dep_ in ("expl:comp", "expl:pv", "expl", "expl:pass") and c.i < x.i]
                obj, o, path = xo, xt, xp
    if path != "obj":
        for x in root.children:
            if x.dep_ == "xcomp" and x.i > root.i and x.pos_ in ("VERB", "AUX", "ADJ"):
                xo, xt, xp = pick_object(x, lang, after_only=True)
                if xo is not None and (obj is None or xp == "obj"):
                    content = x
                    chain = chain_of(x, lang)
                    obj, o, path = xo, xt, xp
                break
    lvc = []
    if lang == "fr":
        for c in content.children:
            if c.i > content.i and c.i - content.i <= 3 and c.pos_ == "NOUN" and c.lemma_.lower() in LVC_FR \
                    and not any(g.dep_ in ("det", "nummod", "amod", "nmod", "det:poss") for g in c.children) \
                    and all(g.dep_ == "case" and g.lower_ == "en" for g in c.children) and len(list(c.subtree)) <= 2:
                lvc = list(c.subtree)        # "mis en place", "tient compte", "prenait en consideration"
                break
        if lvc:
            chain = chain + lvc
            if obj is not None and obj in lvc:
                no, nt, np_ = pick_object(content, lang, after_only=True, skip=set(lvc))
                if no is not None and nt:
                    obj, o, path = no, nt, np_
                else:
                    chain = [t for t in chain if t not in lvc]   # "la loi prendrait fin": nothing else to be the object
        if content is root and path != "obj" and root.lemma_.lower() in ("devoir", "pouvoir"):
            return None                      # "Des verifications devraient ... sans avertissement": the real verb is lost
    if obj is None or not o or not o.split() or o.split()[-1].lower() == "ago":   # an object of only stripped words: no claim
        return None
    if lang == "en" and path == "obj" and content.lemma_.lower() in TELL_EN:
        cc = next((c for c in content.children if c.dep_ == "ccomp" and c.i > obj.i), None)
        if cc is not None and any(content.doc[j].text in ('"', "“", "``", "'", "‘", "«") for j in
                                  range(content.i + 1, next(iter(cc.subtree)).i + 1)):
            return None                      # 'told me one time, "You know, ..."': a quotation
        if cc is not None:
            o = clause_text(cc) or o         # "Doctors told Nick's family he wouldn't survive": the message is the object
    if lang == "en" and path == "obj" and QTY.match(o):
        pp = next((c for c in content.children if c.dep_ == "prep" and c.i > obj.i and c.lower_ in
                   ("from", "of", "on", "in", "to", "for")), None)
        if pp is not None and span_text(pp, lang=lang):
            o += " " + span_text(pp, lang=lang)          # "cut 30% from WSIB payments"
    if lang == "en" and path == "obj" and content.lemma_.lower() in PREVENT_EN:
        pp = next((c for c in content.children if c.dep_ == "prep" and c.lower_ == "from" and c.i > obj.i), None)
        if pp is not None:
            o += " " + clause_text(pp, max_tokens=10, keep_mark=True)   # "prevent a lot of people from ever going ..."
    if obj is not None and obj.lemma_.lower() in FACT_HEAD:
        cl = next((c for c in obj.children if c.dep_ in ("acl", "ccomp", "acl:relcl") and c.i > obj.i
                   and any(g.dep_ == "mark" and g.lower_ in ("que", "qu'", "qu’", "that") for g in c.children)), None)
        if cl is None:
            return None                      # "souligne le fait": the fact itself is missing
        o = o + " " + clause_text(cl, max_tokens=12, keep_mark=True)
    s = span_text(subj, lang=lang, subject=True)
    if any(t.pos_ in ("AUX", "VERB") and "Fin" in t.morph.get("VerbForm") and t.i != subj.i
           for t in subj.subtree if t.text in s.split() and t.head.i == subj.i):
        return None                          # "La mairesse est en train ...": a whole clause, not a subject
    if tail:
        if tail[0].dep_ == "conj" and any(g.dep_ == "cc" for g in tail[0].children):
            s += " " + clause_text(tail[0], max_tokens=8, keep_mark=True)    # "la pauvrete et la mauvaise sante"
        else:
            s += " " + span_text(tail[0], lang=lang)
    if not s or not o or s.lower() == o.lower() or is_pron(subj, s, lang) or is_pron(obj, o, lang):
        return None
    if lang == "en":
        acl = next((c for c in subj.children if c.dep_ == "acl" and c.i == subj.i + 2 and
                    any(g.lower_ == "to" and g.i == subj.i + 1 for g in c.children)), None)
        if acl is not None and s.split()[-1] == subj.text and len([t for t in acl.subtree if t.pos_ != "PUNCT"]) <= 8:
            s = s + " " + clause_text(acl, max_tokens=8, keep_mark=True)   # "My right to swing my arm", only when whole
    if lang == "en" and (LEGAL_EN.search(sent.doc.text) or LEGAL_EN_CS.search(sent.doc.text)):
        return None                          # statute text read into the record ("is amended ... by striking")
    first_w = next((t for t in sorted(subj.subtree, key=lambda t: t.i) if t.text == s.split()[0]), None)
    if first_w is not None and first_w.pos_ == "ADP" and LEAD_PREP.match(s):
        return None                          # "dans l'essentiel ce projet de loi": a phrase, not the subject
    if STATUTE_SUBJ.search(s) or CAPS_RUN.search(s) or REL_SUBJ[lang].search(s):
        return None                          # "1395m(m)(7)(B)(i", "E. COST SHARING ...", "most of whom"
    if o.lower() in ("là", "l'", "l’") or o.split()[-1].lower() == "ago":
        return None                          # the same test as before, now on the finished object (v19 lengthens some)
    if lang == "fr" and re.match(r"^(?:on|lorsqu|quand|si|parce)\b", o, re.I):
        return None                          # the object is a clause ("lorsqu'on entre dans une loi")
    words = {t.lemma_.lower() for t in sent} | {t.lower_ for t in sent}
    hedged = bool(words & HEDGE[lang])
    if lang == "fr":
        first_v = min([root.i] + [c.i for c in root.children if c.dep_.startswith("aux")])
        doc = root.doc
        ne = [j for j in range(max(0, first_v - 3), first_v) if doc[j].lower_ in ("ne", "n'", "n’")]
        negated = False
        if ne:
            for j in range(ne[0] + 1, min(len(doc), max(root.i, content.i) + 4)):
                w = doc[j].lower_
                if w in ("que", "qu'", "qu’"):
                    break
                if w in NEG_FR_REAL and not (w == "plus" and j + 1 < len(doc) and doc[j + 1].lower_ in ("de", "d'", "d’")):
                    negated = True
                    break
    else:
        negated = any(c.dep_ == "neg" for c in root.children) or (
            content is not root and any(c.dep_ == "neg" for c in content.children))
    verb = verb_words(root, lang, extra=chain + ([c for c in content.children if c.dep_ in ("prt", "compound:prt")]
                                                   if content is not root else []))
    lemma = content.lemma_.lower()
    prt = [c for c in content.children if c.dep_ in ("prt", "compound:prt")]
    if prt:
        lemma += " " + " ".join(c.lower_ for c in prt)
    if any(w[:1].isupper() for w in verb.split()[1:]):
        return None                          # "dit Bon": a quoted word taken into the verb
    return {"subject": s, "verb": verb, "verb_lemma": lemma, "object": o,
            "hedged": hedged, "negated": negated}


# PATCHED_QUESTIONS_V18: a sentence that is itself a question gives no claim (outputs/audit/claim_rules_v17.txt, v18)
_END = "»”\"')]} .,;"
_EN_Q = {"does", "do", "did", "is", "are", "was", "were", "will", "would", "can", "could", "should", "shall", "has",
         "have", "had", "may", "might", "must", "why", "what", "who", "whom", "whose", "which", "where", "when", "how",
         "isn't", "aren't", "doesn't", "don't", "didn't", "wasn't", "weren't", "won't", "wouldn't", "can't",
         "couldn't", "shouldn't", "hasn't", "haven't", "hadn't"}
_FR_Q = {"pourquoi", "comment", "quand", "où", "qui", "quel", "quelle", "quels", "quelles", "combien", "que", "qu'",
         "qu’", "est-ce", "lequel", "laquelle", "lesquels", "lesquelles"}
_FR_INV = re.compile(r"\w-(?:t-)?(?:il|elle|ils|elles|on|je|tu|nous|vous)\b", re.I)
_FR_ESTCE = re.compile(r"\best-ce\s+qu", re.I)


def _lead_words(text):
    """First word of the sentence, and the first word after each of up to three short lead-in pieces
    ("Quatrièmement,", "Mr. Speaker,", "M. Boulerice: M. le Président,")."""
    out, rest = [], text.strip()
    for _ in range(4):
        m = re.match(r"\s*([^\s,:;]+)", rest)
        if not m:
            break
        out.append(m.group(1).lower().strip("«“\"'("))
        cut = re.match(r"\s*([^,:;]{0,40}?)[,:;]\s*", rest)       # a short piece ending in , : or ;
        if not cut or len(cut.group(1).split()) > 5:
            break
        rest = rest[cut.end():]
    return out


def is_question(text, lang):
    """True when the sentence is itself a question: it ends with '?' and its main clause is asked
    (a question word or inverted verb at the start, 'est-ce que', or a French inverted pronoun).
    'X voulait abolir Y, il est vrai, mais pourquoi?' is a statement and stays."""
    t = (text or "").strip().rstrip(_END)
    if not t.endswith("?"):
        return False
    lead = _lead_words(t)
    if lang == "fr":
        return bool(_FR_ESTCE.search(t) or _FR_INV.search(t) or any(w in _FR_Q for w in lead))
    return any(w in _EN_Q for w in lead)


EXTRACT_ERRORS = os.path.join("outputs", "audit", "extract_errors.txt")


def extract(sent, lang):
    """One sentence that breaks a rule is written to outputs/audit/extract_errors.txt and gets no claim;
    the run goes on, and the fix17 checks fail if the file has any line."""
    if is_question(getattr(getattr(sent, "doc", None), "text", ""), lang):
        return None
    try:
        return _extract_one(sent, lang)
    except Exception as e:
        import traceback
        tb = traceback.extract_tb(e.__traceback__)[-1]
        try:
            os.makedirs(os.path.dirname(EXTRACT_ERRORS), exist_ok=True)
            with open(EXTRACT_ERRORS, "a", encoding="utf-8") as f:
                f.write(f"{lang}\t{type(e).__name__} line {tb.lineno}: {tb.line}\t{getattr(sent, 'text', '')[:300]!r}\n")
        except OSError:
            pass
        return None


def run(j):
    import spacy
    sents = load_json(rp("data/dbpedia_pipeline", j, "sentences_v3.json")) or sys.exit(
        f"sentences_v3.json missing for {j}. Run build_sentences_v3.py first.")
    out_path = rp("data/dbpedia_pipeline", j, "predications_v3.json")
    ck_path = out_path + ".checkpoint"
    ck = load_json(ck_path, {"done": {}, "preds": []})
    preds = ck["preds"]
    stats = Counter()
    by_lang = {}
    for s in sents:
        by_lang.setdefault(s["lang"], []).append(s)
    for lang, group in sorted(by_lang.items()):
        if lang not in MODELS:
            continue
        start = ck["done"].get(lang, 0)
        if start >= len(group):
            continue
        print(f"{j} [{lang}] loading {MODELS[lang]} for {len(group):,} sentences (resuming at {start:,})", flush=True)
        nlp = spacy.load(MODELS[lang], disable=["ner"])
        t0 = time.time()
        texts = (x["text"] for x in group[start:])
        for i, doc in enumerate(nlp.pipe(texts, batch_size=256), start):
            src = group[i]
            p = None
            for sent in doc.sents:
                p = extract(sent, lang)
                if p:
                    break
            if p:
                p.update({"sentence_id": src["sentence_id"], "bill_key": src["bill_key"], "session": src["session"],
                          "date": src["date"], "language": lang, "full_text": src["text"]})
                preds.append(p)
                stats[f"{lang}_predications"] += 1
            if (i + 1) % 25000 == 0:
                ck["done"][lang] = i + 1
                save_json(ck, ck_path)
                rate = (i + 1 - start) / max(time.time() - t0, 1)
                print(f"   {i + 1:,}/{len(group):,} ({rate:.0f}/s), predications so far {len(preds):,}", flush=True)
        ck["done"][lang] = len(group)
        save_json(ck, ck_path)
    save_json(preds, out_path)
    if os.path.exists(ck_path):
        os.remove(ck_path)
    n = len(sents)
    print(f"{j}: {len(preds):,} predications from {n:,} sentences ({100.0 * len(preds) / max(n, 1):.1f}%)")
    print(f"   by language: {dict(Counter(p['language'] for p in preds))}")
    print(f"   hedged: {sum(p['hedged'] for p in preds):,}  negated: {sum(p['negated'] for p in preds):,}")
    print(f"   saved {out_path}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for j in (["ontario", "quebec", "us"] if which == "all" else [which]):
        run(j)
