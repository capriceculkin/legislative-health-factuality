"""wsj_check.py  The first sentences of the Penn Treebank (WSJ file wsj_0001, wsj_0003) through the extraction rules.
Constituency rules run on the treebank's own gold trees (function tags like -SBJ removed), so a wrong line there is a
rule error, not a parser error. Dependency rules run on a UDPipe 1.4 (UD 2.5 EWT) parse of the same words.
The gold trees are typed out from the treebank's first file and should be checked against the LDC copy."""
import sys, re, subprocess, json
sys.path.insert(0, sys.argv[1])
import preds as P
GOLD = {
 "wsj_0001.1": "(ROOT (S (NP-SBJ (NP (NNP Pierre) (NNP Vinken)) (, ,) (ADJP (NP (CD 61) (NNS years)) (JJ old)) (, ,)) (VP (MD will) (VP (VB join) (NP (DT the) (NN board)) (PP-CLR (IN as) (NP (DT a) (JJ nonexecutive) (NN director))) (NP-TMP (NNP Nov.) (CD 29)))) (. .)))",
 "wsj_0001.2": "(ROOT (S (NP-SBJ (NNP Mr.) (NNP Vinken)) (VP (VBZ is) (NP-PRD (NP (NN chairman)) (PP (IN of) (NP (NP (NNP Elsevier) (NNP N.V.)) (, ,) (NP (DT the) (NNP Dutch) (VBG publishing) (NN group)))))) (. .)))",
}
TEXT = {
 "wsj_0001.1": "Pierre Vinken , 61 years old , will join the board as a nonexecutive director Nov. 29 .",
 "wsj_0001.2": "Mr. Vinken is chairman of Elsevier N.V. , the Dutch publishing group .",
 "wsj_0003.1": "A form of asbestos once used to make Kent cigarette filters has caused a high percentage of cancer deaths among a group of workers exposed to it more than 30 years ago , researchers reported .",
}
UD = "/home/claude/jwijffels/ufal-udpipe/src/udpipe"
M = "/home/claude/jwijffels/udpipe.models.ud.2.5/inst/udpipe-ud-2.5-191206/english-ewt-ud-2.5-191206.udpipe"
ids = list(TEXT)
p = subprocess.run([UD, "--input=horizontal", "--tag", "--parse", M], input="\n".join(TEXT[i] for i in ids) + "\n", capture_output=True, text=True)
blocks = [b for b in p.stdout.strip().split("\n\n") if b.strip()]
show = lambda ps: [(x["subject"], x["verb"], x["object"], x.get("kind","asserted")) for x in ps]
for i, b in zip(ids, blocks):
    toks = []
    for line in b.splitlines():
        if line.startswith("#"): continue
        f = line.split("\t")
        if "-" in f[0] or "." in f[0]: continue
        toks.append([int(f[0]) - 1, f[1], f[2], f[3], f[7], (int(f[6]) - 1) if f[6] != "0" else None, f[5] if f[5] != "_" else ""])
    print("==", i, TEXT[i])
    print("   UDPipe arcs:", [(t[1], t[4], toks[t[5]][1] if t[5] is not None else "ROOT") for t in toks])
    T = [P.T(*x) for x in toks]; P.link_kids(T)
    print("   dependency rules:", show(P.from_dependencies(T)), " appositions:", show(P.appositions(T)))
    if i in GOLD:
        g = re.sub(r"\(([A-Z]+)-[A-Z-]+", r"(\1", GOLD[i])
        print("   constituency rules on GOLD tree:", show(P.from_constituency(g, "en")))
