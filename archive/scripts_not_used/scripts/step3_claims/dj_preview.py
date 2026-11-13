import sys, subprocess
sys.path.insert(0, sys.argv[1]); import preds as P
UD = "/home/claude/jwijffels/ufal-udpipe/src/udpipe"; B = "/home/claude/jwijffels/udpipe.models.ud.2.5/inst/udpipe-ud-2.5-191206/"
S = {"en": ["Dick and Jane go to the moon , their dog goes to Mars .", "Dick and Jane go to the moon , their house is on Mars .",
            "Dick and Jane go to the moon and then go to Mars .", "Dick and Jane go to the moon , then they go to Mars ."],
     "fr": ["Dick et Jane vont sur la Lune , leur chien va sur Mars .", "Dick et Jane vont sur la Lune , leur maison est sur Mars .",
            "Dick et Jane vont sur la Lune et vont ensuite sur Mars .", "Dick et Jane vont sur la Lune , puis ils vont sur Mars ."]}
M = {"en": B + "english-ewt-ud-2.5-191206.udpipe", "fr": B + "french-gsd-ud-2.5-191206.udpipe"}
for L in S:
    out = subprocess.run([UD, "--input=horizontal", "--tag", "--parse", M[L]], input="\n".join(S[L]) + "\n", capture_output=True, text=True).stdout
    for s, b in zip(S[L], [b for b in out.strip().split("\n\n") if b.strip()]):
        tk = []
        for line in b.splitlines():
            if line.startswith("#"): continue
            f = line.split("\t")
            if "-" in f[0] or "." in f[0]: continue
            tk.append([int(f[0]) - 1, f[1], f[2], f[3], f[7], (int(f[6]) - 1) if f[6] != "0" else None, f[5] if f[5] != "_" else ""])
        T = [P.T(*x) for x in tk]; P.link_kids(T)
        print(L, "|", s, "|", [(p["subject"], p["verb"], p["object"], p["kind"]) for p in P.from_dependencies(T)])
