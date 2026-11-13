"""run_full_corpus.py   Discourse first, on the whole corpus, in chunks that can be stopped and restarted.

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 scripts/step3_claims/run_full_corpus.py --count                      how many sentences are in each pool (no parsing)
  python3 scripts/step3_claims/run_full_corpus.py --check                      before the full run: reparse the 900 CLAY sentences
                                                                     with this script and compare to the saved results
  python3 scripts/step3_claims/run_full_corpus.py --jur ontario --limit 200    timing test: parse 200 sentences, save nothing
  bash scripts/step3_claims/run_full.sh ontario                                the full run for one legislature (restarts itself)
  python3 scripts/step3_claims/run_full_corpus.py --status                     how many chunks are done, and any sentences that failed
  python3 scripts/step3_claims/run_full_corpus.py --claims                     the claims for every chunk already parsed
  python3 scripts/step3_claims/run_full_corpus.py --verify                     at the end: every sentence is there exactly once

Which sentences: the same pool the samples were drawn from (edu_collect.py). Every sentence in
data/dbpedia_pipeline/<legislature>/sentences_v3.json with an id and text, 8 to 60 words, and not quoted bill text.
Sorted by date and sentence id, so the chunks are always the same.

What each sentence gets: the same parsing as edu_collect.py (the discourse parse, the sentence's constituency tree, and
a tree for every discourse unit), then the claims from edu_pipeline.py with the current rules.

Where it goes: outputs/full/<legislature>/parses_00000.json and trees_00000.json for each chunk of sentences, and
claims_00000.json once --claims is run. A chunk that already has its file is skipped, so a crash or a closed laptop
only costs the chunk that was running. Files are written to a temporary name first and then renamed.

Safety:
  - the first run saves a fingerprint (outputs/full/<legislature>/input.json): the list of sentences, the chunk size,
    the parsing code and the versions of the parser packages. If any of these change later, the run stops instead of
    mixing two versions. The claims step does the same for the rules (claims_rules.json).
  - two copies cannot work on the same chunks: each copy leaves a lock file and a second copy that overlaps stops.
  - a chunk where many sentences fail (a parser not loaded, the GPU out of memory) is not saved, and the run stops.
  - a sentence that takes longer than --sentence-timeout seconds is recorded as failed and the run goes on.

Exit codes: 0 finished; 3 stopped on purpose (fix something first); anything else is a crash and can be restarted."""
import argparse, atexit, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
sys.path.insert(0, str(HERE))
import preds as P            # noqa: E402   the v6 rules, loaded first so parse_corpus_v5 uses them
import edu_pipeline as E     # noqa: E402   only for is_bill_text, so the pool matches the samples
sys.path.insert(1, str(PROJECT / "scripts" / "step2_parsers"))

JUR = {"us": "US", "ontario": "ON", "quebec": "QC"}

ap = argparse.ArgumentParser()
ap.add_argument("--jur", default="all", choices=["all"] + list(JUR))
ap.add_argument("--chunk", type=int, default=500, help="sentences per chunk file")
ap.add_argument("--limit", type=int, default=0, help="stop after this many sentences and save nothing (timing test)")
ap.add_argument("--shard", type=int, default=0)
ap.add_argument("--shards", type=int, default=1)
ap.add_argument("--sentence-timeout", type=int, default=300, help="seconds before one sentence is given up on")
ap.add_argument("--max-failed", type=float, default=0.10, help="share of a chunk that may fail before the run stops")
ap.add_argument("--count", action="store_true", help="only count the pool")
ap.add_argument("--claims", action="store_true", help="run edu_pipeline.py on every parsed chunk")
ap.add_argument("--status", action="store_true", help="progress and failed sentences")
ap.add_argument("--verify", action="store_true", help="every pool sentence is in the parses and the claims exactly once")
ap.add_argument("--check", action="store_true", help="reparse the 900 CLAY sentences and compare to outputs/edu")
A = ap.parse_args()

OUT = PROJECT / "outputs" / "full"
PARSE_CODE = [HERE / "edu_collect.py", HERE / "preds.py", HERE / "lexicon.py", HERE / "const_fr.py", HERE / "combine_lib.py",
              PROJECT / "scripts" / "step2_parsers" / "parse_corpus_v5.py"]
RULES_CODE = [HERE / "edu_pipeline.py", HERE / "preds.py", HERE / "lexicon.py", HERE / "const_fr.py"]
PACKAGES = ["stanza", "benepar", "spacy", "torch", "transformers", "isanlp_rst"]


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def stop(m):
    # something has to be fixed by hand first; run_full.sh does not restart after this
    say("STOP: " + m)
    sys.exit(3)


def save(path, obj):
    # write to a temporary name in the same folder, then rename, so a half-written file never looks finished
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def ok_row(r):
    # a sentence counts as parsed when it has a discourse parse and a constituency tree
    return str(r.get("disc_native_status", "")).startswith("ok") and bool(r.get("trees"))


# fingerprints, so a run never mixes two versions of the data, the code or the rules

def sha_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def versions():
    from importlib import metadata
    out = {}
    for p in PACKAGES:
        try:
            out[p] = metadata.version(p)
        except Exception:                                # noqa: BLE001
            out[p] = "not found"
    return out


def same_or_stop(path, now, what):
    # first time: save the fingerprint; later: stop if anything in it changed
    if path.exists():
        before = json.load(open(path, encoding="utf-8"))
        changed = sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
        if changed:
            stop(f"{what} changed since this run started: {', '.join(changed)} (see {path}). "
                 f"Put it back, or move outputs/full/ aside to start over.")
    else:
        save(path, now)


def input_print(j, recs):
    ids = hashlib.sha1("\n".join(x["sentence_id"] for x in recs).encode("utf-8")).hexdigest()
    now = {"sentences": len(recs), "sentence_ids_sha1": ids, "chunk": A.chunk}
    now.update({"code " + p.name: sha_file(p) for p in PARSE_CODE if p.exists()})
    now.update({"package " + k: v for k, v in versions().items()})
    return now


def rules_print():
    return {p.name: sha_file(p) for p in RULES_CODE if p.exists()}


# one copy per set of chunks: a lock file per running copy

def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def take_lock(j):
    d = OUT / j
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("lock_*.json"):
        try:
            other = json.load(open(f, encoding="utf-8"))
        except Exception:                                # noqa: BLE001
            continue
        if other.get("pid") == os.getpid():
            continue                                     # this copy's own lock (it holds one per legislature)
        if not alive(other.get("pid", -1)):
            f.unlink(missing_ok=True)                    # left behind by a copy that crashed
        elif other["shards"] != A.shards or other["shard"] == A.shard:
            stop(f"another copy is already running on {j} (process {other['pid']}, shard {other['shard']} of {other['shards']}). "
                 f"Wait for it, or stop it first.")
    mine = d / f"lock_{os.getpid()}.json"
    save(mine, {"pid": os.getpid(), "shard": A.shard, "shards": A.shards, "started": time.strftime("%Y-%m-%d %H:%M")})
    atexit.register(lambda: mine.unlink(missing_ok=True))


# the pool of sentences for one legislature

def pool(j):
    p = PROJECT / "data" / "dbpedia_pipeline" / j / "sentences_v3.json"
    recs = [x for x in json.load(open(p, encoding="utf-8")) if x.get("sentence_id") and x.get("text")]
    recs = [x for x in recs if 8 <= len(x["text"].split()) <= 60 and not E.is_bill_text(x["text"])]
    recs.sort(key=lambda x: (x.get("date") or "", x["sentence_id"]))   # same order every time
    # only the fields the run needs, to keep memory down
    return [{k: x.get(k) for k in ("sentence_id", "text", "lang", "date", "bill_key")} for x in recs]


# parsing one chunk, the same way edu_collect.py parses its new sentences

class TooSlow(Exception):
    pass


def on_alarm(signum, frame):
    raise TooSlow()


def parse_chunk(recs, j, V, C):
    code = JUR[j]
    rows, trees = [], {}
    default = "fr" if j == "quebec" else "en"
    signal.signal(signal.SIGALRM, on_alarm)
    for x in recs:
        lang = x.get("lang") if x.get("lang") in ("en", "fr") else default
        s = {"n": f"full|{code}|{x['sentence_id']}", "set": "full", "lang": lang, "text": V.clean(x["text"]),
             "sentence_id": x["sentence_id"], "date": x.get("date"), "bill_key": x.get("bill_key")}
        for attempt in (1, 2):                           # a second try, in case the Mac slept or the GPU hiccuped
            signal.alarm(A.sentence_timeout)
            try:
                d, st = V.rst_parse(s["text"], lang)
                s["disc_native"], s["disc_native_status"] = d, st
                s["trees"] = C.tree_of(s["text"], lang)
                trees[s["n"]] = C.unit_trees(s)
                break
            except TooSlow:
                s["disc_native"], s["disc_native_status"] = None, f"error: took longer than {A.sentence_timeout}s"
                s["trees"], trees[s["n"]] = [], []
            except Exception as ex:                      # noqa: BLE001
                s["disc_native"], s["disc_native_status"] = None, f"error: {type(ex).__name__}: {str(ex)[:80]}"
                s["trees"], trees[s["n"]] = [], []
            finally:
                signal.alarm(0)
        rows.append(s)
    return rows, trees


def parse_all(jurs):
    pools = {}
    for j in jurs:                                       # every check before any model is loaded
        pools[j] = pool(j)
        if len({x["sentence_id"] for x in pools[j]}) != len(pools[j]):
            stop(f"{j}: two sentences share an id")
        if not A.limit:
            same_or_stop(OUT / j / "input.json", input_print(j, pools[j]), f"the {j} sentences, the chunk size, the parsing code or a package")
            take_lock(j)
    import parse_corpus_v5 as V          # loads the models only when they are first used
    sys.argv = [sys.argv[0]]             # edu_collect reads its own arguments when imported
    import edu_collect as C              # tree_of and unit_trees, so the parsing matches the samples exactly
    done, t0 = 0, time.time()
    for j in jurs:
        recs = pools[j]
        chunks = [recs[i:i + A.chunk] for i in range(0, len(recs), A.chunk)]
        say(f"== {j}: {len(recs)} sentences in {len(chunks)} chunks; this copy does shard {A.shard} of {A.shards}")
        for k, ch in enumerate(chunks):
            if k % A.shards != A.shard:
                continue
            pf, tf = OUT / j / f"parses_{k:05d}.json", OUT / j / f"trees_{k:05d}.json"
            if pf.exists() and tf.exists():
                continue                                 # finished in an earlier run
            if A.limit:
                ch = ch[:max(0, A.limit - done)]
                if not ch:
                    break
            t1 = time.time()
            rows, trees = parse_chunk(ch, j, V, C)
            done += len(rows)
            bad = sum(1 for r in rows if not ok_row(r))
            per = (time.time() - t1) / max(1, len(rows))
            if bad > A.max_failed * len(rows):           # not saved: something is wrong with the parsers, not the sentences
                why = sorted({str(r.get("disc_native_status")) if not str(r.get("disc_native_status", "")).startswith("ok")
                              else "no constituency tree" for r in rows if not ok_row(r)})[:3]
                say(f"   {j} chunk {k}: {bad} of {len(rows)} sentences failed ({'; '.join(why)}). Chunk not saved.")
                sys.exit(4)                              # run_full.sh restarts a few times, in case it was the GPU
            if not A.limit:                              # a timing test does not leave chunks behind
                save(pf, {"made": time.strftime("%Y-%m-%d %H:%M"), "rows": rows})
                save(tf, trees)
            say(f"   {j} chunk {k}: {len(rows)} sentences, {per:.2f}s each" + (f", {bad} failed" if bad else ""))
        if A.limit and done >= A.limit:
            break
    if done:
        per = (time.time() - t0) / done
        say(f"== {done} sentences parsed at {per:.2f}s each (models loading included)")
        if A.limit:
            total = sum(len(pool(j)) for j in JUR)
            say(f"   at that speed the whole pool of {total} sentences takes about {total * per / 3600:.0f} hours with one copy running")
    say("== nothing left to parse for " + ", ".join(jurs))


# claims for every chunk that has been parsed

def claims_all(jurs):
    failed = []
    for j in jurs:
        if not (OUT / j).exists():
            continue
        same_or_stop(OUT / j / "claims_rules.json", rules_print(), f"the rules for {j}")
        for pf in sorted((OUT / j).glob("parses_[0-9]*.json")):
            k = pf.stem.split("_")[1]
            tf, cf = OUT / j / f"trees_{k}.json", OUT / j / f"claims_{k}.json"
            if cf.exists() or not tf.exists():
                continue
            tmp = OUT / j / f"claims_{k}.json.{os.getpid()}.tmp"
            r = subprocess.run([sys.executable, str(HERE / "edu_pipeline.py"), str(HERE), str(pf), str(tmp),
                                "--edu-trees", str(tf)], capture_output=True, text=True)
            if r.returncode != 0:
                failed.append(f"{j} chunk {k}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'no message'}")
                tmp.unlink(missing_ok=True)
                continue
            # the sentence id, date and bill go on each record, so the claims can be joined to bills later
            src = {x["n"]: x for x in json.load(open(pf, encoding="utf-8"))["rows"]}
            out = json.load(open(tmp, encoding="utf-8"))
            if [x["n"] for x in out["rows"]] != list(src):
                failed.append(f"{j} chunk {k}: the claims file does not have the same sentences as the parses")
                tmp.unlink(missing_ok=True)
                continue
            for x in out["rows"]:
                for f in ("sentence_id", "date", "bill_key"):
                    x[f] = src[x["n"]].get(f)
            save(cf, out)
            tmp.unlink(missing_ok=True)
        say(f"== {j}: claims written for {len(list((OUT / j).glob('claims_[0-9]*.json')))} chunks")
    for f in failed:
        say("   FAILED " + f)
    if failed:
        sys.exit(1)


# progress

def status(jurs):
    for j in jurs:
        n = len(pool(j))
        total = -(-n // A.chunk)
        parsed = sorted((OUT / j).glob("parses_[0-9]*.json"))
        claims = list((OUT / j).glob("claims_[0-9]*.json"))
        rows = bad = 0
        for pf in parsed:
            rr = json.load(open(pf, encoding="utf-8"))["rows"]
            rows += len(rr)
            bad += sum(1 for r in rr if not ok_row(r))
        say(f"{j}: parsed {len(parsed)}/{total} chunks ({rows}/{n} sentences), claims {len(claims)}/{total}, failed sentences {bad}")


# at the end: every sentence of the pool is in the parses, the trees and the claims exactly once

def verify(jurs):
    good = True
    for j in jurs:
        want = [x["sentence_id"] for x in pool(j)]
        got_p, got_t, got_c, bad, lines = [], [], [], 0, 0
        for pf in sorted((OUT / j).glob("parses_[0-9]*.json")):
            rr = json.load(open(pf, encoding="utf-8"))["rows"]
            got_p += [r["sentence_id"] for r in rr]
            bad += sum(1 for r in rr if not ok_row(r))
            tf = pf.with_name(pf.name.replace("parses_", "trees_"))
            if tf.exists():
                tt = json.load(open(tf, encoding="utf-8"))
                got_t += [r["sentence_id"] for r in rr if r["n"] in tt]
        for cf in sorted((OUT / j).glob("claims_[0-9]*.json")):
            for r in json.load(open(cf, encoding="utf-8"))["rows"]:
                got_c.append(r["sentence_id"])
                lines += len(r["lines"])
        res = {"parses": got_p == want, "trees": got_t == want, "claims": got_c == want}
        say(f"{j}: {len(want)} sentences in the pool; parses {len(got_p)} ({'same, same order' if res['parses'] else 'NOT THE SAME'}), "
            f"trees {len(got_t)} ({'same' if res['trees'] else 'NOT THE SAME'}), claims {len(got_c)} ({'same' if res['claims'] else 'NOT THE SAME'}); "
            f"failed sentences {bad}; {lines} claims")
        good = good and all(res.values())
    say("== VERIFIED: every sentence is there exactly once" if good else "== NOT COMPLETE: see the lines above")
    if not good:
        sys.exit(1)


# the check before the full run: same 900 sentences, this script's parsing, compared to the saved files

def check():
    import parse_corpus_v5 as V
    sys.argv = [sys.argv[0]]
    import edu_collect as C
    saved = json.load(open(PROJECT / "outputs" / "edu" / "more_parses.json", encoding="utf-8"))["rows"]
    saved_trees = json.load(open(PROJECT / "outputs" / "edu" / "edu_trees.json", encoding="utf-8"))
    jname = {v: k for k, v in JUR.items()}
    rows, trees = [], {}
    for k, s in enumerate(saved, 1):
        rec = {"sentence_id": s["sentence_id"], "text": s["text"], "lang": s["lang"]}
        r, t = parse_chunk([rec], jname[s["n"].split("|")[1]], V, C)
        trees[s["n"]] = t[r[0]["n"]]                   # the unit trees, under the sample's name
        r[0]["n"] = s["n"]                               # keep the sample's name so the claims can be compared
        rows.append(r[0])
        if k % 100 == 0:
            say(f"   {k}/{len(saved)} reparsed")
    # 1. the parses: same units, same relations, same trees
    def units(r):
        return [(e.get("start"), e.get("end")) for e in ((r.get("disc_native") or {}).get("edus") or [])]
    def rels(r):
        return [(x.get("relation"), x.get("nuclearity")) for x in ((r.get("disc_native") or {}).get("relations") or [])]
    same_units = sum(units(a) == units(b) for a, b in zip(rows, saved))
    same_rels = sum(rels(a) == rels(b) for a, b in zip(rows, saved))
    same_trees = sum(json.dumps(trees[a["n"]]) == json.dumps(saved_trees.get(a["n"])) for a in rows)
    same_sent = sum(json.dumps(a.get("trees")) == json.dumps(b.get("trees")) for a, b in zip(rows, saved))
    say(f"parses: same units {same_units}/{len(saved)}, same relations {same_rels}/{len(saved)}, "
        f"same sentence trees {same_sent}/{len(saved)}, same unit trees {same_trees}/{len(saved)}")
    # 2. the claims: run edu_pipeline on the new parses and compare to outputs/edu/more_reparsed.json
    tmp = OUT / "_check"
    save(tmp / "parses.json", {"rows": rows}); save(tmp / "trees.json", trees)
    subprocess.run([sys.executable, str(HERE / "edu_pipeline.py"), str(HERE), str(tmp / "parses.json"), str(tmp / "claims.json"),
                    "--edu-trees", str(tmp / "trees.json")], check=True)
    def lines(r):
        return [(l.get("subject"), l.get("verb"), l.get("object"), l.get("kind")) for u in r.get("units", []) for l in u.get("lines", [])]
    new = json.load(open(tmp / "claims.json", encoding="utf-8"))["rows"]
    old = json.load(open(PROJECT / "outputs" / "edu" / "more_reparsed.json", encoding="utf-8"))["rows"]
    same = sum(lines(a) == lines(b) for a, b in zip(new, old))
    say(f"claims: {same}/{len(old)} sentences give the same claims ({sum(len(lines(a)) for a in new)} vs {sum(len(lines(b)) for b in old)} claims)")
    diffs = [(a, b) for a, b in zip(new, old) if lines(a) != lines(b)]
    for a, b in diffs[:10]:                              # the first ten that differ, to look at by hand
        say(f"   differs: {a['n']}  new {lines(a)[:2]}  saved {lines(b)[:2]}")


if __name__ == "__main__":
    jurs = list(JUR) if A.jur == "all" else [A.jur]
    if not 0 <= A.shard < A.shards:
        stop("--shard has to be from 0 to --shards minus 1")
    try:
        if A.check:
            check()
        elif A.status:
            status(jurs)
        elif A.verify:
            verify(jurs)
        elif A.count:
            for j in jurs:
                say(f"{j}: {len(pool(j))} sentences")
        elif A.claims:
            claims_all(jurs)
        else:
            parse_all(jurs)
    except KeyboardInterrupt:
        stop("stopped by you (Ctrl-C). Finished chunks are kept; run the same command to carry on.")
