"""udpipe_parse.py PARSES.json OUT.json   UDPipe 1.4 (UD 2.5 models: English EWT, French GSD) on the backbone's own words
(Stanza), one sentence per line, so both parses have the same tokens and can be compared word by word."""
import json, subprocess, sys, tempfile, os
UD = "/home/claude/jwijffels/ufal-udpipe/src/udpipe"
M = {"en": "/home/claude/jwijffels/udpipe.models.ud.2.5/inst/udpipe-ud-2.5-191206/english-ewt-ud-2.5-191206.udpipe",
     "fr": "/home/claude/jwijffels/udpipe.models.ud.2.5/inst/udpipe-ud-2.5-191206/french-gsd-ud-2.5-191206.udpipe"}
rows = json.load(open(sys.argv[1], encoding="utf-8"))["rows"]
out = {}
for L in ("en", "fr"):
    sents = [(r["n"], si, [w[1] for w in s]) for r in rows if r["lang"] == L for si, s in enumerate(r["deps_stanza"])]
    txt = "\n".join(" ".join(w.replace(" ", "_") for w in ws) for _, _, ws in sents) + "\n"
    p = subprocess.run([UD, "--input=horizontal", "--tag", "--parse", M[L]], input=txt, capture_output=True, text=True)
    if p.returncode:
        sys.exit(p.stderr)
    blocks = [b for b in p.stdout.strip().split("\n\n") if b.strip()]
    assert len(blocks) == len(sents), (L, len(blocks), len(sents))
    for (n, si, ws), b in zip(sents, blocks):
        toks = []
        for line in b.splitlines():
            if line.startswith("#"):
                continue
            f = line.split("\t")
            if "-" in f[0] or "." in f[0]:
                continue
            toks.append([int(f[0]) - 1, f[1], f[2], f[3], f[7], (int(f[6]) - 1) if f[6] != "0" else None, f[5] if f[5] != "_" else ""])
        assert [t[1] for t in toks] == [w.replace(" ", "_") for w in ws], (n, [t[1] for t in toks][:8], ws[:8])
        out.setdefault(n, []).append(toks)
json.dump({"parser": "UDPipe 1.4.1, models udpipe-ud-2.5-191206 (english-ewt, french-gsd), input = Stanza words", "rows": out},
          open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
print(len(out), "sentences parsed")
