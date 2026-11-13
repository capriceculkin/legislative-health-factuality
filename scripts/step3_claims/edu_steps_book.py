"""Builds the step-by-step examples book: every step for each example sentence, from the raw sentence to the readers' verdicts.
python3 book.py TRACE.json LOO.json PARSES.json READINGS.csv FIGDIR OUT.html"""
import sys, json, csv, html, re, base64, collections
T = json.load(open(sys.argv[1]))
L = json.load(open(sys.argv[2]))
P = {r["n"]: r for r in json.load(open(sys.argv[3]))["rows"]}
RD = collections.defaultdict(dict)
for r in csv.DictReader(open(sys.argv[4], encoding="utf-8")):
    RD[r["sentence"]][int(r["claim"])] = r
FIG, OUT = sys.argv[5], sys.argv[6]
e = lambda x: html.escape(str(x if x is not None else ""))
LEG = {"US": "US House", "ON": "Ontario", "QC": "Quebec"}

DESC = {
 "collapse": "merge a verb phrase that holds only another verb phrase", "drop_address": "“Mr. Speaker,” is not the subject",
 "unwrap_coord": "French: a clause inside COORD is read as a clause", "participles": "French: participle phrases on a noun",
 "fix_verb": "the verb as written, with its auxiliaries and negation", "relpron": "who / which / qui = the noun before it, found through the discourse relation",
 "demonstrative": "“that” pointing back to whole units, through the discourse relation", "tree_subject": "a missing subject found in the unit’s own tree",
 "discourse_subject": "a missing subject taken from the unit the discourse relation points to", "verb_join": "“refused to act” is one verb",
 "control_list": "“X to do” takes X as subject only after verbs like urge, require", "apposition": "“Jean Martin, the health minister,”: the name is the subject",
 "apposition_across": "an apposition split over two units", "questions": "a unit that is a question is not a claim",
 "neg_particles": "French: ne … plus / pas is part of the verb; ne … que is not negation", "adverbial_object": "a time clause (“before the report came out”) is not the object",
 "said_object": "“the HMO said,” | “You need another opinion”: the object is what the next unit says", "reanchor": "unit positions checked against the sentence",
 "frame_context": "a unit with no clause (“L’an dernier,”) is kept as context", "time_subject": "“Last year the House passed”: a time is not the subject",
 "bare_lines": "a unit with a verb the tree rules gave no line for gets one", "better_object": "an adverb is not the object; “mess that up” = mess up",
 "object_fill": "(not used in the units-only design)", "backfill": "(not used in the units-only design)",
 "r6_stranded": "round 6: a lone preposition belongs to the verb (“heard from”)", "r6_experiencer": "round 6: “it seems to me”: “to me” is not the object",
 "r6_aux_carry": "round 6: a second verb keeps the first one’s “cannot”", "r6_object_after": "round 6: the object can come after a comma or in a later unit",
 "r6_procedural": "round 6: “a motion to recommit” is the name of a motion, not a claim", "r6_split_verb": "round 6: “getting it done”: the pronoun inside the verb is the object",
 "r6b_adjunct": "round 6b: “said very well”, “la semaine dernière”: how or when, not the object", "r6b_vocative": "round 6b: the person spoken to is not the subject",
 "r6b_copula": "round 6b: what follows “is” / “est” is its complement", "r6b_make_sure": "round 6b: “make sure that …”: the that-clause is the object",
 "r6b_passive_part": "round 6b: “a group called X”: a participle on a noun is passive", "r7_subject_pron": "round 7: a verb right after a pronoun takes it as subject",
 "r7_expletive_inf": "round 7: “it is important to give”: “it” does not do the giving", "r7_list_not_appos": "round 7: a list of names is not an apposition",
 "r7_bare_aux": "round 7: a false start (“il | est |”) is not a claim"}
GROUP = lambda f: "round 7" if f.startswith("r7") else "round 6b" if f.startswith("r6b") else "round 6" if f.startswith("r6") else "rounds 1 to 5"

def fig(n):
    p = f"{FIG}/{n.replace('|', '_')}.png"
    try:
        return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
    except OSError:
        return ""

def claims_table(lines, extra=False):
    h = "<table class='c'><tr><th>unit</th><th>subject</th><th>verb</th><th>object</th>" + ("<th>how it was read</th><th>subject from</th>" if extra else "") + "</tr>"
    for l in lines:
        h += f"<tr><td>{e(l.get('unit'))}</td><td>{e(l['subject'])}</td><td>{e(l['verb'])}</td><td>{e(l['object'])}</td>"
        if extra:
            h += f"<td class='s'>{e(l.get('how'))}</td><td class='s'>{e(l.get('subject_from'))}</td>"
        h += "</tr>"
    return h + "</table>"

key = lambda l: (l.get("unit"), l["subject"], l["verb"], l["object"])

def diff(a, b):
    A, B = [key(x) for x in a], [key(x) for x in b]
    gone = [x for x in A if x not in B]; new = [x for x in B if x not in A]
    if not gone and not new:
        return "<p class='nc'>No change.</p>"
    h = "<table class='c'><tr><th></th><th>unit</th><th>subject</th><th>verb</th><th>object</th></tr>"
    for x in gone:
        h += "<tr class='gone'><td>before</td>" + "".join(f"<td>{e(v)}</td>" for v in x) + "</tr>"
    for x in new:
        h += "<tr class='new'><td>after</td>" + "".join(f"<td>{e(v)}</td>" for v in x) + "</tr>"
    return h + "</table>"

parts = []
order = [n for n in T["res"]]
order.sort(key=lambda n: (["US", "ON", "QC"].index(n.split("|")[1]), int(n.split("|")[2])))
for k, n in enumerate(order, 1):
    R = T["res"][n]; row = P[n]; st = R["stages"]; fin = st[-1]["out"]
    sid = row.get("sentence_id", "")
    m = re.match(r"(\w+)\|([^|]+)\|([\d-]+)\|p(\d+)\|s(\d+)", sid)
    src = f"bill {m.group(2)}, {m.group(3)}, paragraph {m.group(4)}, sentence {m.group(5)}" if m else sid
    h = [f"<section><h2>Example {k}: {e(LEG[n.split('|')[1]])}</h2>"]
    h.append(f"<p class='sent'>{e(row['text'])}</p><p>Sentence ID: {e(sid)} ({e(src)}).</p>")
    # step 1
    d = row.get("disc_native") or {}
    h.append("<h3>Step 1. Discourse parse</h3><p>Units and relations from isanlp RST (" + e(d.get("inventory")) + "). Character positions are counted from the start of the sentence.</p>")
    h.append("<table class='c'><tr><th>unit</th><th>characters</th><th>text</th></tr>" + "".join(
        f"<tr><td>{u['unit']}</td><td>{u['start']} to {u['end']}</td><td>{e(u['text'])}</td></tr>" for u in fin["units"]) + "</table>")
    if fin["relations"]:
        h.append("<table class='c'><tr><th>left</th><th>right</th><th>parser label</th><th>our label</th><th>main part</th><th>how to read it</th></tr>" + "".join(
            f"<tr><td>{'–'.join(map(str, sorted(set(r['left']))))}</td><td>{'–'.join(map(str, sorted(set(r['right']))))}</td><td>{e(r['relation'])}</td><td>{e(r['shared'])}</td><td>{e('both' if not r.get('main') else '–'.join(map(str, sorted(set(r['main'])))))}</td><td class='s'>{e(r['reads'])}</td></tr>"
            for r in fin["relations"]) + "</table>")
    else:
        h.append("<p class='nc'>One unit, no relations.</p>")
    # step 2
    h.append("<h3>Step 2. Constituency tree for each unit</h3><p>Each unit was parsed on its own with " + ("Stanza (Penn Treebank labels)." if row["lang"] == "en" else "benepar_fr2 (French Treebank labels).") + "</p>")
    for u in fin["units"]:
        h.append(f"<p class='tree'><b>unit {u['unit']}</b> {e(' '.join(u['tree']))}</p>")
    # step 3
    h.append("<h3>Step 3. Claims from each unit's tree, before any repair rules</h3>")
    h.append(claims_table(st[0]["out"]["lines"]))
    # steps 4 and 5 by round
    h.append("<h3>Steps 4 and 5. Links across units and repair rules</h3><p>Changes after each round of rules was turned on. Rounds 1 to 5 include the rules that use the discourse relations.</p>")
    for i in range(1, len(st)):
        h.append(f"<p class='stage'>{e(st[i]['name'])}</p>" + diff(st[i - 1]["out"]["lines"], st[i]["out"]["lines"]))
    # rules that matter
    off = L["loo"][n]["off"]
    h.append("<h3>Rules that change this sentence</h3><p>Each rule turned off by itself, with all other rules on.</p>")
    if off:
        full = [tuple(x) for x in L["loo"][n]["full"]]
        h.append("<table class='c'><tr><th>rule</th><th>round</th><th>what it does</th><th>claims without it (changed lines only)</th></tr>")
        for f, o in off.items():
            o = [tuple(x) for x in o]
            ch = [x for x in o if x not in full]
            miss = [x for x in full if x not in o]
            txt = "; ".join(" | ".join(map(str, x[1:])) for x in ch) or "(none)"
            if miss:
                txt += "<br><span class='s'>instead of: " + e("; ".join(" | ".join(map(str, x[1:])) for x in miss)) + "</span>"
            h.append(f"<tr><td>{e(f)}</td><td>{GROUP(f)}</td><td class='s'>{e(DESC.get(f, ''))}</td><td>{txt if txt.startswith('(') else e(txt.split('<br>')[0]) + (('<br>' + txt.split('<br>', 1)[1]) if '<br>' in txt else '')}</td></tr>")
        h.append("</table>")
    else:
        h.append("<p class='nc'>No single rule changes this sentence.</p>")
    # final
    h.append("<h3>Final claims</h3>" + claims_table(fin["lines"], extra=True))
    # readers
    rd = RD.get(n, {})
    h.append("<h3>Check: two independent AI readings</h3><table class='c'><tr><th>#</th><th>claim</th><th>reader A</th><th>reader B</th><th>result</th></tr>")
    for i, l in enumerate(fin["lines"], 1):
        r = rd.get(i, {})
        cl = " | ".join([l["subject"], l["verb"], l["object"]])
        if r and (r["subject"], r["verb"], r["object"]) != (l["subject"], l["verb"], l["object"]):
            cl += " (does not match the readings file)"
        ra = e(r.get("reading_A", "")) + (f"<br><span class='s'>{e(r['reason_A'])}</span>" if r.get("reason_A") else "")
        rb = e(r.get("reading_B", "")) + (f"<br><span class='s'>{e(r['reason_B'])}</span>" if r.get("reason_B") else "")
        res = r.get("both", "")
        h.append(f"<tr><td>{i}</td><td>{e(cl)}</td><td>{ra}</td><td>{rb}</td><td class='{'ok' if res == 'right' else 'bad' if res == 'wrong' else ''}'>{e(res)}</td></tr>")
    h.append("</table>")
    src_img = fig(n)
    if src_img:
        h.append(f"<img src='{src_img}'><p class='cap'>Figure {k}: {e(n)}. Discourse relations on top, each unit's constituency tree below.</p>")
    h.append("</section>")
    parts.append("".join(h))

# front matter
stage = L["stage"]
names = ["Rounds 1 to 5", "Round 6", "Round 6b", "Round 7"]
chg = [sum(stage[k][i] != stage[k][i + 1] for k in stage) for i in range(4)]
cnt = collections.Counter(f for k in L["loo"] for f in L["loo"][k]["off"])
rules_rows = "".join(f"<tr><td>{e(f)}</td><td>{GROUP(f)}</td><td class='s'>{e(DESC.get(f, ''))}</td><td>{cnt.get(f, 0)}</td></tr>"
                     for f in L["flags"] if f not in ("object_fill", "backfill"))
front = f"""
<section class='front'><h1>Step-by-step examples</h1>
<p>Caprice Culkin<br>Legislative Health Factuality, Solomon Center for Health Law and Policy<br>November 2, 2026</p>
<p>This document shows each step of the pipeline for 24 sentences, 8 from each legislature. The sentences are from the batch of sentences 201 to 300 per legislature, which was drawn after the rules were written. For each sentence I list the discourse units and relations, the constituency tree for each unit, the claims before any repair rules, what each round of rules changed, the rules the sentence depends on, the final claims, the two readings, and the figure.</p>
<h3>Pipeline</h3>
<ol><li>Discourse parse: isanlp RST splits the sentence into units and labels the relations between them (RST-DT for English, ANNODIS for French).</li>
<li>Constituency parse: each unit is parsed on its own (Stanza for English, benepar_fr2 for French). The whole-sentence tree is not used.</li>
<li>Claims: subject, verb and object for each clause in a unit's tree.</li>
<li>Links across units: a unit without a subject takes the subject of the unit its relation points to. "That", "who" and "qui" are resolved the same way, and the object of "said" is the unit that follows.</li>
<li>Repair rules: each rule fixes one pattern found in checking. Every rule can be turned off, and a rule is kept only if the 220 answer-key sentences and the 111 notebook checks still pass.</li></ol>
<h3>How the tables were made</h3>
<p>Each sentence was run through scripts/step3_claims/edu_pipeline.py five times: with no repair rules, then adding rounds 1 to 5, 6, 6b and 7. For the rule tables, each rule was turned off by itself. The final run matches outputs/edu/more_reparsed.json and claim_readings_fresh2.csv for all 24 sentences.</p>
<h3>Sentences changed by each round (all 900 new sentences)</h3>
<table class='c'><tr><th>Rules turned on</th><th>Sentences changed</th></tr>{''.join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in zip(names, chg))}</table>
<h3>Accuracy by round</h3>
<table class='c'><tr><th>Rules</th><th>Batch</th><th>Claims</th><th>Both readings right</th></tr>
<tr><td>Round 6</td><td>Sentences 21 to 100 per legislature</td><td>672</td><td>418 (62%)</td></tr>
<tr><td>Round 6b</td><td>Sentences 101 to 200</td><td>839</td><td>545 (65%)</td></tr>
<tr><td>Round 7 (current)</td><td>Sentences 201 to 300</td><td>959</td><td>649 (68%; 95% CI 65 to 71)</td></tr></table>
<p>The two readings are from AI readers, not people. A blind sample of 120 claims for a person to check is in docs/hand_check_sample.xlsx.</p>
<h3>Rules</h3>
<p>The last column is the number of the 900 sentences that change when the rule is turned off by itself. A 0 means another rule covers the same case.</p>
<table class='c'><tr><th>Rule</th><th>Round</th><th>What it does</th><th>Sentences</th></tr>{rules_rows}</table>
</section>"""

CSS = """body{font-family:'Times New Roman',Tinos,Times,serif;color:#000;font-size:12pt;line-height:1.0;margin:0}
section{page-break-before:always}section.front{page-break-before:auto}
h1{font-size:12pt;font-weight:bold;text-align:center;margin:0 0 12pt}h2{font-size:12pt;font-weight:bold;margin:0 0 12pt}
h3{font-size:12pt;font-weight:bold;margin:12pt 0 6pt}p{margin:0 0 12pt}ol{margin:0 0 12pt;padding-left:24pt}li{margin:0}
.sent{font-style:italic}.s,.meta{font-size:12pt}.nc{margin:0 0 6pt}.stage{font-weight:bold;margin:6pt 0 3pt}
table.c{border-collapse:collapse;width:100%;margin:0 0 12pt;font-size:12pt;line-height:1.0}table.c th{border:1px solid #000;text-align:left;padding:2pt 4pt;font-weight:bold}
table.c td{border:1px solid #000;padding:2pt 4pt;vertical-align:top}tr.gone td{text-decoration:line-through}tr.new td{font-weight:bold}
.tree{font-size:10pt;margin:0 0 6pt;word-break:break-all}td.ok,td.bad{font-weight:normal}
img{max-width:100%;max-height:7.5in;display:block;margin:6pt auto 0}.cap{text-align:center;margin:3pt 0 12pt}"""
open(OUT, "w", encoding="utf-8").write(f"<!doctype html><html><head><meta charset='utf-8'><title>Step-by-step examples</title><style>{CSS}</style></head><body>{front}{''.join(parts)}</body></html>")
print("wrote", OUT, len(parts))
