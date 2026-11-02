"""edu_dbpedia_senses.py EDU_DBPEDIA.json SENSE_CHECK.csv OUT.json [--concepts-dir scripts/v4]

The share of claims with both ends in DBpedia again, counting only concepts whose page was judged the right sense in
SENSE_CHECK.csv (columns word, page, reading_A, reading_B). Strict: both readings say right. Lenient: either one does.
The walk is recomputed between judged-right pages only, with the same path score as edu_dbpedia.py (concepts_v3.Paths
on the 2022 graph in ~/.kg_dump). Prints the counts and writes them to OUT.json. Needs no tunnel."""
import argparse, collections, csv, json, os, sys
ap = argparse.ArgumentParser()
ap.add_argument("edu"); ap.add_argument("senses"); ap.add_argument("out")
ap.add_argument("--concepts-dir", default="scripts/v4")
A = ap.parse_args()
sys.path.insert(0, os.path.abspath(A.concepts_dir))
import concepts_v3 as C  # noqa: E402
d = json.load(open(A.edu, encoding="utf-8"))
SX = {(x["word"], x["page"]): x for x in csv.DictReader(open(A.senses, encoding="utf-8"))}
f, names, props, indptr, indices, code, _ = C.load_graph()
idx = {nm: i for i, nm in enumerate(names)}
indptr, indices, code, _r = C.factual_only(indptr, indices, code, props)
P = C.Paths(names, indptr, indices, code, props)
out = {"note": f"from {os.path.basename(A.edu)} and {os.path.basename(A.senses)}; a rerun of edu_dbpedia.py needs this rerun too"}
unjudged = set()
for mode in ("strict", "lenient"):
    def ok(k):
        x = SX.get((k["surface"], k["page"]))
        if x is None:
            unjudged.add((k["surface"], k["page"])); return False
        v = (x["reading_A"], x["reading_B"])
        return v == ("right", "right") if mode == "strict" else "right" in v
    cnt = collections.Counter()
    for r in d["rows"]:
        for c in r["claims"]:
            ends = [[k["page"] for k in c[s]["concepts"] if k["in_graph"] and ok(k)][:4] for s in ("subject", "object")]
            both = bool(ends[0] and ends[1])
            walk = both and max((P.score(idx[a], idx[b]) or {"tau": 0})["tau"] for a in ends[0] for b in ends[1] if a != b) > 0 \
                if both and any(a != b for a in ends[0] for b in ends[1]) else False
            for g in (r["legislature"], "all", "asserted" if c["kind"] == "asserted" else None, "English" if r["lang"] == "en" else "French"):
                if g:
                    cnt[(g, "claims")] += 1; cnt[(g, "both")] += both; cnt[(g, "walk")] += bool(walk)
    out[mode] = {f"{g}|{m}": v for (g, m), v in cnt.items()}
out["concepts_not_judged"] = len(unjudged)
json.dump(out, open(A.out, "w"), indent=1)
for mode in ("strict", "lenient"):
    print(mode)
    for g in ("all", "asserted", "US House", "Ontario", "Quebec", "English", "French"):
        n = out[mode][f"{g}|claims"]
        print(f"   {g:<10} both ends right {out[mode][f'{g}|both']}/{n} ({100 * out[mode][f'{g}|both'] / n:.0f}%); a walk {out[mode][f'{g}|walk']}/{n}")
print(f"concepts with no reading in {os.path.basename(A.senses)}: {len(unjudged)}")
