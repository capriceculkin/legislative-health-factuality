"""edu_walk_baseline.py EDU_DBPEDIA.json SENSE_CHECK.csv OUT.json [--concepts-dir scripts/step2_parsers] [--pairs 1000]

Is a short walk between a claim's two concepts evidence for the claim? For every claim whose two ends have a concept
judged the right sense (lenient: either reading says right), the walk score of the real pair is set beside the walk
score of shuffled pairs: a subject concept from one claim with an object concept from another (seed 20261102). If the
real pairs score no higher than the shuffled ones, the walk alone says little about the claim. Same graph and path score
as edu_dbpedia.py (concepts_v3.Paths). Needs no tunnel."""
import argparse, csv, json, os, random, statistics, sys
ap = argparse.ArgumentParser()
ap.add_argument("edu"); ap.add_argument("senses"); ap.add_argument("out")
ap.add_argument("--concepts-dir", default="scripts/step2_parsers"); ap.add_argument("--pairs", type=int, default=1000)
A = ap.parse_args()
sys.path.insert(0, os.path.abspath(A.concepts_dir))
import concepts_v3 as C  # noqa: E402
SX = {(x["word"], x["page"]): x for x in csv.DictReader(open(A.senses, encoding="utf-8"))}
ok = lambda k: (k["surface"], k["page"]) in SX and "right" in (SX[(k["surface"], k["page"])]["reading_A"], SX[(k["surface"], k["page"])]["reading_B"])
d = json.load(open(A.edu, encoding="utf-8"))
f, names, props, indptr, indices, code, _ = C.load_graph()
idx = {nm: i for i, nm in enumerate(names)}
indptr, indices, code, _r = C.factual_only(indptr, indices, code, props)
P = C.Paths(names, indptr, indices, code, props)
real = []
for r in d["rows"]:
    for c in r["claims"]:
        s = [k["page"] for k in c["subject"]["concepts"] if k["in_graph"] and ok(k)][:4]
        o = [k["page"] for k in c["object"]["concepts"] if k["in_graph"] and ok(k)][:4]
        if s and o:
            real.append({"n": r["n"], "claim": f"{c['subject']['phrase']} | {c['verb']} | {c['object']['phrase']}", "s": s, "o": o})


from scipy.sparse.csgraph import dijkstra  # noqa: E402
import numpy as np  # noqa: E402
objs = sorted({z for x in real for z in x["o"]})
oi = np.array([idx[z] for z in objs])
DIST = {}
for a in sorted({a for x in real for a in x["s"]}):          # one shortest-path run per subject page, kept only for the object pages
    d = dijkstra(P.G, directed=True, indices=idx[a])
    DIST[a] = dict(zip(objs, d[oi]))


def tau(a, z):
    if a == z:
        return None
    d = DIST[a][z]
    if not np.isfinite(d) or d >= 1e14:
        return 0.0
    return round(1 / (1 + max(0.0, float(d - P.logk[idx[z]]))), 4)


def best(ss, oo):
    vals = [t for a in ss for z in oo for t in [tau(a, z)] if t is not None]
    return max(vals) if vals else 0.0


for x in real:
    x["tau"] = best(x["s"], x["o"])
rnd = random.Random(20261102)
shuf = []
for _ in range(A.pairs):
    a, b = rnd.sample(real, 2)
    if set(a["s"]) & set(b["o"]):
        continue
    shuf.append(best(a["s"], b["o"]))
rt = [x["tau"] for x in real]
higher = sum(1 for t in rt for u in shuf if t > u) + 0.5 * sum(1 for t in rt for u in shuf if t == u)
auc = higher / (len(rt) * len(shuf)) if rt and shuf else None
res = {"real_pairs": len(rt), "shuffled_pairs": len(shuf), "real_median_tau": statistics.median(rt) if rt else None,
       "shuffled_median_tau": statistics.median(shuf) if shuf else None,
       "real_share_with_walk": sum(1 for t in rt if t > 0) / len(rt) if rt else None,
       "shuffled_share_with_walk": sum(1 for t in shuf if t > 0) / len(shuf) if shuf else None,
       "auc_real_over_shuffled": auc, "real": real}
json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
print(f"claims with both ends the right sense: {len(rt)}; shuffled pairs: {len(shuf)}")
print(f"a walk exists: real {100 * res['real_share_with_walk']:.0f}%, shuffled {100 * res['shuffled_share_with_walk']:.0f}%")
print(f"median walk score: real {res['real_median_tau']:.3f}, shuffled {res['shuffled_median_tau']:.3f}")
print(f"chance a real pair scores above a shuffled one (0.5 = no difference): {auc:.2f}")
