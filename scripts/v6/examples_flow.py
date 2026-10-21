"""Flow sheets for examples_xlsx.py: one sentence read top to bottom through every step, in plain words, with the
real output of each step. Everything below is computed from the saved parses; only the 'What this example shows'
notes for the featured sentences are written text, and each was checked against the parses."""
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

FONT = "Calibri"
STEP_FILL = PatternFill("solid", fgColor="404040")
STEP_FONT = Font(name=FONT, bold=True, size=10, color="FFFFFF")
WHAT_FONT = Font(name=FONT, italic=True, size=9, color="404040")
OUT_FONT = Font(name=FONT, size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=13)
ARROW_FONT = Font(name=FONT, size=12, color="7F7F7F")
NOTE_FILL = PatternFill("solid", fgColor="E7E7E7")
LINE = Border(bottom=Side(style="thin", color="BFBFBF"))

PLAIN = {"nsubj": "subject", "nsubj:pass": "subject (passive)", "nsubjpass": "subject (passive)", "csubj": "clause as subject",
         "obj": "object", "dobj": "object", "iobj": "indirect object", "dative": "indirect object (spaCy: dative)",
         "iobj:agent": "person made to act (causative)", "ccomp": "clause as object", "xcomp": "to-clause / open clause",
         "obl": "phrase with a preposition", "obl:arg": "phrase with a preposition (required)", "obl:mod": "phrase with a preposition (optional)",
         "obl:agent": "by / par doer", "agent": "by doer", "prep": "phrase with a preposition", "advcl": "adverbial clause",
         "conj": "joined verb", "appos": "apposition", "acl:relcl": "relative clause", "relcl": "relative clause", "acl": "clause on a noun",
         "attr": "description after 'be'", "acomp": "adjective after the verb", "npadvmod": "noun phrase used as time / measure",
         "obl:unmarked": "noun phrase used as time / measure", "aux": "helper verb", "advcl:relcl": "relative-type clause"}
SHOW = set(PLAIN) - {"aux"}
STEPS = [
    ("1  SOURCE", "Where the sentence comes from."),
    ("2  SENTENCE", "The stored sentence that every parser receives."),
    ("3a  spaCy", "spaCy's dependency parse: for each verb, who does what (from its labels)."),
    ("3b  Stanza", "Stanza's dependency parse, read the same way."),
    ("3c  TREE", "The constituency parse: the sentence as nested phrases."),
    ("3d  DISCOURSE", "The discourse parse, made with the others but used only at step 6, and only when the vote keeps 2+ lines or a speech word appears."),
    ("4  RULES", "The rules read subject | verb | object lines from each parse separately."),
    ("5  VOTE", "Lines that two or three parsers share are kept; one-parser lines are dropped for review."),
    ("6  DISCOURSE CHECK", "Whether the discourse parse changed the status of any kept line."),
    ("7  OUTPUT", "One triple per clause, with the parts the DBpedia step will need. This step can rework a kept line: majority wording, recipient moved out of the object, 'that is why' folded into a tie."),
    ("8  TREE FIRST", "The proposed design on the same sentence: every line the tree gave and what the two dependency parses did to it, then the output triples it gives."),
]


def who_does_what(toks):
    out = []
    for t in toks:
        if t[3] not in ("VERB", "AUX") and t[4] != "root":     # verbs only: who does what to whom
            continue
        kids = [k for k in toks if k[5] == t[0] and k[4] in SHOW]
        if not kids:
            continue
        parts = []
        for k in kids:
            span = k[1]
            parts.append(f"{PLAIN.get(k[4], k[4])} = {span}   [{k[4]}]")
        out.append(f"{t[1]}:  " + ";   ".join(parts))
    return "\n".join(out) or "(no verb with labelled parts)"


def tree_text(t, P):
    n = P.parse_tree(t) if isinstance(t, str) else P._tuples(t)
    def s(x):
        return x if isinstance(x, str) else "(" + x[0] + " " + " ".join(s(k) for k in x[1]) + ")"
    return s(n)


def line_text(x, kind_map):
    o = x.get("object") or "(no object)"
    k = kind_map.get(x.get("kind"), x.get("kind"))
    extra = (", negated" if x.get("negated") else "") + (", hedged" if x.get("hedged") else "")
    return f"{x.get('subject')}  |  {x.get('verb')}  |  {o}     ({k}{extra})"


def block(ws, r, row, why, note, F, S, P, C, kind_map, gold=None, gh=None, link=None):
    """Write one sentence's flow starting at sheet row r. Returns the next free row."""
    c = ws.cell(row=r, column=1, value=f"{row['n']}   {why}")
    c.font = TITLE_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    r += 1
    if note:
        c = ws.cell(row=r, column=1, value="What this example shows:  " + note)
        c.font = Font(name=FONT, size=10, bold=True); c.fill = NOTE_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        ws.row_dimensions[r].height = 15 * max(2, len(note) // 150 + 1)
        r += 1
    res = S.analyze(P, C, row, "native", "prod", "multi")
    fr = F.full_row(row)
    sid = row.get("sentence_id") or ""
    if row.get("set") == "wsj":
        src = f"Penn Treebank sample, file {row['file']}, sentence {row['k']} (Wall Street Journal, hand-annotated)"
    elif sid:
        leg, bill, date, page, sn = (sid.split("|") + ["", "", "", "", ""])[:5]
        name = {"US": "US House of Representatives", "ON": "Legislative Assembly of Ontario", "QC": "Quebec National Assembly"}.get(leg, leg)
        jur = {"US": "us", "ON": "ontario", "QC": "quebec"}.get(leg, "")
        src = f"{name}, {date}, {bill}, page {page[1:]}, sentence {sn[1:]}\nID {sid}\nFile data/dbpedia_pipeline/{jur}/sentences_v3.json"
    else:
        src = "A written test pair (scripts/v6/parallel_tests.py): one construction, in English and French. Not from the record."
    spa = who_does_what(row["deps_spacy"])
    sta = "\n".join(who_does_what(s_) for s_ in row["deps_stanza"])
    trees = "\n".join(tree_text(t, P) for t in row.get("trees", [])) or "(none)"
    d = row.get("disc_native")
    if d and d.get("edus"):
        disc = "\n".join(f"unit {k}: {e.get('text') or row['text'][e['start']:e['end']]}" for k, e in enumerate(d["edus"]))
        disc += "\n" + "\n".join(f"units {x['left'][0]}-{x['left'][1]} and {x['right'][0]}-{x['right'][1]}: {x['relation']} "
                                 f"(shared label: {F.DISC_SHARED.get(x['relation'], x['relation'])})" for x in d.get("relations", []))
    else:
        disc = "Not run for this sentence: it only runs when the vote keeps 2 or more lines or a speech word appears."
    rules = "\n".join(f"{name}:\n" + ("\n".join("    " + line_text(x, kind_map) for x in res[src_]) or "    (no lines)")
                      for src_, name in (("spacy", "from spaCy"), ("stanza", "from Stanza"), ("const", "from the tree")))
    kept = "\n".join(f"KEPT     {line_text(x, kind_map)}     found by: {', '.join(x.get('found_by') or [])}" for x in res["vote"])
    drop = "\n".join(f"DROPPED  {line_text(x, kind_map)}     only: {', '.join(x.get('found_by') or [])}" for x in res["review"])
    vote = (kept + ("\n" + drop if drop else "\n(nothing dropped)")).strip()
    ch = [f"{line_text(a, kind_map)}:  {kind_map.get(a.get('kind_parser'), a.get('kind_parser'))} -> {kind_map.get(b.get('kind_rst'), b.get('kind_rst'))}"
          for a, b in zip(res["vote"], res["final"]) if a.get("kind_parser") and b.get("kind_rst") and a.get("kind_parser") != b.get("kind_rst")]
    dchk = ("Changed:\n" + "\n".join(ch)) if ch else ("No line changed." if d and d.get("edus") else "Not run, so nothing changed.")
    def fmt(fr):
      outs = []
      for i, L in enumerate(fr["lines"], 1):
          rc = L["record"]
          obj = rc["object"] or (f"(not stated; refers back to: {rc['object_inferred']}, inferred)" if rc["object_inferred"] else "(none)")
          bits = [f"{i}.  {rc['subject']}  |  {rc['predicate']}  |  {obj}"]
          if rc["recipient"]:
              bits.append(f"to whom: {rc['recipient']} ({L.get('recipient_function', '')})" + (f"; not to: {rc['recipient_not']}" if rc.get("recipient_not") else ""))
          if rc["when"]:
              bits.append(f"when: {rc['when']}" + (" (inherited from the start of the sentence)" if rc.get("when_inherited") else ""))
          bits.append(f"{rc['polarity']}, {rc['status'].replace('asserted', 'stated')}; found by {rc['parsers_agreeing']} of 3 parsers")
          if L["links"]:
              bits.append("tied to " + "; ".join(f"line {l['to'] + 1} as {l['relation']}" + (f" ('{l['word']}')" if l["word"] else "") for l in L["links"]))
          if L["needs_referent"]:
              bits.append("needs a referent before DBpedia: " + "; ".join(f"{x['words']}" for x in L["needs_referent"]))
          outs.append("\n      ".join(bits))
      output = "\n".join(outs) or "(no output)"
      if fr.get("dropped"):
          output += "\n(folded into a tie, not a line of its own: " + ", ".join(fr["dropped"]) + ")"
      return output
    output = fmt(fr)
    tf = F.tree_backbone(C.run(row, P), plus=True)
    tf_lines = "\n".join(f"{line_text(x, kind_map)}     " + ("; ".join(x.get("notes") or []) or "kept as the tree has it; a dependency parse agrees") for x in tf) or "(the tree gave no lines)"
    tree_first = "What the dependency parses did to each tree line:\n" + tf_lines + "\n\nOutput triples, tree-first design:\n" + fmt(F.full_row(row, method="tree_plus"))
    contents = [src, row["text"], spa, sta, trees, disc, rules, vote, dchk, output, tree_first]
    if gold is not None:
        contents.append("\n".join(f"{g['subject'] or '(unstated)'}  |  {g['verb']}  |  {g['object'] or '(none)'}" + (f"     to whom: {g['recipient']}" if g["recipient"] else "") for g in gold))
    steps = STEPS + ([("9  GOLD", "The Penn Treebank annotators' answer for the same sentence, to compare with steps 7 and 8.")] if gold is not None else [])
    for (label, what), content in zip(steps, contents):
        a = ws.cell(row=r, column=1, value=label); a.font = STEP_FONT; a.fill = STEP_FILL; a.alignment = Alignment(vertical="top")
        b = ws.cell(row=r, column=2, value=what); b.font = WHAT_FONT; b.alignment = Alignment(wrap_text=True, vertical="top")
        cc = ws.cell(row=r, column=3, value=content); cc.font = Font(name="Calibri" if label.startswith(("3", "4", "5")) else FONT, size=9 if label.startswith("3") else 10)
        cc.alignment = Alignment(wrap_text=True, vertical="top"); cc.data_type = "s"
        lines = sum(max(1, -(-len(x) // 150)) for x in str(content).split("\n"))
        ws.row_dimensions[r].height = min(409, max(16, 12.5 * lines + 4))
        for j in (1, 2, 3):
            ws.cell(row=r, column=j).border = LINE
        if gh and link and label.startswith(("1 ", "3a", "3b", "3c", "3d", "4 ", "5 ", "7 ", "8 ")):
            # step 1 links the sentence file; parse steps link the saved parses; rules, vote and output link their code
            pf = "outputs/wsj/wsj_parses.json" if row.get("set") == "wsj" else "data/parity_oct19/parity_parses.json"
            target = {"1 ": src, "3a": pf, "3b": pf, "3c": pf, "3d": pf,
                      "4 ": "scripts/v6/preds.py", "5 ": "scripts/v6/combine_lib.py", "7 ": "scripts/v6/full.py", "8 ": "scripts/v6/full.py"}[label[:2]]
            u = gh(target)
            if u:
                bcell = ws.cell(row=r, column=2)
                bcell.value = (bcell.value or "") + "\n(open on GitHub)"
                link(bcell, u)
        r += 1
        if label != steps[-1][0]:
            ar = ws.cell(row=r, column=1, value="↓"); ar.font = ARROW_FONT; ar.alignment = Alignment(horizontal="center")
            ws.row_dimensions[r].height = 14
            r += 1
    return r + 2


def setup(ws):
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 125
    ws.sheet_view.showGridLines = False


OVERVIEW = [
    ("Debate record", "US House, Ontario, Quebec: the official record of what was said", "scripts/v3/build_sentences_v3.py"),
    ("Sentences", "each paragraph split into sentences, each with an ID", "data/dbpedia_pipeline/*/sentences_v3.json"),
    ("Parse each sentence", "the constituency tree, which is the backbone; spaCy and Stanza dependency parses, which check it; a discourse parse, for status and the ties between clauses", "scripts/v6/parity_collect.py -> data/parity_oct19/parity_parses.json"),
    ("Read the lines", "rules read subject | verb | object lines, with stated / reported / embedded, from the tree, and the same from each dependency parse so they can be compared with it", "scripts/v6/preds.py, const_fr.py, lexicon.py"),
    ("Combine, tree first (proposed)", "start from the tree's lines; where spaCy and Stanza agree on a different subject or object, theirs replaces the tree's; lines both of them found and the tree missed are added", "scripts/v6/full.py tree_backbone()"),
    ("Discourse check", "can relabel a line as reported or embedded, and names the relation on ties; not yet used to find errors", "scripts/v6/combine_lib.py rst_kind()"),
    ("Output: one triple per clause", "subject | predicate | object, plus to whom, when, polarity, status, ties, slots needing a referent", "scripts/v6/full.py record()"),
    ("Next (not built)", "the discourse parse used to find errors in the tree; then DBpedia: each slot linked to an entity, pronouns and roles resolved first", ""),
]
FIRST_DESIGN = ("The first design, kept for comparison", "2-of-3 vote: keep the lines two or three parsers share (scripts/v6/combine_lib.py vote()). The Flow sheets show it at steps 5 to 7 and the tree-first design at step 8.")


def overview(ws, gh=None, link=None, scores=None):
    setup(ws)
    ws.column_dimensions["B"].width = 70
    ws.column_dimensions["C"].width = 60
    t = ws.cell(row=1, column=1, value="The pipeline, top to bottom")
    t.font = Font(name=FONT, bold=True, size=15)
    ws.cell(row=2, column=1, value="Each box is a step; the right column is the file or code that does it. The Flow sheets follow one real sentence through every box.").font = WHAT_FONT
    r = 4
    for k, (box, what, code) in enumerate(OVERVIEW):
        a = ws.cell(row=r, column=1, value=box); a.font = STEP_FONT; a.fill = STEP_FILL; a.alignment = Alignment(wrap_text=True, vertical="center")
        b = ws.cell(row=r, column=2, value=what); b.font = OUT_FONT; b.alignment = Alignment(wrap_text=True, vertical="center")
        c = ws.cell(row=r, column=3, value=code); c.font = Font(name="Calibri", size=9); c.alignment = Alignment(wrap_text=True, vertical="center")
        if gh and link:
            link(c, gh(code))
        ws.row_dimensions[r].height = 32
        r += 1
        if k < len(OVERVIEW) - 1:
            ar = ws.cell(row=r, column=1, value="↓"); ar.font = ARROW_FONT; ar.alignment = Alignment(horizontal="center")
            r += 1
    r += 1
    a = ws.cell(row=r, column=1, value=FIRST_DESIGN[0]); a.font = Font(name=FONT, bold=True, size=10); a.alignment = Alignment(wrap_text=True, vertical="center")
    b = ws.cell(row=r, column=2, value=FIRST_DESIGN[1]); b.font = OUT_FONT; b.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[r].height = 32
    r += 2
    if scores:                       # the two designs on the Penn Treebank, read from the score file this workbook ships with
        ws.cell(row=r, column=1, value="Both designs on the Penn Treebank").font = Font(name=FONT, bold=True, size=11)
        n = scores.get("vote", {}).get("all", {}).get("n", 0)
        ws.cell(row=r, column=2, value=f"{n:,} gold lines from the annotators' marks. Found: the loose match. Exact: subject, verb and object word for word. From outputs/wsj/wsj_score.txt.").font = WHAT_FONT
        r += 1
        for j, h in enumerate(("Design", "Found", "Exact"), 1):
            c = ws.cell(row=r, column=j, value=h); c.font = STEP_FONT; c.fill = STEP_FILL
        r += 1
        for m, name in (("tree_plus", "Tree first, deps correct and add (proposed)"), ("tree_fixed", "Tree first, deps correct only"), ("vote", "2-of-3 vote (first design)")):
            c = scores.get(m, {}).get("all", {})
            if not c.get("n"):
                continue
            ws.cell(row=r, column=1, value=name).font = OUT_FONT
            ws.cell(row=r, column=2, value=f"{100 * c['found'] / c['n']:.1f}%").font = OUT_FONT
            ws.cell(row=r, column=3, value=f"{100 * c['exact'] / c['n']:.1f}%").font = OUT_FONT
            for j in (1, 2, 3):
                ws.cell(row=r, column=j).border = LINE
            r += 1
    ws.cell(row=r, column=1, value="On the debate keys the two designs are close; those keys were drafted with AI assistance (Scores sheet: compare3.txt).").font = Font(name=FONT, size=10, italic=True)
