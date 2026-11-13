#!/usr/bin/env python3
"""
test_v17.py   (reads only; a minute)

Before the full run: the 1,380 sentences Claude worked the rules out on are parsed again here with spaCy and run
through the patched extractor. Every claim (subject, verb, verb_lemma, object, hedged, negated) must be exactly what
Claude got from the same rules on the parses you sent. If even one differs, the run stops (the parses or the code are
not what Claude tested) and the differences are in outputs/audit/v17_gate.txt.
Run from the project folder:  python3 scripts/step1_debate_text/test_v17.py <expected_claims.json>
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
spec = importlib.util.spec_from_file_location("x17", str(ROOT / "scripts" / "step1_debate_text" / "extract_predications_v3.py"))
X = importlib.util.module_from_spec(spec)
spec.loader.exec_module(X)
import spacy  # noqa: E402

E = json.load(open(sys.argv[1], encoding="utf-8"))
F = ("subject", "verb", "verb_lemma", "object", "hedged", "negated")
out, bad, n_claims = [], 0, 0
for lang in ("en", "fr"):
    rows = [r for r in E["sentences"] if r["lang"] == lang]
    nlp = spacy.load(X.MODELS[lang], disable=["ner"])
    for r, doc in zip(rows, nlp.pipe((r["text"] for r in rows), batch_size=128)):
        p = None
        for sent in doc.sents:
            p = X.extract(sent, lang)
            if p:
                break
        got = {k: p[k] for k in F} if p else None
        n_claims += got is not None
        if got != r["expected"]:
            bad += 1
            out.append(f"{r['sentence_id']}\n  expected: {r['expected']}\n  got:      {got}\n  {r['text'][:200]}\n")
Path("outputs/audit").mkdir(parents=True, exist_ok=True)
Path("outputs/audit/v17_gate.txt").write_text(f"spaCy {spacy.__version__} (Claude tested with {E['spacy']})\n"
                                              f"{len(E['sentences'])} sentences, {bad} differ\n\n" + "\n".join(out),
                                              encoding="utf-8")
print(f"   {len(E['sentences'])} sentences parsed again; {n_claims} claims; {bad} differ from what Claude tested")
if bad:
    print("   the patched extractor does not give what Claude tested; the full run is NOT started.")
    sys.exit(2)
print("   PASS: every claim is exactly what Claude tested")
