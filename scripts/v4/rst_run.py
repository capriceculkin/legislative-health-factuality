#!/usr/bin/env python3
"""rst_run.py   Discourse parse (RST for English, SDRT for French) of the 100 spot-check sentences with the IsaNLP UniRST
parser (one multilingual model; English uses the RST-DT relation set, French the ANNODIS SDRT set).
Reads only. Writes ~/Desktop/next_steps/discourse.json."""
import json, os, signal, subprocess, sys, time
from pathlib import Path

# The model is already on this Mac after the first run: use the saved copy and never wait on the network for it.
# (The second run hung for days on a HuggingFace check with no time limit.)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(TimeoutError("discourse step took over 30 minutes")))
signal.alarm(1800)

HERE = Path(__file__).resolve().parent
OUT = Path.home() / "Desktop" / "next_steps"; OUT.mkdir(parents=True, exist_ok=True)
COMMIT = "cc8789f44c1341c3e7752b472634d75e81b62518"


def pip(*args):
    return subprocess.call([sys.executable, "-m", "pip", "install", "-q", *args]) == 0


try:
    from isanlp_rst.parser import Parser
except ImportError:
    print("   installing the IsaNLP RST parser (first run only, a few minutes)")
    ok = pip("git+https://github.com/iinemo/isanlp.git") and pip(f"git+https://github.com/tchewik/isanlp_rst.git@{COMMIT}")
    if not ok:
        sys.exit("Could not install the RST parser. Paste the lines above into the chat. Nothing else changed.")
    from isanlp_rst.parser import Parser

sample = json.loads((HERE / "spot_check_sample_v19.json").read_text(encoding="utf-8"))["claims"]


def clean(t):
    return " ".join(t.replace("``", "“").replace("''", "”").split())


print("== loading the discourse model (the first run downloads it; it is large)")
parser = Parser(hf_model_name="tchewik/isanlp_rst_v3", hf_model_version="unirst", relinventory="eng.rst.rstdt", cuda_device=-1)
pred = parser.predictor
INV = {"en": "eng.rst.rstdt", "fr": "fra.sdrt.annodis"}


def walk(node, edus, rels):
    """Leaves are the EDUs (elementary discourse units); every inner node joins a left and a right span with a relation."""
    if node.left is None or node.relation == "elementary":
        edus.append({"text": node.text, "start": node.start, "end": node.end})
        return [len(edus) - 1]
    a = walk(node.left, edus, rels)
    b = walk(node.right, edus, rels)
    rels.append({"left": [a[0], a[-1]], "right": [b[0], b[-1]], "relation": node.relation, "nuclearity": node.nuclearity})
    return a + b


prev = {}
if (OUT / "discourse.json").exists():          # keep sentences already parsed; only redo the ones that failed
    try:
        prev = {r["n"]: r for r in json.loads((OUT / "discourse.json").read_text(encoding="utf-8"))["rows"] if "edus" in r}
    except Exception:
        prev = {}
    print(f"   {len(prev)} sentences already parsed; parsing the rest")


def parse(text, lang):
    pred.relinventory_idx = pred.dataset_names.index(INV[lang])
    res = parser(text)
    edus, rels = [], []
    walk(res["rst"][0], edus, rels)
    return edus, rels


rows, t0 = [], time.time()
for n, c in enumerate(sample, 1):
    lang, text = c["language"], clean(c["full_text"])
    if n in prev:
        rows.append(prev[n]); continue
    try:
        edus, rels = parse(text, lang)
        rows.append({"n": n, "lang": lang, "text": text, "inventory": INV[lang], "edus": edus, "relations": rels})
    except Exception as e:
        try:                                    # a long dash glued to words ("Leacock—and") can break the parser's alignment
            edus, rels = parse(text.replace("—", " — ").replace("–", " – "), lang)
            rows.append({"n": n, "lang": lang, "text": text, "inventory": INV[lang], "edus": edus, "relations": rels, "note": "dashes spaced out"})
        except Exception:
            rows.append({"n": n, "lang": lang, "text": text, "inventory": INV[lang], "error": f"{type(e).__name__}: {e}"})
    if n % 20 == 0:
        print(f"   {n} sentences ({time.time() - t0:.0f}s)")
(OUT / "discourse.json").write_text(json.dumps({"parser": f"isanlp_rst {COMMIT[:10]} unirst", "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
bad = sum("error" in r for r in rows)
print(f"== discourse: {len(rows) - bad} sentences parsed, {bad} failed; {sum(len(r.get('edus', [])) for r in rows)} discourse units")
