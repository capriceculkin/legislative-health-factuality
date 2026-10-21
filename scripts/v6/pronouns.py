"""pronouns.py RULES PARSES   How often a claim's subject or object is a pronoun or a stand-in instead of a name, so the
size of the entity problem raised in review (names hidden behind pronouns and replacements) is measured before any
coreference step is chosen. Counts the vote's full predications on the 130 answer-key sentences, by language."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import full as F
S, P, C = F.S, F.P, F.C
X = P.X
PRON = {w for w in X.both(X.PRONOUNS)} | {"i", "we", "you", "they", "he", "she", "it", "this", "that", "these", "those", "who", "which",
        "je", "nous", "vous", "on", "ils", "elles", "il", "elle", "ce", "c'", "cela", "ça", "ceci", "celui", "celle", "ceux", "qui", "que", "l'", "le", "la", "les", "lui", "leur", "y", "en", "me", "te", "se"}
STAND_IN_HEAD = {"government", "minister", "member", "bill", "committee", "house", "senate", "department", "agency", "party", "administration", "speaker",
                 "gouvernement", "ministre", "député", "projet", "commission", "chambre", "sénat", "ministère", "agence", "parti", "président", "opposition"}
rows = json.load(open(sys.argv[2], encoding="utf-8"))["rows"]
c = collections.defaultdict(collections.Counter)
ex = collections.defaultdict(list)
for r in rows:
    if r["set"] not in ("sample", "heldout"):
        continue
    for q in F.full_row(r)["lines"]:
        if q["source"] == "apposition":
            continue
        L = r["lang"]
        for slot in ("subject", "object"):
            v = (q[slot] or "").replace(" (inh)", "").strip()
            if not v or v.startswith("["):
                continue
            w = P.fold(v)
            if not w:
                continue
            c[L][slot + "s"] += 1
            if len(w) == 1 and w[0] in PRON:
                c[L][slot + "s: pronoun"] += 1; c[L + " which"][w[0]] += 1
                if len(ex[L]) < 8:
                    ex[L].append((r["n"], slot, v, q["verb"]))
            elif w[0] in ("the", "this", "that", "le", "la", "les", "ce", "cette", "l'", "notre", "our", "my", "mon") and any(x in STAND_IN_HEAD for x in w[1:4]):
                c[L][slot + "s: role or institution (the minister, ce gouvernement)"] += 1
for L in ("en", "fr"):
    print(f"== {L}")
    for k in ("subjects", "subjects: pronoun", "subjects: role or institution (the minister, ce gouvernement)", "objects", "objects: pronoun", "objects: role or institution (the minister, ce gouvernement)"):
        base = c[L]["subjects" if k.startswith("subj") else "objects"]
        print(f"   {k:60s} {c[L][k]:4d}" + (f"  ({100*c[L][k]/base:.0f}%)" if ":" in k and base else ""))
    print("   most common pronouns:", c[L + " which"].most_common(8))
    for e in ex[L]:
        print("     e.g.", e)
