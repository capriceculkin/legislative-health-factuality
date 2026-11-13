#!/usr/bin/env python3
"""rel_linker.py   The relational knowledge linker (KL-REL, Shiralkar, Tyagi, Flammini, Menczer and Ciampaglia 2017) on the
full 2022 DBpedia graph, next to the plain knowledge linker (KL, Ciampaglia et al. 2015) we have used so far.

KL treats every link the same: a path through someone's birthplace counts as much as a path through a court ruling.
KL-REL divides each step's cost by how similar that link's relation is to the relation the claim is about:
    score = 1 / [ sum over inner pages v_i of log k(v_i) / u(r_(i-1), p)  +  1 / u(r_(n-1), p) ]
where k is a page's number of links, r the relation of each link, p the claim's relation and u the relation similarity
(cosine of TF-IDF rows of the relation co-occurrence matrix: two relations co-occur when their links share a page).
A direct link with the claim's own relation scores 1.

Tested first on the 300 judged facts, where the relation is known (place of birth -> birthPlace; institution ->
almaMater or education). For the debate statements the relation is picked from the verb, by word-vector similarity
between the verb and the relation names (spaCy's large English model); that choice is shown on every row.
Writes ~/Desktop/next_steps/oct16/rel_linker.json."""
import json, os, re, sys, time
import numpy as np
from scipy.sparse import csr_matrix, coo_matrix
from scipy.sparse.csgraph import dijkstra
import ev_common as E

FLOOR = 1e-3          # a relation with no similarity at all still lets a path through, at a very high cost
CUT = 1e15
FR_VERBS = {  # French verbs in the stated predications -> English, so the English word vectors can match a relation
    "adopter": "adopt", "connaître": "know", "laisser": "let", "encourager": "encourage", "viser": "aim", "permettre": "allow",
    "resserrer": "tighten", "prendre": "take", "préciser": "specify", "apporter": "bring", "interdire": "ban", "prévoir": "provide",
    "créer": "create", "modifier": "amend", "financer": "fund", "payer": "pay", "soigner": "treat", "fermer": "close", "ouvrir": "open",
    "augmenter": "increase", "réduire": "reduce", "couper": "cut", "protéger": "protect", "exiger": "require", "obliger": "require",
    "donner": "give", "recevoir": "receive", "travailler": "work", "vivre": "live", "mourir": "die", "naître": "born", "étudier": "study",
}


def relation_similarity(indptr, code, R):
    """u(r_i, r_j): cosine similarity of TF-IDF rows of the contracted line graph's adjacency (relation co-occurrence)."""
    N = len(indptr) - 1
    rows = np.repeat(np.arange(N, dtype=np.int32), np.diff(indptr))
    rel = (code // 2).astype(np.int32)
    A = coo_matrix((np.ones(len(rel), dtype=np.float64), (rows, rel)), shape=(N, R)).tocsr()   # A[v, r]: links of relation r at page v
    del rows
    C = (A.T @ A).toarray()                                       # pairs of links that share a page
    C[np.diag_indices(R)] -= np.asarray(A.sum(axis=0)).ravel()    # a link does not pair with itself
    C = np.maximum(C, 0)
    tf = np.log1p(C)
    df = (C > 0).sum(axis=0)
    idf = np.where(df > 0, np.log(R / np.maximum(df, 1)), 0.0)
    W = tf * idf[None, :]
    nrm = np.linalg.norm(W, axis=1)
    nrm[nrm == 0] = 1.0
    Wn = W / nrm[:, None]
    U = Wn @ Wn.T
    np.fill_diagonal(U, 1.0)
    return np.clip(U, 0.0, 1.0)


class Linker:
    def __init__(self, names, props, indptr, indices, code):
        self.names, self.props, self.indptr, self.indices, self.code = names, props, indptr, indices, code
        self.N, self.R = len(names), len(props)
        self.deg = np.diff(indptr).astype(np.int64)
        self.logk = np.log(np.maximum(self.deg, 1)).astype(np.float64) + 1e-9
        self.rel = (code // 2).astype(np.int32)
        self.idx = {n: i for i, n in enumerate(names)}
        self.G_kl = csr_matrix((self.logk[indices], indices, indptr), shape=(self.N, self.N))
        self._G = {}
        self._d = {}

    def edge(self, x, y):
        lo, hi = self.indptr[x], self.indptr[x + 1]
        j = lo + np.searchsorted(self.indices[lo:hi], y)
        return j if j < hi and self.indices[j] == y else None

    def graph_for(self, key, up):
        if key not in self._G:
            self._G.clear()                                  # one relation-weighted graph in memory at a time
            u = np.maximum(up[self.rel], FLOOR)
            self._G[key] = (csr_matrix((self.logk[self.indices] / u, self.indices, self.indptr), shape=(self.N, self.N)), u)
        return self._G[key]

    def _dij(self, G, key, s, cut_t=None):
        ck = (key, s, cut_t)
        if ck in self._d:
            return self._d[ck]
        saved = []
        if cut_t is not None:
            for x, y in ((s, cut_t), (cut_t, s)):
                j = self.edge(x, y)
                if j is not None:
                    saved.append((j, G.data[j])); G.data[j] = CUT
        d, pred = dijkstra(G, directed=True, indices=s, return_predecessors=True)
        for j, v in saved:
            G.data[j] = v
        if len(self._d) > 3:
            self._d.clear()
        self._d[ck] = (d, pred)
        return d, pred

    def describe(self, nodes):
        parts = [self.names[nodes[0]]]
        for a, b in zip(nodes, nodes[1:]):
            c = int(self.code[self.edge(a, b)])
            rel = E.prop_name(self.props[c // 2])
            parts.append(f"-[{rel}]->" if c % 2 == 0 else f"<-[{rel}]-")
            parts.append(self.names[b] if b == nodes[-1] else f"{self.names[b]} (links {self.deg[b]})")
        return " ".join(parts)

    def walk(self, pred, s, x):
        nodes = [x]
        while nodes[-1] != s:
            nodes.append(int(pred[nodes[-1]]))
        return nodes[::-1]

    def kl(self, s, t, cut=False):
        """The plain knowledge linker, as in the earlier runs, on the same factual graph."""
        if s == t:
            return None
        d, pred = self._dij(self.G_kl, "kl", s, t if cut else None)
        if not np.isfinite(d[t]) or d[t] >= CUT / 10:
            return {"tau": 0.0, "links": None, "path": ""}
        nodes = self.walk(pred, s, t)
        return {"tau": round(1 / (1 + max(0.0, float(d[t] - self.logk[t]))), 4), "links": len(nodes) - 1, "path": self.describe(nodes)}

    def klrel(self, s, t, key, up, cut=False):
        """KL-REL: the best path's score, with the last step costing 1/u (the object's own link count is not counted)."""
        if s == t:
            return None
        G, u = self.graph_for(key, up)
        d, pred = self._dij(G, key, s, t if cut else None)
        lo, hi = self.indptr[t], self.indptr[t + 1]
        nb = self.indices[lo:hi]
        # the link from neighbour x into t: its relation is the same entry seen from t's side
        last = 1.0 / np.maximum(up[self.rel[lo:hi]], FLOOR)
        tot = d[nb] + last
        if cut:
            tot = np.where(nb == s, np.inf, tot)
        if not len(tot) or not np.isfinite(tot.min()) or tot.min() >= CUT / 10:
            return {"tau": 0.0, "links": None, "path": ""}
        k = int(np.argmin(tot)); x = int(nb[k])
        nodes = self.walk(pred, s, x) + [t] if x != s else [s, t]
        return {"tau": round(float(1.0 / tot[k]), 4), "links": len(nodes) - 1, "path": self.describe(nodes)}


def relation_index(props):
    out = {}
    for i, p in enumerate(props):
        out.setdefault(E.prop_name(p), i)
    return out


def words_of_relation(name):
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", name)]


def verb_lemma(nlp, verb, lang):
    v = verb.replace("(apposition)", "").strip()
    if lang == "fr":
        try:
            import spacy
            if not hasattr(verb_lemma, "fr"):
                verb_lemma.fr = spacy.load("fr_core_news_lg")
            toks = [t for t in verb_lemma.fr(v) if t.pos_ in ("VERB", "AUX")]
            lem = (toks[-1].lemma_ if toks else v.split()[-1]).lower()
        except Exception:
            lem = v.split()[-1].lower()
        return FR_VERBS.get(lem), lem
    toks = [t for t in nlp(v) if t.pos_ in ("VERB", "AUX")]
    main = [t for t in toks if t.pos_ == "VERB"] or toks
    lem = (main[-1].lemma_ if main else v.split()[-1]).lower()
    return lem, lem


def main():
    t0 = time.time()
    E.say("== 1. the full graph, factual links only")
    names, props, indptr, indices, code = E.load_graph()
    indptr, indices, code, removed = E.factual_only(indptr, indices, code, props)
    E.say(f"   {len(names):,} pages, {len(indices) // 2:,} factual links ({removed // 2:,} 'see also' links left out)")
    R = len(props)
    E.say(f"== 2. how similar each pair of the {R} relations is (shared pages, TF-IDF, cosine)")
    U = relation_similarity(indptr, code, R)
    L = Linker(names, props, indptr, indices, code)
    ri = relation_index(props)
    counts = np.bincount(L.rel, minlength=R)

    def up_for(rel_names):
        ids = [ri[r] for r in rel_names if r in ri]
        return (U[:, ids].max(axis=1) if ids else np.zeros(R)), ids

    show = {}
    for p in ("birthPlace", "almaMater", "education"):
        if p in ri:
            row = U[ri[p]]
            top = [E.prop_name(props[j]) for j in np.argsort(-row)[:8] if j != ri[p]]
            show[p] = top[:6]
            E.say(f"   relations closest to {p}: " + ", ".join(top[:6]))

    E.say("== 3. the 300 judged facts: KL (as before) and KL-REL (relation-aware), same graph")
    facts, ren = E.judged_facts()
    target = {"place_of_birth": ["birthPlace"], "institution": ["almaMater", "education"]}
    node = lambda nm: L.idx.get(nm) if nm in L.idx else L.idx.get(ren.get(nm, ""))
    order = sorted(range(len(facts)), key=lambda i: (facts[i]["rel"], facts[i]["s"] or ""))
    res = [None] * len(facts)
    done = 0
    for i in order:
        f = facts[i]
        si, ti = (node(f["s"]) if f["s"] else None), (node(f["o"]) if f["o"] else None)
        row = {"rel": f["rel"], "group": f["group"], "s": f["s"], "o": f["o"], "in_graph": si is not None and ti is not None}
        if row["in_graph"] and si != ti:
            up, _ = up_for(target[f["rel"]])
            a = L.kl(si, ti); b = L.klrel(si, ti, f["rel"], up)
            row.update(kl=a["tau"], kl_path=a["path"], klrel=b["tau"], klrel_path=b["path"], direct=a["links"] == 1)
            if a["links"] == 1:
                a2 = L.kl(si, ti, cut=True); b2 = L.klrel(si, ti, f["rel"], up, cut=True)
                row.update(kl_no_direct=a2["tau"], klrel_no_direct=b2["tau"], klrel_path_no_direct=b2["path"])
            else:
                row.update(kl_no_direct=a["tau"], klrel_no_direct=b["tau"], klrel_path_no_direct=b["path"])
        res[i] = row
        done += 1
        if done % 25 == 0:
            el = time.time() - t0
            E.say(f"   {done} of {len(facts)} done")
    summary = []
    for rel in ("place_of_birth", "institution", "all"):
        rows = [r for r in res if r["in_graph"] and "kl" in r and (rel == "all" or r["rel"] == rel)]
        for key in ("kl", "klrel", "kl_no_direct", "klrel_no_direct"):
            t = [r[key] for r in rows if r["group"] == "judged true"]
            for grp, lab in (("swapped (made up)", "true vs made up"), ("judged false", "true vs judged false")):
                n = [r[key] for r in rows if r["group"] == grp]
                summary.append({"relation": rel, "score": key, "comparison": lab, "true": len(t), "other": len(n),
                                "auc": E.auc_ranksum(t, n), "auc_pairs": E.auc_pairs(t, n)})
    for s in summary:
        if s["relation"] == "all":
            E.say(f"   {s['score']:16s} {s['comparison']:22s} AUC {s['auc']} (pair count {s['auc_pairs']}; {s['true']} true, {s['other']} other)")

    E.say("== 4. debate statements with a page at both ends (concepts from the Oct 15e run)")
    st, src, ver = E.debate_statements()
    import spacy
    nlp = spacy.load("en_core_web_lg")
    rel_ok = [j for j in range(R) if counts[j] >= 500 and E.prop_name(props[j]) not in E.NONFACT]
    rel_vec = {}
    for j in rel_ok:
        ws = [w for w in words_of_relation(E.prop_name(props[j])) if nlp.vocab.has_vector(w)]
        if ws:
            v = np.mean([nlp.vocab.get_vector(w) for w in ws], axis=0)
            if np.linalg.norm(v) > 0:
                rel_vec[j] = v / np.linalg.norm(v)
    deb = []
    for s in st:
        subj = [c[1] for c in s["v1_subject"] if c[1] in L.idx][:4]
        obj = [c[1] for c in s["v1_object"] if c[1] in L.idx][:4]
        subj_s, verb, obj_s = [x.strip() for x in s["statement"].split("|")][:3]
        row = {"n": s["n"], "lang": s["lang"], "statement": s["statement"], "negated": s["negated"], "subject_pages": subj,
               "object_pages": obj}
        if not subj or not obj:
            row["status"] = "no page at both ends"; deb.append(row); continue
        en_verb, lem = verb_lemma(nlp, verb, s["lang"])
        row["verb"] = lem
        if not en_verb or not nlp.vocab.has_vector(en_verb):
            row["status"] = f"verb '{lem}' could not be matched to a relation"; deb.append(row); continue
        vv = nlp.vocab.get_vector(en_verb); vv = vv / np.linalg.norm(vv)
        sims = sorted(((float(rel_vec[j] @ vv), j) for j in rel_vec), reverse=True)[:3]
        row["relations_for_verb"] = [(E.prop_name(props[j]), round(x, 3)) for x, j in sims]
        up = U[:, [j for _, j in sims]].max(axis=1)
        best = None
        for a in subj:
            for b in obj:
                if a == b:
                    continue
                r1 = L.klrel(L.idx[a], L.idx[b], "verb:" + en_verb, up)
                r0 = L.kl(L.idx[a], L.idx[b])
                if r1 and (best is None or r1["tau"] > best["klrel"]):
                    best = {"subject_page": a, "object_page": b, "klrel": r1["tau"], "klrel_path": r1["path"],
                            "kl": r0["tau"], "kl_path": r0["path"]}
        row.update(best or {}); row["status"] = "scored" if best else "same page at both ends"
        deb.append(row)
    out = {"version": "rel_linker (Oct 16a)", "graph_links_left_out": removed // 2, "closest_relations": show,
           "statements_from": src, "statements_version": ver, "summary": summary, "judged_facts": res, "debate": deb,
           "minutes": round((time.time() - t0) / 60, 1)}
    (E.OUT / "rel_linker.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    sc = [d for d in deb if d.get("status") == "scored"]
    E.say(f"   {len(sc)} debate statements scored; the relation picked for each verb is in the file")
    E.say("== wrote " + str(E.OUT / "rel_linker.json"))


if __name__ == "__main__":
    main()
