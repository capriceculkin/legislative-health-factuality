"""eval_roles.py RULES EN_UP.conllu FR_UP.conllu   The design-2 frame mapping (frames.py) scored against Universal Proposition
Bank 1.0 test sets, the same way in both languages.

The UP files carry a UD tree and PropBank roles for each verb, marked on the argument's head word. The mapping is run on
that UD tree, so this measures the rules alone (UD relation -> PropBank role), not a parser. For each gold verb and each
of its arguments that is a direct dependent of the verb in the tree, the role the mapping gives that word is compared with
the gold role.

English: UP_English-EWT (English PropBank roles on the English Web Treebank).
French: UP_French test (roles projected automatically from English PropBank, so silver, not hand-checked); its trees use
UD version 1 labels, which are renamed to version 2 first (dobj -> obj, nsubjpass -> nsubj:pass, nmod on a verb -> obl ...)."""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parity_score as S
P, C = S.load_rules(sys.argv[1])
import frames as FR
frame, CORE = FR.make(P)

V1 = {"dobj": "obj", "nsubjpass": "nsubj:pass", "auxpass": "aux:pass", "csubjpass": "csubj:pass", "mwe": "fixed", "name": "flat", "neg": "advmod"}
NORM = {"A0": "ARG0", "A1": "ARG1", "A2": "ARG2", "A3": "ARG3", "A4": "ARG4"}


def norm(lab):
    lab = NORM.get(lab, lab)
    return lab.replace("AM-", "ARGM-") if lab.startswith("AM-") else lab


def read(path, lang):
    sents, cur = [], []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            if cur:
                sents.append(cur); cur = []
            continue
        if line.startswith("#"):
            continue
        f = line.split("\t")
        if "-" in f[0] or "." in f[0]:
            continue
        cur.append(f)
    if cur:
        sents.append(cur)
    out = []
    for s in sents:
        if lang == "en":
            sense = [f[10] if len(f) > 10 else "_" for f in s]; args = [f[11:] for f in s]
        else:
            sense = [f[9] if len(f) > 9 and f[8] == "Y" else "_" for f in s]; args = [f[10:] for f in s]
        toks = []
        for k, f in enumerate(s):
            dep = f[7]
            if lang == "fr":
                dep = V1.get(dep, dep)
                head_upos = None
            toks.append([k, f[1], f[2], f[3], dep, int(f[6]) - 1 if f[6] not in ("0", "_") else None, f[5] if f[5] != "_" else ""])
        if lang == "fr":                       # UD v1 nmod on a verb is v2 obl
            for t in toks:
                if t[4].startswith("nmod") and t[5] is not None and toks[t[5]][3] in ("VERB", "AUX"):
                    t[4] = "obl" + t[4][4:]
        preds = [k for k, x in enumerate(sense) if x not in ("_", "")]
        gold = {}
        for j, pk in enumerate(preds):
            for k, a in enumerate(args):
                if j < len(a) and a[j] not in ("_", "", "V"):
                    gold[(pk, k)] = norm(a[j])
        out.append((toks, preds, gold))
    return out


def score(path, lang):
    c = collections.Counter(); conf = collections.Counter()
    for raw, preds, gold in read(path, lang):
        toks = [P.T(x[0], x[1], x[2], x[3], x[4], x[5], x[6], " ", None) for x in raw]
        P.link_kids(toks)
        P._TOKS["toks"] = toks
        for pk in preds:
            t = toks[pk]
            if t.upos not in ("VERB",):
                continue
            c["verbs"] += 1
            fr = frame(toks, t, {"verb": t.text, "negated": P.negated(t), "lang": lang})
            ours = {r[2]: r[0] for r in fr["roles"] if r[2] is not None}
            kids = {k.i for k in t.kids}
            for (p_, k), g in gold.items():
                if p_ != pk:
                    continue
                c["gold"] += 1
                if k not in kids:
                    c["gold_not_child"] += 1
                    continue
                c["gold_child"] += 1
                o = ours.get(k)
                gk = g if g in ("ARG0", "ARG1", "ARG2", "ARGM-TMP", "ARGM-NEG", "ARGM-MOD") else ("ARGM-other" if g.startswith("ARGM") else "other core")
                ok_ = o == g or (o is not None and o.startswith("ARGM-") and o not in ("ARGM-TMP", "ARGM-NEG", "ARGM-MOD") and gk == "ARGM-other")
                c["labeled"] += o is not None
                c["right"] += ok_
                conf[(gk, "right" if ok_ else (o or "none"))] += 1
            for k, o in ours.items():
                c["ours"] += 1
                c["ours_right"] += gold.get((pk, k)) == o or (o.startswith("ARGM-") and o not in ("ARGM-TMP", "ARGM-NEG", "ARGM-MOD") and str(gold.get((pk, k), "")).startswith("ARGM") and gold.get((pk, k)) not in ("ARGM-TMP", "ARGM-NEG", "ARGM-MOD"))
    return c, conf


for lang, path in (("en", sys.argv[2]), ("fr", sys.argv[3])):
    c, conf = score(path, lang)
    print(f"== {lang}: {c['verbs']} verbs, {c['gold']} gold arguments, {c['gold_child']} of them direct dependents of the verb")
    print(f"   recall on direct dependents: {c['right']}/{c['gold_child']} = {c['right'] / max(1, c['gold_child']):.1%}"
          f"   precision of our roles: {c['ours_right']}/{c['ours']} = {c['ours_right'] / max(1, c['ours']):.1%}")
    for gk in ("ARG0", "ARG1", "ARG2", "ARGM-TMP", "ARGM-NEG", "ARGM-MOD", "ARGM-other", "other core"):
        tot = sum(v for (g, _), v in conf.items() if g == gk)
        if not tot:
            continue
        rt = conf[(gk, "right")]
        worst = sorted(((v, o) for (g, o), v in conf.items() if g == gk and o != "right"), reverse=True)[:3]
        print(f"   {gk:11s} {rt:4d}/{tot:<4d} {rt / tot:5.1%}   most often given instead: " + ", ".join(f"{o} {v}" for v, o in worst))
