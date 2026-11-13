#!/usr/bin/env python3
"""
patch_quebec_oldformat3.py   (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)

The last fix to the reading of the 1985-1991 pages, from the trace of every place a bill's text was cut (Oct 5):
  1. On these pages there is no "Affaires du jour" heading, so after "Renseignements sur les travaux de
     l'Assemblee" or "Avis touchant les travaux des commissions" the parser thought it was still in that section and
     ignored the "Projet de loi N ..." headings that follow. Bills 87, 90, 98, 99, 89 and 64 on 1986-06-17 got no
     text at all, Bill 74 of 1986-11-13 swallowed Bills 113 and 83, and Bill 63 of 1988-12-12 swallowed Bill 37's
     whole report-stage debate. Now a "Projet de loi N" heading always starts that bill on these pages (except
     inside oral questions).
  2. A speaker heading garbled by the scan ("M.AndreVallerand", "La Vice-Presidentes Merci, M. le ministre...")
     ended the bill's debate. Speaker and Chair headings are now recognised with or without the space, and a
     heading that is really a line of speech ("Merci, M. le ...") does not end anything.
  3. Stray pieces of the scan ("IV.", "tion.", a garbled line followed by a sentence that carries on) and headings
     followed by "... toujours concernant ce projet de loi ..." no longer end the bill. Neither do a revocation,
     a motion to adjourn, the withdrawal of a motion, or a request for a ruling.
  4. The Chair's call "A l'article 48 de notre feuilleton ..." (not only "du feuilleton") starts the bill it names.
Pages of 1994 on, and pages that print "Affaires courantes" or "Affaires du jour", are read exactly as before.

Run from the project folder:  python3 scripts/step1_debate_text/patch_quebec_oldformat3.py
If the file does not contain the expected code, nothing is changed.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py"
s = P.read_text(encoding="utf-8")
if "PATCHED_OLDFORMAT3_2026_10_05" in s:
    print("quebec_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)
if "PATCHED_OLDFORMAT2_2026_10_05" not in s:
    sys.exit("quebec_rebuild.py does not have the Oct 5 patch (patch_quebec_oldformat2.py); nothing changed. "
             "Send this output to Claude.")

AFTER = '''def _old_continues(n):  # noqa: F811
    return _old_continues_v1(n) or bool(_OLD_CONTINUE2.match(n)) or bool(_OLD_BILL_MOTION.match(n))
'''
DEFS3 = r'''

# PATCHED_OLDFORMAT3_2026_10_05: bill headings after "Renseignements sur les travaux", garbled speaker headings,
# stray pieces of the scan, and the Chair's call "de notre feuilleton". See patch_quebec_oldformat3.py.
_OLD_SPEAKER = re.compile(r"^(?:m|mm|mme|mmes|mlle)(?:\.\s*|\s+)[a-z]|^(?:le|la|les)\s+(?:vice-)?president|^(?:une|des)\s+voix\b")
_OLD_SPEECH = re.compile(r"\bmerci\b|\b(?:m\.|mme)\s*(?:le|la)\s+(?:president|presidente|ministre|depute|deputee|leader)\b")
_OLD_CONTINUE3 = re.compile(r"^(?:revocation\b|motion\s+d['’]ajournement|retrait\s+de\s+la\s+motion|demande\s+de\s+directive"
                            r"|[ivxlc]+\.?$)")
_QUESTION_SECTIONS = ("questions et reponses", "periode de questions", "reponses orales")
_OLD_CALL = re.compile(r"^(?:(?:le|la)\s+(?:vice-)?presidente?[^:]{0,40}:\s*(?:a\s+)?|a\s+)l['’]article\s+\d+\s*,?\s*"
                       r"(?:(?:du|au|de\s+notre|de\s+son)\s+feuilleton)?[^.]{0,250}?projet\s+de\s+loi\s+" + N_NUM)
_old_continues_v2 = _old_continues


def _old_continues(n):  # noqa: F811
    if _old_continues_v2(n) or _OLD_SPEAKER.match(n) or _OLD_CONTINUE3.match(n) or _OLD_SPEECH.search(n):
        return True
    words = re.findall(r"[a-z]+", n)
    return len(words) <= 1 and sum(len(w) for w in words) <= 4     # a piece of a word left by the scan ("tion.")


_OLD_SAME_BILL = re.compile(r"(?:concernant|a\s+l['’]egard\s+de|au\s+sujet\s+de|sur)\s+ce\s+projet\s+de\s+loi")


def _old_goes_on(t):
    """the paragraph after a heading carries on the same matter: it continues a sentence ("venants dans le
    domaine ..."), or its speaker opens with "toujours concernant ce projet de loi" / "a l'egard de ce projet de loi" """
    t = (t or "").strip()
    if not t:
        return False
    head = _norm(t.split(":", 1)[1] if ":" in t[:60] else t)[:80]
    return t[:1].islower() or bool(_OLD_SAME_BILL.search(head))
'''

EDITS = [
    (AFTER, AFTER + DEFS3),
    ('    for p in root.find_all("p"):\n        if p.find("tabledesmatieres")',
     '    ps = root.find_all("p")\n\n'
     '    def _next_para(i):\n'
     '        for q in ps[i + 1:i + 8]:\n'
     '            t = re.sub(r"\\s+", " ", q.get_text(" ", strip=True)).strip()\n'
     '            if len(t) >= 3 and not _is_heading(q, toc_labels):\n'
     '                return t\n'
     '        return ""\n'
     '    for pi, p in enumerate(ps):\n        if p.find("tabledesmatieres")'),
    ('            if m and len(text) <= 250 and not section.startswith(_NO_DEBATE_SECTIONS):\n'
     '                current, method = int(m.group(1)), ("heading" if structural else "heading_line")\n',
     '            if m and len(text) <= 250 and (not section.startswith(_NO_DEBATE_SECTIONS) or (\n'
     '                    strict and nj.startswith("projet de loi") and not section.startswith(_QUESTION_SECTIONS))):\n'
     '                if strict and section.startswith(_NO_DEBATE_SECTIONS):\n'
     '                    section = "affaires du jour (implied: older page, a bill is called)"\n'
     '                current, method = int(m.group(1)), ("heading" if structural else "heading_line")\n'),
    ('            elif (current is None and pending is not None and n.startswith(_DEBATE_STAGE_HEADS)\n',
     '            elif (current is None and pending is not None and (hrun if strict else n).startswith(_DEBATE_STAGE_HEADS)\n'),
    ('            elif current is not None and strict and not _old_keeps(hrun, study_bill == current):\n',
     '            elif (current is not None and strict and not _old_keeps(hrun, study_bill == current)\n'
     '                  and not _old_goes_on(_next_para(pi))):\n'),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"quebec_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. "
             "Send this output to Claude.")
for a, b in EDITS:
    s = s.replace(a, b)
compile(s, str(P), "exec")
backup = P.with_name("quebec_rebuild_before_oldformat3_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")

sys.path.insert(0, str(P.parent))
try:
    import importlib  # noqa: E402
    Q = importlib.import_module("quebec_rebuild")
    SP = "Merci, M. le President. " * 30
    H = "<p align='center'>{}</p>"
    P_ = "<p>{}</p>"
    page = ("<html><body><contenu>"
            # 1. bills called after "Renseignements sur les travaux de l'Assemblee"
            + H.format("Renseignements sur les travaux de l'Assemblée") + P_.format("M. Gratton: Nous commencerons par le projet de loi 74. " + SP)
            + H.format("Projet de loi 74") + H.format("Prise en considération") + H.format("du rapport de la commission")
            + H.format("qui en a fait l'étude détaillée")
            + P_.format("Le Vice-Président: À l'article 43 du feuilleton, nous allons procéder à la prise en considération du rapport sur le projet de loi 74. " + SP)
            + P_.format("Une voix: Adopté.")
            + H.format("Projet de loi 113 Adoption")
            + P_.format("Le Vice-Président: Nous en sommes à l'étape de l'adoption du projet de loi 113. " + SP) + H.format("M. John Ciaccia") + P_.format(SP)
            + H.format("Projet de loi 83") + H.format("Commission plénière") + P_.format(SP) + H.format("Étude détaillée")
            + H.format("Fonds au bénéfice des personnes incarcérées") + P_.format("M. Marx: " + SP)
            + H.format("Projet de loi 99") + H.format("Prise en considération du rapport de la commission qui en a fait l'étude détaillée")
            + P_.format("M. Lincoln: " + SP)
            + H.format("Projet de loi 37") + H.format("Prise en considération du rapport de la commission qui en a fait l'étude détaillée")
            + P_.format("La Vice-Présidente: À l'article 48 de notre feuilleton, le ministre propose que l'Assemblée prenne en considération le rapport sur le projet de loi 37. " + SP)
            + H.format("M. André Bourbeau") + P_.format(SP)
            # 2. garbled speaker headings and stray pieces of the scan
            + H.format("Projet de loi 42 Adoption du principe") + P_.format("La Vice-Présidente: À l'article 5 de notre feuilleton, le ministre propose l'adoption du principe du projet de loi 42. " + SP)
            + H.format("M.AndréVallerand") + P_.format("M. Vallerand: Merci. " + SP)
            + H.format("La Vice-Présidentes Merci, M. le ministre des Finances. M. le député de Lévis.") + H.format("M. Jean Garon") + P_.format("M. Garon: " + SP)
            + H.format("IV.") + P_.format("(11 h 10)") + P_.format(SP)
            + H.format("nrinninauy utilisateurs ries nrinrinanv inter.") + P_.format("venants dans le domaine des plans cadastraux. " + SP)
            + H.format("Étude en commission des délais d'application") + P_.format("M. Pagé: M. le Président, toujours concernant ce projet de loi, je dois indiquer. " + SP)
            + H.format("Présence de l'ambassadeur d'Italie") + P_.format("J'ai le plaisir de souligner la présence de l'ambassadeur. " + SP)
            # 3. a bill named in oral questions is not a debate
            + H.format("QUESTIONS ET RÉPONSES ORALES") + H.format("Projet de loi 75") + P_.format("M. X: Est-ce que le ministre va retirer le projet de loi 75? " + SP)
            + "</contenu></body></html>")
    got = {k: len(v) for k, v in Q.parse_page(page, old_format=True)[0].items()}
    want = {74: 2, 113: 2, 83: 2, 99: 1, 37: 2, 42: 7}
    assert got == want, ("old-format page", got, "expected", want)
    with_aff = page.replace("<contenu>", "<contenu>" + H.format("Affaires du jour"))
    assert Q.parse_page(with_aff, old_format=True)[0] == Q.parse_page(with_aff)[0], "a page with Affaires du jour reads as before"
except Exception as e:  # noqa: BLE001
    shutil.copy2(backup, P)
    sys.exit(f"The checks on the edited quebec_rebuild.py failed ({e!r}); quebec_rebuild.py was put back as it was. "
             "Send this output to Claude.")
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}). Checks passed: bills called after 'Renseignements sur "
      "les travaux' get their text, garbled speaker headings and stray pieces of the scan no longer cut a debate, and "
      "a page with Affaires du jour reads as before.")
