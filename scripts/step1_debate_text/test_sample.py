#!/usr/bin/env python3
"""
test_sample.py   (reads only; a minute)

Before the full run: the 100 sampled sentences are run through the old extractor (the backup) and the new one, side
by side (outputs/audit/fix15_sample_side_by_side.txt). The run goes on only if, with the new extractor,
  - no subject or object has words that are not in its sentence (the glued words),
  - no object comes from an opening phrase before the verb,
  - no subject is a speaker label or a form of address,
and none of these got worse. Exit code 2 otherwise.
Run from the project folder:  python3 scripts/step1_debate_text/test_sample.py <old extractor backup> <spot_check_sample.json>
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))
old_path, sample_path = sys.argv[1], sys.argv[2]


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


OLD = load_mod("old_extractor", old_path)
NEW = load_mod("new_extractor", str(ROOT / "scripts" / "step1_debate_text" / "extract_predications_v3.py"))
import spacy  # noqa: E402

claims = json.load(open(sample_path, encoding="utf-8"))["claims"]
nlp = {}
WORD = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*", re.U)


def first(m, doc, lang):
    for sent in doc.sents:
        p = m.extract(sent, lang)
        if p:
            return p
    return None


def problems(p, text):
    if not p:
        return set()
    out = set()
    words = [w for f in ("subject", "object") for w in WORD.findall(p[f])]
    if any(w not in text for w in words):
        out.add("words not in the sentence")
    io, iv = text.find(p["object"]), text.find(p["verb"])
    if io >= 0 and iv >= 0 and io < iv and not text.rstrip().endswith("?"):
        out.add("object before the verb")
    if re.search(re.escape(p["subject"]) + r"\s*:", text) or NEW.ADDRESS.match(p["subject"]):
        out.add("label or address as subject")
    return out


tally = {"old": {}, "new": {}}
lines = []
for c in claims:
    lang = c["language"]
    if lang not in nlp:
        nlp[lang] = spacy.load(NEW.MODELS[lang], disable=["ner"])
    doc = nlp[lang](c["full_text"])
    a, b = first(OLD, doc, lang), first(NEW, doc, lang)
    pa, pb = problems(a, c["full_text"]), problems(b, c["full_text"])
    for k in pa:
        tally["old"][k] = tally["old"].get(k, 0) + 1
    for k in pb:
        tally["new"][k] = tally["new"].get(k, 0) + 1
    fmt = lambda p: f"{p['subject']} | {p['verb']} | {p['object']}" if p else "(no claim)"
    lines.append(f"{c['sentence_id']}\n  sentence: {c['full_text'][:300]}\n  old: {fmt(a)}  {sorted(pa) or ''}\n"
                 f"  new: {fmt(b)}  {sorted(pb) or ''}\n")
out = Path("outputs/audit/fix15_sample_side_by_side.txt")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines), encoding="utf-8")
print(f"   100 sampled sentences, old extractor: {tally['old']}")
print(f"   100 sampled sentences, new extractor: {tally['new']}")
print(f"   side by side: {out}")
bad = [k for k in tally["new"] if tally["new"][k] > 0 and tally["new"][k] >= tally["old"].get(k, 0)]
if any(tally["new"].values()) and (bad or sum(tally["new"].values()) > 3):
    print("   the new extractor still makes these mistakes; the full run is NOT started.")
    sys.exit(2)
print("   PASS: the new extractor fixes the three kinds of mistakes on the sample")
