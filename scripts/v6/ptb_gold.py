"""ptb_gold.py RULES TREEBANK_DIR [--n N] [--show K]

A gold standard made by people, before AI: the Penn Treebank (Marcus, Santorini and Marcinkiewicz 1993; function tags
and traces from Treebank II, Marcus et al. 1994). The free sample that ships with NLTK holds 199 Wall Street Journal
files (wsj_0001 to wsj_0199, sections 00 and 01, 3,914 sentences), hand-bracketed and hand-tagged.

The annotators marked, for every clause:
  -SBJ   the subject                         -PRD   a predicative complement ("is chairman")
  -DTV   the recipient ("gave it to them")   -LGS   the doer in a passive ("by the board")
  -TMP   a time adjunct                      -NONE- *-k / *T*-k   a word that is understood, not said, pointing to
                                                    the phrase numbered k ("the Senate refused [*-1] to act")
Step 1 turns those marks into gold lines (subject | verb | object, plus recipient, predicative complement, time,
negation, and whether the subject is understood). That conversion is a program written for this check: the marks are
the gold, the conversion must be spot-checked by a person (20 sentences are printed with --show).
Step 2 removes the marks and the understood words, so the tree looks like a parser's tree, and runs our English tree
rules on it. A wrong line in step 2 is a rule error, because the tree itself is right.
Step 3 scores step 2 against step 1 with the same loose test as the vote, and an exact test.
Plain python3, no packages."""
import sys, os, re, glob, argparse, collections, json

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("rules"); ap.add_argument("treebank")
    ap.add_argument("--n", type=int, default=0, help="only the first N sentences")
    ap.add_argument("--show", type=int, default=0, help="print the first K sentences in full, for a person to check")
    ap.add_argument("--json", default="")
    A = ap.parse_args()
    sys.path.insert(0, A.rules)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preds as P            # noqa: E402
import combine_lib as C      # noqa: E402

CLAUSE = {"S", "SINV", "SQ"}
AUX_TAGS = {"MD", "VB", "VBD", "VBG", "VBN", "VBP", "VBZ", "TO"}
NEG = {"not", "n't", "never"}


def read_trees(path):
    s = open(path, encoding="utf-8").read()
    out, depth, start = [], 0, None
    for i, ch in enumerate(s):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                out.append(s[start:i + 1])
    return out


def label(n):
    return "" if isinstance(n, str) else n[0]


def cat(n):
    """Category without function tags or indices: NP-SBJ-1 -> NP. Keeps -NONE-."""
    l = label(n)
    if l == "-NONE-":
        return l
    return re.split(r"[-=]", l)[0] if l else ""


def tags(n):
    l = label(n)
    if l == "-NONE-" or not l:
        return set()
    return {t for t in re.split(r"[-=]", l)[1:] if t and not t.isdigit()}


def index(n):
    m = re.search(r"-(\d+)$", label(n))
    return m.group(1) if m else None


def words(n):
    """The words a person reads: understood elements (-NONE-) left out."""
    if isinstance(n, str):
        return [n]
    if cat(n) == "-NONE-":
        return []
    return [w for k in n[1] for w in words(k)]


def words_without(n, skip):
    """The words of n, leaving out the subtree skip and the commas or dashes around it (for 'X, he said, Y')."""
    out = []
    def walk(x, parent_kids=None):
        if isinstance(x, str):
            out.append(x); return
        if x is skip or cat(x) == "-NONE-":
            return
        for k in x[1]:
            if isinstance(k, str):
                out.append(k)
            elif k is skip or (cat(k) == "PRN" and any(y is skip for y in all_nodes(k))):
                continue
            else:
                walk(k)
    walk(n)
    return out


def txt(n):
    return P.text(("X", words(n))) if not isinstance(n, str) else n


def only_trace(n):
    """The trace inside a phrase that holds no words, e.g. (NP-SBJ (-NONE- *-1)) -> '*-1'. When there are several
    (SBAR (-NONE- 0) (S (-NONE- *T*-1))), the one with an index wins: '*T*-1', not the empty complementizer '0'."""
    if isinstance(n, str) or words(n):
        return None
    leaves = [k[1][0] for k in all_nodes(n) if cat(k) == "-NONE-" and k[1]]
    indexed = [t for t in leaves if re.match(r"\*(T\*|ICH\*|EXP\*|RNR\*)?-\d+", t)]
    return (indexed or leaves or [None])[0]


def all_nodes(n):
    if isinstance(n, str):
        return
    yield n
    for k in n[1]:
        yield from all_nodes(k)


def verb_chains(vp):
    """Walk down nested VPs: (VP (MD will) (VP (VB join) ...)) -> ['will','join'], the lowest VP, negated?
    Coordinated VPs, (VP (VP closing plants) (CC and) (VP eliminating jobs)), give one chain each, sharing the
    auxiliaries above them. The verb's own spelling is kept ('ve, 's)."""
    out = []
    def walk(cur, chain, neg):
        vps = []
        for k in cur[1]:
            if cat(k) in AUX_TAGS and words(k):
                chain = chain + [" ".join(words(k))]
            elif cat(k) == "RB" and txt(k).lower() in NEG:
                neg = True; chain = chain + [txt(k)]
            elif cat(k) == "ADVP" and txt(k).lower() in NEG:
                neg = True; chain = chain + [txt(k)]
            elif cat(k) == "VP":
                vps.append(k)
        if not vps:
            out.append((chain, cur, neg)); return
        coord = len(vps) > 1 and any(cat(k) == "CC" or label(k) in (",", ":") for k in cur[1])
        for v in (vps if coord else vps[:1]):
            walk(v, chain, neg)
    walk(vp, [], False)
    return out


# verbs that take a person and a content clause (Huddleston and Pullum ch. 4: "told her that ..."), every form in the sample
IO_CLAUSE_VERBS = {f for v in ("tell told telling", "assure assured assuring", "remind reminded reminding", "warn warned warning",
                               "inform informed informing", "notify notified notifying", "advise advised advising",
                               "convince convinced convincing", "persuade persuaded persuading", "promise promised promising",
                               "show showed shown showing", "teach taught teaching", "ask asked asking", "write wrote written writing",
                               "guarantee guaranteed guaranteeing", "bet betting") for f in v.split()} | {"tell", "assure", "remind", "warn", "inform", "notify", "advise", "convince", "persuade", "promise", "show", "teach", "ask", "write", "guarantee", "bet"}
BE_GET = {"is", "was", "were", "be", "been", "being", "are", "am", "'s", "'re", "get", "gets", "got", "gotten", "getting", "become", "became"}


NOUNISH = ("NN", "NNS", "NNP", "NNPS", "PRP", "CD", "EX", "DT", "WP")


def head(n):
    """The head word of a phrase, by the usual Penn Treebank head rules, simplified: the noun phrase's last noun before
    any PP or clause; a PP's head is the head of its object; a clause's head is its first verb; an adjective phrase's
    head is its adjective."""
    if n is None or isinstance(n, str):
        return n
    c = cat(n)
    kids = [k for k in n[1] if not isinstance(k, str) and words(k)]
    if c == "NP":
        if kids and cat(kids[0]) == "NP":
            return head(kids[0])
        cand = [k for k in kids if cat(k) in NOUNISH or cat(k) in ("NX", "QP", "NAC")]
        cand = [k for k in cand if cat(k) != "DT"] or cand
        return head(cand[-1]) if cand else (head(kids[-1]) if kids else None)
    if c in ("PP",):
        obj = next((k for k in kids if cat(k) in ("NP", "S", "SBAR", "ADJP", "ADVP")), None)
        return head(obj) if obj is not None else (words(n)[0] if words(n) else None)
    if c in ("S", "SBAR", "SINV", "SQ", "VP"):
        for k in kids:
            if cat(k) in AUX_TAGS:
                pass
        vs = [k for k in all_nodes(n) if cat(k) in ("VB", "VBD", "VBG", "VBN", "VBP", "VBZ") and words(k)]
        if vs:
            return words(vs[0])[0] if c != "VP" else words(vs[-1])[0]
        prd = next((k for k in kids if "PRD" in tags(k) or cat(k) in ("NP", "ADJP")), None)    # small clause: named [a director]
        return head(prd) if prd is not None else (words(n)[0] if words(n) else None)
    if c == "ADJP":
        a = [k for k in kids if cat(k).startswith("JJ")]
        return words(a[-1])[0] if a else (head(kids[-1]) if kids else None)
    if c in ("NX", "QP", "NAC", "WHNP", "ADVP"):
        return words(n)[-1] if words(n) else None
    return words(n)[-1] if words(n) else None


def gold_lines(root):
    """Every clause with a verb phrase becomes one gold line."""
    idx, parent = {}, {}
    for n in all_nodes(root):
        for k in n[1]:
            if not isinstance(k, str):
                parent[id(k)] = n
    for n in all_nodes(root):
        i = index(n)
        if not i or cat(n) == "-NONE-":
            continue
        if cat(n) == "WHNP":
            # a relative pronoun (that, which, who, or none at all: "the arrangement [0] he had") stands for the noun
            # its clause hangs on: (NP (NP symptoms) (SBAR (WHNP-1 that) (S (NP-SBJ *T*-1) ...))) -> symptoms
            sb = parent.get(id(n)); np = parent.get(id(sb)) if sb is not None else None
            if np is not None and cat(np) == "NP":
                noun = next((k for k in np[1] if cat(k) == "NP" and words(k)), None)
                if noun is not None:
                    idx.setdefault(i, noun); continue
        idx.setdefault(i, n)

    def resolve(tr, depth=0):
        """Follow a trace to the words it stands for, through chains (*-1 -> NP-SBJ-1 *T*-138 -> which -> the Commission)."""
        m = re.match(r"\*(?:T\*|ICH\*|EXP\*|RNR\*)?-(\d+)", tr or "")
        if not m or m.group(1) not in idx or depth > 6:
            return None
        n = idx[m.group(1)]
        return n if words(n) else resolve(only_trace(n), depth + 1)
    out = []
    for cl in all_nodes(root):
        if cat(cl) not in CLAUSE:
            continue
        vp = next((k for k in cl[1] if cat(k) == "VP"), None)
        if vp is None:
            continue
        for chain, low, neg in verb_chains(vp):
            g = clause_line(cl, chain, low, neg, resolve)
            if g:
                out.append(g)
    return out


def clause_line(cl, chain, low, neg, resolve):
    if True:
        heads = [w for w in chain if w.lower() not in NEG]
        if not heads:
            return None
        g = {"verb": " ".join(chain), "negated": neg, "subject": "", "subject_understood": None, "object": "",
             "object_kind": None, "recipient": "", "predicative": "", "time": [], "passive_doer": "", "passive": False, "first_word": None, "subject_head": None, "object_head": None}
        sbj = next((k for k in cl[1] if "SBJ" in tags(k)), None)
        if sbj is not None:
            if words(sbj):
                g["subject"] = txt(sbj); g["subject_head"] = head(sbj)
            else:
                tr = only_trace(sbj) or ""
                ant = resolve(tr)
                if ant is not None:
                    g["subject"] = txt(ant); g["subject_head"] = head(ant); g["subject_understood"] = "from " + tr
                else:
                    g["subject_understood"] = "unstated (" + (tr or "*") + ")"
        nps = []
        for k in low[1]:
            t = tags(k)
            if "PRD" in t:
                ant = k if words(k) else resolve(only_trace(k))
                if ant is not None:
                    g["predicative"] = txt(ant); g["predicative_head"] = head(ant)
            elif "DTV" in t or "BNF" in t:
                g["recipient"] = txt(k)
            elif "TMP" in t and words(k):
                g["time"].append(txt(k))
            elif cat(k) == "PP" and any("LGS" in tags(x) for x in k[1] if not isinstance(x, str)):
                g["passive_doer"] = txt(k)
            elif cat(k) == "NP" and not t and words(k):
                nps.append(k)
            elif cat(k) == "NP" and not t and not words(k) and only_trace(k):
                tr = only_trace(k); m = re.match(r"\*(T\*|ICH\*)?-(\d+)", tr or "")
                if m and not m.group(1) and sbj is not None and index(sbj) == m.group(2):
                    g["passive"] = True          # (NP-SBJ-1 findings) were (VP reported (NP *-1)): the subject is what was reported
                elif m and resolve(tr) is not None:
                    nps.append(resolve(tr))
            elif cat(k) in ("SBAR", "S", "SQ", "SINV", "SBARQ") and not (t & {"ADV", "PRP", "TMP", "LOC", "MNR", "CND"}) and not g["object"]:
                # a fronted quote can be a question (SQ) or an inverted clause (SINV): "'Do I ...?' Mr. Watson asks"
                g["object"] = txt(k); g["object_kind"] = "clause"; g["object_head"] = head(k)
                tr = only_trace(k)
                if tr and not words(k):
                    ant = resolve(tr)
                    if ant is not None:
                        # a parenthetical reporting clause ("..., he said, ...") points at the whole sentence around it:
                        # its own words are left out of what is said
                        inside = any(x is cl for x in all_nodes(ant))
                        g["object"] = P.text(("X", words_without(ant, cl))) if inside else txt(ant)
                        g["object_kind"] = "clause (fronted, " + tr + ")" + (" around the reporting clause" if inside else ""); g["object_head"] = head(ant)
                elif cat(k) == "S" and words(k) and not any(cat(x) in AUX_TAGS for x in all_nodes(k)):
                    g["object_kind"] = "predicative complement (small clause, no verb)"      # named [a director], found [the rates illegal]
        for k in cl[1]:
            if "TMP" in tags(k) and words(k):
                g["time"].append(txt(k))
        # Huddleston and Pullum ch. 4: in "told her (that) she was pushing too hard", "her" is the indirect object and the
        # finite clause is the complement. The treebank has no tag for this (no -DTV on a bare noun phrase), so the rule
        # is ours: one noun phrase followed by a finite clause (SBAR) -> recipient + clause object.
        io_verb = (heads[-1].lower() if heads else "").rstrip("s") in IO_CLAUSE_VERBS or (heads[-1].lower() if heads else "") in IO_CLAUSE_VERBS

        def content_clause(k):
            """A finite content clause: SBAR opened by that / whether / if or an unstated 'that' (-NONE- 0), holding a
            clause with a finite verb. Not a relative (WHNP), not a comparative (than), not an infinitive."""
            if cat(k) != "SBAR" or tags(k) & {"ADV", "PRP", "TMP", "LOC", "MNR", "CND"}:
                return False
            kids = [x for x in k[1] if not isinstance(x, str)]
            if not kids:
                return False
            first = kids[0]
            opener = (cat(first) == "-NONE-" and first[1] and first[1][0] == "0") or (cat(first) == "IN" and txt(first).lower() in ("that", "whether", "if")) \
                or (cat(first) in ("WHNP", "WHADVP", "WHADJP") and io_verb)      # "tells you what ...": a question clause after a person
            if not opener:
                return False
            inner = next((x for x in kids[1:] if cat(x) == "S"), None)
            if inner is None:
                return False
            if not words(inner):
                return True                                   # a fronted quote, resolved through its trace
            vp = next((x for x in inner[1] if cat(x) == "VP"), None)
            return vp is not None and any(cat(x) in ("VBD", "VBZ", "VBP", "MD") for x in vp[1])
        fin = next((k for k in low[1] if content_clause(k)), None)
        if len(nps) == 1 and fin is not None and io_verb and g["object_kind"] and g["object_kind"].startswith("clause"):
            g["recipient"] = txt(nps[0]); nps = []
            g["object_kind"] = g["object_kind"] + " (with an indirect object before it)"
        if len(nps) >= 2:
            g["recipient"] = g["recipient"] or txt(nps[0])
            g["object"], g["object_kind"] = txt(nps[1]), "noun phrase (second of two: the first is the indirect object)"; g["object_head"] = head(nps[1])
        elif nps:
            g["object"], g["object_kind"] = txt(nps[0]), "noun phrase"; g["object_head"] = head(nps[0])
        if not g["object"] and not nps:
            clr = next((k for k in low[1] if "CLR" in tags(k) and cat(k) == "PP" and words(k)), None)
            if clr is not None:
                g["object"], g["object_kind"] = txt(clr), "prepositional complement (-CLR)"; g["object_head"] = head(clr)
        g["adjuncts"] = [txt(k) for k in low[1] if tags(k) & {"LOC", "DIR", "MNR", "PRP", "ADV", "EXT"} and words(k)]
        if not g["object"] and g["predicative"]:
            g["object"], g["object_kind"] = g["predicative"], "predicative complement"; g["object_head"] = g.get("predicative_head")
        # passive, a second way: a form of be or get, then a past participle (Bies et al. 1995 mark the passive with a
        # trace, but the trace can sit inside an infinitive: "is empowered [*-1 to impose]")
        last = next((k for k in reversed(low[1]) if cat(k) in AUX_TAGS and words(k)), None)
        if last is not None and cat(last) == "VBN" and any(w.lower() in BE_GET for w in chain[:-1]):
            g["passive"] = True
        lv = [w for w in words(low) if w]
        g["first_word"] = lv[0] if lv else None
        return g


def strip_marks(n):
    """What a parser would output: no function tags, no indices, no understood words, no empty phrases."""
    if isinstance(n, str):
        return n
    if cat(n) == "-NONE-":
        return None
    kids = [strip_marks(k) for k in n[1]]
    kids = [k for k in kids if k is not None]
    if not kids:
        return None
    return (cat(n) or n[0], kids)


def to_str(n):
    if isinstance(n, str):
        return n.replace("(", "-LRB-").replace(")", "-RRB-")
    return "(" + n[0] + " " + " ".join(to_str(k) for k in n[1]) + ")"


def norm(x):
    x = (x or "").replace("(inh)", " ").replace("’", "'")
    x = re.sub(r"\((?!inh)[^)]*\)", " ", x)
    x = re.sub(r"[^\w' ]", " ", x.lower())
    return " ".join(x.replace("'", " ' ").split())


def key_line(g):
    return (g["subject"] or "(unstated)", g["verb"], g["object"], "asserted")


def head_ok(gold_text, gold_head, ours):
    """Right head, nothing extra: the gold head word is in our slot, and every content word of our slot is in the gold
    phrase. Fair to rules that keep the core noun phrase (symptoms) where the treebank keeps the whole phrase
    (symptoms that show up decades later). Both empty also counts."""
    g = set(P.fold(gold_text or "")); o = [w for w in P.fold((ours or "").replace("(inh)", " ")) if w not in P.STOP and len(w) > 1]
    if not gold_text:
        return not o
    if not gold_head:
        return False
    return P.fold(gold_head)[:1] and P.fold(gold_head)[0] in set(P.fold(ours or "")) and all(w in g for w in o)


def treebank_sentences(folder):
    """(file, number in file, tree with marks) for every sentence, in file order."""
    for f in sorted(glob.glob(os.path.join(folder, "wsj_*.mrg"))):
        for k, s in enumerate(read_trees(f)):
            tree = P.parse_tree(re.sub(r"^\(\s*\(", "(ROOT (", s, count=1))
            root = tree[1][0] if label(tree) == "ROOT" and len(tree[1]) == 1 else tree
            yield os.path.basename(f), k + 1, root


def main():
    files = sorted(glob.glob(os.path.join(A.treebank, "wsj_*.mrg")))
    tot = collections.Counter()
    by_kind = collections.defaultdict(collections.Counter)
    shown, dump = 0, []
    n_sent = 0
    for f in files:
        for k, s in enumerate(read_trees(f)):
            if A.n and n_sent >= A.n:
                break
            n_sent += 1
            tree = P.parse_tree(re.sub(r"^\(\s*\(", "(ROOT (", s, count=1))
            root = tree[1][0] if label(tree) == "ROOT" and len(tree[1]) == 1 else tree
            gold = gold_lines(root)
            plain = strip_marks(root)
            if plain is None:
                continue
            try:
                ours = P.from_constituency("(ROOT " + to_str(plain) + ")", "en")
            except Exception as e:
                ours = []; tot["rule errors (crash)"] += 1
            key = [key_line(g) for g in gold]
            al = P.align(key, ours) if key else []
            exact_set = {(norm(o["subject"]), norm(o["verb"]), norm(o["object"])) for o in ours}
            tot["gold lines"] += len(key); tot["our lines"] += len(ours)
            tot["extra"] += len(ours) - len({a for a in al if a is not None})
            for g, kl, a in zip(gold, key, al):
                kinds = ["all"]
                if g["subject_understood"]:
                    kinds.append("subject understood (trace)")
                if g["object_kind"] == "predicative complement":
                    kinds.append("predicative complement")
                if g["recipient"]:
                    kinds.append("recipient or indirect object")
                if g["object_kind"] and g["object_kind"].startswith("clause"):
                    kinds.append("clause as object")
                if g["negated"]:
                    kinds.append("negated")
                if g["object_kind"] and g["object_kind"].startswith("prepositional complement"):
                    kinds.append("prepositional complement (CLR)")
                if not g["object"] and g["adjuncts"]:
                    kinds.append("no object, adjunct only")
                if g["passive"] or g["passive_doer"]:
                    kinds.append("passive")
                hit = a is not None
                ex = (norm(kl[0]), norm(kl[1]), norm(kl[2])) in exact_set
                hd = hit and bool(head_ok(g["subject"], g["subject_head"], ours[a]["subject"])) and bool(head_ok(g["object"], g["object_head"], ours[a]["object"]))
                sv = any(P.verb_match(kl[1], o["verb"]) and set(P.fold(kl[0])) & set(P.fold(o["subject"])) for o in ours) if kl[0] != "(unstated)" else None
                rec = None
                if g["recipient"] and hit:
                    o = ours[a]
                    rec = bool(set(P.fold(g["recipient"])) - P.STOP & set(P.fold((o.get("object") or "") + " " + (o.get("recipient") or ""))))
                for kd in kinds:
                    c = by_kind[kd]
                    c["n"] += 1; c["found"] += hit; c["exact"] += ex; c["head"] += hd
                    if sv is not None:
                        c["sv_n"] += 1; c["sv"] += bool(sv)
                    if rec is not None:
                        c["rec_n"] += 1; c["rec"] += rec
            if A.json:
                dump.append({"file": os.path.basename(f), "k": k + 1, "text": txt(root), "gold": gold,
                             "ours": [{x: o.get(x) for x in ("subject", "verb", "object", "kind")} for o in ours]})
            if shown < A.show:
                shown += 1
                print(f"== {os.path.basename(f)} #{k + 1}: {txt(root)}")
                for g, a in zip(gold, al):
                    extra = "; ".join(x for x in [
                        f"subject understood {g['subject_understood']}" if g["subject_understood"] else "",
                        f"recipient: {g['recipient']}" if g["recipient"] else "",
                        f"object is a {g['object_kind']}" if g["object_kind"] else "",
                        f"time: {', '.join(g['time'])}" if g["time"] else "",
                        "PASSIVE" if g["passive"] else "", f"passive doer: {g['passive_doer']}" if g["passive_doer"] else "",
                        "NEGATED" if g["negated"] else ""] if x)
                    o = ours[a] if a is not None else None
                    print(f"   gold: {g['subject'] or '(unstated)'} | {g['verb']} | {g['object'] or '-'}" + (f"   [{extra}]" if extra else ""))
                    print(f"   ours: " + (f"{o['subject']} | {o['verb']} | {o['object']}" if o else "NOT FOUND"))
                used = {a for a in al if a is not None}
                for j, o in enumerate(ours):
                    if j not in used:
                        print(f"   extra (ours, not in gold): {o['subject']} | {o['verb']} | {o['object']}")
        if A.n and n_sent >= A.n:
            break

    print(f"\nPenn Treebank sample: {n_sent} sentences, {len(files)} files. Our English tree rules on the gold trees (marks removed).")
    print(f"gold lines {tot['gold lines']}, our lines {tot['our lines']}, our lines not in gold {tot['extra']}" +
          (f", rule crashes {tot['rule errors (crash)']}" if tot['rule errors (crash)'] else ""))
    print(f"{'kind of gold line':34s} {'lines':>6s} {'found (loose)':>14s} {'heads':>7s} {'exact':>8s} {'subj+verb right':>16s} {'recipient kept':>15s}")
    for kd in ("all", "subject understood (trace)", "predicative complement", "recipient or indirect object", "clause as object",
               "prepositional complement (CLR)", "no object, adjunct only", "negated", "passive"):
        c = by_kind[kd]
        if not c["n"]:
            continue
        pc = lambda a, b: f"{100 * a / b:5.1f}%" if b else "   - "
        print(f"{kd:34s} {c['n']:6d} {c['found']:6d} {pc(c['found'], c['n'])} {pc(c['head'], c['n'])} {pc(c['exact'], c['n']):>8s} "
              f"{pc(c['sv'], c['sv_n']):>16s} {pc(c['rec'], c['rec_n']):>15s}")
    if A.json:
        json.dump(dump, open(A.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

