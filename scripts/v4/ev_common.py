"""ev_common.py   Shared pieces for the Oct 16 evidence step: the full 2022 DBpedia graph from ~/.kg_dump (factual links
only), the 300 judged facts, the debate statements from the Oct 15e concept run, and AUC computed two ways."""
import glob, json, os, re, sys, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = os.path.expanduser(os.environ.get("FULLGRAPH_CACHE", "~/.kg_dump"))
OUT = Path(os.environ.get("OCT16_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct16"))); OUT.mkdir(parents=True, exist_ok=True)
NONFACT = {"seeAlso", "differentFrom"}


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def prop_name(p):
    return re.split(r"[#/]", p)[-1]


def load_graph():
    files = sorted(glob.glob(os.path.join(CACHE, "*.merged.graph.npz")))
    if not files:
        sys.exit("The full graph is not in ~/.kg_dump. Run full_graph_bundle.sh (Oct 14d) first. Nothing changed.")
    f = files[-1]
    z = np.load(f, allow_pickle=False)
    names = json.load(open(f + ".names.json", encoding="utf-8"))
    props = json.load(open(f + ".props.json", encoding="utf-8"))
    indptr, indices, code = z["indptr"], z["indices"], z["code"]
    if len(names) != len(indptr) - 1:
        sys.exit("The saved graph and its page list do not match. Run full_graph_bundle.sh again. Nothing changed.")
    return names, props, indptr, indices, code


def factual_only(indptr, indices, code, props):
    """The same graph without rdfs:seeAlso and owl:differentFrom links (both directions)."""
    bad = np.array([prop_name(p) in NONFACT for p in props])
    keep = ~bad[(code // 2).astype(np.int64)]
    rows = np.repeat(np.arange(len(indptr) - 1, dtype=np.int32), np.diff(indptr))
    counts = np.bincount(rows[keep], minlength=len(indptr) - 1)
    del rows
    new_indptr = np.zeros(len(indptr), dtype=np.int64); np.cumsum(counts, out=new_indptr[1:])
    return new_indptr, indices[keep], code[keep], int((~keep).sum())


def judged_facts():
    """The 300 judged facts (Google relation-extraction corpus: 50 judged true, 50 judged false, 50 made up by swapping,
    for place of birth and for institution attended), with the renamed pages from the Oct 14d run."""
    inp = json.load(open(HERE / "full_graph_inputs.json", encoding="utf-8"))["calibration"]
    ren = json.load(open(HERE / "renamed.json", encoding="utf-8"))["renamed"]
    return inp, ren


def debate_statements():
    """Stated predications with their concepts from the Oct 15e run (the newest concepts_v3.json on the Desktop, or the
    copy shipped with this bundle)."""
    p = Path.home() / "Desktop" / "next_steps" / "oct15" / "concepts_v3.json"
    src = p if p.exists() else HERE / "concepts_v3_oct15e.json"
    d = json.load(open(src, encoding="utf-8"))
    return d["statements"], str(src), d.get("version", "?")


def auc_ranksum(pos, neg):
    """Mann-Whitney: the chance a random true fact scores above a random false one (ties count half)."""
    if not pos or not neg:
        return None
    vals = sorted([(v, 0) for v in pos] + [(v, 1) for v in neg])
    ranks, i = {}, 0
    while i < len(vals):
        j = i
        while j < len(vals) and vals[j][0] == vals[i][0]:
            j += 1
        ranks[vals[i][0]] = (i + 1 + j) / 2
        i = j
    r = sum(ranks[v] for v in pos)
    return round((r - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)), 3)


def auc_pairs(pos, neg):
    """The same quantity counted pair by pair (a separate computation, to check the first)."""
    if not pos or not neg:
        return None
    s = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return round(s / (len(pos) * len(neg)), 3)


def strip_name(page):
    """Page title as plain words: Joseph_Dixon_(bishop) -> Joseph Dixon."""
    return re.sub(r"\s*\([^)]*\)", "", (page or "").replace("_", " ")).strip()
