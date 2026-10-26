"""build_disc_nb.py OUT.ipynb [--run]   Writes the discourse-first notebook (the Oct 22 design, step by step, with its
tests); with --run, also executes every cell in one Python process and stores the outputs (text, tables, figures) in
the notebook, so it opens with results already shown."""
import sys, json, io, base64, contextlib, traceback, os, types

CELLS = []
def md(s): CELLS.append(("markdown", s.strip("\n")))
def code(s): CELLS.append(("code", s.strip("\n")))

md(r"""
# Discourse first, then a constituency tree for each unit

The design agreed at the Oct 22 meeting, run step by step. Each step is code; run the cells in order.

| What was agreed on Oct 22 (time in the recording) | Where it is here |
|---|---|
| Run the discourse parse first (27:30, 33:40) | Step 1 |
| Run the constituency parse on each discourse unit, not on the whole sentence (27:30, 33:45) | Step 2 |
| Take the subjects and objects from each unit's constituency tree: the connections within a unit (33:45) | Step 3 |
| Use the discourse parse for the connections between units: unit 1 takes the subject of unit 0 ("inferential substitution", 28:20); "that is why" points to unit 0 and unit 1 together (29:35 to 30:25) | Step 4 |
| Only these two parsers: no dependency parse, nothing to reconcile (34:10) | Steps 1 to 4; checked in Part 7 |
| The same for French: the Quebec sentence gives "L'an dernier" as the frame and two facts (35:00 to 38:45) | Part 2 |
| Write the connections as "unit 0 and unit 1 to unit 2" (47:05) | every relation |
| The trees expanded, a tree inside a tree, drawn the way Mann and Thompson draw discourse trees (41:40 to 46:15) | Step 5 |
| Run it on more sentences from each legislature (40:25) | Part 4 |
| Keep every step in a data structure that can be read, to check what is in DBpedia (48:20) | Part 5 |

**Parsers.** On the Mac, with the project's venv, the cells below run the real parsers: isanlp_rst for the discourse parse, Stanza (English) and Berkeley benepar_fr2 (French) for the constituency parse of each unit. Anywhere else the notebook uses the parses saved on Oct 19 and says so at the top of each output.

**Answer keys.** The keys used in Part 7 were drafted with AI assistance; they are working keys, not a gold standard.
""")

code(r"""
import os, sys, json, ast, random, math, collections, re, copy, time
from pathlib import Path
import pandas as pd
from IPython.display import display, SVG, HTML
pd.set_option("display.max_colwidth", 90); pd.set_option("display.width", 220)

PROJECT = Path(os.environ.get("LHF_PROJECT", Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"))
RULES = Path(os.environ.get("LHF_RULES", PROJECT / "scripts" / "v6"))
PARSES = Path(os.environ.get("LHF_PARSES", PROJECT / "data" / "parity_oct19" / "parity_parses.json"))
EDU_TREES = Path(os.environ.get("LHF_EDU_TREES", PROJECT / "outputs" / "edu" / "edu_trees.json"))
MORE = Path(os.environ.get("LHF_MORE", PROJECT / "outputs" / "edu" / "more_parses.json"))
OUTDIR = Path(os.environ.get("LHF_OUT", PROJECT / "outputs" / "edu"))
OUTDIR.mkdir(parents=True, exist_ok=True)

sys.argv = [sys.argv[0], str(RULES), str(PARSES)]
sys.path.insert(0, str(RULES))
import edu_pipeline as E          # the steps below call this file's functions
import edu_draw as D              # the tree-inside-a-tree figure
P = E.P
# every rule and key file is loaded from scripts/v6 now, before the parsers are imported: the parser module puts
# scripts/v4 (older copies of some of these files) at the front of Python's search path
import importlib
RULE_MODULES = ["preds", "lexicon", "const_fr", "combine_lib", "frames", "parity_score", "full", "compare3", "gold", "gold2",
                "gold_heldout", "parallel_tests", "edu_pipeline", "edu_draw"]
for m in RULE_MODULES:
    importlib.import_module(m)
E.OPT["units_only"] = True        # the Oct 22 design: only each unit's own tree and the discourse parse

ROWS = json.load(open(PARSES, encoding="utf-8"))["rows"]
BY_N = {r["n"]: r for r in ROWS}
BY_TEXT = {r["text"]: r for r in ROWS}
REPARSED = json.load(open(EDU_TREES, encoding="utf-8")) if EDU_TREES.exists() else {}

LIVE, WHY = False, ""
if os.environ.get("LHF_LIVE", "1") != "0":
    try:
        sys.path.insert(1, str(PROJECT / "scripts" / "v4"))
        import parse_corpus_v5 as V
        assert V.P is P, "parse_corpus_v5 loaded another copy of the rules"
        LIVE = True
    except Exception as ex:                       # noqa: BLE001
        WHY = f"{type(ex).__name__}: {ex}"
    finally:
        v4 = str(PROJECT / "scripts" / "v4")
        sys.path[:] = [x for x in sys.path if x != v4] + [v4]      # scripts/v6 first again; v4 only for the parsers
print("parsers:", "live (isanlp_rst, Stanza, Berkeley benepar_fr2)" if LIVE else f"not loaded here ({WHY[:80]}); using the parses saved Oct 19")
print("units parsed on their own, saved:", f"{len(REPARSED)} sentences" if REPARSED else "none yet (run_edu.sh makes them)")
print(f"saved sentences: {len(ROWS)}")
WRONG = {m: sys.modules[m].__file__ for m in RULE_MODULES if Path(sys.modules[m].__file__).resolve().parent != RULES.resolve()}
print("rules and keys loaded from:", RULES, "(all of them)" if not WRONG else f"-- NOT ALL: {WRONG}")
""")

code(r"""
def tree_of(text, lang):
    "Step 2 for one piece of text: its constituency tree(s), read the same way as the full corpus run."
    if lang == "en":
        doc = V.stanza_model("en")(text)
        return [P.from_stanza_tree(x.constituency) for x in doc.sentences if getattr(x, "constituency", None) is not None]
    bp = V.berkeley()
    if bp is None:
        return []
    trees, _ = V.berkeley_trees(bp, V.BEN["mod"], V.spacy_model("fr")(text))
    return trees

def edus_of(row):
    d = row.get("disc_native") or {}
    edus = d.get("edus") or [{"text": row["text"], "start": 0, "end": len(row["text"])}]
    return E.reanchor(edus, row["text"])

def step1(text, lang, n=None):
    "Step 1: the discourse parse. Live on the Mac; otherwise the saved parse of this sentence."
    if LIVE:
        d, status = V.rst_parse(text, lang)
        return {"n": n or "(typed)", "set": "typed", "lang": lang, "text": text, "trees": [], "disc_native": d, "disc_native_status": status}, "parsed now"
    row = BY_N.get(n) or BY_TEXT.get(text)
    if row is None:
        raise ValueError("no parsers here and this sentence was not saved; run this on the Mac")
    return row, "saved Oct 19"

def step2(row):
    "Step 2: a constituency tree for each unit, parsing the unit's own text."
    if LIVE and row.get("set") == "typed":
        return [tree_of(e["text"].strip(), row["lang"]) for e in edus_of(row)], "each unit parsed now"
    if row["n"] in REPARSED:
        return REPARSED[row["n"]], "each unit parsed on its own (saved by run_edu.sh)"
    # stand-in until run_edu.sh has run: the sentence's saved tree cut down to each unit's words
    return [[t for t, _ in ps] for ps in E.unit_trees(row, edus_of(row))], "STAND-IN: the sentence's tree cut to each unit (run_edu.sh parses each unit alone)"

WITHIN_ONLY = {"discourse_subject": False, "demonstrative": False, "said_object": False, "frame_context": False, "relpron": False}

def run(row, trees, opt=None):
    saved = dict(E.OPT)
    try:
        E.OPT.update(opt or {})
        return E.process(row, trees)
    finally:
        E.OPT.clear(); E.OPT.update(saved)

def relation_table(rec):
    return pd.DataFrame([{"connection": c["from"] + " to " + c["to"], "relation": c["relation"], "parser's own label": c.get("parser_label", ""), "main part": c["main"],
                          "how it reads": c["reads"].split(": ", 1)[1]} for c in rec["connections"]])

def lines_table(rec, with_source=True):
    out = []
    for l in rec["lines"]:
        d = {"unit": l["unit"], "subject": l["subject"], "verb": l["verb"], "object": l["object"]}
        if with_source:
            d["where the subject came from"] = l.get("subject_from") or "its own unit"
            d["object from"] = l.get("object_from") or ""
            d["context"] = "; ".join(l.get("context") or [])
            d["that = "] = (l.get("refers_to") or "")
        out.append(d)
    return pd.DataFrame(out)

def walk_through(text, lang, n=None):
    row, src1 = step1(text, lang, n)
    print(f"Sentence: {row['text']}\n")
    print(f"STEP 1. Discourse parse ({src1}): the units")
    edus = edus_of(row)
    display(pd.DataFrame([{"unit": i, "text": e["text"].strip()} for i, e in enumerate(edus)]))
    rec0 = run(row, None)                    # only to read the relations in the shared wording
    print("        and how the discourse parse connects them")
    display(relation_table(rec0))
    trees, src2 = step2(row)
    print(f"\nSTEP 2. A constituency tree for each unit ({src2})")
    within = run(row, trees, WITHIN_ONLY)
    for u in within["units"]:
        print(f"   unit {u['unit']}: " + "  ".join(u["tree"]))
    print("\nSTEP 3. Subject | verb | object read from each unit's own tree (connections within a unit; nothing taken from other units yet)")
    display(lines_table(within, with_source=False))
    rec = run(row, trees)
    print("\nSTEP 4. The discourse parse connects the units: a gap in a unit is filled from the unit it is connected to, and 'that' is read as the units it points to")
    display(lines_table(rec))
    print("\nSTEP 5. The tree inside a tree")
    display(SVG(D.figure(rec)))
    return rec
""")

md(r"""
## Part 1. The English sentence from the meeting

*A small hardware store in an AHP would be joining an association, sending their premiums not to themselves but off to others, and that is why we need the check.*

What was said should come out (28:20 to 32:30): unit 0 is a fact on its own (the store would be joining an association); unit 1 elaborates unit 0, so its subject is the subject of unit 0 (the store is sending its premiums to others); unit 2 explains unit 0 and unit 1 together, so "that" is all of unit 0 and unit 1; and inside unit 2, we need the check.
""")

code(r"""
REC_EN = walk_through("A small hardware store in an AHP would be joining an association, sending their premiums not to themselves but off to others, and that is why we need the check.", "en", "sample|1")
""")

md(r"""
## Part 2. The French sentence from the meeting

*L'an dernier, la Chambre a adopté un projet de loi identique au projet de loi 5, mais le Sénat a refusé d'agir.*

What was said should come out (35:00 to 38:45): unit 1 and unit 2 are a contrast; unit 0, "L'an dernier", is the frame for both; and the facts are that the Chambre adopted a bill identical to bill 5, and that the Senate refused to act, both last year. The same steps as for English.
""")

code(r"""
REC_FR = walk_through("L'an dernier, la Chambre a adopté un projet de loi identique au projet de loi 5, mais le Sénat a refusé d'agir.", "fr", "test|A8|fr")
""")

md(r"""
## Part 3. Any sentence

Change `TEXT` and `LANG` and run the cell. On the Mac this parses the sentence now; elsewhere it only works for a saved sentence.
""")

code(r"""
TEXT = "Way back in the day, miners who went underground were constantly exposed to various types of carcinogens."
LANG = "en"
_ = walk_through(TEXT, LANG)
""")

md(r"""
## Part 4. More sentences from each legislature

On the Mac, `N_MORE` new sentences are drawn at random from each legislature's debate sentences (US House, Ontario, Quebec; seed 20261026; 8 to 60 words; none already in the answer keys) and run through steps 1 to 4. Without the parsers, the saved sentences are used, grouped by legislature, plus any new ones `run_edu.sh` saved.
""")

code(r"""
N_MORE = int(os.environ.get("LHF_N_MORE", "20"))
JUR = {"US": ("us", "en", "US House"), "ON": ("ontario", "en", "Ontario"), "QC": ("quebec", "fr", "Quebec")}

def legislature(row):
    sid = row.get("sentence_id") or ""
    return JUR[sid[:2]][2] if sid[:2] in JUR else None

def draw_new(n):
    rnd = random.Random(20261026); taken = {r.get("sentence_id") for r in ROWS}; out = []
    for code_, (j, lang, name) in JUR.items():
        recs = json.load(open(PROJECT / "data" / "dbpedia_pipeline" / j / "sentences_v3.json", encoding="utf-8"))
        recs = [x for x in recs if x.get("sentence_id") and x.get("text") and x["sentence_id"] not in taken and 8 <= len(x["text"].split()) <= 60]
        rnd.shuffle(recs)
        out += [(f"more|{code_}|{k}", V.clean(x["text"]), lang, x["sentence_id"], name) for k, x in enumerate(recs[:n], 1)]
    return out

RECS = {}                                 # every sentence run in this part: n -> the record with every step
if LIVE:
    t0 = time.time()
    for k, (n, text, lang, sid, name) in enumerate(draw_new(N_MORE), 1):
        row, _ = step1(text, lang, n); row.update(n=n, set="more", sentence_id=sid)
        RECS[n] = dict(run(row, [tree_of(e["text"].strip(), lang) for e in edus_of(row)]), legislature=name, sentence_id=sid)
        if k % 10 == 0:
            print(f"   {k} new sentences parsed ({(time.time() - t0) / k:.1f}s each)")
else:
    more_rows = json.load(open(MORE, encoding="utf-8"))["rows"] if MORE.exists() else []
    for row in [r for r in ROWS if legislature(r)] + more_rows:
        if row["n"].startswith("more|") and row["n"] not in REPARSED:
            continue
        trees, _ = step2(row)
        RECS[row["n"]] = dict(run(row, trees), legislature=legislature(row) or JUR[row["n"].split("|")[1]][2], sentence_id=row.get("sentence_id"))
src = "parsed now" if LIVE else ("saved sentences" + (", units parsed on their own" if REPARSED else ", units are STAND-INS cut from the sentence's tree"))
print(f"{len(RECS)} sentences ({src})")

def summary(recs):
    rows_ = []
    for name in ("US House", "Ontario", "Quebec"):
        xs = [x for x in recs.values() if x["legislature"] == name]
        if not xs:
            continue
        ls = [l for x in xs for l in x["lines"]]
        rows_.append({"legislature": name, "sentences": len(xs), "units per sentence": round(sum(len(x["units"]) for x in xs) / len(xs), 2),
                      "lines per sentence": round(len(ls) / len(xs), 2),
                      "units with no line": sum(1 for x in xs for u in x["units"] if not u["lines"]),
                      "subjects found through the discourse parse": sum(1 for l in ls if (l.get("subject_from") or "") and "unit tree" not in l["subject_from"]),
                      "'that' pointing to units": sum(1 for l in ls if l.get("refers_to")),
                      "most common relations": ", ".join(f"{k} {v}" for k, v in collections.Counter(r["shared"] for x in xs for r in x["relations"]).most_common(4))})
    return pd.DataFrame(rows_)
display(summary(RECS))
""")

code(r"""
# two figures per legislature
shown = collections.Counter()
for n, x in RECS.items():
    if shown[x["legislature"]] < 2 and 2 <= len(x["units"]) <= 6:
        shown[x["legislature"]] += 1
        print(f"\n{x['legislature']}  {n}: {x['text']}")
        display(relation_table(x)); display(lines_table(x))
        display(SVG(D.figure(x)))
""")

md(r"""
## Part 5. The data structure, with every step

One record per sentence, written to `outputs/edu/discourse_first_records.json`, and three flat tables for looking things up in DBpedia. Every record keeps the discourse parse as it came out of the parser, the units, each unit's tree (bracketed and as nested lists), the lines from each unit, where every borrowed subject or object came from, and the connections between units.
""")

code(r"""
SCHEMA = [
 ("n, legislature, sentence_id, lang, text", "which sentence"),
 ("discourse_status", "how the discourse parse ran"),
 ("units[].unit, text, start, end", "step 1: each discourse unit and where it sits in the sentence (characters)"),
 ("units[].tree, units[].tree_nodes", "step 2: the unit's constituency tree, bracketed and as nested lists [label, [children]]"),
 ("units[].lines[]", "step 3 and 4: subject, verb, object read from that unit"),
 ("lines[].subject_from / object_from", "step 4: blank when it came from the unit itself; otherwise which unit and which relation it came through"),
 ("lines[].refers_to", "step 4: what 'that' / 'ça' stands for (the text of the units it points to)"),
 ("lines[].context", "step 4: a unit with no clause of its own that frames this line ('L'an dernier')"),
 ("lines[].negated, kind, how", "negation; stated or embedded; which tree rule gave the line"),
 ("relations[]", "the discourse parse's relations: left and right units, relation, nuclearity, main part"),
 ("connections[]", "the same relations written as 'unit 0 and unit 1 to unit 2', with the text on each side"),
]
display(pd.DataFrame(SCHEMA, columns=["field", "what it holds"]))

ALL = dict(RECS)
for n in ("sample|1", "test|A8|fr"):
    r = BY_N[n]; t, _ = step2(r); ALL.setdefault(n, dict(run(r, t), legislature=legislature(r), sentence_id=r.get("sentence_id")))
json.dump({"design": "discourse first, then a constituency tree per unit (Oct 22)", "made": time.strftime("%Y-%m-%d %H:%M"),
           "trees": "parsed now" if LIVE else src, "rows": list(ALL.values())},
          open(OUTDIR / "discourse_first_records.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

flat, conns = [], []
for n, x in ALL.items():
    for l in x["lines"]:
        flat.append({"n": n, "legislature": x.get("legislature"), "lang": x["lang"], "unit": l["unit"],
                     "unit text": x["units"][l["unit"]]["text"], "subject": l["subject"], "verb": l["verb"], "object": l["object"],
                     "negated": l["negated"], "kind": l["kind"], "subject from": l.get("subject_from") or "",
                     "object from": l.get("object_from") or "", "that =": l.get("refers_to") or "", "context": "; ".join(l.get("context") or [])})
    for c in x["connections"]:
        conns.append({"n": n, "legislature": x.get("legislature"), "connection": c["from"] + " to " + c["to"], "relation": c["relation"], "parser's own label": c.get("parser_label", ""),
                      "main part": c["main"], "from text": c["from_text"], "to text": c["to_text"]})
DL = pd.DataFrame(flat); DC_ = pd.DataFrame(conns)
DL.to_csv(OUTDIR / "discourse_first_lines.csv", index=False); DC_.to_csv(OUTDIR / "discourse_first_connections.csv", index=False)

# the noun phrases to look up in DBpedia: every subject and object, with how often it comes up
def clean_np(s):
    s = re.sub(r"\(inh\)|\(unstated\)", "", s or "").strip(" ,.;:«»“”\"")
    return s if s and s.lower() not in E.DEMONSTR | {"i", "we", "you", "he", "she", "they", "il", "elle", "nous", "vous", "ils", "elles", "je", "on"} else ""
nouns = collections.Counter()
for l in flat:
    for k in ("subject", "object"):
        if clean_np(l[k]):
            nouns[(clean_np(l[k]), l["lang"], k)] += 1
DN = pd.DataFrame([{"noun phrase": a, "lang": b, "as": c, "times": v} for (a, b, c), v in nouns.most_common()])
DN.to_csv(OUTDIR / "discourse_first_noun_phrases.csv", index=False)
print(f"wrote {OUTDIR / 'discourse_first_records.json'} ({len(ALL)} sentences)")
print(f"      {OUTDIR / 'discourse_first_lines.csv'} ({len(DL)} lines)")
print(f"      {OUTDIR / 'discourse_first_connections.csv'} ({len(DC_)} connections)")
print(f"      {OUTDIR / 'discourse_first_noun_phrases.csv'} ({len(DN)} noun phrases to look up)")
print("\nOne record, the English sentence from the meeting (trees shortened):")
rec = copy.deepcopy(ALL["sample|1"])
for u in rec["units"]:
    u["tree_nodes"] = "[...]"; u["tree"] = [t[:80] + "..." for t in u["tree"]]
print(json.dumps({k: rec[k] for k in ("n", "lang", "text", "units", "connections")}, ensure_ascii=False, indent=1)[:4000])
""")

md(r"""
## Part 6. How the design was kept

Checks that the notebook does what was agreed, and nothing else. Each prints PASS or FAIL.
""")

code(r"""
RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL"))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"\n        {detail}" if detail and not ok else ""))

TREES = {r["n"]: step2(r)[0] for r in ROWS}
OUT = {r["n"]: run(r, TREES[r["n"]]) for r in ROWS}

# every rule and key file comes from scripts/v6, including the French rules, which load only when first needed
import const_fr as _cf
WRONG = {m: sys.modules[m].__file__ for m in RULE_MODULES if Path(sys.modules[m].__file__).resolve().parent != RULES.resolve()}
check("every rule and key file is the scripts/v6 copy (" + ", ".join(RULE_MODULES) + ")", not WRONG, WRONG)

# no dependency parse: the saved dependency parses are removed and every output stays the same
no_deps = {r["n"]: run({k: v for k, v in r.items() if not k.startswith("deps")}, TREES[r["n"]]) for r in ROWS}
diff = [n for n in OUT if json.dumps(OUT[n], sort_keys=True) != json.dumps(no_deps[n], sort_keys=True)]
check("no dependency parse is used (outputs identical with the dependency parses deleted)", not diff, diff[:5])

# no whole-sentence constituency tree: the sentence's tree is removed and every output stays the same
no_tree = {r["n"]: run(dict(r, trees=[]), TREES[r["n"]]) for r in ROWS}
diff = [n for n in OUT if json.dumps(OUT[n]["lines"], sort_keys=True) != json.dumps(no_tree[n]["lines"], sort_keys=True)]
check("the sentence's own tree is not read (lines identical with it deleted)", not diff, diff[:5])

# the discourse parse comes first: every unit's tree holds exactly that unit's words, in order
bad = []
for n, x in OUT.items():
    for u in x["units"]:
        words = re.sub(r"[^\w]", "", "".join(w for t in u["tree_nodes"] for w in E.leaves_of(t))).lower()
        if words != re.sub(r"[^\w]", "", u["text"]).lower() and not (words and words in re.sub(r"[^\w]", "", u["text"]).lower()):
            bad.append((n, u["unit"]))
check("each unit's tree holds that unit's words and nothing else", not bad, bad[:5])

# connections within a unit: a line's verb is in its own unit
bad = [(n, l["unit"], l["verb"]) for n, x in OUT.items() for l in x["lines"]
       if not all(w in x["units"][l["unit"]]["text"].lower().replace("’", "'") for w in E.tokens(l["verb"].lower().replace("’", "'")) if w)]
check("every verb is in its own unit", not bad, bad[:5])

# connections between units: anything taken from another unit says which one and through which relation
bad = []
for n, x in OUT.items():
    for l in x["lines"]:
        s = re.sub(r"[^\w]", "", l["subject"].replace("(inh)", "").lower())
        if s and s != "unstated" and s not in re.sub(r"[^\w]", "", x["units"][l["unit"]]["text"].lower()) and not l.get("subject_from"):
            bad.append((n, l["unit"], l["subject"]))
check("every subject taken from another unit is labelled with where it came from", not bad, bad[:5])

# the agreed notation
reads = [c["from"] + " to " + c["to"] for x in OUT.values() for c in x["connections"]]
check("relations are written 'unit 0 and unit 1 to unit 2'", all(re.fullmatch(r"unit \d+((, unit \d+)* and unit \d+)? to unit \d+((, unit \d+)* and unit \d+)?", r) for r in reads)
      and not any(re.search(r"units \d", c["reads"]) for x in OUT.values() for c in x["connections"]), [r for r in reads if "units" in r][:3])

# well formed relations, and the same result twice
bad = [(n, r["reads"]) for n, x in OUT.items() for r in x["relations"]
       if not (0 <= r["left"][0] <= r["left"][1] < r["right"][0] <= r["right"][1] < len(x["units"]) and r["left"][1] + 1 == r["right"][0])]
check("discourse relations join neighbouring spans", not bad, bad[:5])
again = {r["n"]: run(r, TREES[r["n"]]) for r in ROWS}
check("the same input gives the same output", all(json.dumps(OUT[n], sort_keys=True) == json.dumps(again[n], sort_keys=True) for n in OUT))
""")

md(r"""
### What the meeting said each example should give
""")

code(r"""
def L(rec):
    return [(l["unit"], l["subject"], l["verb"], l["object"]) for l in rec["lines"]]
en = OUT["sample|1"]; fr = OUT["test|A8|fr"]
check("EN unit 0: A small hardware store in an AHP | would be joining | an association",
      (0, "A small hardware store in an AHP", "would be joining", "an association") in L(en), L(en))
u1 = [l for l in en["lines"] if l["unit"] == 1]
check("EN unit 1 takes the subject of unit 0 through the elaboration: ... | sending | their premiums",
      bool(u1) and u1[0]["subject"] == "A small hardware store in an AHP" and u1[0]["verb"] == "sending" and "elaboration" in u1[0]["subject_from"], u1)
th = [l for l in en["lines"] if l["subject"].lower() == "that"]
check("EN unit 2: 'that' is unit 0 and unit 1 together", bool(th) and th[0].get("refers_to", "").startswith("unit 0 and unit 1:"), th)
check("EN unit 2: we | need | the check", (2, "we", "need", "the check") in L(en), L(en))
check("EN connection: unit 0 and unit 1 to unit 2, explanation, unit 2 the main part",
      any(c["from"] == "unit 0 and unit 1" and c["to"] == "unit 2" and c["relation"] == "explanation" and c["main"] == "unit 2" for c in en["connections"]), en["connections"])
check("EN connection: unit 0 to unit 1, elaboration", any(c["from"] == "unit 0" and c["to"] == "unit 1" and c["relation"] == "elaboration" for c in en["connections"]))
check("FR unit 1 and unit 2 are a contrast", any(c["from"] == "unit 1" and c["to"] == "unit 2" and c["relation"] == "contrast" for c in fr["connections"]), fr["connections"])
check("FR unit 0 (L'an dernier) frames unit 1 and unit 2", any(c["from"] == "unit 0" and c["to"] == "unit 1 and unit 2" and c["relation"] == "background" for c in fr["connections"]))
check("FR: la Chambre | a adopté | un projet de loi identique au projet de loi 5",
      (1, "la Chambre", "a adopté", "un projet de loi identique au projet de loi 5") in L(fr), L(fr))
check("FR: le Sénat | a refusé d'agir", (2, "le Sénat", "a refusé d'agir", "") in L(fr), L(fr))
check("FR: both facts carry 'L'an dernier' as their frame", all(any(c.startswith("L'an dernier") for c in l.get("context", [])) for l in fr["lines"]), fr["lines"])
""")

md(r"""
### Each rule on its own

Small cases with a known answer. Trees are written in the bracket form the parsers give. The rules marked *discourse* are the connections between units (step 4); the others read one unit's tree (step 3).
""")

code(r"""
def T(s):
    def conv(n):
        return n if isinstance(n, str) else [n[0], [conv(k) for k in n[1]]]
    return conv(P.parse_tree(s))

def leaf_path(tree, word, nth=0):
    ps = E.paths([tree]); ws = E.leaves_of(tree)
    return ps[[i for i, w in enumerate(ws) if w == word][nth]]

def lines_of(n):
    return [(l["subject"], l["verb"], l["object"]) for l in OUT[n]["lines"]]

# step 3, inside one unit's tree
check("unit tree: VP holding only (CC, VP) after cutting is merged",
      E.bracket(E.collapse(T("(VP (CC and) (VP (VBP rise) (PP (IN in) (NP (NN support)))))"))) == "(VP (CC and) (VBP rise) (PP (IN in) (NP (NN support))))")
check("unit tree: 'Mr. Speaker,' is someone addressed, not the subject",
      E.bracket(E.drop_address(T("(S (NP (NNP Mr.) (NNP Speaker)) (, ,) (NP (PRP I)) (VP (VBP thank) (NP (DT the) (NN gentleman))))"))) == "(S (NP (PRP I)) (VP (VBP thank) (NP (DT the) (NN gentleman))))")
check("unit tree (French): a clause inside COORD is read as a clause",
      E.bracket(E.unwrap_coord(T("(SENT (COORD (CC mais) (NP (DET le) (NPP Sénat)) (VN (V a) (VPP refusé))))"))) == "(SENT (CC mais) (NP (DET le) (NPP Sénat)) (VN (V a) (VPP refusé)))")
t = T("(ROOT (S (NP (DT The) (NN minister)) (VP (VBD urged) (NP (DT the) (NNS doctors)) (S (VP (TO to) (VP (VB accept) (NP (DT the) (NN deal))))))))")
check("unit tree: urged the doctors to accept -> the doctors accept", E.subject_from_tree(leaf_path(t, "accept"), "en")[0] == "the doctors")
t = T("(ROOT (S (NP (DT The) (NNP Senate)) (VP (VBD refused) (S (VP (TO to) (VP (VB act)))))))")
check("unit tree: The Senate refused to act -> the Senate acts", E.subject_from_tree(leaf_path(t, "act"), "en")[0] == "The Senate")
t = T("(ROOT (S (NP (DT The) (NN government)) (VP (VBD cut) (NP (NNS taxes)) (S (VP (TO to) (VP (VB help) (NP (NNS families))))))))")
check("unit tree: cut taxes to help families -> the government helps (purpose, not 'urge X to')", E.subject_from_tree(leaf_path(t, "help"), "en")[0] == "The government")
t = T("(TOP (SENT (NP (DET Le) (NC ministre)) (VN (V a) (VPP exhorté)) (NP (DET les) (NC médecins)) (PP (P à) (VPinf (VN (VINF accepter)) (NP (DET l') (NC entente))))))")
check("unit tree (French): a exhorté les médecins à accepter -> les médecins", E.subject_from_tree(leaf_path(t, "accepter"), "fr")[0] == "les médecins")
ln = {"verb": "ne pourra congédier", "negated": False}; E.fix_verb(ln, "le gouvernement ne pourra pas congédier les gens")
check("unit text: 'ne ... pas' stays in the verb and marks negation", (ln["verb"], ln["negated"]) == ("ne pourra pas congédier", True))
check("unit tree: refused to act is one verb (sample|6)", [l[1] for l in lines_of("sample|6")] == ["passed", "refused to act"], lines_of("sample|6"))
check("unit: a question is not a claim (test|A11|en)", lines_of("test|A11|en") == [], lines_of("test|A11|en"))

# step 4, through the discourse parse
check("discourse: 'who went underground' -> miners (the noun phrase of the unit it elaborates; sample|43)",
      ("miners", "went", "underground") in lines_of("sample|43"), lines_of("sample|43"))
check("discourse: 'miners | who ... | were exposed' -> miners (same-unit; sample|43)",
      any(l[0] == "miners" and l[1] == "were exposed" for l in lines_of("sample|43")), lines_of("sample|43"))
check("discourse: 'women | donating fetal tissue' (no comma) -> women (sample|2)",
      any(l[0] == "women" and l[1] == "donating" for l in lines_of("sample|2")), lines_of("sample|2"))
check("discourse: 'a store ..., | sending' (comma) -> the store, not the association (sample|1)",
      any(l[0].startswith("A small hardware store") and l[1] == "sending" for l in lines_of("sample|1")))
check("discourse: 'The report also recommends' | 'that ...' -> the object is what unit 2 says (attribution; sample|38)",
      any(l[1] == "recommends" and l[2].startswith("that the Ministry") for l in lines_of("sample|38")), lines_of("sample|38"))
check("discourse: 'repeal these ... rights' | 'that were extended' -> these health care rights and protections (sample|17)",
      any(l[0] == "these health care rights and protections" and l[1] == "were extended" for l in lines_of("sample|17")), lines_of("sample|17"))
check("discourse: 'cut taxes' | 'to help families' -> the government (purpose; test|E7|en)",
      any(l[0] == "The government" and "help" in l[1] for l in lines_of("test|E7|en")), lines_of("test|E7|en"))
check("discourse: a verbless unit is context only for background-type relations (no context in sample|37)",
      not any(l.get("context") for l in OUT["sample|37"]["lines"]))
""")

md(r"""
## Part 7. How well it does

**Found**: the key line has a matching output line (same verb, overlapping subject and object). **Exact**: subject, verb and object word for word, ignoring case and punctuation. Intervals are 95% Wilson intervals.

The rules were written while looking at the 100-sentence sample and the 45 simple test pairs, and at held-out sentences 2, 3, 8, 18, 23, 26, 29 and 30; the last table leaves those out, so it is the fairest check.
""")

code(r"""
import full as F, compare3 as K, combine_lib as C, gold_heldout as GH, parallel_tests as PT
nm = K.norm
def key_lines(t, lang):
    k = t[lang]["lines"]
    return ast.literal_eval(k) if isinstance(k, str) else k
def key_of(r):
    if r["set"] == "sample":
        return C.KEY.get(r["key_n"]) or []
    if r["set"] == "heldout":
        return GH.GH.get(r["key_n"]) or []
    t = next((t for t in PT.T if t["id"] == r["key_n"]), None)
    return key_lines(t, r["lang"]) if t else []
def as_dicts(x):
    return [dict(subject=l["subject"], verb=l["verb"], object=l["object"], negated=l["negated"], kind=l["kind"]) for l in x["lines"]]
def wilson(k, n, z=1.96):
    if not n:
        return (0, 0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - h), 100 * (c + h))
def marks(key, L):
    al = P.align(key, L); ex = {(nm(x["subject"]), nm(x["verb"]), nm(x["object"])) for x in L}
    return [a is not None for a in al], [(nm(k[0]), nm(k[1]), nm(P._no_note(k[2]))) in ex for k in key]
def group(r):
    return ("simple tests" if r["set"] == "test" else r["set"]) + " " + r["lang"]
def score_table(out, label, rows=ROWS):
    tot = collections.defaultdict(collections.Counter)
    for r in rows:
        key = key_of(r)
        if not key:
            continue
        f_, e_ = marks(key, as_dicts(out[r["n"]]))
        c = tot[group(r)]; c["key"] += len(key); c["found"] += sum(f_); c["exact"] += sum(e_)
    return pd.DataFrame([{"set": g, "design": label, "key lines": c["key"], "found %": round(100 * c["found"] / c["key"]),
                          "exact %": round(100 * c["exact"] / c["key"]), "exact 95% interval": "%.0f to %.0f" % wilson(c["exact"], c["key"])}
                         for g, c in sorted(tot.items())])
DS = score_table(OUT, "discourse first (Oct 22 design)")
display(DS)
SEEN = {"heldout|2", "heldout|3", "heldout|8", "heldout|18", "heldout|23", "heldout|26", "heldout|29", "heldout|30"}
fair = [r for r in ROWS if r["set"] == "heldout" and r["n"] not in SEEN]
print(f"held-out sentences never looked at while writing the rules ({len(fair)}):")
display(score_table(OUT, "discourse first (Oct 22 design)", fair))
""")

code(r"""
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(9, 3.4))
vals = DS["exact %"].values; lohi = [tuple(map(float, s.split(" to "))) for s in DS["exact 95% interval"]]
ax.bar(DS["set"], vals, color="#4a4a4a", yerr=[[max(0, v - a) for v, (a, b) in zip(vals, lohi)], [max(0, b - v) for v, (a, b) in zip(vals, lohi)]], capsize=3)
ax.bar(DS["set"], DS["found %"] - vals, bottom=vals, color="#c8c8c8")
ax.set_ylim(0, 100); ax.set_ylabel("key lines (%)"); ax.set_title("Exact (dark, with 95% interval) and found (dark + light)")
plt.xticks(rotation=20); plt.tight_layout(); plt.show()
""")

md(r"""
### The 45 simple test pairs, one construction each
""")

code(r"""
rows_c = []
for t in PT.T:
    for lang in ("en", "fr"):
        n = f"test|{t['id']}|{lang}"
        key = key_lines(t, lang)
        f_, e_ = marks(key, as_dicts(OUT[n])) if key else ([], [])
        rows_c.append(dict(pair=t["id"], group=t["group"], construction=t["construction"], lang=lang, found=all(f_) if key else not OUT[n]["lines"],
                           exact=all(e_) if key else not OUT[n]["lines"],
                           expected=" / ".join(" | ".join(map(str, k[:3])) for k in key) or "(none)",
                           output=" / ".join(f"{a} | {b} | {c}" for a, b, c in lines_of(n)) or "(none)"))
DCt = pd.DataFrame(rows_c)
display(DCt.groupby(["group", "lang"])[["found", "exact"]].mean().mul(100).round(0))
print("pairs not exactly right:")
display(DCt[~DCt.exact][["pair", "lang", "construction", "expected", "output"]])
""")

md(r"""
### What kind of mistake each miss is
""")

code(r"""
def classify(k, lines):
    kv = P.fold(k[1])[-1:]
    cand = [x for x in lines if kv and (kv[0] in P.fold(x["verb"]) or any(w[:4] == kv[0][:4] for w in P.fold(x["verb"])))]
    if not cand:
        return "no line with that verb"
    so = lambda x: bool(P.content(k[0].replace("(inh)", "")) & P.content(x["subject"])) or nm(k[0]) == nm(x["subject"])
    oo = lambda x: nm(P._no_note(k[2])) == nm(x["object"]) or bool(P.content(P._no_note(k[2])) & P.content(x["object"]))
    b = max(cand, key=lambda x: (so(x), oo(x)))
    if P.gold_negated(k) != bool(b["negated"]):
        return "negation differs"
    return {(False, False): "subject and object wrong", (False, True): "subject wrong", (True, False): "object wrong"}.get((so(b), oo(b)), "right words, not word for word")
err = collections.defaultdict(collections.Counter); EX = collections.defaultdict(list)
for r in ROWS:
    key = key_of(r)
    L_ = as_dicts(OUT[r["n"]]); ex = {(nm(x["subject"]), nm(x["verb"]), nm(x["object"])) for x in L_}
    for k in key:
        if (nm(k[0]), nm(k[1]), nm(P._no_note(k[2]))) in ex:
            err[group(r)]["exact"] += 1
        else:
            c = classify(k, L_); err[group(r)][c] += 1; EX[c].append((r["n"], " | ".join(map(str, k[:3]))))
display(pd.DataFrame(err).T.fillna(0).astype(int))
for c, xs in EX.items():
    print(f"\n{c} (first 5):")
    for n, k in xs[:5]:
        print(f"   {n:14s} key: {k[:110]}")
""")

md(r"""
### Each rule switched off, one at a time

A rule earns its place when switching it off loses key lines. The discourse rules (step 4) are listed first.
""")

code(r"""
def totals(out):
    t = collections.Counter()
    for r in ROWS:
        key = key_of(r)
        if not key:
            continue
        g = "held-out" if r["set"] == "heldout" else ("simple tests" if r["set"] == "test" else "sample")
        f_, e_ = marks(key, as_dicts(out[r["n"]]))
        t[g, "found"] += sum(f_); t[g, "exact"] += sum(e_); t[g, "key"] += len(key)
    return t
base = totals(OUT)
DISCOURSE_RULES = ["discourse_subject", "demonstrative", "relpron", "said_object", "frame_context"]
UNIT_RULES = [k for k in E.OPT if k not in DISCOURSE_RULES + ["units_only"] + list(E.SENTENCE_TREE_RULES)]
abl = []
for rule in DISCOURSE_RULES + UNIT_RULES:
    s = totals({r["n"]: run(r, TREES[r["n"]], {rule: False}) for r in ROWS})
    abl.append({"rule switched off": rule, "step": "4 (discourse)" if rule in DISCOURSE_RULES else "3 (unit tree)",
                **{f"{g} {m}": s[g, m] - base[g, m] for g in ("sample", "held-out", "simple tests") for m in ("found", "exact")}})
DA = pd.DataFrame(abl)
print("change in key lines when the rule is off (negative = the rule helps):")
display(DA)
off = {r["n"]: run(r, TREES[r["n"]], {k: False for k in DISCOURSE_RULES}) for r in ROWS}
s = totals(off)
print("all of step 4 off (units read alone, nothing connected):",
      {g: f"found {s[g, 'found'] - base[g, 'found']:+d}, exact {s[g, 'exact'] - base[g, 'exact']:+d}" for g in ("sample", "held-out", "simple tests")})
""")

md(r"""
### Units parsed on their own vs cut from the sentence's tree

Once `run_edu.sh` has parsed every unit on its own, this compares the lines from those trees with the lines from the stand-in (the sentence's tree cut to the unit).
""")

code(r"""
if not REPARSED:
    print("skipped: units have not been parsed on their own yet (run scripts/v6/run_edu.sh on the Mac)")
else:
    CUT = {r["n"]: run(r, [[t for t, _ in ps] for ps in E.unit_trees(r, edus_of(r))]) for r in ROWS}
    display(pd.concat([score_table(OUT, "units parsed on their own"), score_table(CUT, "stand-in: cut from the sentence")]).sort_values(["set", "design"]))
    diff = [n for n in OUT if [(l["subject"], l["verb"], l["object"]) for l in OUT[n]["lines"]] != [(l["subject"], l["verb"], l["object"]) for l in CUT[n]["lines"]]]
    print(f"sentences whose lines differ: {len(diff)} of {len(OUT)}")
    for n in diff[:8]:
        print(f"\n{n}: {BY_N[n]['text'][:110]}\n   parsed alone: {[(l['subject'], l['verb'], l['object']) for l in OUT[n]['lines']]}\n   cut:          {[(l['subject'], l['verb'], l['object']) for l in CUT[n]['lines']]}")
""")

md(r"""
### To check by hand

Fifteen debate sentences drawn at random (seed 20261026), saved as `outputs/edu/hand_check.csv` with empty "Right?" and "What it should be" columns.
""")

code(r"""
rnd = random.Random(20261026)
pool = [n for n in OUT if BY_N[n]["set"] in ("sample", "heldout")]
pick = sorted(rnd.sample(pool, 15), key=pool.index)
hc = []
for n in pick:
    x = OUT[n]
    for l in x["lines"]:
        hc.append({"ID": n, "Unit": l["unit"], "Unit text": x["units"][l["unit"]]["text"], "Subject": l["subject"], "Verb": l["verb"], "Object": l["object"],
                   "Where the subject came from": l.get("subject_from") or "its own unit", "Right?": "", "What it should be": ""})
    for c in x["connections"]:
        hc.append({"ID": n, "Unit": c["from"] + " to " + c["to"], "Unit text": "", "Subject": "", "Verb": c["relation"], "Object": "",
                   "Where the subject came from": "discourse parse", "Right?": "", "What it should be": ""})
pd.DataFrame(hc).to_csv(OUTDIR / "hand_check.csv", index=False)
print(f"saved {OUTDIR / 'hand_check.csv'} ({len(hc)} rows from {len(pick)} sentences)")
display(pd.DataFrame(hc).head(20))
""")

md(r"""
## Summary
""")

code(r"""
st = collections.Counter(s for _, s in RESULTS)
print(f"checks and rule tests: {st['PASS']} pass, {st['FAIL']} fail")
for name, s in RESULTS:
    if s != "PASS":
        print("   FAIL:", name)
print("trees:", "parsed now" if LIVE else ("units parsed on their own (saved)" if REPARSED else "STAND-INS cut from the sentence's tree; run run_edu.sh on the Mac for the real per-unit parses"))
print(DS[["set", "found %", "exact %", "exact 95% interval"]].to_string(index=False))
""")


class _Shown:
    def __init__(self):
        self.items = []


SHOWN = _Shown()


def _fake_ipython():
    """Stands in for IPython.display when the notebook is run here, and stores what each cell displays."""
    mod = types.ModuleType("IPython.display")

    class SVG:
        def __init__(self, data): self.data = data
    class HTML:
        def __init__(self, data): self.data = data

    def display(*objs):
        for o in objs:
            if isinstance(o, SVG):
                SHOWN.items.append({"image/svg+xml": o.data, "text/plain": "<SVG>"})
            elif isinstance(o, HTML):
                SHOWN.items.append({"text/html": o.data, "text/plain": "<HTML>"})
            elif hasattr(o, "_repr_html_"):
                SHOWN.items.append({"text/html": o._repr_html_(), "text/plain": o.to_string() if hasattr(o, "to_string") else str(o)})
            else:
                print(o)
    mod.display, mod.SVG, mod.HTML = display, SVG, HTML
    pkg = types.ModuleType("IPython"); pkg.display = mod; pkg.get_ipython = lambda: None; pkg.version_info = (8, 30)
    sys.modules["IPython"] = pkg; sys.modules["IPython.display"] = mod


def build(path, outputs=None):
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                                           "language_info": {"name": "python"}}, "cells": []}
    k = 0
    for i, (kind, src) in enumerate(CELLS):
        lines = [l + "\n" for l in src.split("\n")]; lines[-1] = lines[-1].rstrip("\n")
        if kind == "markdown":
            nb["cells"].append({"cell_type": "markdown", "id": f"c{i}", "metadata": {}, "source": lines})
        else:
            k += 1
            nb["cells"].append({"cell_type": "code", "id": f"c{i}", "metadata": {}, "execution_count": k if outputs else None,
                                "outputs": (outputs or {}).get(i, []), "source": lines})
    json.dump(nb, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


class _Tee(io.StringIO):
    """Collects printed text and displayed objects in the order they appear."""
    def __init__(self):
        super().__init__(); self.parts = []
    def write(self, s):
        if self.parts and self.parts[-1][0] == "text":
            self.parts[-1][1].append(s)
        else:
            self.parts.append(("text", [s]))
        return len(s)


def run():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.show = lambda *a, **k: None
    _fake_ipython()
    ns = {"__name__": "__main__"}
    outs = {}
    for i, (kind, src) in enumerate(CELLS):
        if kind != "code":
            continue
        tee = _Tee(); cell_out = []
        orig = SHOWN.items
        class Rec(list):
            def append(self, x):
                tee.parts.append(("data", x))
        SHOWN.items = Rec()
        try:
            with contextlib.redirect_stdout(tee):
                exec(compile(src, f"<cell {i}>", "exec"), ns)
        except Exception:                               # noqa: BLE001
            tee.write(traceback.format_exc())
            print(f"cell {i} FAILED:\n{traceback.format_exc()}", file=sys.stderr)
        SHOWN.items = orig
        for kind_, val in tee.parts:
            if kind_ == "text":
                text = "".join(val)
                if text.strip():
                    cell_out.append({"output_type": "stream", "name": "stdout", "text": [l + "\n" for l in text.rstrip("\n").split("\n")]})
            else:
                data = {k: (v if k != "text/plain" else [v]) for k, v in val.items()}
                cell_out.append({"output_type": "display_data", "metadata": {}, "data": data})
        for num in plt.get_fignums():
            b = io.BytesIO(); plt.figure(num).savefig(b, format="png", dpi=100, bbox_inches="tight")
            cell_out.append({"output_type": "display_data", "metadata": {}, "data": {"image/png": base64.b64encode(b.getvalue()).decode(), "text/plain": ["<Figure>"]}})
        plt.close("all")
        outs[i] = cell_out
        print(f"cell {i} done", file=sys.stderr)
    return outs


if __name__ == "__main__":
    out = sys.argv[1]
    outs = run() if "--run" in sys.argv else None
    build(out, outs)
    print("wrote", out)
    if outs:
        last = outs[max(outs)]
        print("".join("".join(o.get("text", [])) for o in last if o.get("output_type") == "stream"))
        failed = [i for i, o in outs.items() if any("Traceback (most recent call last)" in "".join(x.get("text", [])) for x in o)]
        if failed:
            print("cells that stopped with an error:", failed)
