"""edu_dbpedia.py OUT_DIR RECORDS.json [MORE.json ...] [--concepts-dir scripts/step2_parsers] [--offline] [--oct15 DIR]

Oct 22 (48:16 to 48:38): "the output ... in a data structure that is consumable because then we can look and say, okay,
well, are there any DBpedia elements in here or not, and why and why not?" and (48:39) "most likely a lot of the
DBpedia stuff is gonna be found [in] the noun ... it's the walk between nouns."

For every claim the discourse-first pipeline read (edu_pipeline.py), this finds the DBpedia concepts at its subject and
its object with the SAME concept step as the Oct 15 run (scripts/step2_parsers/concepts_v3.py, version 1: the institution list,
exact page titles, Spotlight's senses re-ranked by the sentence, the common-noun list, French mapped to English), then
the walk between them on the 2022 infobox graph (the Ciampaglia path score, "see also" links left out). Nothing in the
concept step is changed or re-implemented: the concepts are concepts_v3.phrase_concepts, the walk is concepts_v3.Paths.

What this adds is the "why not" for every end of every claim that has no concept:
    a pronoun (and, for "that" and "ça", the units it stands for), a whole clause (its own claim is read separately),
    a number or an amount, no object, the bill under debate, Spotlight spotted nothing there, Spotlight's senses were
    all rejected (with the reason), the words are not a noun or a name, or the page is not in the 2022 graph.
It also lists the concepts that ARE in the claim's unit but at neither end of the claim (in the verb or an adjunct).

Needs, as on Oct 15: the SSH tunnel (Spotlight on 2222 and 2223) and the graph in ~/.kg_dump. Spotlight's answers are
saved (spotlight_edu_raw.json) so --offline reruns everything from them without the tunnel.
Writes OUT_DIR/edu_dbpedia.json (one record per sentence, one per claim), OUT_DIR/edu_dbpedia_summary.txt and, when
--oct15 holds concepts_v3.json and spotlight_raw.json, the comparison with the Oct 15 run."""
import argparse
import collections
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("records", nargs="+")
ap.add_argument("--concepts-dir", default=os.environ.get("CONCEPTS_DIR", "scripts/step2_parsers"),
                help="the folder with concepts_v3.py, concept_check.json and pc.json (the Oct 15 concept step)")
ap.add_argument("--offline", action="store_true", help="use the saved Spotlight answers instead of the tunnel")
ap.add_argument("--oct15", default=os.environ.get("OCT15_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct15")),
                help="the Oct 15 output folder (concepts_v3.json, spotlight_raw.json), for the comparison")
ap.add_argument("--sets", default="sample,heldout,more", help="which sets of sentences (the made-up test pairs are left out)")
A = ap.parse_args()

OUT = Path(A.out)
OUT.mkdir(parents=True, exist_ok=True)
CDIR = Path(A.concepts_dir).resolve()
if not (CDIR / "concepts_v3.py").exists():
    sys.exit(f"concepts_v3.py is not in {CDIR}. Pass --concepts-dir with the folder that has the Oct 15 concept step. Nothing changed.")
os.environ.setdefault("OCT15_OUT", A.oct15)        # concepts_v3 makes this folder when it loads; it is where the Oct 15 run wrote
sys.path.insert(0, str(CDIR))
C = importlib.import_module("concepts_v3")
RAW_FILE = OUT / "spotlight_edu_raw.json"


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


# ------------------------------------------------------------------ the sentences
SETS = set(A.sets.split(","))
JUR = {"US": "us", "ON": "ontario", "QC": "quebec"}
LEG = {"us": "US House", "ontario": "Ontario", "quebec": "Quebec"}
pc = {}
try:
    pc = {r["text"]: r for r in json.loads((CDIR / "pc.json").read_text(encoding="utf-8"))["rows"]}
except Exception:
    pass
held = {}
for hp in (Path(__file__).resolve().parent / "heldout.json",):
    try:
        held = {f"heldout|{r['h']}": r for r in json.loads(hp.read_text(encoding="utf-8"))}
    except Exception:
        pass


def jurisdiction(r):
    p = r["n"].split("|")
    if p[0] == "more" and len(p) > 1 and p[1] in JUR:
        return JUR[p[1]]
    for x in (pc.get(r["text"]), held.get(r["n"])):
        if x:
            if x.get("jurisdiction"):
                return x["jurisdiction"]
            if x.get("sentence_id"):
                return JUR.get(x["sentence_id"].split("|")[0])
    return None


recs = []
for f in A.records:
    for r in json.load(open(f, encoding="utf-8"))["rows"]:
        if r.get("set", r["n"].split("|")[0]) in SETS:
            recs.append(r)
recs.sort(key=lambda r: (["sample", "heldout", "more"].index(r["n"].split("|")[0]) if r["n"].split("|")[0] in ("sample", "heldout", "more") else 9,
                         r["n"]))
nojur = [r["n"] for r in recs if not jurisdiction(r)]
if nojur:
    sys.exit(f"no legislature found for {len(nojur)} sentences ({', '.join(nojur[:4])}); pc.json or heldout.json is missing. Nothing changed.")

# ------------------------------------------------------------------ the parts of speech the noun check uses
# concepts_v3 takes them from the saved spaCy parse (pc.json), which has the 100 sample sentences. For the others the
# same check reads the parts of speech off the unit's own constituency tree, so "The", "You" or "major" are not
# taken as concepts there either.
C.load_pos()
POS_FROM = collections.Counter()
TAG_POS = {"NN": "NOUN", "NNS": "NOUN", "NNP": "PROPN", "NNPS": "PROPN", "JJ": "ADJ", "JJR": "ADJ", "JJS": "ADJ", "CD": "NUM",
           "NC": "NOUN", "NPP": "PROPN", "ADJ": "ADJ", "ET": "PROPN"}


def leaves(n):
    if isinstance(n, str):
        return []
    if len(n[1]) == 1 and isinstance(n[1][0], str):
        return [(n[0], n[1][0])]
    return [x for k in n[1] for x in leaves(k)]


def tree_pos(r):
    spans = []
    for u in r["units"]:
        at = u["start"]
        for t in u.get("tree_nodes") or []:
            for tag, w in leaves(t):
                w2 = {"-LRB-": "(", "-RRB-": ")", "``": '"', "''": '"'}.get(w, w)
                k = r["text"].find(w2, at)
                if k < 0 or k > u["end"] + 2:
                    continue
                base = tag.rstrip("+") if tag.endswith("+") else tag
                spans.append((k, k + len(w2), TAG_POS.get(base, "X")))
                at = k + len(w2)
    return spans


for r in recs:
    if r["text"] in C.POS:
        POS_FROM["the saved spaCy parse (as on Oct 15)"] += 1
    else:
        sp = tree_pos(r)
        if sp:
            C.POS[r["text"]] = sp
            POS_FROM["the unit trees"] += 1
        else:
            POS_FROM["none (every spotted phrase counts as a noun)"] += 1

# ------------------------------------------------------------------ the graph and Spotlight
say("== 1. the full graph from ~/.kg_dump")
gfile, names, props, indptr, indices, code, _red = C.load_graph()
idx = {nm: i for i, nm in enumerate(names)}
indptr, indices, code, removed = C.factual_only(indptr, indices, code, props)
say(f"   {len(names):,} pages; {len(indices) // 2:,} factual links ({removed // 2:,} 'see also' and 'not to be confused with' links left out)")
chooser = C.Chooser(idx, indptr, indices, names, code, props)
paths = C.Paths(names, indptr, indices, code, props)

raw = {}
if A.offline:
    if not RAW_FILE.exists():
        sys.exit(f"--offline needs {RAW_FILE} from a run with the tunnel open. Nothing changed.")
    raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    miss = [r["n"] for r in recs if r["n"] not in raw]
    if miss:
        sys.exit(f"{len(miss)} sentences have no saved Spotlight answer ({', '.join(miss[:3])}); run once with the tunnel open. Nothing changed.")
    say(f"== 2. Spotlight: the saved answers in {RAW_FILE.name} (no tunnel needed)")
else:
    say("== 2. Spotlight (tunnel to Dunkleosteus)")
    try:
        C.annotate("Barack Obama was born in Hawaii.", "en")
    except Exception as e:
        sys.exit(f"Spotlight is not answering on {C.SPOT['en']} ({type(e).__name__}: {e}). Open the SSH tunnel, or use --offline. Nothing changed.")
    t0 = time.time()
    for k, r in enumerate(recs, 1):
        entry = {"text": r["text"], "lang": r["lang"], "candidates": [], "first_choices": None, "error": None}
        try:
            entry["candidates"] = C.candidates(r["text"], r["lang"])
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {str(e)[:150]}"
        if not entry["candidates"]:               # as on Oct 15: Spotlight's first choices on the whole sentence instead
            try:
                entry["first_choices"] = C.annotate(r["text"], r["lang"])
            except Exception:
                entry["first_choices"] = []
        raw[r["n"]] = entry
        if k % 40 == 0:
            say(f"   {k} of {len(recs)} sentences ({time.time() - t0:.0f}s)")
    RAW_FILE.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    say(f"   saved Spotlight's answers to {RAW_FILE}")


def sentence_cands(n):
    e = raw[n]
    if e["candidates"]:
        return e["candidates"]
    return [{"surface": x["surface"], "offset": x["offset"], "senses": [{"page": x["page"], "label": "", "score": 1.0, "context": 1.0,
             "support": 0.0, "types": x.get("types", "")}]} for x in (e.get("first_choices") or [])]


frp = [c["page"] for r in recs if r["lang"] == "fr" for sc in sentence_cands(r["n"]) for c in sc["senses"][:8]]
if frp:
    say(f"   mapping {len(set(frp))} French pages to English (cached in ~/.kg_dump/fr_to_en_cache.json)")
    C.fr_to_en(frp)

# ------------------------------------------------------------------ why a phrase has no concept
PRON = {"en": set("i me my we us our you your he him his she her it its they them their this that these those who whom which what "
                  "one ones someone somebody anyone anybody everyone everybody something anything everything nothing nobody none "
                  "myself ourselves yourself yourselves himself herself itself themselves there here so".split()),
        "fr": set("je j' me m' moi nous vous tu te t' toi il elle ils elles on lui leur eux se s' y en ça ce c' cela ceci celui celle "
                  "ceux celles qui que qu' quoi dont lequel laquelle lesquels le la les l' tout tous rien personne chacun".split())}
DETS = {"en": set("the a an this that these those our my your his her their its some any all every each no".split()),
        "fr": set("le la les l' un une des du de d' ce cet cette ces notre nos mon ma mes son sa ses leur leurs votre vos".split())}
NUMBER = re.compile(r"^(?:about |over |more than |less than |nearly |plus de |environ |près de )?[$€]?\s?[\d][\d.,\s]*"
                    r"(?:\s?(?:%|percent|per cent|pour cent|million|millions|billion|milliards?|dollars?|\$|years?|ans|hours?|heures))*$", re.I)
CLAUSE_LABELS = {"S", "SBAR", "SQ", "SBARQ", "SINV", "VP", "Ssub", "Sint", "Srel", "VPinf", "VPpart", "SENT"}
CLAUSE_OPENER = re.compile(r"^(?:that|why|how|whether|if|what|who|when|where|to)\s+\S+\s+\S+|^(?:(?:que|si|pourquoi|comment|ce que|ce qui)\s+|qu['’])\S+", re.I)


def toks(s):
    return re.findall(r"[\wÀ-ÿ]+['’]?|[^\s\w]", s.lower())


def is_pronoun(phrase, lang):
    w = [t.replace("’", "'") for t in toks(phrase) if re.match(r"[\wÀ-ÿ]", t)]
    return bool(w) and all(x in PRON[lang] for x in w)


def squash(s):
    return re.sub(r"[\W_]+", "", s.lower())


def tree_label_of(phrase, unit):
    """The label of the smallest constituent in the unit's tree whose words are exactly the phrase (None if none is)."""
    want = squash(phrase)
    best = [None]

    def walk(n):
        if isinstance(n, str):
            return n
        s = "".join(walk(k) if not isinstance(k, str) else k for k in n[1])
        if squash(s) == want and best[0] is None:
            best[0] = n[0]
        return s
    for t in (unit or {}).get("tree_nodes") or []:
        walk(t)
    return best[0]


def why_not(phrase, side, line, r, unit, found, sent_cands, diag):
    """Why this end of the claim has no DBpedia concept. Returns (status, reason)."""
    lang = r["lang"]
    if not phrase.strip():
        return "nothing to link", "no object: the verb takes none here" if side == "object" else "no subject"
    lab = tree_label_of(phrase, unit)
    clause = (lab in CLAUSE_LABELS) or (lab is None and CLAUSE_OPENER.match(phrase.strip())) or \
        (side == "object" and (line.get("object_from") or "").startswith("discourse: what is said"))
    if clause and not is_pronoun(phrase, lang):
        return "a clause", (f"a whole statement ({lab or 'clause opener'}), not a thing; its own claim is read on its own line"
                            + ("; it mentions the bill" if found else ""))
    if found and all(f[1] == "(the bill)" for f in found):
        return "the bill under debate", ("names the bill or a law: the Oct 15 concept step marks these as (the bill) and does not look up a page")
    if found and not [f for f in found if f[1] in idx]:
        return "page not in the graph", "Spotlight or the name list gave " + ", ".join(sorted({f[1] for f in found})) + ", which is not in the 2022 graph"
    if is_pronoun(phrase, lang):
        w = phrase.strip().lower()
        if side == "subject" and line.get("refers_to"):
            return "pronoun", f"'{phrase}' stands for {line['refers_to']}"
        if w in ("i", "je", "j'", "me", "moi"):
            return "pronoun", f"'{phrase}' is the speaker"
        if w in ("we", "us", "nous", "on"):
            return "pronoun", f"'{phrase}' is the speaker's side (the government, the party or the House); the sentence does not say which"
        if w in ("you", "vous"):
            return "pronoun", f"'{phrase}' is the person spoken to"
        return "pronoun", f"'{phrase}' stands for something named elsewhere" + (f" ({line['subject_from']})" if side == "subject" and line.get("subject_from") else "")
    if NUMBER.match(phrase.strip()):
        return "a number or an amount", "a number or an amount: DBpedia has no page for it"
    small = [x for x in diag["not_noun"] if x.lower() in C.STOP]
    if diag["spotted"] == len(small):             # only 'The', 'a' and the like were spotted: as good as nothing
        diag = dict(diag, spotted=0)
    if diag["spotted"] == 0:
        content = [t for t in toks(phrase) if re.match(r"[\wÀ-ÿ]", t) and t not in C.STOP and t not in DETS[lang]]
        if not content:
            return "no content word", "only small words (articles, prepositions)"
        lex = [(t, C.LEX[t]) for t in content if t in C.LEX]
        if lex:
            return "page not in the graph", (f"Spotlight spotted no phrase here; the common-noun list gives {lex[0][1]} for '{lex[0][0]}', "
                                             f"which is not in the 2022 graph")
        return "Spotlight spotted nothing", "Spotlight spotted no phrase here, and the words are not in the name list or the common-noun list"
    if diag["rejected"]:
        return "senses rejected", "; ".join(diag["rejected"][:2])
    big = [x for x in diag["not_noun"] if x.lower() not in C.STOP]
    if big:
        return "not a noun or a name", "Spotlight spotted " + ", ".join(f"'{x}'" for x in big[:3]) + ", which is not a noun or a name here"
    if diag["numeral"]:
        return "a number or an amount", "Spotlight spotted only a numeral (" + ", ".join(diag["numeral"][:2]) + ")"
    return "no concept", "no concept found (no reason recorded)"


def diagnose(phrase, lang, jur, sentence, sent_cands):
    """Replays the Spotlight part of concepts_v3.phrase_concepts (version 1) and records what was dropped and why.
    Only for the explanation: the concepts themselves always come from concepts_v3.phrase_concepts."""
    d = {"spotted": 0, "not_noun": [], "numeral": [], "rejected": [], "kept": []}
    pl = phrase.lower()
    for sc in sent_cands:
        s = sc["surface"]
        if not s or s.lower() not in pl:
            continue
        if not re.search(r"(?<![\wÀ-ÿ])" + re.escape(s.lower()) + r"(?![\wÀ-ÿ])", pl):
            continue                              # inside a longer word (the concept step still sees it; it finds nothing there)
        d["spotted"] += 1
        if C.ROMAN.match(s):
            d["numeral"].append(s); continue
        if not C.has_noun(sentence, sc.get("offset"), s, (sc["senses"][0]["page"] if sc["senses"] else None)):
            d["not_noun"].append(s); continue
        senses = sc["senses"]
        if lang == "fr" and senses:
            m = C.fr_to_en([c["page"] for c in senses[:8]])
            senses = [dict(c, page=m[c["page"]]) for c in senses if m.get(c["page"])]
            if not senses:
                d["rejected"].append(f"'{s}': its French pages have no English page"); continue
        page, how = chooser.pick(senses, sentence, jur, s[:1].islower(), 1)
        if page:
            d["kept"].append((s, page))
        else:
            d["rejected"].append(f"'{s}': {how}")
    return d


def unit_concepts(r, unit, jur, sent_cands):
    """Every concept Spotlight's senses give inside the unit (the same choice as for claims), by surface."""
    out = []
    for sc in sent_cands:
        off = sc.get("offset")
        if off is None or not (unit["start"] <= off < unit["end"] + 1):
            continue
        s = sc["surface"]
        if not s or C.ROMAN.match(s) or not C.has_noun(r["text"], off, s, (sc["senses"][0]["page"] if sc["senses"] else None)):
            continue
        senses = sc["senses"]
        if r["lang"] == "fr" and senses:
            m = C.fr_to_en([c["page"] for c in senses[:8]])
            senses = [dict(c, page=m[c["page"]]) for c in senses if m.get(c["page"])]
        page, _how = chooser.pick(senses, r["text"], jur, s[:1].islower(), 1)
        if page and page in idx:
            out.append((s, page))
    return out


def unlike(surface, page):
    """A name or an acronym whose page name shares no word (or initials) with it: worth a look (AHP -> Krasue on Oct 15).
    Common nouns ("seniors" -> Old_age) and French words (mapped to English pages) are not flagged."""
    if not surface[:1].isupper():
        return False
    sw = {w for w in re.findall(r"[a-zà-ÿ0-9]+", surface.lower()) if w not in C.STOP}
    pw = {w for w in re.findall(r"[a-zà-ÿ0-9]+", page.lower().replace("_", " ")) if w not in C.STOP}
    if sw & pw or any(p.startswith(s[:4]) or s.startswith(p[:4]) for s in sw for p in pw if len(s) >= 4 and len(p) >= 4):
        return False
    initials = "".join(w[0] for w in re.findall(r"[A-Za-zÀ-ÿ]+", page.replace("_", " ")) if w[0].isupper()).lower()
    return not any(s == initials for s in sw)


CHECKED = {(str(c["n"]), c["surface"].lower()): c for c in C.CHECKED}


def side_record(phrase, side, line, r, unit, jur, cands):
    clean = phrase.replace(" (inh)", "")
    found = C.phrase_concepts(clean, r["lang"], jur, r["text"], cands, chooser, idx, 1) if clean.strip() else []
    in_graph = [f for f in found if f[1] in idx]
    diag = diagnose(clean, r["lang"], jur, r["text"], cands) if clean.strip() else {"spotted": 0, "not_noun": [], "numeral": [], "rejected": [], "kept": []}
    # the replay must agree with the concept step: every concept it keeps from Spotlight is one the step found
    for s, page in diag["kept"]:
        if not any(f[0].lower() == s.lower() for f in found) and not any(s.lower() in f[0].lower() or f[0].lower() in s.lower() for f in found):
            AGREE["replay kept a sense the concept step did not"] += 1
            MISMATCH.append({"sentence": r["n"], "side": side, "phrase": phrase, "replay_kept": [s, page],
                             "concept_step_found": [list(f[:2]) for f in found]})
    concepts = []
    for s, page, how in found:
        old = CHECKED.get((r["n"].split("|")[1], s.lower())) if r["n"].startswith("sample|") else None
        concepts.append({"surface": s, "page": page, "how": how, "in_graph": page in idx,
                         "dbpedia": f"https://dbpedia.org/page/{page}" if page in idx else "",
                         "page_name_unlike_words": bool(page in idx and how.startswith("Spotlight") and r["lang"] == "en" and unlike(s, page)),
                         "hand_checked_oct13": (old["right"] if old else None)})
    if in_graph:
        status, reason = "in DBpedia", ""
    else:
        status, reason = why_not(clean, side, line, r, unit, found, cands, diag)
    return {"phrase": phrase, "status": status, "reason": reason, "concepts": concepts}


AGREE = collections.Counter()
MISMATCH = []
say("== 3. concepts at both ends of every claim, and the walk between them")
out_rows, flat = [], []
t0 = time.time()
for r in recs:
    jur = jurisdiction(r)
    cands = sentence_cands(r["n"])
    units = {u["unit"]: u for u in r["units"]}
    ucon = {k: unit_concepts(r, u, jur, cands) for k, u in units.items()}
    claims = []
    for li, l in enumerate(r["lines"]):
        unit = units.get(l["unit"])
        subj = side_record(l["subject"], "subject", l, r, unit, jur, cands)
        obj = side_record(l["object"], "object", l, r, unit, jur, cands)
        best = None
        for a in [c for c in subj["concepts"] if c["in_graph"]][:4]:
            for b in [c for c in obj["concepts"] if c["in_graph"]][:4]:
                if a["page"] == b["page"]:
                    continue
                p = paths.score(idx[a["page"]], idx[b["page"]])
                if p and (best is None or p["tau"] > best["tau"]):
                    best = dict(p, subject=a["page"], object=b["page"])
        if best:
            nd = paths.score(idx[best["subject"]], idx[best["object"]], cut=True) if best["links"] == 1 else dict(best)
            best["tau_no_direct"], best["path_no_direct"] = nd["tau"], nd["path"]
            best["claim_score"] = round(1 - best["tau"], 4) if l.get("negated") else best["tau"]
        both = subj["status"] == "in DBpedia" and obj["status"] == "in DBpedia"
        used = {c["page"] for c in subj["concepts"] + obj["concepts"]}
        elsewhere = sorted({p for s, p in ucon.get(l["unit"], []) if p not in used})
        if both:
            verdict = "both ends in DBpedia" + ("; a walk links them" if best and best.get("tau", 0) > 0 else "; no walk links them in the graph")
        elif subj["status"] == "in DBpedia" or obj["status"] == "in DBpedia":
            verdict = "one end in DBpedia"
        else:
            verdict = "neither end in DBpedia"
        c = {"claim": li + 1, "unit": l["unit"], "kind": l["kind"], "negated": l.get("negated", False), "hedged": l.get("hedged", False),
             "subject": subj, "verb": l["verb"], "object": obj, "walk": best, "verdict": verdict,
             "unit_concepts_not_in_claim": elsewhere, "how_the_claim_was_read": l.get("how", "")}
        claims.append(c)
        flat.append((r, c, jur))
    out_rows.append({"n": r["n"], "set": r["n"].split("|")[0], "legislature": LEG[jur], "jurisdiction": jur, "lang": r["lang"],
                     "text": r["text"], "units": [{"unit": u["unit"], "text": u["text"],
                                                    "concepts": [{"surface": s, "page": p} for s, p in ucon[u["unit"]]]} for u in r["units"]],
                     "connections": r.get("connections", []), "claims": claims,
                     "spotlight": "candidates" if raw[r["n"]]["candidates"] else ("first choices only" if raw[r["n"]].get("first_choices") else "nothing")})
say(f"   {len(flat)} claims in {len(out_rows)} sentences ({time.time() - t0:.0f}s)")
if AGREE:
    say(f"   WARNING: the why-not replay disagreed with the concept step {sum(AGREE.values())} times; the reasons for those may be off")
    for m in MISMATCH:
        say(f"      {m['sentence']} {m['side']} '{m['phrase'][:60]}': replay kept {m['replay_kept']}, the concept step found {m['concept_step_found']}")

# ------------------------------------------------------------------ summary
L = []


def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "0/0"


def block(title, items):
    n = len(items)
    L.append(f"\n{title}: {n} claims")
    v = collections.Counter(c["verdict"].split(";")[0] for _r, c, _j in items)
    for k in ("both ends in DBpedia", "one end in DBpedia", "neither end in DBpedia"):
        L.append(f"   {k:<28}{pct(v[k], n)}")
    walk = sum(1 for _r, c, _j in items if c["walk"] and c["walk"].get("tau", 0) > 0)
    L.append(f"   {'a walk links the two ends':<28}{pct(walk, n)}")


L.append(f"DBpedia concepts in the discourse-first claims (concept step: concepts_v3 version 1, as on Oct 15; graph {os.path.basename(gfile)})")
L.append(f"sentences: {len(out_rows)} ({', '.join(f'{k} {v}' for k, v in collections.Counter(r['set'] for r in out_rows).items())}); "
         f"Spotlight: {'saved answers' if A.offline else 'live, through the tunnel'}")
L.append("parts of speech for the noun check: " + "; ".join(f"{v} sentences from {k}" for k, v in POS_FROM.items()))
block("All claims", flat)
block("Claims the speaker asserts (kind = asserted)", [x for x in flat if x[1]["kind"] == "asserted"])
for jur in ("us", "ontario", "quebec"):
    block(f"{LEG[jur]}", [x for x in flat if x[2] == jur])
for lang in ("en", "fr"):
    block("English" if lang == "en" else "French", [x for x in flat if x[0]["lang"] == lang])
for side in ("subject", "object"):
    st = collections.Counter(c[side]["status"] for _r, c, _j in flat)
    L.append(f"\nWhy a {side} has no concept (all {len(flat)} claims)")
    for k, v in st.most_common():
        L.append(f"   {k:<30}{v}")
odd = [(r["n"], cc["surface"], cc["page"]) for r, c, _j in flat for s in ("subject", "object") for cc in c[s]["concepts"] if cc["page_name_unlike_words"]]
L.append(f"\nConcepts whose page name shares no word with the words spotted (worth a look, like AHP -> Krasue): {len(set(odd))}")
for x in sorted(set(odd))[:40]:
    L.append(f"   {x[0]:<18}{x[1]!r} -> {x[2]}")
L.append("\nWhat Spotlight spotted, by language (phrases with at least one candidate sense, per sentence)")
for lang in ("en", "fr"):
    ns = [len(raw[r["n"]]["candidates"]) for r in out_rows if r["lang"] == lang]
    if ns:
        L.append(f"   {'English' if lang == 'en' else 'French':<10}{len(ns)} sentences; {sum(ns) / len(ns):.1f} phrases per sentence; "
                 f"none at all in {sum(1 for x in ns if x == 0)}")
ng = collections.Counter(cc["page"] for _r, c, _j in flat for s in ("subject", "object") if c[s]["status"] == "page not in the graph"
                         for cc in c[s]["concepts"] if not cc["in_graph"])
if ng:
    L.append("\nPages given but not in the 2022 graph (the graph holds only pages with infobox links): "
             + ", ".join(f"{p} ({v})" if v > 1 else p for p, v in ng.most_common()))
if MISMATCH:
    L.append(f"\nThe why-not replay disagreed with the concept step {len(MISMATCH)} times (the concepts are the concept step's; only the reason may be off):")
    for m in MISMATCH:
        L.append(f"   {m['sentence']} {m['side']} '{m['phrase'][:60]}': replay kept {m['replay_kept']}, concept step found {m['concept_step_found']}")
eu = sum(1 for _r, c, _j in flat if c["unit_concepts_not_in_claim"])
L.append(f"\nClaims whose unit has a DBpedia concept at neither end of the claim (in the verb or an adjunct): {pct(eu, len(flat))}")

# ------------------------------------------------------------------ the Oct 15 run on the same 100 sentences
O15 = Path(A.oct15)
cmp_out = {}
if (O15 / "concepts_v3.json").exists():
    old = json.loads((O15 / "concepts_v3.json").read_text(encoding="utf-8"))
    text_of = {str(r["n"]): r["text"] for r in json.loads((CDIR / "pc.json").read_text(encoding="utf-8"))["rows"]} if (CDIR / "pc.json").exists() else {}
    os_ = old["statements"]
    ob = sum(1 for s in os_ if [c for c in s["v1_subject"] if c[1] in idx] and [c for c in s["v1_object"] if c[1] in idx])
    ow = sum(1 for s in os_ if s.get("v1_path") and s["v1_path"].get("tau", 0) > 0)
    samp = [x for x in flat if x[0]["n"].startswith("sample|") and x[1]["kind"] == "asserted"]
    nb = sum(1 for _r, c, _j in samp if c["verdict"].startswith("both"))
    nw = sum(1 for _r, c, _j in samp if c["walk"] and c["walk"].get("tau", 0) > 0)
    L.append("\nCompared with the Oct 15 run (the same 100 sample sentences, asserted claims only)")
    L.append(f"   Oct 15 (statements v4, 2 of 3 parsers): {len(os_)} claims; both ends in DBpedia {pct(ob, len(os_))}; a walk {pct(ow, len(os_))}")
    L.append(f"   now (discourse first):                  {len(samp)} claims; both ends in DBpedia {pct(nb, len(samp))}; a walk {pct(nw, len(samp))}")
    # claims with the same subject and object in both runs must get the same concepts: the concept step is unchanged
    key_old = {}
    for s in os_:
        a, _v, b = [x.strip() for x in s["statement"].split("|")]
        key_old[(str(s["n"]), a.replace(" (inh)", ""), b)] = s
    same = diff = 0
    diffs = []
    for r, c, _j in samp:
        k = (r["n"].split("|")[1], c["subject"]["phrase"].replace(" (inh)", ""), c["object"]["phrase"])
        if k in key_old:
            s = key_old[k]
            a = (sorted(x[1] for x in s["v1_subject"]), sorted(x[1] for x in s["v1_object"]))
            b = (sorted(x["page"] for x in c["subject"]["concepts"]), sorted(x["page"] for x in c["object"]["concepts"]))
            if a == b:
                same += 1
            else:
                diff += 1; diffs.append((r["n"], k[1], k[2], a, b))
    L.append(f"   claims with the same subject and object in both runs: {same + diff}; the same concepts {same}, different {diff}")
    for d in diffs[:10]:
        L.append(f"      {d[0]}: {d[1]!r} / {d[2]!r}: Oct 15 {d[3]} now {d[4]}")
    cmp_out = {"oct15_claims": len(os_), "oct15_both": ob, "oct15_walk": ow, "now_claims": len(samp), "now_both": nb, "now_walk": nw,
               "same_claims": same + diff, "same_concepts": same, "different": [list(map(str, d)) for d in diffs]}
    if (O15 / "spotlight_raw.json").exists():           # Spotlight itself: the same answers for the same sentence?
        old_raw = json.loads((O15 / "spotlight_raw.json").read_text(encoding="utf-8"))
        eq = ne = 0
        for r in out_rows:
            if not r["n"].startswith("sample|"):
                continue
            o = old_raw.get(r["n"].split("|")[1])
            if o is None:
                continue
            a = [(x["surface"], x["offset"], [y["page"] for y in x["senses"]]) for x in o]
            b = [(x["surface"], x["offset"], [y["page"] for y in x["senses"]]) for x in raw[r["n"]]["candidates"]]
            eq += a == b; ne += a != b
        L.append(f"   Spotlight's candidates for the sample sentences: the same as on Oct 15 for {eq}, different for {ne}")
        cmp_out["spotlight_same"], cmp_out["spotlight_different"] = eq, ne
else:
    L.append(f"\n(no Oct 15 comparison: {O15 / 'concepts_v3.json'} was not found; pass --oct15 with that folder)")

res = {"version": "edu_dbpedia (Oct 30): concepts_v3 version 1 on the discourse-first claims", "graph": os.path.basename(gfile),
       "spotlight": "saved answers" if A.offline else "live", "summary": "\n".join(L), "compared_with_oct15": cmp_out, "replay_disagreements": MISMATCH, "rows": out_rows}
(OUT / "edu_dbpedia.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "edu_dbpedia_summary.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
say(f"== wrote {OUT / 'edu_dbpedia.json'} and {OUT / 'edu_dbpedia_summary.txt'}")
