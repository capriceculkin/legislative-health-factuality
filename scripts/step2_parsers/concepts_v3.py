#!/usr/bin/env python3
"""concepts_v3.py   Concepts in DBpedia for every stated predication, then the Ciampaglia path score over the whole
2022 infobox graph (built by the full-graph run, kept in ~/.kg_dump).

David (Oct 8): "dbpedia should connect the bill or the government to the correct thing"; "His doctor prescribed the
medication ... wikipedia should be able to get the doctor"; "next is identification of concepts".
What changed from the Oct 13 run (Spotlight's first choice on the statement text):
  1. institutions by jurisdiction: "the House", "the Senate", "this government", "cette Assemblée", "le gouvernement";
  2. exact page titles for names: "Ontario Health", "Cancer Care Ontario" (instead of "Ontario" cut out of them);
  3. Spotlight's other candidate senses, re-ranked by the sentence: a sense tied to another country (the Sri Lankan police
     unit, the Australian Capital Territory, German reunification), or a film, album or sports sense with no sports or
     film words in the sentence, loses to the next candidate; Roman numerals are dropped;
  4. common nouns with no name: "his doctor" -> Physician, "the medication" -> Medication, "prisoners" -> Prisoner;
  5. French concepts are mapped to English DBpedia (owl:sameAs) so French statements can be scored on the same graph.
The 43 concepts checked by hand on Oct 13 are re-scored under each version so the change can be measured.

Changed on Oct 15 after the first real run (concepts_v2.json), each for a failure seen in that run:
  a. "tied to another country" now means the page itself says where it is (an outgoing country, location, state ...
     link, or the country in its title, as in Special_Task_Force_(Sri_Lanka)). The old rule counted any link to a
     country, so Abortion (linked to Ireland and Singapore) and HIV (linked to Benin and Eswatini) were thrown out.
  b. a concept has to contain a noun or a name. Spotlight had turned "The", "You", "major", "independent",
     "traditional" and "identical" into pages (The, Israel, Major, Independent_politician, Traditional_medicine, Twin).
  c. sentence-initial "The government", "The House" now reach the institution list (the list only knew "the government",
     so the Ontario sentence went to Spotlight and came back as the government of Iran).
  d. French pages are mapped to English through Wikipedia's own language links first (fr.wikipedia.org), then
     fr.dbpedia.org, with retries and a saved cache. In the first run fr.dbpedia.org failed 25 times, so 46 of the 72
     French statements had no concept at all.
  e. paths use only factual relations: rdfs:seeAlso ("see also" lists) and owl:differentFrom ("not to be confused
     with") are left out of the graph, since a "see also" entry says nothing about the world.
  f. Spotlight's raw answers are saved (spotlight_raw.json) so the concept step can be re-checked offline.
Needs: the SSH tunnel (Spotlight on 2222 and 2223) and the full-graph files in ~/.kg_dump. Live DBpedia is optional.
Writes ~/Desktop/next_steps/oct15/concepts_v3.json."""
import glob, json, math, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = Path(os.environ.get("OCT15_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct15"))); OUT.mkdir(parents=True, exist_ok=True)
CACHE = os.path.expanduser(os.environ.get("FULLGRAPH_CACHE", "~/.kg_dump"))
SPOT = {"en": os.environ.get("SPOTLIGHT_EN", "http://localhost:2222/rest"), "fr": os.environ.get("SPOTLIGHT_FR", "http://localhost:2223/rest")}
FR_SPARQL = os.environ.get("SPARQL_FR", "http://fr.dbpedia.org/sparql")
FR_WIKI = os.environ.get("WIKI_FR", "https://fr.wikipedia.org/w/api.php")
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


# ------------------------------------------------------------------ the graph from the full-graph run
def load_graph():
    files = sorted(glob.glob(os.path.join(CACHE, "*.merged.graph.npz")))
    if not files:
        sys.exit("The full graph is not in ~/.kg_dump. Run full_graph_bundle.sh (Oct 14d) first. Nothing changed.")
    f = files[-1]
    z = np.load(f, allow_pickle=False)
    names = json.load(open(f + ".names.json", encoding="utf-8"))
    props = json.load(open(f + ".props.json", encoding="utf-8"))
    if len(names) != len(z["indptr"]) - 1:
        sys.exit("The saved graph and its page list do not match. Run full_graph_bundle.sh again. Nothing changed.")
    reds = sorted(glob.glob(os.path.join(CACHE, "redirects_*_en.ttl.bz2")))
    return f, names, props, z["indptr"], z["indices"], z["code"], (reds[-1] if reds else None)


# ------------------------------------------------------------------ word lists
BILL = {"en": re.compile(r"\b(?:this|the|that|our|their|his|her|my|another)\s+(?:bill|legislation|amendment|substitute)\b|\bH\.\s?R\.\s?\d+|\bBill\s+\d+|\bS\.\s?\d+", re.I),
        "fr": re.compile(r"\b(?:ce|le|du|notre|son|leur)\s+projet\s+de\s+loi\b|projet\s+de\s+loi\s+(?:n°\s*)?\d+|\b(?:la|cette)\s+loi\b", re.I)}
GAZ = {
    "us": [(r"\b(?:the|this)\s+House(?:\s+of\s+Representatives)?\b", "United_States_House_of_Representatives"),
           (r"\b(?:the|this)\s+Senate\b", "United_States_Senate"), (r"\bCongress\b", "United_States_Congress"),
           (r"\b(?:the|this)\s+Administration\b", "Federal_government_of_the_United_States"),
           (r"\b(?:the|this|our)\s+(?:federal\s+)?[Gg]overnment\b", "Federal_government_of_the_United_States"),
           (r"\b(?:the|this|our)\s+Nation\b|\bthis\s+country\b", "United_States"),
           (r"\bthe\s+President\b", "President_of_the_United_States"),
           (r"\bthe\s+Speaker\b", "Speaker_of_the_United_States_House_of_Representatives"),
           (r"\bthe\s+Clerk\b", "Clerk_of_the_United_States_House_of_Representatives"),
           (r"\bMedicare\b(?!\s+Advantage)", "Medicare_(United_States)"), (r"\bMedicaid\b", "Medicaid"),
           (r"\bCMS\b|\bCenters\s+for\s+Medicare", "Centers_for_Medicare_&_Medicaid_Services"),
           (r"\bFDA\b", "Food_and_Drug_Administration"), (r"\bCDC\b", "Centers_for_Disease_Control_and_Prevention")],
    "ontario": [(r"\b(?:this|the)\s+(?:House|Legislature|Legislative\s+Assembly|Assembly)\b|\bQueen[’']s\s+Park\b", "Legislative_Assembly_of_Ontario"),
                (r"\b(?:the|this|our)\s+government\b", "Government_of_Ontario"),
                (r"\b(?:the|this|our)\s+province\b", "Ontario"),
                (r"\bthe\s+(?:Minister|Ministry)\s+of\s+Health\b", "Ministry_of_Health_(Ontario)"),
                (r"\bthe\s+Treasurer\b", "Treasurer_of_Ontario"), (r"\bthe\s+Premier\b", "Premier_of_Ontario"),
                (r"\bOHIP\b|\bOntario\s+Health\s+Insurance\s+Plan\b", "Ontario_Health_Insurance_Plan")],
    "quebec": [(r"\b(?:cette|l['’])\s*Assemblée(?:\s+nationale)?\b", "National_Assembly_of_Quebec"),
               (r"\b(?:le|ce|notre|du)\s+gouvernement\b", "Government_of_Quebec"),
               (r"\b(?:la|cette|notre)\s+province\b", "Quebec"),
               (r"\bConseil\s+exécutif\b", "Executive_Council_of_Quebec"),
               (r"\bSûreté\s+du\s+Québec\b", "Sûreté_du_Québec"),
               (r"\b(?:le|la)\s+premi(?:er|ère)\s+ministre\b", "Premier_of_Quebec"),
               (r"\bRAMQ\b|\bRégie\s+de\s+l['’]assurance\s+maladie", "Régie_de_l'assurance_maladie_du_Québec")],
}
LEX = {  # common nouns that name a concept (English and French) -> English DBpedia page
    "doctor": "Physician", "doctors": "Physician", "physician": "Physician", "physicians": "Physician", "médecin": "Physician", "médecins": "Physician",
    "nurse": "Nurse", "nurses": "Nurse", "infirmière": "Nurse", "infirmières": "Nurse",
    "patient": "Patient", "patients": "Patient", "hospital": "Hospital", "hospitals": "Hospital", "hôpital": "Hospital", "hôpitaux": "Hospital",
    "clinic": "Clinic", "clinics": "Clinic", "clinique": "Clinic", "cliniques": "Clinic",
    "pharmacy": "Pharmacy", "pharmacies": "Pharmacy", "pharmacie": "Pharmacy", "pharmacist": "Pharmacist", "pharmacists": "Pharmacist",
    "medication": "Medication", "medications": "Medication", "medicine": "Medication", "drug": "Medication", "drugs": "Medication",
    "médicament": "Medication", "médicaments": "Medication",
    "prisoner": "Prisoner", "prisoners": "Prisoner", "prisonnier": "Prisoner", "prisonniers": "Prisoner", "détenus": "Prisoner",
    "prison": "Prison", "prisons": "Prison", "woman": "Woman", "women": "Woman", "femme": "Woman", "femmes": "Woman",
    "child": "Child", "children": "Child", "enfant": "Child", "enfants": "Child", "parent": "Parent", "parents": "Parent",
    "senior": "Old_age", "seniors": "Old_age", "aînés": "Old_age", "taxpayer": "Taxpayer", "taxpayers": "Taxpayer",
    "contribuable": "Taxpayer", "contribuables": "Taxpayer", "miner": "Miner", "miners": "Miner",
    "immigrant": "Immigration", "immigrants": "Immigration", "refugee": "Refugee", "refugees": "Refugee", "réfugiés": "Refugee",
    "tax": "Tax", "taxes": "Tax", "impôt": "Tax", "insurance": "Insurance", "assurance": "Insurance",
    "tobacco": "Tobacco", "tabac": "Tobacco", "cancer": "Cancer", "vaccine": "Vaccine", "vaccines": "Vaccine", "vaccin": "Vaccine",
    "school": "School", "schools": "School", "école": "School", "écoles": "School", "university": "University", "université": "University",
    "union": "Trade_union", "unions": "Trade_union", "syndicat": "Trade_union", "syndicats": "Trade_union",
    "police": "Police", "court": "Court", "courts": "Court", "tribunal": "Court", "judge": "Judge", "judges": "Judge", "juge": "Judge",
    "landlord": "Landlord", "propriétaire": "Landlord", "citizen": "Citizenship", "citizens": "Citizenship", "citoyens": "Citizenship",
    "voter": "Voting", "voters": "Voting", "électeurs": "Voting", "family": "Family", "families": "Family", "famille": "Family", "familles": "Family",
    "store": "Retail", "stores": "Retail", "lawyer": "Lawyer", "lawyers": "Lawyer", "avocat": "Lawyer", "avocats": "Lawyer",
    "cost": "Cost", "costs": "Cost", "coût": "Cost", "coûts": "Cost", "budget": "Budget", "staff": "Employment", "workers": "Workforce",
}
STOP = set("the a an of to in on for and or with that this these those their his her its our my your by at as from is are was were be "
           "le la les un une des du de d l au aux et ou en dans sur pour par avec ce cette ces son sa ses leur leurs notre nos".split())
SPORT = {"rugby", "football", "hockey", "baseball", "basketball", "cricket", "soccer", "player", "team", "league", "coach", "season", "game", "games"}
MEDIA = {"film", "movie", "album", "song", "single", "band", "series", "show", "episode", "novel", "book", "journal", "magazine", "video", "game"}
TITLE_FLAGS = {"film", "tv", "series", "album", "song", "band", "video", "game", "novel", "journal", "magazine", "rugby", "footballer",
               "cricketer", "basketball", "baseball", "soccer", "play", "musical", "opera", "ep", "single"}
COUNTRIES = set("""Afghanistan Albania Algeria Andorra Angola Argentina Armenia Australia Austria Azerbaijan The_Bahamas Bahrain Bangladesh
Barbados Belarus Belgium Belize Benin Bhutan Bolivia Bosnia_and_Herzegovina Botswana Brazil Brunei Bulgaria Burkina_Faso Burundi Cambodia
Cameroon Canada Cape_Verde Central_African_Republic Chad Chile China Colombia Comoros Costa_Rica Croatia Cuba Cyprus Czech_Republic
Czechoslovakia Denmark Djibouti Dominica Dominican_Republic East_Timor Ecuador Egypt El_Salvador Equatorial_Guinea Eritrea Estonia Eswatini
Ethiopia Fiji Finland France Gabon The_Gambia Georgia_(country) Germany West_Germany East_Germany Ghana Greece Grenada Guatemala Guinea
Guinea-Bissau Guyana Haiti Honduras Hungary Iceland India Indonesia Iran Iraq Republic_of_Ireland Israel Italy Ivory_Coast Jamaica Japan
Jordan Kazakhstan Kenya Kiribati Kuwait Kyrgyzstan Laos Latvia Lebanon Lesotho Liberia Libya Liechtenstein Lithuania Luxembourg Madagascar
Malawi Malaysia Maldives Mali Malta Marshall_Islands Mauritania Mauritius Mexico Federated_States_of_Micronesia Moldova Monaco Mongolia
Montenegro Morocco Mozambique Myanmar Namibia Nauru Nepal Netherlands New_Zealand Nicaragua Niger Nigeria North_Korea North_Macedonia Norway
Oman Pakistan Palau Panama Papua_New_Guinea Paraguay Peru Philippines Poland Portugal Qatar Romania Russia Soviet_Union Rwanda
Saint_Kitts_and_Nevis Saint_Lucia Saint_Vincent_and_the_Grenadines Samoa San_Marino Saudi_Arabia Senegal Serbia Yugoslavia Seychelles
Sierra_Leone Singapore Slovakia Slovenia Solomon_Islands Somalia South_Africa South_Korea South_Sudan Spain Catalonia Sri_Lanka Sudan Suriname
Sweden Switzerland Syria Taiwan Tajikistan Tanzania Thailand Togo Tonga Trinidad_and_Tobago Tunisia Turkey Turkmenistan Tuvalu Uganda
Ukraine United_Arab_Emirates United_Kingdom England Scotland Wales Northern_Ireland United_States Uruguay Uzbekistan Vanuatu Vatican_City
Venezuela Vietnam Yemen Zambia Zimbabwe""".split())
LOC_PROPS = {"country", "location", "locationCountry", "state", "jurisdiction", "headquarter", "territory", "region",
             "countryOrigin", "sovereignCountry", "place", "ground", "city", "nationality", "citizenship", "isPartOf"}
NONFACT = {"seeAlso", "differentFrom"}          # rdfs:seeAlso and owl:differentFrom: lists, not facts
NOUNISH = {"NOUN", "PROPN"}


def prop_name(p):
    return re.split(r"[#/]", p)[-1]


HOME = {"us": {"United_States"}, "ontario": {"Canada"}, "quebec": {"Canada"}}
ROMAN = re.compile(r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})$|^\d{1,2}$")   # "section II", "3": not concepts
# The 43 concepts checked by hand on Oct 13 (Claude's reading; yellow column for David and Joanie): the senses that
# count as right. None = no concept is the right answer (the phrase has no page of its own in this sense).
EXPECTED = {
    (8, "acceleration"): {None}, (14, "meth lab"): {None, "Clandestine_chemistry", "Methamphetamine"},
    (16, "The substitute"): {None}, (24, "ACT"): {None, "Ocata_Therapeutics", "Advanced_Cell_Technology"},
    (24, "special task force"): {None}, (26, "cartridge"): {None, "Electronic_cigarette"},
    (28, "Brian Smith"): {None, "Brian_Smith_(ice_hockey,_born_1940)", "Brian_Smith_(sportscaster)", "Brian_Smith_(ice_hockey)"},
    (31, "folly"): {None, "Foolishness", "Stupidity"}, (32, "Ontario"): {None, "Ontario_Health"},
    (33, "reunification"): {None, "Family_reunification"}, (49, "environmental values"): {None},
    (91, "II"): {None}, (91, "Conseil exécutif"): {None, "Executive_Council_of_Quebec", "Conseil_exécutif_du_Québec"},
}


CAND_FAIL = []
CHECKED = json.loads((HERE / "concept_check.json").read_text(encoding="utf-8"))


def words_of(s):
    return {w for w in re.findall(r"[a-zà-ÿ]{4,}", s.lower()) if w not in STOP}


# ------------------------------------------------------------------ Spotlight
def http_json(url, params, timeout=60):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def as_list(x):
    return [] if x is None else x if isinstance(x, list) else [x]


def short(u):
    return urllib.parse.unquote(u.rsplit("/", 1)[-1]) if u else u


def annotate(text, lang):
    """Spotlight's first choice (the Oct 13 method)."""
    d = http_json(SPOT[lang] + "/annotate", {"text": text, "confidence": 0.5})
    out = []
    for r in as_list(d.get("Resources")):
        try:
            if float(r.get("@percentageOfSecondRank", 0)) >= 0.5:
                continue
            out.append({"surface": r["@surfaceForm"], "offset": int(r["@offset"]), "page": short(r["@URI"]), "types": r.get("@types", "")})
        except (KeyError, ValueError):
            continue
    return out


def candidates(text, lang):
    """Every sense Spotlight considered for every phrase it spotted."""
    d = http_json(SPOT[lang] + "/candidates", {"text": text, "confidence": 0.3})
    ann = d.get("annotation", d)
    out = []
    for sf in as_list(ann.get("surfaceForm")):
        res = []
        for c in as_list(sf.get("resource")):
            try:
                res.append({"page": short(c.get("@uri") or c.get("@URI")), "label": c.get("@label", ""),
                            "score": float(c.get("@finalScore", c.get("@contextualScore", 0)) or 0),
                            "context": float(c.get("@contextualScore", 0) or 0), "support": float(c.get("@support", 0) or 0),
                            "types": c.get("@types", "")})
            except (TypeError, ValueError):
                continue
        res.sort(key=lambda c: -c["score"])
        out.append({"surface": sf.get("@name", ""), "offset": int(sf.get("@offset", 0)), "senses": res})
    return out


# ------------------------------------------------------------------ French to English
_fr_cache = {}
FR_CACHE_FILE = Path(CACHE) / "fr_to_en_cache.json"
FR_STATS = {"wikipedia": 0, "dbpedia": 0, "none": 0, "failed_batches": 0}
try:
    _fr_cache.update(json.loads(FR_CACHE_FILE.read_text(encoding="utf-8")))
except Exception:
    pass


def _get(url, params, timeout=30, tries=3, accept="application/json"):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                         headers={"Accept": accept, "User-Agent": "FACTUALITY-study/1.0 (Yale; research use)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            wait = e.headers.get("Retry-After") if e.headers else None
            time.sleep(min(30, int(wait)) if wait and wait.isdigit() else 3 * (k + 1))
        except Exception as e:
            last = e
            time.sleep(3 * (k + 1))
    raise last


def why(e):
    return f"{type(e).__name__} {getattr(e, 'code', '')}".strip()


def _wiki_langlinks(batch):
    """French Wikipedia titles -> English titles through Wikipedia's own language links (follows French redirects)."""
    d = _get(FR_WIKI, {"action": "query", "format": "json", "prop": "langlinks", "lllang": "en", "lllimit": "max", "redirects": 1,
                       "titles": "|".join(t.replace("_", " ") for t in batch)})
    q = d.get("query", {})
    back = {}
    for x in q.get("normalized", []) + q.get("redirects", []):
        back.setdefault(x["to"], []).append(x["from"])
    out = {}
    for pg in q.get("pages", {}).values():
        ll = pg.get("langlinks")
        if not ll:
            continue
        en = ll[0].get("*") or ll[0].get("title")
        if not en:
            continue
        names, todo = {pg["title"]}, [pg["title"]]
        while todo:                                  # walk back through normalisation and redirects to the asked title
            t = todo.pop()
            for f in back.get(t, []):
                if f not in names:
                    names.add(f); todo.append(f)
        for nm in names:
            out[nm.replace(" ", "_")] = en.replace(" ", "_")
    return out


def _dbpedia_sameas(batch):
    vals = " ".join("<http://fr.dbpedia.org/resource/" + urllib.parse.quote(p.replace(" ", "_"), safe="_()',.-:!*;&=+$@~%/") + ">" for p in batch)
    q = ("SELECT ?f ?e WHERE { VALUES ?f { " + vals + " } ?f <http://www.w3.org/2002/07/owl#sameAs> ?e "
         "FILTER(STRSTARTS(STR(?e), \"http://dbpedia.org/resource/\")) }")
    d = _get(FR_SPARQL, {"query": q}, timeout=60, tries=2, accept="application/sparql-results+json")
    return {short(row["f"]["value"]): short(row["e"]["value"]) for row in d["results"]["bindings"]}


def fr_to_en(pages):
    """French DBpedia page names -> English page names: Wikipedia language links first, then fr.dbpedia owl:sameAs."""
    want = [p for p in dict.fromkeys(pages) if p and p not in _fr_cache]
    for b in range(0, len(want), 40):
        batch = want[b:b + 40]
        if b:
            time.sleep(1)                             # be gentle with Wikipedia's servers
        got = {}
        try:
            got = {k: v for k, v in _wiki_langlinks(batch).items() if k in batch}
            FR_STATS["wikipedia"] += len(got)
        except Exception as e:
            FR_STATS["failed_batches"] += 1
            say(f"   Wikipedia language links failed for a batch of {len(batch)} ({why(e)}); trying fr.dbpedia.org")
        rest = [p for p in batch if p not in got]
        if rest:
            try:
                more = _dbpedia_sameas(rest)
                FR_STATS["dbpedia"] += len(more); got.update(more)
            except Exception as e:
                FR_STATS["failed_batches"] += 1
                say(f"   fr.dbpedia.org also failed for a batch ({why(e)}); {len(rest)} French pages stay unmapped this run")
                for p in rest:
                    got.setdefault(p, "__retry__")
        for p in batch:
            v = got.get(p)
            if v == "__retry__":
                continue                              # not cached, so a later run tries again
            _fr_cache[p] = v
            if v is None:
                FR_STATS["none"] += 1
    try:
        FR_CACHE_FILE.write_text(json.dumps(_fr_cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return {p: _fr_cache.get(p) for p in pages}


# ------------------------------------------------------------------ choosing a sense
class Chooser:
    def __init__(self, idx, indptr, indices, names, code=None, props=None):
        self.idx, self.indptr, self.indices, self.names, self.code, self.props = idx, indptr, indices, names, code, props
        self._nb, self._where = {}, {}

    def located_in(self, page):
        """Countries the page itself says it is in: outgoing country/location/state ... links, or a country in its title."""
        if page in self._where:
            return self._where[page]
        out = set()
        for p in re.findall(r"\(([^)]*)\)", page):
            for c in COUNTRIES:
                if c.replace("_", " ").lower() == p.replace("_", " ").lower().strip():
                    out.add(c)
        i = self.idx.get(page)
        if i is not None and self.code is not None:
            lo, hi = self.indptr[i], self.indptr[i + 1]
            for j in range(lo, min(hi, lo + 4000)):
                c = int(self.code[j])
                if c % 2 == 0 and prop_name(self.props[c // 2]) in LOC_PROPS:
                    nm = self.names[self.indices[j]]
                    if nm in COUNTRIES:
                        out.add(nm)
        self._where[page] = out
        return out

    def neighbours(self, page):
        i = self.idx.get(page)
        if i is None:
            return set()
        if page not in self._nb:
            self._nb[page] = {self.names[j] for j in self.indices[self.indptr[i]:self.indptr[i + 1]][:4000]}
        return self._nb[page]

    def check(self, c, sentence, sw, allowed, lowercase, variant):
        """Reasons this sense does not fit the sentence (empty = it fits), and how much the sentence supports it."""
        page, why = c["page"], []
        nb = self.neighbours(page)
        where = self.located_in(page)
        foreign = where - allowed
        if foreign and not (where & allowed):
            why.append("located in " + ", ".join(sorted(foreign)[:2]))
        paren = re.findall(r"\(([^)]*)\)", page)
        flags = {w for p in paren for w in re.findall(r"[a-z]+", p.lower())} & TITLE_FLAGS
        tflags = {t.split(":")[-1].lower() for t in c["types"].split(",") if t}
        media = (flags - {"rugby", "footballer", "cricketer", "basketball", "baseball", "soccer"}) | {t for t in tflags if any(
            m in t for m in ("film", "album", "single", "band", "televisionshow", "videogame", "academicjournal", "magazine", "musicalwork"))}
        sporty = (flags & {"rugby", "footballer", "cricketer", "basketball", "baseball", "soccer"}) or any("athlete" in t or "player" in t for t in tflags)
        if media and not (sw & MEDIA):
            why.append("a creative work")
        if sporty and not (sw & SPORT):
            why.append("a sports sense")
        nbw = {w for x in list(nb)[:4000] for w in re.findall(r"[a-zà-ÿ]{4,}", x.lower())}
        support = len(sw & nbw)
        if variant == 2 and lowercase and support == 0:
            why.append("no support in the sentence")
        if variant == 3 and lowercase and c["context"] < 0.5:
            why.append(f"low context score ({c['context']:.2f})")
        return why, support

    def pick(self, sense_list, sentence, jur, lowercase, variant):
        """variant 0: Spotlight's first choice. 1: the first choice stands unless it is tied to another country, is a
        film/album/journal or a sports sense with no such words in the sentence; then the next sense the sentence
        supports (a neighbouring page shares a word with the sentence), or none. 2: as 1, and a lowercase word's sense
        must be supported by the sentence. 3: as 1, and a lowercase word needs Spotlight's context score >= 0.5."""
        if not sense_list:
            return None, "no candidate"
        if variant == 0:
            return sense_list[0]["page"], "Spotlight's first choice"
        sw = words_of(sentence)
        mentioned = {c for c in COUNTRIES if c.replace("_", " ").lower() in sentence.lower()}
        allowed = HOME.get(jur, set()) | mentioned
        why0, _ = self.check(sense_list[0], sentence, sw, allowed, lowercase, variant)
        if not why0:
            return sense_list[0]["page"], "Spotlight's first choice passes the checks"
        for c in sense_list[1:8]:
            why, support = self.check(c, sentence, sw, allowed, lowercase, variant)
            if not why and support > 0:
                return c["page"], f"first choice {sense_list[0]['page']} rejected ({'; '.join(why0)}); next sense supported by the sentence"
        return None, f"first choice {sense_list[0]['page']} rejected ({'; '.join(why0)}); no other sense fits"


POS = {}          # sentence number -> [(start, end, part of speech)] from the saved spaCy parse


def load_pos():
    try:
        rows = json.loads((HERE / "pc.json").read_text(encoding="utf-8"))["rows"]
    except Exception:
        return
    for r in rows:
        spans, at = [], 0
        for t in r.get("deps_spacy", []):
            w, pos, ws = t[1], t[3], t[7] if len(t) > 7 else " "
            k = r["text"].find(w, at)
            if k < 0:
                spans = None; break
            spans.append((k, k + len(w), pos)); at = k + len(w)
        if spans:
            POS[r["text"]] = spans


PARTY = re.compile(r"Part(?:y|i)\b|_Party_|^Parti_|Party$|^Bloc_|^Coalition_Avenir|^New_Democratic")


def has_noun(sentence, offset, surface, page=None):
    """True when the words Spotlight spotted include a noun or a name (or when the sentence has no saved parse).
    An adjective also counts when it names a party ("Republican bill", "le gouvernement libéral", "péquiste") or,
    in English, when it is capitalised away from the start of the sentence (a proper adjective)."""
    spans = POS.get(sentence)
    if not spans or offset is None:
        return True
    a, b = offset, offset + len(surface)
    tags = [p for (x, y, p) in spans if x < b and y > a]
    if not tags:
        return True
    if any(p in NOUNISH for p in tags) or (all(p == "NUM" for p in tags) and re.fullmatch(r"\d{4}", surface or "") is not None):
        return True
    if all(p == "ADJ" for p in tags):
        if page and PARTY.search(page):
            return True
        if offset > 0 and surface[:1].isupper() and re.fullmatch(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*", surface or ""):
            return True
    return False


def phrase_concepts(phrase, lang, jur, sentence, sent_cands, chooser, idx, variant, nouns_only=True):
    """Concepts for one subject or object phrase. Returns list of (surface, page, how)."""
    found, covered = [], []
    phrase_g = re.sub(r"^(The|This|Our|That|Le|La|Les|Ce|Cette|Notre)\b", lambda m: m.group(1).lower(), phrase)
    if BILL[lang].search(phrase):
        found.append((BILL[lang].search(phrase).group(0), "(the bill)", "the bill under debate"))
        covered.append(BILL[lang].search(phrase).span())
    for pat, page in GAZ.get(jur, []):
        m = re.search(pat, phrase_g)
        if m and page in idx:
            found.append((m.group(0), page, "institution of this legislature"))
            covered.append(m.span())
    # names: the longest capitalised run that is a page title
    for m in re.finditer(r"(?:[A-ZÀ-Ý][\w’'.-]*)(?:\s+(?:of|de|du|des|la|le|et|and|for|pour|sur)?\s*[A-ZÀ-Ý][\w’'.-]*)+", phrase):
        if any(a <= m.start() < b for a, b in covered):
            continue
        t = m.group(0).strip().replace(" ", "_")
        t2 = re.sub(r"^(?:The|Le|La|Les|L')_", "", t)
        for cand in (t, t2):
            if cand in idx:
                found.append((m.group(0), cand, "page title")); covered.append(m.span()); break
    pl = phrase.lower()
    for sc in sent_cands:
        s = sc["surface"]
        if not s or s.lower() not in pl:
            continue
        a = pl.find(s.lower())
        if any(x <= a < y for x, y in covered):
            continue
        if ROMAN.match(s) and variant > 0:
            continue
        if variant > 0 and nouns_only and not has_noun(sentence, sc.get("offset"), s, (sc["senses"][0]["page"] if sc["senses"] else None)):
            continue
        senses = sc["senses"]
        if lang == "fr" and senses:
            m = fr_to_en([c["page"] for c in senses[:8]])
            senses = [dict(c, page=m[c["page"]]) for c in senses if m.get(c["page"])] if variant > 0 else senses
        page, how = chooser.pick(senses, sentence, jur, s[:1].islower(), variant)
        if page:
            found.append((s, page, "Spotlight, " + how)); covered.append((a, a + len(s)))
    if variant > 0 and not [f for f in found if f[1] != "(the bill)"]:
        heads = [w for w in re.findall(r"[a-zà-ÿ]+", pl) if w not in STOP]
        for w in reversed(heads[:6]):
            if w in LEX and LEX[w] in idx:
                found.append((w, LEX[w], "common noun")); break
    return found


# ------------------------------------------------------------------ path score
def factual_only(indptr, indices, code, props):
    """The same graph without rdfs:seeAlso and owl:differentFrom links (both directions)."""
    bad = np.array([prop_name(p) in NONFACT for p in props] + [False])
    pidx = (code // 2).astype(np.int64)
    keep = ~bad[np.minimum(pidx, len(props))]
    rows = np.repeat(np.arange(len(indptr) - 1, dtype=np.int32), np.diff(indptr))
    counts = np.bincount(rows[keep], minlength=len(indptr) - 1)
    new_indptr = np.zeros(len(indptr), dtype=np.int64); np.cumsum(counts, out=new_indptr[1:])
    removed = int((~keep).sum())
    del rows
    return new_indptr, indices[keep], code[keep], removed


class Paths:
    def __init__(self, names, indptr, indices, code, props):
        self.names, self.indptr, self.indices, self.code, self.props = names, indptr, indices, code, props
        deg = np.diff(indptr).astype(np.int64); self.deg = deg
        self.logk = np.log(np.maximum(deg, 1)).astype(np.float64) + 1e-9
        self.G = csr_matrix((self.logk[indices], indices, indptr), shape=(len(names), len(names)))
        self._last = (None, None)

    def edge(self, x, y):
        lo, hi = self.indptr[x], self.indptr[x + 1]
        j = lo + np.searchsorted(self.indices[lo:hi], y)
        return j if j < hi and self.indices[j] == y else None

    def score(self, si, ti, cut=False):
        if si == ti:
            return None
        saved = []
        if cut:
            for x, y in ((si, ti), (ti, si)):
                j = self.edge(x, y)
                if j is not None:
                    saved.append((j, self.G.data[j])); self.G.data[j] = 1e15
        if not cut and self._last[0] == si:
            d, pred = self._last[1]
        else:
            d, pred = dijkstra(self.G, directed=True, indices=si, return_predecessors=True)
            if not cut:
                self._last = (si, (d, pred))
        for j, v in saved:
            self.G.data[j] = v
        if not np.isfinite(d[ti]) or d[ti] >= 1e14:
            return {"tau": 0.0, "links": None, "path": ""}
        cost = max(0.0, float(d[ti] - self.logk[ti]))
        nodes, x = [ti], ti
        while x != si:
            x = int(pred[x]); nodes.append(x)
        nodes.reverse()
        parts = [self.names[nodes[0]]]
        for a, b in zip(nodes, nodes[1:]):
            c = int(self.code[self.edge(a, b)])
            rel = self.props[c // 2]
            parts.append(f"-[{rel}]->" if c % 2 == 0 else f"<-[{rel}]-")
            parts.append(self.names[b] if b == nodes[-1] else f"{self.names[b]} (links {self.deg[b]})")
        return {"tau": round(1 / (1 + cost), 4), "links": len(nodes) - 1, "path": " ".join(parts)}


def main():
    st = json.loads((OUT / "statements_v4.json").read_text(encoding="utf-8"))
    rows = st["rows"]
    say("== 1. the full graph from ~/.kg_dump")
    f, names, props, indptr, indices, code, red = load_graph()
    idx = {nm: i for i, nm in enumerate(names)}
    say(f"   {len(names):,} pages, {len(indices) // 2:,} links")
    indptr, indices, code, removed = factual_only(indptr, indices, code, props)
    say(f"   left out {removed // 2:,} 'see also' and 'not to be confused with' links; {len(indices) // 2:,} factual links remain")
    load_pos()
    say(f"   parts of speech for {len(POS)} of {len(rows)} sentences (so 'The', 'You', 'major' are not taken as concepts)")
    chooser = Chooser(idx, indptr, indices, names, code, props)
    paths = Paths(names, indptr, indices, code, props)
    say("== 2. Spotlight (tunnel to Dunkleosteus)")
    try:
        annotate("Barack Obama was born in Hawaii.", "en")
    except Exception as e:
        sys.exit(f"Spotlight is not answering on localhost:2222 ({type(e).__name__}: {e}). Open the SSH tunnel and run again. Nothing changed.")
    out, sense_eval, t0, raw = [], [], time.time(), {}
    pre = {}
    for r in rows:                               # Spotlight first, for every sentence
        try:
            pre[r["n"]] = candidates(r["text"], r["lang"])
        except Exception as e:
            pre[r["n"]] = []
            if not CAND_FAIL:
                say(f"   Spotlight's candidate list failed ({type(e).__name__}: {str(e)[:150]}); using its first choices instead")
            CAND_FAIL.append(r["n"])
    frp = [c["page"] for r in rows if r["lang"] == "fr" for sc in pre[r["n"]] for c in sc["senses"][:8]]
    frp += [cc["old"] for cc in CHECKED if any(r["n"] == cc["n"] and r["lang"] == "fr" for r in rows)]
    if frp:
        say(f"   mapping {len(set(frp))} French pages to English in a few batches")
        fr_to_en(frp)
    for r in rows:
        lang, jur, text = r["lang"], r["jurisdiction"], r["text"]
        cands = pre[r["n"]]
        raw[str(r["n"])] = cands
        if not cands:
            try:                               # fall back to Spotlight's first choices on the whole sentence
                cands = [{"surface": e["surface"], "offset": e["offset"], "senses": [{"page": e["page"], "label": "", "score": 1.0,
                          "context": 1.0, "support": 0.0, "types": e.get("types", "")}]} for e in annotate(text, lang)]
            except Exception:
                cands = []
        for s in r["statements"]:
            if s["kind"] != "asserted":
                continue
            rec = {"n": r["n"], "lang": lang, "jurisdiction": jur, "bill_key": r["bill_key"], "sentence": text,
                   "statement": f"{s['subject']} | {s['verb']} | {s['object']}", "negated": s.get("negated", False), "hedged": s.get("hedged", False),
                   "found_by": s.get("found_by", []), "source": s.get("source", "agreed")}
            try:
                old = annotate(f"{s['subject']} {s['verb']} {s['object']}".strip(), lang)
            except Exception:
                old = []
            cut1, cut2 = len(s["subject"]), len(s["subject"]) + 1 + len(s["verb"])
            rec["old_subject"] = [(e["surface"], e["page"]) for e in old if e["offset"] < cut1]
            rec["old_object"] = [(e["surface"], e["page"]) for e in old if e["offset"] > cut2]
            for v in (1, 2, 3):
                subj = phrase_concepts(s["subject"].replace(" (inh)", ""), lang, jur, text, cands, chooser, idx, v)
                obj = phrase_concepts(s["object"], lang, jur, text, cands, chooser, idx, v)
                rec[f"v{v}_subject"], rec[f"v{v}_object"] = subj, obj
                best = None
                for a in [x for x in subj if x[1] in idx][:4]:
                    for b in [x for x in obj if x[1] in idx][:4]:
                        if a[1] == b[1]:
                            continue
                        p = paths.score(idx[a[1]], idx[b[1]])
                        if p and (best is None or p["tau"] > best["tau"]):
                            best = dict(p, subject=a[1], object=b[1])
                if best:
                    nd = paths.score(idx[best["subject"]], idx[best["object"]], cut=True) if best["links"] == 1 else dict(best)
                    best["tau_no_direct"], best["path_no_direct"] = nd["tau"], nd["path"]
                    best["claim_score"] = round(1 - best["tau"], 4) if s.get("negated", False) else best["tau"]
                    best["reading"] = ("negated claim: a short path argues against it" if s.get("negated", False) else "a short path supports it")
                rec[f"v{v}_path"] = best
            out.append(rec)
        for cc in CHECKED:
            n, surf = cc["n"], cc["surface"]
            if n != r["n"]:
                continue
            if (n, surf) in EXPECTED:
                ok = EXPECTED[(n, surf)]
            else:                              # judged right on Oct 13: the same page, or its English name for French
                ok = {cc["old"]} | ({fr_to_en([cc["old"]]).get(cc["old"])} - {None} if lang == "fr" else set())
            sc = next((c for c in cands if c["surface"].lower() == surf.lower()), None)
            row = {"n": n, "side": cc["side"], "surface": surf, "old_pick": cc["old"], "judged_right_oct13": cc["right"],
                   "accept": sorted(x or "(none)" for x in ok), "spotlight_senses": [c["page"] for c in (sc["senses"][:6] if sc else [])]}
            for v in (0, 1, 2, 3):
                senses = sc["senses"] if sc else []
                if lang == "fr" and senses and v > 0:
                    m = fr_to_en([c["page"] for c in senses[:8]]); senses = [dict(c, page=m[c["page"]]) for c in senses if m.get(c["page"])]
                if v > 0 and ROMAN.match(surf):
                    page, how = None, "a numeral"
                elif v > 0 and sc and not has_noun(text, sc.get("offset"), surf, (sc["senses"][0]["page"] if sc["senses"] else None)):
                    page, how = None, "not a noun or a name"
                else:
                    page, how = chooser.pick(senses, text, jur, surf[:1].islower(), v)
                if v > 0:
                    for m in re.finditer(r"(?:[A-ZÀ-Ý][\w’'.-]*)(?:\s+(?:of|de|du|des|la|le|et|and|for)?\s*[A-ZÀ-Ý][\w’'.-]*)+", text):
                        if surf in m.group(0) and m.group(0) != surf and m.group(0).replace(" ", "_") in idx:
                            page, how = m.group(0).replace(" ", "_"), "page title (longer name)"; break
                row[f"v{v}"], row[f"v{v}_how"] = page, how
                row[f"v{v}_right"] = page in ok
            sense_eval.append(row)
        if len(out) % 20 == 0:
            say(f"   {len(out)} statements done ({time.time() - t0:.0f}s)")
    # David's example sentence: "This House condemns capital punishment"
    demo = []
    for a in ("United_States_House_of_Representatives", "Legislative_Assembly_of_Ontario", "National_Assembly_of_Quebec",
              "House_of_Commons_of_Canada", "Supreme_Court_of_the_United_States"):
        if a in idx and "Capital_punishment" in idx:
            p = paths.score(idx[a], idx["Capital_punishment"])
            demo.append(dict(subject=a, object="Capital_punishment", **(p or {})))
    summ = {}
    for v in ("old", "v1", "v2", "v3"):
        if v == "old":
            both = sum(1 for x in out if x["old_subject"] and x["old_object"])
        else:
            both = sum(1 for x in out if [c for c in x[f"{v}_subject"] if c[1] in idx] and [c for c in x[f"{v}_object"] if c[1] in idx])
        summ[v] = {"statements": len(out), "concept at both ends": both,
                   "with a path": sum(1 for x in out if v != "old" and x.get(f"{v}_path")) if v != "old" else None}
    for v in (0, 1, 2, 3):
        summ[f"hand-checked senses right, version {v}"] = f"{sum(1 for r in sense_eval if r[f'v{v}_right'])}/{len(sense_eval)}"
    summ["sentences where the candidate list failed"] = len(CAND_FAIL)
    summ["French pages mapped to English"] = dict(FR_STATS)
    summ["French statements with a concept at either end (v1)"] = (
        f"{sum(1 for x in out if x['lang'] == 'fr' and (x['v1_subject'] or x['v1_object']))}/{sum(1 for x in out if x['lang'] == 'fr')}")
    summ["links left out (see also, not to be confused with)"] = removed // 2
    (OUT / "spotlight_raw.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    res = {"version": "concepts v3 (Oct 15e)", "graph": os.path.basename(f), "summary": summ, "sense_eval": sense_eval,
           "statements": out, "this_house_condemns_capital_punishment": demo}
    (OUT / "concepts_v3.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    say("== results")
    for k, v in summ.items():
        print("   ", k, v)
    for d in demo:
        print("    This House condemns capital punishment:", d["subject"], "->", d.get("tau"), d.get("path", "")[:160])
    say("== wrote " + str(OUT / "concepts_v3.json"))


if __name__ == "__main__":
    main()
