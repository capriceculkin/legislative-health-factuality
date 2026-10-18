#!/usr/bin/env python3
"""text_evidence_v2.py   Checking claims against Wikipedia text (the FEVER-style approach), second version with the
retrieval fix from the Oct 16 workbook: a Wikipedia sentence only counts as evidence when it mentions BOTH ends of the
claim (or comes from the page that is about one end), and the search uses the claim's own words and concept names, not
the whole debate sentence. For each claim:
  1. pages to read: the claim's concept pages (Oct 15e run), the top 3 search results for the subject and object words
     in the claim's language (French claims search French Wikipedia), and the top 2 for the concept names in English;
  2. the 5 sentences that share the most words with the claim AND mention both the subject and the object (a sentence
     on the subject's own page only needs the object, and the other way round);
  3. a natural-language-inference model reads each sentence against the claim and gives the chance that the sentence
     supports it, contradicts it, or neither. The model is multilingual (mDeBERTa-v3 trained on NLI data in 27
     languages, including French), so French claims can be read against English or French text.
A claim counts as supported when some sentence supports it with probability >= 0.5 (and more than it contradicts),
contradicted when some sentence contradicts it with >= 0.5, and otherwise "not enough information".
A claim whose subject has no name (a pronoun, or the bill under debate) is "not checkable by text" and gets no label.
Tested first on the 300 judged facts ("X was born in Y", "X studied at Y"), reading X's Wikipedia page.
Caveat for that test: Google built its true facts from Wikipedia sentences, so true facts are easier to find in
Wikipedia than ours will be. Writes ~/Desktop/next_steps/oct19/text_evidence_v2.json."""
import hashlib, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import ev_common as E

MODEL = os.environ.get("NLI_MODEL", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
WIKI = {"en": os.environ.get("WIKI_EN", "https://en.wikipedia.org/w/api.php"), "fr": os.environ.get("WIKI_FR", "https://fr.wikipedia.org/w/api.php")}
TEXT_CACHE = Path(E.CACHE) / "wiki_text"
UA = "FACTUALITY-study/1.0 (Yale; research use)"
STOP = set("""the a an of to in on for and or with that this these those their his her its our my your by at as from is are was were be been
being it they them he she we you i not no do does did would will shall should can could may might must have has had there here which who
whom what when where why how than then so such also only very more most some any all each other into over under about after before
le la les un une des du de d l au aux et ou en dans sur pour par avec ce cette ces son sa ses leur leurs notre nos qui que quoi dont où
est sont été être a ont avait ne pas plus se sa il elle ils elles nous vous je on y""".split())
STATS = {"pages_fetched": 0, "pages_cached": 0, "searches": 0, "fetch_failed": 0}
OUT = Path(os.environ.get("OCT19_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct19"))); OUT.mkdir(parents=True, exist_ok=True)
PRONOUNS = set("""i we you he she it they me us him her them this that these those one ones who what which
je j nous vous il elle ils elles on ce c ça cela ceci celui celle ceux celles qui que quoi dont où y en lui leur moi toi""".split())
GENERIC = {"bill", "bills", "projet", "loi", "lois", "house", "chambre", "assembly", "assemblée", "legislation", "measure", "act", "amendment"}


def _get(url, params, tries=4):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            wait = e.headers.get("Retry-After") if e.headers else None
            time.sleep(min(30, int(wait)) if wait and wait.isdigit() else 2 * (k + 1))
        except Exception as e:
            last = e
            time.sleep(2 * (k + 1))
    raise last


def page_text(title, lang):
    """Plain text of a Wikipedia page (follows redirects), cached in ~/.kg_dump/wiki_text."""
    if not title:
        return ""
    p = TEXT_CACHE / lang / (hashlib.md5(title.encode("utf-8")).hexdigest() + ".txt")
    if p.exists():
        STATS["pages_cached"] += 1
        return p.read_text(encoding="utf-8")
    try:
        d = _get(WIKI[lang], {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "format": "json",
                              "formatversion": 2, "titles": title.replace("_", " ")})
        pages = d.get("query", {}).get("pages", [])
        txt = (pages[0].get("extract") or "") if pages else ""
        STATS["pages_fetched"] += 1
    except Exception as e:
        STATS["fetch_failed"] += 1
        return ""
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    time.sleep(0.2)
    return txt


def search(query, lang, n=3):
    try:
        d = _get(WIKI[lang], {"action": "query", "list": "search", "srsearch": query[:280], "srlimit": n, "format": "json", "formatversion": 2})
        STATS["searches"] += 1
        time.sleep(0.2)
        return [x["title"].replace(" ", "_") for x in d.get("query", {}).get("search", [])]
    except Exception:
        return []


def sentences(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("=="):
            continue
        for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9\"“(])", line):
            n = len(s.split())
            if 5 <= n <= 80:
                out.append(s)
    return out


CODE_RE = re.compile(r"\b(?:h\.?\s?r\.?|hr|s\.?\s?b\.?|sb|bill|projet de loi(?: n[o°]?)?|loi)\s*-?\s*(\d+)\b")


def codes(s):
    """Bill numbers as one token each, so 'H.R. 5', 'SB-8' and 'projet de loi n° 83' can be matched: hr5, sb8, bill83."""
    out = set()
    for m in CODE_RE.finditer(s.lower()):
        kind = m.group(0)[:2].replace(".", "").replace(" ", "")
        kind = "hr" if kind.startswith("h") else "sb" if kind.startswith("s") else "bill"
        out.add(kind + m.group(1))
    return out


def stems(s):
    low = s.lower()
    return {w[:6] for w in re.findall(r"[a-zà-ÿ0-9]+", low) if w not in STOP and (len(w) > 2 or (any(c.isdigit() for c in w) and len(w) > 1))} | codes(low)


def name_words(page):
    """Arkansas_(state) -> arkansas; Government_of_Ontario -> government ontario"""
    return E.strip_name(page).replace("_", " ")


def end_terms(phrase, pages=()):
    """Stems that name one end of a claim: the phrase's content words (pronouns and generic words like 'bill' left out)
    plus the words of its concept page names."""
    low = phrase.replace("(inh)", "").lower()
    words = [w for w in re.findall(r"[a-zà-ÿ0-9']+", low) if w.strip("'") not in PRONOUNS]
    t = {w[:6] for w in words if w not in STOP and w not in GENERIC and (len(w) > 2 or (any(c.isdigit() for c in w) and len(w) > 1))} | codes(low)
    for pg in pages:
        t |= stems(name_words(pg))
    return t


def top_sentences(claim, pages, subj, obj, subj_pages=(), obj_pages=(), k=5):
    """The k sentences sharing the most word stems with the claim, among those that mention both ends of it.
    A sentence on a page that is about the subject only needs to mention the object, and the other way round."""
    cw = stems(claim)
    sp, op = {t.lower() for t in subj_pages}, {t.lower() for t in obj_pages}
    scored, seen = [], set()
    for title, lang, text in pages:
        about_s, about_o = title.lower() in sp, title.lower() in op
        for s in sentences(text):
            if s in seen:
                continue
            seen.add(s)
            sw = stems(s)
            has_s, has_o = bool(sw & subj) or about_s, bool(sw & obj) or about_o
            if not (has_s and has_o):
                continue
            sc = len(cw & sw) + 2 * len(obj & sw) + len(subj & sw)
            if sc:
                scored.append((sc, s, title, lang))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


class NLI:
    def __init__(self):
        if os.environ.get("NLI_BACKEND") == "overlap":          # test stand-in only (no model download): word overlap
            self.kind = "overlap"; return
        self.kind = "model"
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL).eval()
        lab = {i: l.lower() for i, l in self.model.config.id2label.items()}
        self.ent = next(i for i, l in lab.items() if l.startswith("entail"))
        self.con = next(i for i, l in lab.items() if l.startswith("contra"))
        self.labels = lab

    def __call__(self, pairs):
        """[(premise, hypothesis)] -> [(p_support, p_contradict)]"""
        if not pairs:
            return []
        if self.kind == "overlap":
            out = []
            for p, h in pairs:
                hs = stems(h); o = len(hs & stems(p)) / max(1, len(hs))
                neg = (" not " in f" {h.lower()} ") != (" not " in f" {p.lower()} ")
                out.append((0.0, o) if neg else (o, 0.0))
            return out
        res = []
        for b in range(0, len(pairs), 8):
            chunk = pairs[b:b + 8]
            enc = self.tok([p for p, _ in chunk], [h for _, h in chunk], truncation=True, max_length=320, padding=True, return_tensors="pt")
            with self.torch.no_grad():
                pr = self.torch.softmax(self.model(**enc).logits, dim=-1)
            res += [(float(r[self.ent]), float(r[self.con])) for r in pr]
        return res


def judge(nli, hyp, cands):
    pr = nli([(s, hyp) for _, s, _, _ in cands])
    best_e = max(range(len(pr)), key=lambda i: pr[i][0]) if pr else None
    best_c = max(range(len(pr)), key=lambda i: pr[i][1]) if pr else None
    e = pr[best_e][0] if pr else 0.0
    c = pr[best_c][1] if pr else 0.0
    if e >= 0.5 and e > c:
        lab, i = "supported", best_e
    elif c >= 0.5 and c > e:
        lab, i = "contradicted", best_c
    else:
        lab, i = "not enough information", best_e
    ev = cands[i] if (cands and i is not None) else None
    return {"label": lab, "support": round(e, 4), "contradict": round(c, 4), "evidence": ev[1] if ev else "",
            "evidence_page": f"{ev[3]}:{ev[2]}" if ev else "", "sentences_read": len(cands)}


def main():
    t0 = time.time()
    E.say(f"== 1. loading the inference model {MODEL} (downloads once, about 1.1 GB)")
    nli = NLI()
    if nli.kind == "model":
        E.say(f"   labels: {nli.labels}")
    E.say("== 2. the 300 judged facts against the subject's Wikipedia page")
    facts, ren = E.judged_facts()
    tmpl = {"place_of_birth": "{s} was born in {o}.", "institution": "{s} studied at {o}."}
    res = []
    for i, f in enumerate(facts):
        row = {"rel": f["rel"], "group": f["group"], "s": f["s"], "o": f["o"]}
        if f["s"] and f["o"]:
            s_page = ren.get(f["s"], f["s"])
            txt = page_text(s_page, "en")
            hyp = tmpl[f["rel"]].format(s=E.strip_name(f["s"]), o=E.strip_name(f["o"]))
            cands = top_sentences(hyp, [(s_page, "en", txt)], end_terms(E.strip_name(f["s"])), end_terms(E.strip_name(f["o"])), subj_pages=[s_page])
            row.update(hypothesis=hyp, page_found=bool(txt), **judge(nli, hyp, cands))
        res.append(row)
        if (i + 1) % 50 == 0:
            E.say(f"   {i + 1} of {len(facts)} done")
    summary = []
    for rel in ("place_of_birth", "institution", "all"):
        rows = [r for r in res if "support" in r and (rel == "all" or r["rel"] == rel)]
        for key, fn in (("support", lambda r: r["support"]), ("support minus contradict", lambda r: r["support"] - r["contradict"])):
            t = [fn(r) for r in rows if r["group"] == "judged true"]
            for grp, lab in (("swapped (made up)", "true vs made up"), ("judged false", "true vs judged false")):
                n = [fn(r) for r in rows if r["group"] == grp]
                summary.append({"relation": rel, "score": key, "comparison": lab, "true": len(t), "other": len(n),
                                "auc": E.auc_ranksum(t, n), "auc_pairs": E.auc_pairs(t, n)})
        for grp in ("judged true", "judged false", "swapped (made up)"):
            g = [r for r in rows if r["group"] == grp]
            summary.append({"relation": rel, "group": grp, "scored": len(g),
                            **{lab: sum(1 for r in g if r["label"] == lab) for lab in ("supported", "contradicted", "not enough information")}})
    for s in summary:
        if s["relation"] == "all" and "auc" in s:
            E.say(f"   {s['score']:26s} {s['comparison']:22s} AUC {s['auc']} (pair count {s['auc_pairs']})")
        elif s["relation"] == "all":
            E.say(f"   {s['group']:18s} supported {s['supported']}, contradicted {s['contradicted']}, not enough information {s['not enough information']}")

    E.say("== 3. the debate statements (stated ones from the Oct 15e run), both ends required")
    st, src, ver = E.debate_statements()
    deb = []
    for j, s in enumerate(st):
        subj, verb, obj = [x.strip() for x in s["statement"].split("|")][:3]
        hyp = re.sub(r"\s+", " ", f"{subj.replace('(inh)', '').strip()} {verb} {obj}").strip()
        lang = s["lang"]
        s_pages = [c[1] for c in s["v1_subject"] if c[1] and not c[1].startswith("(")]
        o_pages = [c[1] for c in s["v1_object"] if c[1] and not c[1].startswith("(")]
        subj_t, obj_t = end_terms(subj, s_pages), end_terms(obj, o_pages)
        row = {"n": s["n"], "lang": lang, "jurisdiction": s["jurisdiction"], "sentence": s["sentence"], "statement": s["statement"],
               "hypothesis": hyp, "negated": s["negated"], "hedged": s["hedged"], "subject_terms": sorted(subj_t), "object_terms": sorted(obj_t)}
        if not subj_t or not obj_t:
            why = "the subject" if not subj_t else "the object"
            row.update(checkable_by_text=False, why_not=f"{why} has no name to look for (a pronoun, or the bill under debate)",
                       label="not checkable by text", support=0.0, contradict=0.0, evidence="", evidence_page="", sentences_read=0, pages_read=[])
            deb.append(row)
            continue
        titles = [(t, "en") for t in s_pages + o_pages]
        q1 = " ".join(w for w in re.findall(r"[a-zà-ÿ0-9']+", f"{subj} {obj}".replace("(inh)", "").lower()) if w not in STOP and w not in PRONOUNS)
        for t in search(q1, lang):
            titles.append((t, lang))
        names = " ".join(name_words(pg) for pg in s_pages[:1] + o_pages[:1])
        if names.strip():
            for t in search(names, "en", n=2):
                titles.append((t, "en"))
        pages = []
        for t, lg in list(dict.fromkeys(titles))[:8]:
            pages.append((t, lg, page_text(t, lg)))
        cands = top_sentences(hyp, pages, subj_t, obj_t, subj_pages=s_pages, obj_pages=o_pages)
        row.update(checkable_by_text=True, pages_read=[f"{lg}:{t}" for t, lg, _ in pages], searches=[q1, names.strip()])
        row.update(judge(nli, hyp, cands))
        deb.append(row)
        if (j + 1) % 20 == 0:
            E.say(f"   {j + 1} of {len(st)} done")
    lab = {}
    for d in deb:
        lab.setdefault(d["lang"], {}).setdefault(d["label"], 0)
        lab[d["lang"]][d["label"]] += 1
    E.say(f"   labels: {lab}")
    out = {"version": "text_evidence v2 (Oct 19): both ends required, search by claim words and concept names", "model": MODEL if nli.kind == "model" else "word-overlap stand-in (test only)",
           "statements_from": src, "statements_version": ver, "wikipedia": STATS, "summary": summary, "judged_facts": res,
           "debate": deb, "debate_labels": lab, "minutes": round((time.time() - t0) / 60, 1)}
    (OUT / "text_evidence_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    E.say(f"   Wikipedia: {STATS}")
    E.say("== wrote " + str(OUT / "text_evidence_v2.json"))


if __name__ == "__main__":
    main()
