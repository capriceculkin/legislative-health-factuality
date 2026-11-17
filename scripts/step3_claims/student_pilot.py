"""student_pilot.py   A small, fast model that marks subject, verb and object, trained on the Penn Treebank's human
annotation, then scored on the same 100 held-out sentences as the LLM pilot and timed on real debate sentences.

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 scripts/step3_claims/student_pilot.py
  python3 scripts/step3_claims/student_pilot.py --model xlm-roberta-base --epochs 4

Why: an LLM is too slow and too costly to run on a million sentences, and its output can change between runs. A small
encoder (XLM-RoBERTa, English and French) that tags words is fast, and with saved weights it gives the same answer
every time. This pilot trains it on human-made labels (the treebank), so nothing here depends on an LLM.

Two models, the way semantic role labelers work:
  1. verbs     tags the verb words of every claim in the sentence
  2. roles     given one verb (marked in the sentence), tags its subject and its object

Training data: every treebank sentence except the 100 in outputs/llm_pilot/sample.json (those are the test).
Writes outputs/student_pilot/: the two models, lines_student.txt (same format as the LLM pilot), score.txt,
timing.txt and run_info.json (seed, versions, times). Run with the full run stopped: it uses the Mac's GPU."""
import argparse, json, os, random, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
ap = argparse.ArgumentParser()
ap.add_argument("--model", default="xlm-roberta-base")
ap.add_argument("--epochs", type=int, default=4)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--lr", type=float, default=3e-5)
ap.add_argument("--seed", type=int, default=20261116)
ap.add_argument("--time-n", type=int, default=2000, help="debate sentences used for the speed test")
A = ap.parse_args()

TB = PROJECT / "data" / "ptb_sample" / "combined"
OUT = PROJECT / "outputs" / "student_pilot"
OUT.mkdir(parents=True, exist_ok=True)
os.environ["HF_HUB_OFFLINE"] = "0"           # the model may need downloading once
os.environ["TRANSFORMERS_OFFLINE"] = "0"
sys.argv = [sys.argv[0], str(HERE), str(TB)]  # ptb_gold reads these when imported
sys.path.insert(0, str(HERE))
import ptb_gold as G                          # noqa: E402

random.seed(A.seed)
LOG = open(OUT / "log.txt", "a", encoding="utf-8")


def say(m):
    m = time.strftime("%H:%M:%S ") + m
    print(m, flush=True); LOG.write(m + "\n"); LOG.flush()


def toks(s):
    return re.findall(r"\w+|[^\w\s]", s or "")


def low(x):
    return [w.lower() for w in x]


# turning the treebank's gold lines into word positions

def joined(s):
    # the treebank splits contractions ("does n't"); the sentence text has them whole ("doesn't")
    return re.sub(r"\b(\w+) n't\b", r"\1n't", s or "")


def find_all(T, S):
    n = len(S)
    return [i for i in range(len(T) - n + 1) if n and T[i:i + n] == S]


def label_sentence(T, gold):
    """For each gold line: the positions of its verb words, subject and object (None when they can't be found)."""
    Tl, used, out, miss = low(T), set(), [], {"verb": 0, "subject": 0, "object": 0}
    for g in gold:
        V = low(toks(joined(g["verb"])))
        vpos = None
        for i in find_all(Tl, V):                              # the verb as one block, first unused place
            if not used & set(range(i, i + len(V))):
                vpos = list(range(i, i + len(V))); break
        if vpos is None:                                       # not one block ("did not note"): word by word, in order
            p, vpos = 0, []
            for w in V:
                j = next((j for j in range(p, len(Tl)) if Tl[j] == w and j not in used), None)
                if j is None:
                    vpos = None; break
                vpos.append(j); p = j + 1
        if not vpos:
            miss["verb"] += 1; continue
        used |= set(vpos)
        line = {"verb": vpos}
        for role in ("subject", "object"):
            S = low(toks(joined(g[role]))) if g[role] else []
            if not S:
                line[role] = None; continue
            cands = find_all(Tl, S)
            if not cands:
                miss[role] += 1; line[role] = None; continue
            c = min(cands, key=lambda i: (abs(i - vpos[0]), i > vpos[0]) if role == "subject" else (abs(i - vpos[-1]), i < vpos[0]))
            line[role] = (c, c + len(S))
        out.append(line)
    return out, miss


# the treebank, split into training sentences and the 100 test sentences

test_keys = {(r["file"], r["k"]) for r in json.load(open(PROJECT / "outputs" / "llm_pilot" / "sample.json", encoding="utf-8"))}
train, test = [], {}
missing = {"verb": 0, "subject": 0, "object": 0}; n_lines = 0
for f, k, root in G.treebank_sentences(str(TB)):
    gold = G.gold_lines(root)
    T = toks(G.txt(root))
    if (f, k) in test_keys:
        test[(f, k)] = T; continue
    if not gold:
        continue
    lines, miss = label_sentence(T, gold)
    for x in miss:
        missing[x] += miss[x]
    n_lines += len(gold)
    train.append((T, lines))
say(f"training sentences {len(train)}, gold lines {n_lines}; not placed in the sentence: {missing}; test sentences {len(test)}")

if os.environ.get("STUDENT_LABELS_ONLY"):      # check the labels without training
    sys.exit(0)
import torch                                  # noqa: E402
from transformers import AutoTokenizer, AutoModelForTokenClassification  # noqa: E402
torch.manual_seed(A.seed)
DEV = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")

MARK_L, MARK_R = "⟦", "⟧"
V_LAB = ["O", "B-V", "I-V"]
R_LAB = ["O", "B-S", "I-S", "B-O", "I-O"]


def verb_tags(T, lines):
    t = ["O"] * len(T)
    for ln in lines:
        prev = None
        for p in ln["verb"]:
            t[p] = "I-V" if prev is not None and p == prev + 1 else "B-V"; prev = p
    return t


def marked(T, vpos):
    a, b = min(vpos), max(vpos)
    return T[:a] + [MARK_L] + T[a:b + 1] + [MARK_R] + T[b + 1:], a, b


def role_example(T, ln):
    M, a, b = marked(T, ln["verb"])
    shift = lambda i: i + (1 if i >= a else 0) + (1 if i > b else 0)
    t = ["O"] * len(M)
    for role, tag in (("subject", "S"), ("object", "O")):
        sp = ln.get(role)
        if sp:
            for j, i in enumerate(range(sp[0], sp[1])):
                t[shift(i)] = ("B-" if j == 0 else "I-") + tag
    return M, t


tok = AutoTokenizer.from_pretrained(A.model)


def encode(words, tags, labels):
    enc = tok(words, is_split_into_words=True, truncation=True, max_length=192)
    ids, prev, lab = enc.word_ids(), None, []
    for w in ids:
        lab.append(-100 if w is None or w == prev else labels.index(tags[w])); prev = w
    enc["labels"] = lab
    return enc


def batches(items, size, shuffle):
    idx = list(range(len(items)))
    if shuffle:
        random.shuffle(idx)
    for i in range(0, len(idx), size):
        chunk = [items[j] for j in idx[i:i + size]]
        L = max(len(c["input_ids"]) for c in chunk)
        pad = lambda key, v: torch.tensor([c[key] + [v] * (L - len(c[key])) for c in chunk])
        yield {"input_ids": pad("input_ids", tok.pad_token_id), "attention_mask": pad("attention_mask", 0),
               "labels": pad("labels", -100)}


def fit(name, items, labels):
    # a model already trained with the same settings is loaded instead of trained again (so a stop costs at most one model)
    done = OUT / f"model_{name}"
    same = {"base_model": A.model, "seed": A.seed, "epochs": A.epochs, "batch": A.batch, "lr": A.lr, "examples": len(items)}
    if (done / "trained_with.json").exists() and json.load(open(done / "trained_with.json")) == same:
        say(f"   {name}: already trained with these settings, loading {done}")
        return AutoModelForTokenClassification.from_pretrained(done).to(DEV).eval()
    model = AutoModelForTokenClassification.from_pretrained(A.model, num_labels=len(labels)).to(DEV)
    opt = torch.optim.AdamW(model.parameters(), lr=A.lr)
    model.train(); t0 = time.time()
    for ep in range(A.epochs):
        tot = n = 0
        for b in batches(items, A.batch, True):
            b = {k: v.to(DEV) for k, v in b.items()}
            loss = model(**b).loss
            loss.backward(); opt.step(); opt.zero_grad()
            tot += loss.item(); n += 1
        say(f"   {name} epoch {ep + 1}: loss {tot / max(n, 1):.4f}")
    model.eval()
    model.save_pretrained(done); tok.save_pretrained(done)
    json.dump(same, open(done / "trained_with.json", "w"))      # written last, so a half-saved model is never reused
    say(f"   {name} trained in {time.time() - t0:.0f}s, saved to {OUT / ('model_' + name)}")
    return model


# training

say(f"device {DEV}, base model {A.model}, seed {A.seed}, epochs {A.epochs}")
t_all = time.time()
v_items = [encode(T, verb_tags(T, lines), V_LAB) for T, lines in train]
r_items = [encode(*role_example(T, ln), R_LAB) for T, lines in train for ln in lines]
say(f"verb examples {len(v_items)}, role examples {len(r_items)}")
vm = fit("verbs", v_items, V_LAB)
rm = fit("roles", r_items, R_LAB)
train_secs = time.time() - t_all


# reading new sentences

@torch.no_grad()
def predict(model, word_lists, labels, size=64):
    out = []
    for i in range(0, len(word_lists), size):
        chunk = word_lists[i:i + size]
        enc = tok(chunk, is_split_into_words=True, truncation=True, max_length=192, padding=True, return_tensors="pt")
        pred = model(**{k: v.to(DEV) for k, v in enc.items()}).logits.argmax(-1).cpu().tolist()
        for j in range(len(chunk)):
            tags, prev = ["O"] * len(chunk[j]), None
            for pos, w in enumerate(enc.word_ids(j)):
                if w is not None and w != prev:
                    tags[w] = labels[pred[j][pos]]
                prev = w
            out.append(tags)
    return out


GAP = {"not", "never", "'", "t", "n", "also", "still", "even", "just", "only", "already", "ultimately", "really"}


def verb_runs(T, tags):
    pos = [i for i, t in enumerate(tags) if t != "O"]
    runs = []
    for p in pos:
        gap = range(runs[-1][-1] + 1, p) if runs else range(0)
        joined = runs and p - runs[-1][-1] <= 3 and (
            (tags[p] == "I-V" and p == runs[-1][-1] + 1) or (len(gap) > 0 and all(T[q].lower() in GAP for q in gap)))
        if joined:
            runs[-1].append(p)
        else:
            runs.append([p])
    return runs


def span_text(M, tags, which):
    best, cur = [], []
    for i, t in enumerate(tags):
        if t == f"B-{which}" or (t == f"I-{which}" and not cur):
            if len(cur) > len(best):
                best = cur
            cur = [i]
        elif t == f"I-{which}" and cur:
            cur.append(i)
        else:
            if len(cur) > len(best):
                best = cur
            cur = []
    if len(cur) > len(best):
        best = cur
    return " ".join(M[i] for i in best)


def read(sentences):
    vt = predict(vm, sentences, V_LAB)
    jobs = []
    for si, (T, tags) in enumerate(zip(sentences, vt)):
        for run in verb_runs(T, tags):
            M, a, b = marked(T, run)
            jobs.append((si, run, M))
    rt = predict(rm, [j[2] for j in jobs], R_LAB) if jobs else []
    lines = [[] for _ in sentences]
    for (si, run, M), tags in zip(jobs, rt):
        T = sentences[si]
        lines[si].append({"subject": span_text(M, tags, "S") or "(unstated)",
                          "verb": " ".join(T[p] for p in run if vt[si][p] != "O"),
                          "object": span_text(M, tags, "O")})
    return lines


# the 100 test sentences, written like the LLM pilot, then scored the same way

sample = json.load(open(PROJECT / "outputs" / "llm_pilot" / "sample.json", encoding="utf-8"))
t0 = time.time()
pred = read([test[(r["file"], r["k"])] for r in sample])
with open(OUT / "lines_student.txt", "w", encoding="utf-8") as fh:
    for i, L in enumerate(pred):
        fh.write(f"#{i}\n")
        for x in L:
            fh.write(f"{x['subject']} | {x['verb']} | {x['object']} | \n")
say(f"test sentences read in {time.time() - t0:.1f}s; lines written to {OUT / 'lines_student.txt'}")
import subprocess                             # noqa: E402
sc = subprocess.run([sys.executable, str(HERE / "llm_score.py"), str(HERE), str(PROJECT / "outputs" / "wsj" / "wsj_parses.json"),
                     str(TB), str(PROJECT / "outputs" / "llm_pilot" / "sample.json"), str(OUT / "lines_student.txt"),
                     "student (XLM-R, treebank)"], capture_output=True, text=True)
(OUT / "score.txt").write_text(sc.stdout + sc.stderr, encoding="utf-8")
print(sc.stdout[-2500:] or sc.stderr[-2500:])


# speed on real debate sentences (English and French), for the full-corpus estimate

rnd = random.Random(A.seed); deb = []
for j in ("us", "ontario", "quebec"):
    recs = json.load(open(PROJECT / "data" / "dbpedia_pipeline" / j / "sentences_v3.json", encoding="utf-8"))
    recs = [x for x in recs if x.get("text") and 8 <= len(x["text"].split()) <= 60]
    deb += [toks(x["text"]) for x in rnd.sample(recs, A.time_n // 3)]
    del recs
t0 = time.time(); _ = read(deb); secs = time.time() - t0
per_s = len(deb) / secs
msg = (f"{len(deb)} debate sentences in {secs:.1f}s = {per_s:.1f} sentences a second on {DEV}; "
       f"all 1,033,450 sentences would take about {1033450 / per_s / 3600:.1f} hours")
(OUT / "timing.txt").write_text(msg + "\n", encoding="utf-8"); say(msg)

import transformers                           # noqa: E402
json.dump({"base_model": A.model, "seed": A.seed, "epochs": A.epochs, "batch": A.batch, "lr": A.lr, "device": DEV,
           "torch": torch.__version__, "transformers": transformers.__version__, "train_sentences": len(train),
           "unplaced_gold_parts": missing, "train_seconds": round(train_secs), "debate_sentences_per_second": round(per_s, 1),
           "made": time.strftime("%Y-%m-%d %H:%M")}, open(OUT / "run_info.json", "w"), indent=1)
say("done")
