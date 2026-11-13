"""parity_score.py   Scores saved parses against an answer key, the way the full run treats a sentence.

    python3 parity_score.py RULES_DIR PARSES.json [--disc native|rstdt] [--const prod|en3] [--rst multi|all] [--json OUT]

RULES_DIR holds preds.py, combine_lib.py, const_fr.py (and lexicon.py for v6). PARSES.json comes from
parity_collect.py: one row per sentence with both dependency parses, the constituency trees, and the discourse
parses. Each row is run exactly as parse_corpus_v5.process_batch runs it: questions and very short sentences skipped,
three parses, the two-of-three vote, the discourse re-read, appositions added. Scored at every stage: each parser
alone, the vote (label from the syntax), and the final line (label after the discourse re-read).

Nothing here loads a parser; it only reads the saved parses, so any rule version can be scored on the same input."""
import argparse, collections, json, os, sys


def load_rules(d):
    sys.path.insert(0, os.path.abspath(d))
    import preds as P            # noqa: E402
    import combine_lib as C      # noqa: E402
    return P, C


def speech_words(P, C):
    return set(P.SPEECH) | set(C.SOURCE_WORDS)


def needs_rst(policy, text, agreed, words):
    if policy == "all":
        return True
    if len(agreed) >= 2:
        return True
    return bool({w.strip(",.;:\"“”«»()").lower() for w in text.split()} & words)


def apply_rst(P, C, agreed, review, r, d):
    so, _ = C.offsets(r["deps_spacy"])
    st = [t for sent in r["deps_stanza"] for t in sent]
    sto, _ = C.offsets(st)
    sat, attributed = C.edu_roles(d) if d else ({}, set())
    for p in agreed + review:
        off = None
        if "spacy" in p["at_by"] and p["at_by"]["spacy"] < len(so):
            off = so[p["at_by"]["spacy"]]
        elif "stanza" in p["at_by"] and p["at_by"]["stanza"] < len(sto):
            off = sto[p["at_by"]["stanza"]]
        first = p["verb"].split(" ")[0] if p["verb"] else ""
        hits = [k for k in range(len(r["text"])) if r["text"].startswith(first, k)] if first else []
        if hits:
            before = [k for k in hits if off is None or k <= off]
            off = max(before) if before else min(hits)
        i = C.edu_of(off, d["edus"]) if (d and off is not None) else None
        p["edu"] = i                      # which discourse unit holds the verb (read by full.py for links)
        p["kind_parser"] = p["kind"]
        p["kind_rst"], p["rst_why"] = C.rst_kind(p, i, d, sat, attributed) if d else (p["kind"], "no discourse parse")


def analyze(P, C, row, disc="native", const="prod", policy="multi"):
    """One saved row -> every stage's lines."""
    text, lang = row["text"], row["lang"]
    trees = row.get("trees_en3") if (const == "en3" and lang == "en" and row.get("trees_en3")) else row.get("trees", [])
    r = {"n": row["n"], "lang": lang, "text": text, "deps_spacy": row["deps_spacy"], "deps_stanza": row["deps_stanza"], "trees": trees}
    res = {"skipped": None, "spacy": [], "stanza": [], "const": [], "vote": [], "final": [], "review": [], "methods": []}
    if text.endswith("?") or len(text.split()) < 3:
        res["skipped"] = "question" if text.endswith("?") else "too short"
        return res
    out = C.run(r, P)
    methods = ["spacy", "stanza"] + (["const"] if trees else [])
    agreed, review = C.vote(out, methods, need=2)
    d = row.get("disc_rstdt") if disc == "rstdt" and row.get("disc_rstdt") else row.get("disc_native")
    if disc.startswith("window") and row.get("disc_window"):
        w = row["disc_window_rstdt"] if (disc == "window_rstdt" and row.get("disc_window_rstdt")) else row["disc_window"]
        st0 = row["window_start"]          # the window's units, moved so offsets count from the start of this sentence
        d = {"edus": [dict(e, start=e["start"] - st0, end=e["end"] - st0) for e in w["edus"]], "relations": w["relations"]}
    if not needs_rst(policy, text, agreed, speech_words(P, C)):
        d = None
    apply_rst(P, C, agreed, review, r, d)
    toks = [P.T(*x) for x in row["deps_spacy"]]
    P.link_kids(toks)
    apps = [dict(a, kind="asserted", kind_parser="asserted", kind_rst="asserted", negated=False, hedged=False, found_by=["spacy"])
            for a in P.appositions(toks)]
    res.update(methods=methods, spacy=out["spacy"], stanza=out["stanza"], const=out["const"], review=review,
               vote=[dict(p, kind=p["kind_parser"]) for p in agreed] + [dict(a, kind="asserted") for a in apps],
               final=[dict(p, kind=p["kind_rst"]) for p in agreed] + [dict(a, kind="asserted") for a in apps])
    return res


def hedged_in(note):
    note = note or ""
    return "hedged" in note and "not hedged" not in note


def score(P, gold, lines, hedge_check=True):
    """found, label right, hedge right, extra lines (output lines matching no key line)."""
    al = P.align(gold, lines) if gold else []
    c = collections.Counter(key=len(gold), produced=len(lines))
    used = {a for a in al if a is not None}
    c["extra"] = len(lines) - len(used)
    for g, a in zip(gold, al):
        if a is None:
            continue
        p = lines[a]
        c["found"] += 1
        c["label"] += p["kind"] == g[3]
        if hedge_check:
            c["hedge_n"] += 1
            c["hedge"] += bool(p.get("hedged")) == hedged_in(g[4] if len(g) > 4 else "")
        c["all_right"] += (p["kind"] == g[3]) and (not hedge_check or bool(p.get("hedged")) == hedged_in(g[4] if len(g) > 4 else ""))
    return c


STAGES = ("spacy", "stanza", "const", "vote", "final")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rules"); ap.add_argument("parses")
    ap.add_argument("--disc", default="native", choices=["native", "rstdt", "window", "window_rstdt"])
    ap.add_argument("--window", help="discourse_window.json from discourse_window.py (needed for --disc window)")
    ap.add_argument("--const", default="prod", choices=["prod", "en3"])
    ap.add_argument("--rst", default="multi", choices=["multi", "all"])
    ap.add_argument("--json")
    a = ap.parse_args()
    P, C = load_rules(a.rules)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import parallel_tests as PT
    import gold_heldout as GHmod
    data = json.load(open(a.parses, encoding="utf-8"))
    rows = {r["n"]: r for r in data["rows"]}
    if a.window:
        for w in json.load(open(a.window, encoding="utf-8"))["rows"]:
            if w["n"] in rows and w.get("disc_window"):
                rows[w["n"]].update(disc_window=w["disc_window"], disc_window_rstdt=w.get("disc_window_rstdt"), window_start=w["start"])
    report = {"settings": vars(a), "tests": [], "heldout": {}, "sample": {}}

    # parallel tests
    for tst in PT.T:
        item = {"id": tst["id"], "group": tst["group"], "construction": tst["construction"]}
        for L in ("en", "fr"):
            row = rows.get(f"test|{tst['id']}|{L}")
            if row is None:
                continue
            res = analyze(P, C, row, a.disc, a.const, a.rst)
            gold = tst[L]["lines"]
            item[L] = {s: dict(score(P, gold, res[s], tst["hedge_check"])) for s in STAGES}
            item[L]["skipped"] = res["skipped"]
            item[L]["final_lines"] = [(p["subject"], p["verb"], p["object"], p["kind"], "negated" if p.get("negated") else "",
                                       "hedged" if p.get("hedged") else "") for p in res["final"]]
            ok = (res["skipped"] == "question") if not gold else (item[L]["final"].get("all_right", 0) == len(gold) and item[L]["final"].get("extra", 0) == 0)
            item[L]["pass"] = bool(ok)
        report["tests"].append(item)

    # held-out key and the 100-sentence sample: totals per language and stage
    for name, keyset in (("heldout", GHmod.GH), ("sample", C.KEY)):
        tot = collections.defaultdict(collections.Counter)
        for n, row in rows.items():
            if row.get("set") != name:
                continue
            gold = keyset.get(row["key_n"])
            if not gold:
                continue
            res = analyze(P, C, row, a.disc, a.const, a.rst)
            for s in STAGES:
                tot[f"{row['lang']}.{s}"].update(score(P, gold, res[s]))
        report[name] = {k: dict(v) for k, v in tot.items()}

    # print
    print(f"== rules {a.rules}   discourse inventory: {a.disc}   English constituency: {a.const}   discourse policy: {a.rst}")
    print("\n-- parallel tests (final output; P = every expected line found with the right label and hedge, and no extra lines)")
    by_group = collections.defaultdict(lambda: collections.Counter())
    for it in report["tests"]:
        e, f = it.get("en", {}), it.get("fr", {})
        print(f"  {it['id']:4s} {it['construction'][:48]:48s} EN {'P' if e.get('pass') else '-'}  FR {'P' if f.get('pass') else '-'}"
              + ("" if e.get("pass") == f.get("pass") else "   <-- the languages differ"))
        by_group[it["group"]]["n"] += 1
        by_group[it["group"]]["en"] += bool(e.get("pass")); by_group[it["group"]]["fr"] += bool(f.get("pass"))
    print("\n  by group:   " + "   ".join(f"{g}: EN {c['en']}/{c['n']} FR {c['fr']}/{c['n']}" for g, c in by_group.items()))
    for name in ("heldout", "sample"):
        if not report[name]:
            continue
        print(f"\n-- {name}: key lines found / produced / right label (of found)")
        for L in ("en", "fr"):
            print("  " + L + "  " + "   ".join(
                f"{s} {report[name].get(L + '.' + s, {}).get('found', 0)}/{report[name].get(L + '.' + s, {}).get('key', 0)}"
                f" p{report[name].get(L + '.' + s, {}).get('produced', 0)} l{report[name].get(L + '.' + s, {}).get('label', 0)}" for s in STAGES))
    if a.json:
        json.dump(report, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
