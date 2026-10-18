#!/usr/bin/env python3
"""statements_v4.py   Predications from all three parses together (David, Oct 8): spaCy dependency, Stanza dependency
and the constituency parse (Stanza for English, the Berkeley parser for French), kept when at least two agree, with the
discourse (RST/SDRT) parse deciding how each is used. Uses the parses saved by the parser comparison, so it needs no
parser itself. Scores everything against the answer key (235 lines) and the held-out key, and writes
~/Desktop/next_steps/oct15/statements_v4.json for the concept step."""
import collections, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import combine_lib as C
import preds as P
import gold_heldout

OUT = Path(os.environ.get("OCT15_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct15"))); OUT.mkdir(parents=True, exist_ok=True)
frt = OUT / "fr_trees.json"
if frt.exists():
    C.FR_CONST = json.loads(frt.read_text(encoding="utf-8"))["trees"]
    print(f"== French constituency trees found for {len(C.FR_CONST)} sentences")
else:
    print("== no French constituency trees (part 1 did not run); French uses the two dependency parses only")

JUR = {"US": "us", "ON": "ontario", "QC": "quebec"}
rows = C.load_rows()
out_rows = []
for r in rows:
    ms, agreed, review = C.combine(r, need=2)
    j, bill = r["sentence_id"].split("|")[:2]
    tk = [P.T(*x) for x in r["deps_spacy"]]; P.link_kids(tk)
    apps = [dict(a, kind="asserted", how="apposition (renames the noun before the comma)", found_by=["spacy"], source="apposition")
            for a in P.appositions(tk)] if hasattr(P, "appositions") else []
    st = [dict(subject=p["subject"], verb=p["verb"], object=p["object"], kind=p["kind_rst"], kind_parser=p["kind_parser"],
               how=p["how"], rst=p["rst_why"], negated=p["negated"], hedged=p["hedged"], found_by=p["found_by"], source="agreed")
          for p in agreed]
    out_rows.append({"n": r["n"], "lang": r["lang"], "jurisdiction": JUR.get(j, j), "bill_key": bill, "sentence_id": r["sentence_id"],
                     "text": r["text"], "methods": ms, "statements": st + apps,
                     "for_review": [dict(subject=p["subject"], verb=p["verb"], object=p["object"], kind=p["kind"],
                                         found_by=p["found_by"]) for p in review]})

# ---- scores against the answer key
lines = []
for need in (2, 1):
    res, _ = C.evaluate(need)
    for L in ("en", "fr"):
        c = res[L]
        lines.append(f"{'2 of 3' if need == 2 else 'any parse'} {L}: key lines found {c['found']}/{c['key']}, lines produced {c['produced']}"
                     f" ({c['produced_in_key']} in the key); stated-or-not right {c['kind_rst_ok']}/{c['kind_pairs']}")
per = collections.defaultdict(lambda: [0, 0])
for r in rows:
    if r["n"] not in C.KEY:
        continue
    rr = dict(r, trees=C.FR_CONST.get(str(r["n"]), [])) if (r["lang"] == "fr" and C.FR_CONST) else r
    out = C.run(rr, P)
    for m in ("spacy", "stanza", "const"):
        if m == "const" and not rr.get("trees"):
            continue
        al = P.align(C.KEY[r["n"]], out[m])
        per[(m, r["lang"])][0] += sum(a is not None for a in al); per[(m, r["lang"])][1] += len(al)
for (m, L), (f, t) in sorted(per.items()):
    lines.append(f"single parse {m} {L}: {f}/{t}")
held_lines = []
if C.FR_CONST:
    GH = gold_heldout.GH
    f = t = 0
    for k, trees in C.FR_CONST.items():
        if not k.startswith("h"):
            continue
        h = int(k[1:])
        if h not in GH:
            continue
        out = [p for tr in trees for p in P.from_constituency(tr, "fr")]
        al = P.align(GH[h], out)
        f += sum(a is not None for a in al); t += len(al)
    held_lines.append(f"held-out French, constituency alone: {f}/{t}")
summary = lines + held_lines
for s in summary:
    print("   " + s)
(OUT / "statements_v4.json").write_text(json.dumps({"version": "v4 (Oct 15)", "summary": summary, "rows": out_rows},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
print("== wrote", OUT / "statements_v4.json")
